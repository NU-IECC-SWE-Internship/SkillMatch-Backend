"""
Generate (or replace) skill quiz questions via Groq.

  python manage.py generate_skill_quizzes
  python manage.py generate_skill_quizzes --skill Python
  python manage.py generate_skill_quizzes --replace
  python manage.py generate_skill_quizzes --only-missing

Requires GROQ_API_KEY in .env
"""

from django.core.management.base import BaseCommand, CommandError

from skillmatch.models import Skill, SkillQuizQuestion
from skillmatch.quiz_llm import QuizGenerationError, generate_quiz_questions
from skillmatch.management.commands.seed_skill_quizzes import SKILL_NAMES


class Command(BaseCommand):
    help = "Generate real per-skill quiz questions using Groq."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skill",
            type=str,
            default="",
            help="Only generate for this skill name (creates skill if missing).",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace existing questions for the selected skills.",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Skip skills that already have 10 questions.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of questions per skill (default 10).",
        )

    def handle(self, *args, **options):
        skill_filter = (options["skill"] or "").strip()
        replace = options["replace"]
        only_missing = options["only_missing"]
        count = options["count"]

        if skill_filter:
            names = [skill_filter]
        else:
            names = list(SKILL_NAMES)
            # Also include any extra skills already in the DB
            for name in Skill.objects.values_list("name", flat=True):
                if name not in names:
                    names.append(name)

        generated = 0
        skipped = 0
        failed = 0

        for name in names:
            skill, _ = Skill.objects.get_or_create(name=name)
            existing = SkillQuizQuestion.objects.filter(skill=skill).count()

            if only_missing and existing >= count and not replace:
                self.stdout.write(f"Skip {name}: already has {existing} questions")
                skipped += 1
                continue

            if existing and not replace and not only_missing:
                self.stdout.write(
                    f"Skip {name}: has questions (use --replace or --only-missing)"
                )
                skipped += 1
                continue

            if existing and replace:
                SkillQuizQuestion.objects.filter(skill=skill).delete()

            if existing >= count and only_missing and not replace:
                skipped += 1
                continue

            self.stdout.write(f"Generating quiz for {name}...")
            try:
                items = generate_quiz_questions(name, count=count)
            except QuizGenerationError as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"  Failed {name}: {exc}"))
                continue

            for item in items:
                SkillQuizQuestion.objects.update_or_create(
                    skill=skill,
                    order=item["order"],
                    defaults={
                        "question_text": item["question_text"],
                        "option_a": item["option_a"],
                        "option_b": item["option_b"],
                        "option_c": item["option_c"],
                        "option_d": item["option_d"],
                        "correct_option": item["correct_option"],
                    },
                )

            generated += 1
            self.stdout.write(self.style.SUCCESS(f"  Saved {count} questions for {name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. generated={generated} skipped={skipped} failed={failed}"
            )
        )

        if failed and not generated:
            raise CommandError("No quizzes generated. Check GROQ_API_KEY and try again.")
