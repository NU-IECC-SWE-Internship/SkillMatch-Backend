"""
Data migration helper: keep one SkillQuizAttempt per (user, skill)
before adding the unique constraint.
"""

from django.db import migrations, models


def dedupe_quiz_attempts(apps, schema_editor):
    SkillQuizAttempt = apps.get_model("skillmatch", "SkillQuizAttempt")
    seen = set()
    # Newest first — keep the latest attempt per user+skill
    for attempt in SkillQuizAttempt.objects.all().order_by("-created_at", "-id"):
        key = (attempt.user_id, attempt.skill_id)
        if key in seen:
            attempt.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ("skillmatch", "0009_skill_quiz_verification"),
    ]

    operations = [
        migrations.RunPython(dedupe_quiz_attempts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="skillquizattempt",
            constraint=models.UniqueConstraint(
                fields=("user", "skill"),
                name="unique_user_skill_quiz_attempt",
            ),
        ),
    ]
