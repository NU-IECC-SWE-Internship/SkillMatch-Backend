from django.db import models
from django.conf import settings


class Profile(models.Model):

    SESSION_DURATION_CHOICES = [
    (15, "15 minutes"),
    (30, "30 minutes"),
    (45, "45 minutes"),

    (60, "1 hour"),
    (75, "1 hour 15 minutes"),
    (90, "1 hour 30 minutes"),
    (105, "1 hour 45 minutes"),

    (120, "2 hours"),
    (135, "2 hours 15 minutes"),
    (150, "2 hours 30 minutes"),
    (165, "2 hours 45 minutes"),

    (180, "3 hours"),
    (195, "3 hours 15 minutes"),
    (210, "3 hours 30 minutes"),
    (225, "3 hours 45 minutes"),

    (240, "4 hours"),
]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    bio = models.TextField(blank=True)

    onboarding_completed = models.BooleanField(
        default=False
    )

    max_session_duration_minutes = models.PositiveIntegerField(
        choices=SESSION_DURATION_CHOICES,
        default=120
    )

    rating_average = models.FloatField(default=0.0)
    rating_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.user.username


class Skill(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True
    )

    def __str__(self):
        return self.name


class UserSkill(models.Model):

    SKILL_TYPES = [
        ("teach", "Teach"),
        ("learn", "Learn"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_skills"
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="users"
    )

    skill_type = models.CharField(
        max_length=10,
        choices=SKILL_TYPES
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "user",
                    "skill",
                    "skill_type"
                ],
                name="unique_user_skill_type"
            )
        ]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.skill.name} - "
            f"{self.skill_type}"
        )


class AvailabilitySlot(models.Model):

    DAYS = [
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
        ("sunday", "Sunday"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_slots"
    )

    day = models.CharField(
        max_length=10,
        choices=DAYS
    )

    start_time = models.TimeField()

    end_time = models.TimeField()

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.day} "
            f"{self.start_time} to {self.end_time}"
        )