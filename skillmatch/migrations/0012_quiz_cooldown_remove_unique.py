from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("skillmatch", "0011_pending_skill_quiz"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="skillquizattempt",
            name="unique_user_skill_quiz_attempt",
        ),
    ]
