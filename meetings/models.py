from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from matching.models import MatchRequest
from system_config.services import get_hours



class Meeting(models.Model):
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("COMPLETED", "Completed"),
        ("MISSED", "Missed"),
        ("CANCELLED", "Cancelled"),
    ]

    SESSION_TYPE_CHOICES = [
        ("REQUESTED_SKILL", "Requested Skill"),
        ("RETURN_SKILL", "Return Skill"),
    ]

    request = models.ForeignKey(
        "matching.MatchRequest",
        on_delete=models.CASCADE,
        related_name="meetings",
    )

    session_type = models.CharField(
        max_length=20,
        choices=SESSION_TYPE_CHOICES,
        default="REQUESTED_SKILL",
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="SCHEDULED",
    )

    room_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
    )

    room_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    token_sender = models.TextField(
        blank=True,
        default="",
    )

    token_receiver = models.TextField(
        blank=True,
        default="",
    )

    cancellation_reason = models.TextField(blank=True, default="")
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_meetings",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    reminder_sent = models.BooleanField(default=False)
    rating_prompt_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["request", "session_type"],
                name="unique_request_session_type",
            )
        ]

    @property
    def review_deadline(self):
        return self.end_time + get_hours("reviews.window_hours")

    @property
    def cancellation_cutoff_time(self):
        return self.start_time - get_hours("meetings.cancel_notice_hours")

    @property
    def can_cancel(self):
        from django.utils import timezone
        if self.status != "SCHEDULED":
            return False
        now = timezone.now()
        if now >= self.start_time:
            return False
        return now <= self.cancellation_cutoff_time

    def __str__(self):
        return (
            f"Meeting #{self.id} ({self.session_type}, {self.status}): "
            f"{self.request.sender.username} & {self.request.receiver.username}"
        )
class MeetingRating(models.Model):
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="ratings"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="given_ratings"
    )
    reviewed_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_ratings"
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    feedback = models.TextField(blank=True, default="")
    is_revealed = models.BooleanField(default=False)
    revealed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "reviewer"],
                name="unique_meeting_reviewer"
            )
        ]

    def __str__(self):
        return f"Review for Meeting #{self.meeting_id} by {self.reviewer.username} ({self.score}★)"
