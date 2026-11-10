from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from skillmatch.models import Skill, AvailabilitySlot, Notification
from matching.models import MatchRequest

User = get_user_model()


class ReturnSessionNotificationsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_sender = User.objects.create_user(username="req_sender", password="password123")
        self.user_receiver = User.objects.create_user(username="req_receiver", password="password123")

        self.skill_a = Skill.objects.get_or_create(name="Python", defaults={"is_approved": True})[0]
        self.skill_b = Skill.objects.get_or_create(name="Design", defaults={"is_approved": True})[0]

        self.slot_receiver = AvailabilitySlot.objects.create(
            user=self.user_receiver,
            day="Wednesday",
            start_time="10:00:00",
            end_time="11:00:00",
        )
        self.slot_sender = AvailabilitySlot.objects.create(
            user=self.user_sender,
            day="Thursday",
            start_time="15:00:00",
            end_time="16:00:00",
        )

        self.match_request = MatchRequest.objects.create(
            sender=self.user_sender,
            receiver=self.user_receiver,
            skill=self.skill_a,
            selected_slot=self.slot_receiver,
            status="SCHEDULING",
            receiver_skill=self.skill_b,
        )

    def test_schedule_return_notifies_sender(self):
        self.client.force_authenticate(user=self.user_receiver)
        response = self.client.post(
            f"/api/requests/{self.match_request.id}/respond/",
            data={
                "action": "schedule_return",
                "receiver_selected_slot": self.slot_sender.id,
                "receiver_requested_start_time": "15:00:00",
                "receiver_requested_end_time": "16:00:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        notif = Notification.objects.filter(
            recipient=self.user_sender,
            notification_type="return_session_proposed",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("req_receiver", notif.title)
        self.assertIn("Design", notif.message)

    def test_decline_return_notifies_receiver(self):
        self.match_request.status = "CONFIRMING"
        self.match_request.receiver_selected_slot = self.slot_sender
        self.match_request.save()

        self.client.force_authenticate(user=self.user_sender)
        response = self.client.post(
            f"/api/requests/{self.match_request.id}/respond/",
            data={"action": "decline_return"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        notif = Notification.objects.filter(
            recipient=self.user_receiver,
            notification_type="return_session_declined",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("req_sender", notif.message)


class GetTeachersTest(TestCase):
    """Browse Skills: teachers list every skill they teach, and any skill can be filtered."""

    def setUp(self):
        from skillmatch.models import UserSkill

        self.client = APIClient()
        self.me = User.objects.create_user(username="learner", password="password123")
        self.ana = User.objects.create_user(username="ana", password="password123")
        self.bob = User.objects.create_user(username="bob", password="password123")

        self.guitar = Skill.objects.get_or_create(name="Guitar", defaults={"is_approved": True})[0]
        self.piano = Skill.objects.get_or_create(name="Piano", defaults={"is_approved": True})[0]
        self.chess = Skill.objects.get_or_create(name="Chess", defaults={"is_approved": True})[0]

        UserSkill.objects.create(user=self.me, skill=self.guitar, skill_type="learn")
        UserSkill.objects.create(user=self.me, skill=self.chess, skill_type="teach")
        # ana teaches what I want plus another skill; bob teaches only something I don't want.
        UserSkill.objects.create(user=self.ana, skill=self.guitar, skill_type="teach")
        UserSkill.objects.create(user=self.ana, skill=self.piano, skill_type="teach")
        UserSkill.objects.create(user=self.bob, skill=self.piano, skill_type="teach")

        self.client.force_authenticate(user=self.me)

    def get(self, query=""):
        response = self.client.get(f"/api/teachers/{query}")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_default_lists_teachers_of_wanted_skills_with_all_their_skills(self):
        data = self.get()
        self.assertEqual([t["username"] for t in data["teachers"]], ["ana"])
        skills = data["teachers"][0]["skills"]
        self.assertEqual([s["name"] for s in skills], ["Guitar", "Piano"])
        self.assertEqual([s["wanted"] for s in skills], [True, False])

    def test_filter_by_skill_you_do_not_want(self):
        data = self.get(f"?skill={self.piano.id}")
        self.assertEqual([t["username"] for t in data["teachers"]], ["ana", "bob"])

    def test_all_lists_every_teacher_except_me(self):
        names = [t["username"] for t in self.get("?skill=all")["teachers"]]
        self.assertEqual(names, ["ana", "bob"])

    def test_all_skills_lists_every_skill_with_teacher_counts(self):
        all_skills = {s["name"]: s for s in self.get()["all_skills"]}
        # Every approved skill is listed, even ones nobody else teaches.
        self.assertEqual(set(all_skills), set(Skill.objects.filter(is_approved=True).values_list("name", flat=True)))
        self.assertEqual(all_skills["Piano"]["teacher_count"], 2)
        # Only I teach Chess, and my own teaching isn't counted.
        self.assertEqual(all_skills["Chess"]["teacher_count"], 0)
        self.assertTrue(all_skills["Guitar"]["wanted"])

    def test_invalid_skill_param(self):
        self.assertEqual(self.client.get("/api/teachers/?skill=abc").status_code, 400)


class RequestSkillsAndDuplicatesTest(TestCase):
    """Return-skill choices list everything the sender teaches; no duplicate open requests."""

    def setUp(self):
        from skillmatch.models import UserSkill

        self.client = APIClient()
        self.sender = User.objects.create_user(username="sender_rs", password="password123")
        self.receiver = User.objects.create_user(username="receiver_rs", password="password123")

        self.cooking = Skill.objects.get_or_create(name="Cooking", defaults={"is_approved": True})[0]
        self.german = Skill.objects.get_or_create(name="German", defaults={"is_approved": True})[0]
        self.chess = Skill.objects.get_or_create(name="Chess", defaults={"is_approved": True})[0]

        UserSkill.objects.create(user=self.receiver, skill=self.cooking, skill_type="teach")
        UserSkill.objects.create(user=self.sender, skill=self.german, skill_type="teach")
        UserSkill.objects.create(user=self.sender, skill=self.chess, skill_type="teach")
        UserSkill.objects.create(user=self.receiver, skill=self.chess, skill_type="learn")

        self.slot = AvailabilitySlot.objects.create(
            user=self.receiver, day="wednesday", start_time="12:00:00", end_time="14:00:00",
        )

    def send(self, start="12:15", end="12:30", sender=None, receiver=None, slot=None):
        self.client.force_authenticate(user=sender or self.sender)
        return self.client.post(
            "/api/requests/",
            {
                "receiver": (receiver or self.receiver).id,
                "skill": self.cooking.id,
                "selected_slot": (slot or self.slot).id,
                "requested_start_time": start,
                "requested_end_time": end,
            },
            format="json",
        )

    def test_return_choices_list_all_sender_skills_wanted_first(self):
        self.assertEqual(self.send().status_code, 201)
        self.client.force_authenticate(user=self.receiver)
        incoming = self.client.get("/api/requests/incoming/").data[0]
        choices = [(s["name"], s["wanted"]) for s in incoming["sender_teach_skills"]]
        self.assertEqual(choices, [("Chess", True), ("German", False)])

    def test_same_time_cannot_be_requested_again_by_anyone(self):
        from skillmatch.models import UserSkill

        self.assertEqual(self.send().status_code, 201)
        other = User.objects.create_user(username="other_rs", password="password123")
        UserSkill.objects.create(user=other, skill=self.chess, skill_type="teach")
        # Overlaps 12:15-12:30 on the same person's Wednesday slot.
        response = self.send(start="12:20", end="12:45", sender=other)
        self.assertEqual(response.status_code, 400)
        self.assertIn("already been requested", str(response.data))

    def test_same_person_and_skill_at_a_different_time_is_allowed(self):
        self.assertEqual(self.send().status_code, 201)
        self.assertEqual(self.send(start="13:00", end="13:15").status_code, 201)

    def test_you_cannot_book_two_overlapping_times(self):
        from skillmatch.models import UserSkill

        self.assertEqual(self.send().status_code, 201)
        second_teacher = User.objects.create_user(username="teacher2_rs", password="password123")
        UserSkill.objects.create(user=second_teacher, skill=self.cooking, skill_type="teach")
        slot2 = AvailabilitySlot.objects.create(
            user=second_teacher, day="wednesday", start_time="12:00:00", end_time="14:00:00",
        )
        response = self.send(start="12:15", end="12:30", receiver=second_teacher, slot=slot2)
        self.assertEqual(response.status_code, 400)
        self.assertIn("already have a request at this time", str(response.data))

    def test_taken_times_are_listed_for_the_request_page(self):
        self.assertEqual(self.send().status_code, 201)
        response = self.client.get(f"/api/users/{self.receiver.id}/session-settings/")
        self.assertIn(
            {"day": "wednesday", "start_time": "12:15", "end_time": "12:30"},
            response.data["requested_times"],
        )

    def test_accept_with_return_skill_not_on_learning_list(self):
        from unittest import mock

        request_id = self.send().data["id"]
        self.client.force_authenticate(user=self.receiver)
        # Accepting creates a video room; don't call the real Daily API in tests.
        room = {"name": "test-room", "url": "https://example.daily.co/test-room"}
        service = "meetings.video_service.DailyVideoService"
        with mock.patch(f"{service}.create_scheduled_room", return_value=room):
            with mock.patch(f"{service}.create_scheduled_token", return_value="token"):
                response = self.client.post(
                    f"/api/requests/{request_id}/respond/",
                    {"action": "accept", "receiver_skill": self.german.id, "schedule_mode": "later"},
                    format="json",
                )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(MatchRequest.objects.get(pk=request_id).receiver_skill, self.german)
