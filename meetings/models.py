from datetime import timedelta
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from matching.models import MatchRequest

class Meeting(models.Model):
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("COMPLETED", "Completed"),
        ("MISSED", "Missed"),
        ("CANCELLED", "Cancelled"),
    ]

    request = models.OneToOneField(
        'matching.MatchRequest',
        on_delete=models.CASCADE,
        related_name="meeting"
    )
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="SCHEDULED")
    
    room_url = models.URLField(max_length=500, blank=True, default="")
    room_name = models.CharField(max_length=255, blank=True, default="")
    token_sender = models.TextField(blank=True, default="")
    token_receiver = models.TextField(blank=True, default="")
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def review_deadline(self):
        return self.end_time + timedelta(hours=48)

    def __str__(self):
        return f"Meeting #{self.id} ({self.status}): {self.request.sender.username} & {self.request.receiver.username}"


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
