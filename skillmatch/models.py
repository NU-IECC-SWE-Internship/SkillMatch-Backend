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

    bio = models.TextField(
        blank=True
    )

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

    # Custom skills added by regular users stay hidden until an admin approves them.
    is_approved = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_skills",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True,
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

    is_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "user",
                    "skill",
                    "skill_type",
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


class SkillQuizQuestion(models.Model):
    """
    Question bank entry. Each skill collects up to `quiz_bank.size` questions per
    monthly cycle ("YYYY-MM"); quizzes draw a random sample from the bank.
    """

    OPTION_CHOICES = [
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("D", "D"),
    ]

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    DIFFICULTY_CHOICES = [
        (EASY, "Easy"),
        (MEDIUM, "Medium"),
        (HARD, "Hard"),
    ]
    DIFFICULTY_ORDER = [EASY, MEDIUM, HARD]

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="quiz_questions",
    )
    cycle = models.CharField(max_length=7, db_index=True)
    difficulty = models.CharField(
        max_length=10,
        choices=DIFFICULTY_CHOICES,
        default=MEDIUM,
        db_index=True,
    )
    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_option = models.CharField(max_length=1, choices=OPTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["skill", "-cycle", "id"]

    def __str__(self):
        return f"{self.skill.name} [{self.cycle}] #{self.id}"


class SkillQuizAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    score = models.PositiveSmallIntegerField()
    passed = models.BooleanField(default=False)
    abandoned = models.BooleanField(default=False)
    # One entry per question: text, options, correct_option, selected (None = timed out).
    review = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.user.username} - {self.skill.name}: "
            f"{self.score}/10 ({'pass' if self.passed else 'fail'})"
        )


class PendingSkillQuiz(models.Model):
    """
    One in-progress quiz per user+skill.
    questions stores full MCQs including correct_option for grading.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_quizzes",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="pending_quizzes",
    )
    questions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "skill"],
                name="unique_pending_skill_quiz",
            )
        ]

    def public_questions(self):
        public = []
        for item in self.questions:
            public.append(
                {
                    "id": item.get("order"),
                    "order": item.get("order"),
                    "question_text": item.get("question_text"),
                    "option_a": item.get("option_a"),
                    "option_b": item.get("option_b"),
                    "option_c": item.get("option_c"),
                    "option_d": item.get("option_d"),
                    "difficulty": item.get("difficulty", SkillQuizQuestion.MEDIUM),
                }
            )
        return public


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