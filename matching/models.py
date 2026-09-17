from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from skillmatch.models import Skill, AvailabilitySlot

# Create your models here.
class MatchRequest(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_match_requests"
    )

    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_match_requests"
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT
    )

    selected_slot = models.ForeignKey(
        AvailabilitySlot,
        on_delete=models.PROTECT
    )

    status = models.CharField(
        max_length=10,
        choices=[
            ("PENDING", "Pending"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_match_requests"
    )

    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_match_requests"
    )

    status = models.CharField(
        max_length=10,
        choices=[
            ("PENDING", "Pending"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING"
    )

    selected_slot = models.ForeignKey(
        AvailabilitySlot,
        on_delete=models.PROTECT
    )