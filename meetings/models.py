from django.db import models
from django.contrib.auth.models import User

class SkillSwapMeeting(models.Model):
    STATUS_PENDING = 'pending' #Requester has sent a request
    STATUS_ACCEPTED = 'accepted' #Invited user has accepted the request
    STATUS_REJECTED = 'rejected' #Invited user has rejected the request
    STATUS_CANCELLED = 'cancelled' #Requester has cancelled the request

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    participant_a = models.ForeignKey(User, related_name="meetings_as_a", on_delete=models.CASCADE) #Requested user
    participant_b = models.ForeignKey(User, related_name="meetings_as_b", on_delete=models.CASCADE) #Invited user
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    room_url = models.URLField(default="", blank=True) 
    token_a = models.CharField(max_length=500, default="", blank=True) 
    token_b = models.CharField(max_length=500, default="", blank=True) 
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Swap ({self.status}): {self.participant_a.username} & {self.participant_b.username} at {self.start_time}"