from django.db import models
from django.contrib.auth.models import User

class SkillSwapMeeting(models.Model):
    participant_a = models.ForeignKey(User, related_name="meetings_as_a", on_delete=models.CASCADE)
    participant_b = models.ForeignKey(User, related_name="meetings_as_b", on_delete=models.CASCADE)
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    room_url = models.URLField()
    token_a = models.CharField(max_length=500) 
    token_b = models.CharField(max_length=500) 
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Swap: {self.participant_a.username} & {self.participant_b.username} at {self.start_time}"