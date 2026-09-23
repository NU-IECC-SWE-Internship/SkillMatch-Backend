"""
Seed 10 MCQ questions per skill for verification quizzes.

  python manage.py seed_skill_quizzes
  python manage.py seed_skill_quizzes --replace
"""

from django.core.management.base import BaseCommand

from skillmatch.models import Skill, SkillQuizQuestion

SKILL_NAMES = [
    "Python", "JavaScript", "TypeScript", "React", "Django", "SQL", "UI Design",
    "Figma", "Public Speaking", "Spanish", "French", "Guitar", "Piano", "Photography",
    "Video Editing", "Excel", "Data Analysis", "Machine Learning", "Copywriting",
    "Marketing", "Yoga", "Cooking", "Chess", "German", "Swift", "Kotlin", "Node.js",
    "CSS", "Product Management", "Career Coaching", "Arabic", "English Conversation",
]


def build_questions(skill_name: str) -> list[dict]:
    """Demo-friendly templates; answer key is always A for predictability in seeding."""
    return [
        {
            "order": 1,
            "question_text": f"What is a core idea when learning or teaching {skill_name}?",
            "option_a": f"Practice fundamentals of {skill_name} consistently",
            "option_b": "Ignore basics and jump to advanced topics only",
            "option_c": "Never ask questions",
            "option_d": "Avoid hands-on practice",
            "correct_option": "A",
        },
        {
            "order": 2,
            "question_text": f"Which habit helps someone improve at {skill_name} fastest?",
            "option_a": "Short, focused practice with feedback",
            "option_b": "Only watching others without trying",
            "option_c": "Memorizing unrelated facts",
            "option_d": "Skipping review sessions",
            "correct_option": "A",
        },
        {
            "order": 3,
            "question_text": f"When teaching {skill_name}, what should you do first?",
            "option_a": "Check the learner’s current level",
            "option_b": "Start with the hardest challenge",
            "option_c": "Assume they already know everything",
            "option_d": "Avoid examples",
            "correct_option": "A",
        },
        {
            "order": 4,
            "question_text": f"A good {skill_name} learning goal is:",
            "option_a": "Specific, measurable, and time-bound",
            "option_b": "Vague and endless",
            "option_c": "Impossible in one session",
            "option_d": "Unrelated to the skill",
            "correct_option": "A",
        },
        {
            "order": 5,
            "question_text": f"If a learner is stuck on {skill_name}, you should:",
            "option_a": "Break the problem into smaller steps",
            "option_b": "Tell them to give up",
            "option_c": "Skip explaining and move on",
            "option_d": "Only give the final answer with no context",
            "correct_option": "A",
        },
        {
            "order": 6,
            "question_text": f"Which resource is usually most useful for {skill_name}?",
            "option_a": "Official docs or trusted references plus practice",
            "option_b": "Random unverified rumors only",
            "option_c": "Avoiding all examples",
            "option_d": "Never reviewing mistakes",
            "correct_option": "A",
        },
        {
            "order": 7,
            "question_text": f"During a {skill_name} skill swap, good etiquette includes:",
            "option_a": "Being respectful, patient, and on time",
            "option_b": "Interrupting constantly",
            "option_c": "Ignoring the other person’s goals",
            "option_d": "Ending without any feedback",
            "correct_option": "A",
        },
        {
            "order": 8,
            "question_text": f"How can you check understanding of {skill_name}?",
            "option_a": "Ask the learner to explain or apply it",
            "option_b": "Assume silence means mastery",
            "option_c": "Never ask follow-up questions",
            "option_d": "Only lecture without interaction",
            "correct_option": "A",
        },
        {
            "order": 9,
            "question_text": f"A common mistake when starting {skill_name} is:",
            "option_a": "Skipping fundamentals for shiny advanced tricks",
            "option_b": "Practicing the basics",
            "option_c": "Asking clarifying questions",
            "option_d": "Using simple examples",
            "correct_option": "A",
        },
        {
            "order": 10,
            "question_text": f"After a {skill_name} session, what helps retention?",
            "option_a": "Summarize key takeaways and practice soon after",
            "option_b": "Forget everything immediately",
            "option_c": "Avoid notes or reflection",
            "option_d": "Never revisit the material",
            "correct_option": "A",
        },
    ]


class Command(BaseCommand):
    help = "Create 10 MCQ quiz questions for each known skill."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing quiz questions for seeded skills before creating new ones.",
        )

    def handle(self, *args, **options):
        replace = options["replace"]
        created_questions = 0
        skills_done = 0

        for name in SKILL_NAMES:
            skill, _ = Skill.objects.get_or_create(name=name)

            if replace:
                SkillQuizQuestion.objects.filter(skill=skill).delete()

            existing = SkillQuizQuestion.objects.filter(skill=skill).count()
            if existing >= 10 and not replace:
                self.stdout.write(f"Skip {name}: already has {existing} questions")
                continue

            for q in build_questions(name):
                _, was_created = SkillQuizQuestion.objects.update_or_create(
                    skill=skill,
                    order=q["order"],
                    defaults={
                        "question_text": q["question_text"],
                        "option_a": q["option_a"],
                        "option_b": q["option_b"],
                        "option_c": q["option_c"],
                        "option_d": q["option_d"],
                        "correct_option": q["correct_option"],
                    },
                )
                if was_created:
                    created_questions += 1

            skills_done += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Quiz seed complete: {skills_done} skill(s), "
                f"{created_questions} new question row(s)."
            )
        )
