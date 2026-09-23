from django.db import models
from django.conf import settings

from skillmatch.models import Skill, AvailabilitySlot


class MatchRequest(models.Model):

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_match_requests",
    )

    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_match_requests",
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT,
    )

    selected_slot = models.ForeignKey(
        AvailabilitySlot,
        on_delete=models.PROTECT,
    )

    requested_start_time = models.TimeField(
        null=True,
        blank=True,
    )

    requested_end_time = models.TimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=10,
        choices=[
            ("PENDING", "Pending"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING",
    )

    rejection_reason = models.TextField(
        blank=True,
        null=True
    )
    receiver_skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="received_match_requests"
    )
