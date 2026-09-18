from django.contrib.auth.models import User
from rest_framework import serializers
from .models import SkillSwapMeeting


class MeetingDetailSerializer(serializers.ModelSerializer):
    participant_a_id = serializers.IntegerField(source='participant_a.id', read_only=True)
    participant_b_id = serializers.IntegerField(source='participant_b.id', read_only=True)
    participant_a_name = serializers.CharField(source='participant_a.username', read_only=True)
    participant_b_name = serializers.CharField(source='participant_b.username', read_only=True)
    partner_name = serializers.SerializerMethodField()
    is_requester = serializers.SerializerMethodField()
    my_token = serializers.SerializerMethodField()
    start_time_ts = serializers.SerializerMethodField()
    end_time_ts = serializers.SerializerMethodField()

    class Meta:
        model = SkillSwapMeeting
        fields = [
            'id',
            'participant_a_id',
            'participant_b_id',
            'participant_a_name',
            'participant_b_name',
            'partner_name',
            'is_requester',
            'status',
            'start_time',
            'end_time',
            'start_time_ts',
            'end_time_ts',
            'room_url',
            'my_token',
            'created_at',
        ]

    def get_partner_name(self, obj):
        request = self.context.get('request')
        user = request.user if request else None
        if obj.participant_a == user:
            return obj.participant_b.username
        return obj.participant_a.username

    def get_is_requester(self, obj):
        request = self.context.get('request')
        user = request.user if request else None
        return bool(user and obj.participant_a == user)

    def get_my_token(self, obj):
        if obj.status != SkillSwapMeeting.STATUS_ACCEPTED:
            return None
        request = self.context.get('request')
        user = request.user if request else None
        if obj.participant_a == user:
            return obj.token_a
        return obj.token_b

    def get_start_time_ts(self, obj):
        return int(obj.start_time.timestamp() * 1000)

    def get_end_time_ts(self, obj):
        return int(obj.end_time.timestamp() * 1000)