from django.db import migrations


def remove_cooldown_hours(apps, schema_editor):
    apps.get_model("system_config", "SystemConfig").objects.filter(
        key="quiz.cooldown_hours"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("system_config", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(remove_cooldown_hours, migrations.RunPython.noop),
    ]
