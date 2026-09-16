from django.contrib.auth.models import User
from rest_framework import serializers
from .models import SkillSwapMeeting

class UserOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class ScheduleMeetingInputSerializer(serializers.Serializer):
    user_b_id = serializers.IntegerField()
    start_iso = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(default=60, min_value=5, max_value=480)

class MeetingDetailSerializer(serializers.ModelSerializer):
    participant_a_name = serializers.CharField(source='participant_a.username', read_only=True)
    participant_b_name = serializers.CharField(source='participant_b.username', read_only=True)
    partner_name = serializers.SerializerMethodField()
    my_token = serializers.SerializerMethodField()
    start_time_ts = serializers.SerializerMethodField()
    end_time_ts = serializers.SerializerMethodField()

    class Meta:
        model = SkillSwapMeeting
        fields = [
            'id', 
            'participant_a_name', 
            'participant_b_name', 
            'partner_name',
            'start_time_ts', 
            'end_time_ts', 
            'room_url', 
            'my_token'
        ]

    def get_partner_name(self, obj):
        user = self.context['request'].user
        if obj.participant_a == user:
            return obj.participant_b.username
        return obj.participant_a.username

    def get_my_token(self, obj):
        user = self.context['request'].user
        if obj.participant_a == user:
            return obj.token_a
        elif obj.participant_b == user:
            return obj.token_b
        return None

    def get_start_time_ts(self, obj):
        return int(obj.start_time.timestamp() * 1000)

    def get_end_time_ts(self, obj):
        return int(obj.end_time.timestamp() * 1000)