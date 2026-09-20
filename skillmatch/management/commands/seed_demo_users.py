"""
Seed ~50 demo users with realistic Arab/English names, skills, and availability.

Usage:
  python manage.py seed_demo_users --replace
  python manage.py seed_demo_users --count 50 --password demo1234 --replace
"""

from __future__ import annotations

import random
import re
from datetime import time

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from skillmatch.models import AvailabilitySlot, Profile, Skill, UserSkill

# Mix of Arab + English first / last names for realistic local feel
FIRST_NAMES = [
    "Omar", "Ali", "Mohamed", "Mostafa", "Peter", "Mahmoud", "Ahmed", "Youssef",
    "Hassan", "Karim", "Tarek", "Nour", "Sara", "Layla", "Mariam", "Hana",
    "James", "Sarah", "Daniel", "Emma", "Michael", "Olivia", "David", "Emily",
    "Khaled", "Amira", "Rania", "Farah", "Adam", "Noor", "Yasmin", "Ziad",
    "Andrew", "Rachel", "Thomas", "Laura", "Mark", "Chloe", "Samir", "Dina",
    "Bassem", "Heba", "Fady", "Nadine", "Walid", "Salma", "Rami", "Jana",
    "Chris", "Maya",
]

LAST_NAMES = [
    "Hassan", "Ali", "Farouk", "Ibrahim", "Saleh", "Mansour", "Khalil", "Nasser",
    "Abdullah", "Mahmoud", "Said", "Gamal", "Fathy", "Soliman", "Osman", "Rashed",
    "Smith", "Johnson", "Brown", "Wilson", "Taylor", "Anderson", "Clark", "Walker",
    "Hegazy", "ElSayed", "Mostafa", "Younis", "Kamal", "Sherif", "Ashraf", "Adel",
    "Miller", "Davis", "Moore", "Martin", "Lee", "White", "Harris", "Lewis",
]

PEOPLE = [
    ("Omar", "Hassan"),
    ("Ali", "Farouk"),
    ("Mohamed", "Ibrahim"),
    ("Mostafa", "Saleh"),
    ("Peter", "Wilson"),
    ("Mahmoud", "Khalil"),
    ("Ahmed", "Nasser"),
    ("Youssef", "Abdullah"),
    ("Hassan", "Mahmoud"),
    ("Karim", "Said"),
    ("Tarek", "Gamal"),
    ("Nour", "ElSayed"),
    ("Sara", "Hegazy"),
    ("Layla", "Mansour"),
    ("Mariam", "Soliman"),
    ("Hana", "Osman"),
    ("James", "Smith"),
    ("Sarah", "Johnson"),
    ("Daniel", "Brown"),
    ("Emma", "Taylor"),
    ("Michael", "Anderson"),
    ("Olivia", "Clark"),
    ("David", "Walker"),
    ("Emily", "Miller"),
    ("Khaled", "Younis"),
    ("Amira", "Kamal"),
    ("Rania", "Sherif"),
    ("Farah", "Ashraf"),
    ("Adam", "Adel"),
    ("Noor", "Fathy"),
    ("Yasmin", "Rashed"),
    ("Ziad", "Mostafa"),
    ("Andrew", "Davis"),
    ("Rachel", "Moore"),
    ("Thomas", "Martin"),
    ("Laura", "Lee"),
    ("Mark", "White"),
    ("Chloe", "Harris"),
    ("Samir", "Hassan"),
    ("Dina", "Ali"),
    ("Bassem", "Farouk"),
    ("Heba", "Ibrahim"),
    ("Fady", "Saleh"),
    ("Nadine", "Khalil"),
    ("Walid", "Nasser"),
    ("Salma", "Abdullah"),
    ("Rami", "Mahmoud"),
    ("Jana", "Said"),
    ("Chris", "Lewis"),
    ("Maya", "Hegazy"),
]

SKILL_NAMES = [
    "Python", "JavaScript", "TypeScript", "React", "Django", "SQL", "UI Design",
    "Figma", "Public Speaking", "Spanish", "French", "Guitar", "Piano", "Photography",
    "Video Editing", "Excel", "Data Analysis", "Machine Learning", "Copywriting",
    "Marketing", "Yoga", "Cooking", "Chess", "German", "Swift", "Kotlin", "Node.js",
    "CSS", "Product Management", "Career Coaching", "Arabic", "English Conversation",
]

BIOS = [
    "Software engineer in Cairo — happy to teach Python and learn design.",
    "CS student looking for patient partners to practice English and React.",
    "Product designer swapping Figma tips for backend basics.",
    "Marketing specialist who wants to get better at data analysis.",
    "Musician trading guitar lessons for public speaking practice.",
    "Recent grad building skills through real conversations, not courses alone.",
    "Full-stack developer who enjoys mentoring beginners.",
    "Language nerd open to Arabic ↔ English conversation swaps.",
]

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

TIME_BLOCKS = [
    (time(9, 0), time(10, 0)),
    (time(10, 0), time(11, 0)),
    (time(11, 0), time(12, 0)),
    (time(14, 0), time(15, 0)),
    (time(15, 0), time(16, 0)),
    (time(16, 0), time(17, 0)),
    (time(18, 0), time(19, 0)),
    (time(19, 0), time(20, 0)),
]

DEMO_EMAIL_DOMAIN = "@skillmatch.demo"


def make_username(first: str, last: str) -> str:
    base = re.sub(r"[^a-z0-9]", "", f"{first}{last}".lower())
    return base[:28] or "user"


class Command(BaseCommand):
    help = "Create demo users with realistic names, skills, and availability."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=50)
        parser.add_argument("--password", type=str, default="demo1234")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete previously seeded demo users before creating new ones.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = min(options["count"], len(PEOPLE))
        password = options["password"]

        if options["replace"]:
            from django.db.models import Q

            qs = User.objects.filter(
                Q(email__endswith=DEMO_EMAIL_DOMAIN) | Q(username__startswith="demo")
            )
            removed = qs.count()
            qs.delete()
            self.stdout.write(f"Removed {removed} previous demo user(s).")

        skills = []
        for name in SKILL_NAMES:
            skill, _ = Skill.objects.get_or_create(name=name)
            skills.append(skill)

        created_users = 0
        skipped = 0
        sample_login = None

        for index, (first, last) in enumerate(PEOPLE[:count], start=1):
            username = make_username(first, last)
            # Keep usernames unique if first+last collide
            candidate = username
            suffix = 1
            while User.objects.filter(username=candidate).exists():
                candidate = f"{username}{suffix}"
                suffix += 1
            username = candidate

            email = f"{username}{DEMO_EMAIL_DOMAIN}"
            if User.objects.filter(email=email).exists():
                skipped += 1
                continue

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first,
                last_name=last,
            )

            if sample_login is None:
                sample_login = username

            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "bio": random.choice(BIOS),
                    "onboarding_completed": True,
                },
            )

            teach_skills = random.sample(skills, k=random.randint(2, 4))
            remaining = [s for s in skills if s not in teach_skills]
            learn_skills = random.sample(remaining, k=random.randint(2, 4))

            for skill in teach_skills:
                UserSkill.objects.create(user=user, skill=skill, skill_type="teach")
            for skill in learn_skills:
                UserSkill.objects.create(user=user, skill=skill, skill_type="learn")

            for day, (start, end) in random.sample(
                [(d, t) for d in DAYS for t in TIME_BLOCKS],
                k=random.randint(3, 6),
            ):
                AvailabilitySlot.objects.create(
                    user=user,
                    day=day,
                    start_time=start,
                    end_time=end,
                )

            created_users += 1

        login_hint = f"{sample_login} / {password}" if sample_login else f"(none) / {password}"
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_users} users "
                f"(skipped {skipped} existing). "
                f"Login example: {login_hint}"
            )
        )
