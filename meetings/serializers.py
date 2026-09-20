from rest_framework import serializers
from .models import Meeting


class MeetingSerializer(serializers.ModelSerializer):
    request_id = serializers.IntegerField(source='request.id', read_only=True)
    sender_id = serializers.IntegerField(source='request.sender.id', read_only=True)
    receiver_id = serializers.IntegerField(source='request.receiver.id', read_only=True)
    sender_username = serializers.CharField(source='request.sender.username', read_only=True)
    receiver_username = serializers.CharField(source='request.receiver.username', read_only=True)
    skill_name = serializers.CharField(source='request.skill.name', read_only=True)

    # Aliases for frontend compatibility
    participant_a_name = serializers.CharField(source='request.sender.username', read_only=True)
    participant_b_name = serializers.CharField(source='request.receiver.username', read_only=True)
    partner_name = serializers.SerializerMethodField()
    is_requester = serializers.SerializerMethodField()
    my_token = serializers.SerializerMethodField()
    start_time_ts = serializers.SerializerMethodField()
    end_time_ts = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            'id',
            'request_id',
            'sender_id',
            'receiver_id',
            'sender_username',
            'receiver_username',
            'participant_a_name',
            'participant_b_name',
            'partner_name',
            'is_requester',
            'skill_name',
            'status',
            'start_time',
            'end_time',
            'start_time_ts',
            'end_time_ts',
            'room_url',
            'room_name',
            'my_token',
            'created_at',
        ]

    def get_partner_name(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if user and obj.request.sender_id == user.id:
            return obj.request.receiver.username
        return obj.request.sender.username

    def get_is_requester(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        return bool(user and obj.request.sender_id == user.id)

    def get_my_token(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or obj.status == "CANCELLED":
            return None
        return obj.token_sender if obj.request.sender_id == user.id else obj.token_receiver

    def get_start_time_ts(self, obj):
        return int(obj.start_time.timestamp() * 1000)

    def get_end_time_ts(self, obj):
        return int(obj.end_time.timestamp() * 1000)
