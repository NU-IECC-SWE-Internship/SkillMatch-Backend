from django.db import models
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

    def __str__(self):
        return f"Meeting #{self.id} ({self.status}): {self.request.sender.username} & {self.request.receiver.username}"
