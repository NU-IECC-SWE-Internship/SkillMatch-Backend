from django.db import migrations

# Standard approved skills every environment starts with
# (same list as the seed_demo_users command).
STANDARD_SKILLS = [
    "Python", "JavaScript", "TypeScript", "React", "Django", "SQL", "UI Design",
    "Figma", "Public Speaking", "Spanish", "French", "Guitar", "Piano", "Photography",
    "Video Editing", "Excel", "Data Analysis", "Machine Learning", "Copywriting",
    "Marketing", "Yoga", "Cooking", "Chess", "German", "Swift", "Kotlin", "Node.js",
    "CSS", "Product Management", "Career Coaching", "Arabic", "English Conversation",
]


def add_standard_skills(apps, schema_editor):
    Skill = apps.get_model("skillmatch", "Skill")
    for name in STANDARD_SKILLS:
        # Leave existing skills (and their approval state) untouched.
        if not Skill.objects.filter(name__iexact=name).exists():
            Skill.objects.create(name=name, is_approved=True)


class Migration(migrations.Migration):

    dependencies = [
        ("skillmatch", "0019_merge_20261016_1827"),
    ]

    operations = [
        # Skills may already be in use, so unapplying leaves them in place.
        migrations.RunPython(add_standard_skills, migrations.RunPython.noop),
    ]
