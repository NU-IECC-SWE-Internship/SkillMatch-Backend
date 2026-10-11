import json
from datetime import date, timedelta
from itertools import count
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    PendingSkillQuiz,
    Profile,
    Skill,
    SkillQuizAttempt,
    SkillQuizQuestion,
    UserSkill,
)
from .quiz_bank import (
    bank_size,
    current_cycle,
    LEVELS,
    daily_batch,
    draw_quiz,
    previous_cycle,
    prune_old_cycles,
    split_by_difficulty,
    top_up_skill,
)
from .quiz_llm import QuizGenerationError, generate_quiz_questions
from .quiz_policy import quiz_availability

_ids = count(1)


def fake_generate(skill_name, count=10, avoid=None, mix=None):
    mix = mix or {"medium": count}
    levels = [level for level in LEVELS for _ in range(mix.get(level, 0))]
    return [
        {
            "order": i,
            "question_text": f"{skill_name} question {next(_ids)}",
            "option_a": "a",
            "option_b": "b",
            "option_c": "c",
            "option_d": "d",
            "correct_option": "A",
            "difficulty": level,
        }
        for i, level in enumerate(levels, start=1)
    ]


def make_questions(skill, cycle, n, difficulty="medium"):
    SkillQuizQuestion.objects.bulk_create(
        SkillQuizQuestion(
            skill=skill,
            cycle=cycle,
            difficulty=difficulty,
            question_text=f"{cycle} {difficulty} q{i}",
            option_a="a",
            option_b="b",
            option_c="c",
            option_d="d",
            correct_option="A",
        )
        for i in range(n)
    )


@patch("skillmatch.quiz_bank.generate_quiz_questions", side_effect=fake_generate)
class QuestionBankTests(TestCase):
    def setUp(self):
        self.skill = Skill.objects.create(name="Python")

    def test_top_up_adds_one_batch_per_day(self, mock_gen):
        self.assertEqual(top_up_skill(self.skill), daily_batch())
        self.assertEqual(top_up_skill(self.skill), 0)
        self.assertEqual(mock_gen.call_count, 1)

    def test_top_up_stops_at_bank_size(self, mock_gen):
        make_questions(self.skill, current_cycle(), bank_size())
        self.assertEqual(top_up_skill(self.skill, force=True), 0)
        mock_gen.assert_not_called()

    def test_duplicates_are_skipped(self, mock_gen):
        make_questions(self.skill, current_cycle(), 1)
        mock_gen.side_effect = lambda *a, **k: [
            {
                "order": 1,
                "question_text": f"  {current_cycle()} MEDIUM Q0 ",
                "option_a": "a",
                "option_b": "b",
                "option_c": "c",
                "option_d": "d",
                "correct_option": "A",
            }
        ]
        self.assertEqual(top_up_skill(self.skill, force=True), 0)

    def test_draw_generates_when_bank_is_empty(self, mock_gen):
        quiz = draw_quiz(self.skill, 10)
        self.assertEqual(len(quiz), 10)
        self.assertEqual([q["order"] for q in quiz], list(range(1, 11)))
        self.assertTrue(all("correct_option" in q for q in quiz))

    def test_draw_mixes_previous_cycle_until_current_is_full(self, mock_gen):
        make_questions(self.skill, previous_cycle(), 50)
        make_questions(self.skill, current_cycle(), 10)
        quiz = draw_quiz(self.skill, 10)
        self.assertEqual(len({q["bank_id"] for q in quiz}), 10)
        mock_gen.assert_not_called()

    def test_prune_keeps_only_current_and_previous(self, mock_gen):
        make_questions(self.skill, "2000-01", 5)
        make_questions(self.skill, previous_cycle(), 5)
        make_questions(self.skill, current_cycle(), 5)
        prune_old_cycles(self.skill)
        cycles = set(SkillQuizQuestion.objects.values_list("cycle", flat=True))
        self.assertEqual(cycles, {previous_cycle(), current_cycle()})

    def test_previous_cycle_wraps_year(self, mock_gen):
        self.assertEqual(previous_cycle(date(2026, 1, 15)), "2025-12")
        self.assertEqual(previous_cycle(date(2026, 10, 7)), "2026-09")

    def test_split_by_difficulty(self, mock_gen):
        weights = {"easy": 4, "medium": 3, "hard": 3}
        self.assertEqual(split_by_difficulty(10, weights), {"easy": 4, "medium": 3, "hard": 3})
        self.assertEqual(split_by_difficulty(7, weights), {"easy": 3, "medium": 2, "hard": 2})
        self.assertEqual(sum(split_by_difficulty(13, weights).values()), 13)

    def test_quiz_follows_mix_and_goes_easy_to_hard(self, mock_gen):
        for level in LEVELS:
            make_questions(self.skill, current_cycle(), 10, difficulty=level)
        quiz = draw_quiz(self.skill, 10)
        levels = [q["difficulty"] for q in quiz]
        self.assertEqual(levels, ["easy"] * 4 + ["medium"] * 3 + ["hard"] * 3)
        mock_gen.assert_not_called()

    def test_missing_level_is_filled_from_others_in_order(self, mock_gen):
        make_questions(self.skill, current_cycle(), 10, difficulty="easy")
        make_questions(self.skill, current_cycle(), 10, difficulty="medium")
        quiz = draw_quiz(self.skill, 10)
        levels = [q["difficulty"] for q in quiz]
        self.assertEqual(len(quiz), 10)
        self.assertNotIn("hard", levels)
        self.assertEqual(levels, sorted(levels, key=LEVELS.index))

    def test_generation_targets_missing_levels(self, mock_gen):
        make_questions(self.skill, current_cycle(), 40, difficulty="easy")
        top_up_skill(self.skill, force=True)
        mix = mock_gen.call_args.kwargs["mix"]
        self.assertEqual(mix["easy"], 0)
        self.assertEqual(sum(mix.values()), daily_batch())


QUESTION_INPUT = {
    "question_text": "What does len([1, 2]) return?",
    "option_a": "2",
    "option_b": "1",
    "option_c": "0",
    "option_d": "Error",
    "correct_option": "a",
}


class AdminQuestionBankApiTests(TestCase):
    def setUp(self):
        self.skill = Skill.objects.create(name="Python")
        self.client = APIClient()
        self.admin = User.objects.create_user("admin", password="x", is_staff=True)
        self.client.force_authenticate(self.admin)
        self.url = f"/api/admin/skills/{self.skill.id}/questions/"

    def test_regular_users_are_forbidden(self):
        user = User.objects.create_user("student", password="x")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_create_list_update_delete(self):
        created = self.client.post(self.url, QUESTION_INPUT, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["correct_option"], "A")
        self.assertEqual(created.data["cycle"], current_cycle())

        bank = self.client.get(self.url).data
        self.assertEqual(bank["current_count"], 1)
        self.assertEqual(len(bank["questions"]), 1)

        detail = f"/api/admin/questions/{created.data['id']}/"
        updated = self.client.patch(detail, {"correct_option": "B"}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["correct_option"], "B")

        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.assertFalse(SkillQuizQuestion.objects.exists())

    def test_create_rejected_when_bank_full(self):
        make_questions(self.skill, current_cycle(), bank_size())
        response = self.client.post(self.url, QUESTION_INPUT, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("skillmatch.quiz_bank.generate_quiz_questions", side_effect=fake_generate)
    def test_generate_adds_a_batch(self, mock_gen):
        response = self.client.post(f"{self.url}generate/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["added"], daily_batch())
        self.assertEqual(response.data["current_count"], daily_batch())


def groq_reply(content, status_code=200):
    response = MagicMock(status_code=status_code, text=str(content))
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


def llm_question(i, difficulty="easy"):
    return {
        "question_text": f"Q{i}",
        "option_a": "a",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_option": "A",
        "difficulty": difficulty,
    }


@override_settings(GROQ_API_KEY="test-key")
@patch("skillmatch.quiz_llm.requests.post")
class QuizLlmTests(TestCase):
    def test_extracts_json_wrapped_in_text(self, mock_post):
        payload = json.dumps({"questions": [llm_question(i) for i in range(3)]})
        mock_post.return_value = groq_reply(f"Sure! Here you go:\n```json\n{payload}\n```")
        questions = generate_quiz_questions("Django", count=3)
        self.assertEqual([q["order"] for q in questions], [1, 2, 3])

    def test_retries_after_empty_reply(self, mock_post):
        good = json.dumps({"questions": [llm_question(i) for i in range(2)]})
        mock_post.side_effect = [groq_reply(""), groq_reply(None), groq_reply(good)]
        questions = generate_quiz_questions("Django", count=2)
        self.assertEqual(len(questions), 2)
        self.assertEqual(mock_post.call_count, 3)

    def test_skips_invalid_items_and_tops_up_on_retry(self, mock_post):
        broken = llm_question(0) | {"correct_option": "E"}
        first = json.dumps({"questions": [broken, llm_question(1)]})
        second = json.dumps({"questions": [llm_question(1), llm_question(2)]})
        mock_post.side_effect = [groq_reply(first), groq_reply(second)]
        questions = generate_quiz_questions("Django", count=2)
        self.assertEqual([q["question_text"] for q in questions], ["Q1", "Q2"])

    def test_gives_up_after_max_attempts(self, mock_post):
        mock_post.return_value = groq_reply("not json at all")
        with self.assertRaises(QuizGenerationError):
            generate_quiz_questions("Django", count=2)
        self.assertEqual(mock_post.call_count, 3)

    def test_rate_limit_is_not_retried(self, mock_post):
        mock_post.return_value = groq_reply("rate limited", status_code=429)
        with self.assertRaises(QuizGenerationError):
            generate_quiz_questions("Django", count=2)
        self.assertEqual(mock_post.call_count, 1)


class AbandonedQuizTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("omar", password="x")
        self.skill = Skill.objects.create(name="Django")
        UserSkill.objects.create(user=self.user, skill=self.skill, skill_type="teach")

    def start_quiz(self, minutes_ago):
        pending = PendingSkillQuiz.objects.create(user=self.user, skill=self.skill, questions=[])
        PendingSkillQuiz.objects.filter(pk=pending.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago)
        )

    def test_timed_out_quiz_starts_cooldown_without_reopening(self):
        self.start_quiz(minutes_ago=30)
        can_take, attempt, available_at = quiz_availability(self.user, self.skill)
        self.assertFalse(can_take)
        self.assertTrue(attempt.abandoned)
        self.assertIsNotNone(available_at)
        self.assertFalse(PendingSkillQuiz.objects.exists())

    def test_quiz_in_progress_is_left_alone(self):
        self.start_quiz(minutes_ago=1)
        can_take, attempt, _ = quiz_availability(self.user, self.skill)
        self.assertTrue(can_take)
        self.assertIsNone(attempt)
        self.assertTrue(PendingSkillQuiz.objects.exists())

    def test_profile_skill_list_shows_cooldown(self):
        self.start_quiz(minutes_ago=30)
        client = APIClient()
        client.force_authenticate(self.user)
        skill = client.get("/api/my-skills/").data[0]
        self.assertFalse(skill["can_take_quiz"])
        self.assertTrue(skill["has_quiz_attempt"])
        self.assertIsNotNone(skill["quiz_available_at"])


class QuizReviewTests(TestCase):
    def setUp(self):
        from system_config.services import clear_cache

        clear_cache()
        self.client = APIClient()
        self.user = User.objects.create_user("learner", password="x")
        self.skill = Skill.objects.create(name="Python")
        UserSkill.objects.create(user=self.user, skill=self.skill, skill_type="teach")
        PendingSkillQuiz.objects.create(
            user=self.user,
            skill=self.skill,
            questions=[
                {
                    "order": i,
                    "question_text": f"Q{i}",
                    "option_a": "a",
                    "option_b": "b",
                    "option_c": "c",
                    "option_d": "d",
                    "correct_option": "A",
                    "difficulty": "easy",
                }
                for i in (1, 2, 3)
            ],
        )
        self.client.force_authenticate(self.user)
        self.url = f"/api/skills/{self.skill.id}/quiz/submit/"
        self.answers = [
            {"question_id": 1, "selected": "A"},
            {"question_id": 2, "selected": "C"},
            {"question_id": 3, "selected": None},
        ]

    def test_submit_returns_and_stores_review(self):
        data = self.client.post(self.url, {"answers": self.answers}, format="json").data
        self.assertEqual(data["score"], 1)
        review = data["review"]
        self.assertEqual([item["order"] for item in review], [1, 2, 3])
        self.assertEqual([item["is_correct"] for item in review], [True, False, False])
        self.assertEqual(review[1]["selected"], "C")
        self.assertEqual(review[1]["correct_option"], "A")
        self.assertIsNone(review[2]["selected"])

        attempt = SkillQuizAttempt.objects.get(user=self.user)
        self.assertEqual(len(attempt.review), 3)

        # The quiz page shows the same review during the cooldown.
        page = self.client.get(f"/api/skills/{self.skill.id}/quiz/").data
        self.assertEqual(page["attempt"]["review"], review)

    def test_review_endpoint_and_profile_flag(self):
        review_url = f"/api/skills/{self.skill.id}/quiz/review/"
        self.assertEqual(self.client.get(review_url).status_code, 404)
        skills = self.client.get("/api/my-skills/").data
        self.assertFalse(skills[0]["has_quiz_review"])

        submitted = self.client.post(self.url, {"answers": self.answers}, format="json").data

        data = self.client.get(review_url).data
        self.assertEqual(data["score"], 1)
        self.assertEqual(data["total"], 3)
        self.assertFalse(data["can_take"])
        self.assertEqual(data["review"], submitted["review"])
        skills = self.client.get("/api/my-skills/").data
        self.assertTrue(skills[0]["has_quiz_review"])

        self.assertTrue(data["has_details"])

        # A later abandoned attempt has nothing to review, so the submitted one is still shown.
        SkillQuizAttempt.objects.create(
            user=self.user, skill=self.skill, score=0, passed=False, abandoned=True
        )
        self.assertEqual(self.client.get(review_url).data["score"], 1)

    def test_old_attempt_without_saved_answers_is_reviewable(self):
        SkillQuizAttempt.objects.create(user=self.user, skill=self.skill, score=6, passed=False)
        self.assertTrue(self.client.get("/api/my-skills/").data[0]["has_quiz_review"])

        data = self.client.get(f"/api/skills/{self.skill.id}/quiz/review/").data
        self.assertEqual(data["score"], 6)
        self.assertEqual(data["total"], 10)
        self.assertFalse(data["has_details"])
        self.assertEqual(data["review"], [])

    def test_correct_answers_hidden_when_disabled(self):
        from system_config.models import SystemConfig

        SystemConfig.objects.filter(key="quiz.review_show_answers").update(value="false")
        from system_config.services import clear_cache

        clear_cache()
        review = self.client.post(self.url, {"answers": self.answers}, format="json").data["review"]
        self.assertEqual(review[0]["correct_option"], "A")
        self.assertIsNone(review[1]["correct_option"])
        self.assertIsNone(review[2]["correct_option"])


class AdminUsersApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("admin", password="x", is_staff=True)
        self.omar = User.objects.create_user(
            "omarali", email="omar@example.com", password="x", first_name="Omar", last_name="Ali"
        )
        self.peter = User.objects.create_user("peteryakoub", password="x")
        skill = Skill.objects.create(name="Python")
        UserSkill.objects.create(user=self.omar, skill=skill, skill_type="teach", is_verified=True)
        self.client.force_authenticate(self.admin)

    def test_members_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(self.omar)
        self.assertEqual(self.client.get("/api/admin/users/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/overview/").status_code, 403)

    def test_list_search_and_filters(self):
        data = self.client.get("/api/admin/users/").data
        self.assertEqual(data["count"], 3)

        data = self.client.get("/api/admin/users/", {"search": "omar"}).data
        self.assertEqual([u["username"] for u in data["results"]], ["omarali"])
        self.assertEqual(data["results"][0]["teach_count"], 1)
        self.assertEqual(data["results"][0]["verified_count"], 1)

        data = self.client.get("/api/admin/users/", {"role": "staff"}).data
        self.assertEqual([u["username"] for u in data["results"]], ["admin"])

    def test_detail_includes_skills(self):
        data = self.client.get(f"/api/admin/users/{self.omar.id}/").data
        self.assertEqual(data["full_name"], "Omar Ali")
        self.assertEqual(data["skills"][0]["name"], "Python")

    def test_deactivate_and_promote(self):
        url = f"/api/admin/users/{self.peter.id}/"
        response = self.client.patch(url, {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

        response = self.client.patch(url, {"is_staff": True}, format="json")
        self.assertTrue(response.data["is_staff"])

        self.assertEqual(
            self.client.get("/api/admin/users/", {"status": "inactive"}).data["count"], 1
        )

    def test_cannot_change_own_account(self):
        response = self.client.patch(
            f"/api/admin/users/{self.admin.id}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_overview_counts(self):
        data = self.client.get("/api/admin/overview/").data
        self.assertEqual(data["users"]["total"], 3)
        self.assertEqual(data["users"]["staff"], 1)
        self.assertEqual(data["skills"]["verified_teachers"], 1)

    def test_overview_signups_and_top_skills(self):
        data = self.client.get("/api/admin/overview/").data
        self.assertEqual(len(data["signups"]), 14)
        self.assertEqual(sum(day["count"] for day in data["signups"]), 3)
        self.assertEqual(data["users"]["onboarding"], 2)
        self.assertEqual(
            data["top_skills"],
            [{"id": data["top_skills"][0]["id"], "name": "Python", "teachers": 1, "learners": 0, "verified": 1}],
        )

    def test_status_counts_and_onboarding_filter(self):
        Profile.objects.create(user=self.omar, onboarding_completed=True)
        data = self.client.get("/api/admin/users/").data
        self.assertEqual(data["counts"]["all"], 3)
        self.assertEqual(data["counts"]["role"], {"staff": 1, "member": 2})
        self.assertEqual(data["counts"]["status"], {"active": 2, "onboarding": 1, "inactive": 0})

        data = self.client.get("/api/admin/users/", {"status": "onboarding"}).data
        self.assertEqual([u["username"] for u in data["results"]], ["peteryakoub"])

        data = self.client.get("/api/admin/users/", {"status": "active"}).data
        self.assertEqual({u["username"] for u in data["results"]}, {"admin", "omarali"})

    def test_sort_by_name(self):
        data = self.client.get("/api/admin/users/", {"sort": "name"}).data
        self.assertEqual(
            [u["username"] for u in data["results"]], ["admin", "omarali", "peteryakoub"]
        )
