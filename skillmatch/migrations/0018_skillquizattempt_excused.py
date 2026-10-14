from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('skillmatch', '0017_merge_0015_notification_0016_quiz_attempt_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='skillquizattempt',
            name='excused',
            field=models.BooleanField(default=False),
        ),
    ]
