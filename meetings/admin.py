from django.contrib import admin
from .models import SkillSwapMeeting

@admin.register(SkillSwapMeeting)
class SkillSwapMeetingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'participant_a',
        'participant_b',
        'status',
        'start_time',
        'end_time',
        'room_url'
    )
    list_filter = (
        'status',
        'participant_a',
        'participant_b',
        'start_time',
    )
    search_fields = (
        'participant_a__username',
        'participant_b__username',
        'room_url',
    )
    readonly_fields = ('room_url',)
    ordering = ('-start_time',)
