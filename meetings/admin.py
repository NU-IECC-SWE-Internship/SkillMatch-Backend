from django.contrib import admin
from .models import Meeting

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'get_sender',
        'get_receiver',
        'status',
        'start_time',
        'end_time',
        'room_url',
    )
    list_filter = (
        'status',
        'start_time',
    )
    search_fields = (
        'request__sender__username',
        'request__receiver__username',
        'room_url',
        'room_name',
    )
    ordering = ('-start_time',)

    @admin.display(description='Sender')
    def get_sender(self, obj):
        return obj.request.sender.username

    @admin.display(description='Receiver')
    def get_receiver(self, obj):
        return obj.request.receiver.username
