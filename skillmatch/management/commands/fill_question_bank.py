"""
Grow each skill's question bank by one daily batch.

Run once a day (Windows Task Scheduler / cron):
  python manage.py fill_question_bank
  python manage.py fill_question_bank --skill Python --force
"""

import time

from django.core.management.base import BaseCommand

from skillmatch.models import Skill, SkillQuizQuestion
from skillmatch.quiz_bank import bank_size, current_cycle, top_up_skill
from skillmatch.quiz_llm import QuizGenerationError


class Command(BaseCommand):
    help = "Add up to one daily batch of questions to each taught skill's bank."

    def add_arguments(self, parser):
        parser.add_argument("--skill", help="Only fill this skill (name, case-insensitive).")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Generate even if a batch was already added today.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=2.0,
            help="Seconds to wait between Groq calls (rate-limit friendly).",
        )

    def handle(self, *args, **options):
        skills = Skill.objects.filter(is_approved=True)
        if options["skill"]:
            skills = skills.filter(name__iexact=options["skill"])
        else:
            # Only skills someone teaches need a quiz bank.
            skills = skills.filter(users__skill_type="teach").distinct()

        cycle = current_cycle()
        total_added = 0

        for skill in skills.order_by("name"):
            try:
                added = top_up_skill(skill, force=options["force"])
            except QuizGenerationError as exc:
                self.stderr.write(self.style.ERROR(f"{skill.name}: {exc}"))
                continue

            size = SkillQuizQuestion.objects.filter(skill=skill, cycle=cycle).count()
            self.stdout.write(f"{skill.name}: +{added} ({size}/{bank_size()} in {cycle})")
            total_added += added

            if added:
                time.sleep(options["sleep"])

        self.stdout.write(self.style.SUCCESS(f"Done. Added {total_added} questions."))
