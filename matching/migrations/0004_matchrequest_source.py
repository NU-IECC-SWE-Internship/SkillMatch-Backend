from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matching", "0003_matchrequest_receiver_skill"),
    ]

    operations = [
        migrations.AddField(
            model_name="matchrequest",
            name="source",
            field=models.CharField(
                choices=[("matches", "Matches"), ("skillbrowse", "Skill Browse")],
                default="matches",
                max_length=20,
            ),
        ),
    ]
