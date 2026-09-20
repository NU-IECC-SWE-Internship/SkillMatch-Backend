from django.db import migrations


def mark_existing_profiles_complete(apps, schema_editor):
    Profile = apps.get_model("skillmatch", "Profile")
    UserSkill = apps.get_model("skillmatch", "UserSkill")

    users_with_skills = UserSkill.objects.values_list("user_id", flat=True).distinct()
    Profile.objects.filter(user_id__in=users_with_skills).update(
        onboarding_completed=True
    )
    Profile.objects.exclude(bio="").update(onboarding_completed=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("skillmatch", "0004_profile_onboarding_completed"),
    ]

    operations = [
        migrations.RunPython(mark_existing_profiles_complete, noop),
    ]
