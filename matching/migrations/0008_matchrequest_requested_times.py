from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matching", "0007_remove_matchrequest_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="matchrequest",
            name="requested_start_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="matchrequest",
            name="requested_end_time",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
