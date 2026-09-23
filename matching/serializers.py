from rest_framework import serializers
from .models import MatchRequest
from skillmatch.models import UserSkill


class MatchSkillSerializer(serializers.Serializer):
    name = serializers.CharField()
    is_verified = serializers.BooleanField()


class MatchSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    teach_me = MatchSkillSerializer(many=True)
    teach_them = MatchSkillSerializer(many=True)
    rating_average = serializers.FloatField(default=0.0)
    rating_count = serializers.IntegerField(default=0)


class MatchRequestSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    sender_rating_average = serializers.SerializerMethodField()
    sender_rating_count = serializers.SerializerMethodField()
    receiver_username = serializers.CharField(source="receiver.username", read_only=True)
    receiver_rating_average = serializers.SerializerMethodField()
    receiver_rating_count = serializers.SerializerMethodField()
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_is_verified = serializers.SerializerMethodField()
    selected_slot_day = serializers.CharField(
        source="selected_slot.day",
        read_only=True,
    )
    selected_slot_start_time = serializers.TimeField(
        source="selected_slot.start_time",
        read_only=True,
        format="%H:%M",
    )
    selected_slot_end_time = serializers.TimeField(
        source="selected_slot.end_time",
        read_only=True,
        format="%H:%M",
    )

    class Meta:
        model = MatchRequest
        fields = [
            "id",
            "sender",
            "sender_username",
            "sender_rating_average",
            "sender_rating_count",
            "receiver",
            "receiver_username",
            "receiver_rating_average",
            "receiver_rating_count",
            "skill",
            "skill_name",
            "skill_is_verified",
            "selected_slot",
            "selected_slot_day",
            "selected_slot_start_time",
            "selected_slot_end_time",
            "status",
            "rejection_reason",
        ]
        read_only_fields = [
            "id",
            "sender",
            "sender_username",
            "sender_rating_average",
            "sender_rating_count",
            "receiver_username",
            "receiver_rating_average",
            "receiver_rating_count",
            "skill_name",
            "skill_is_verified",
            "selected_slot_day",
            "selected_slot_start_time",
            "selected_slot_end_time",
            "status",
            "rejection_reason",
        ]

    def get_sender_rating_average(self, obj):
        profile = getattr(obj.sender, "profile", None)
        return round(profile.rating_average, 1) if profile and profile.rating_average else 0.0

    def get_sender_rating_count(self, obj):
        profile = getattr(obj.sender, "profile", None)
        return profile.rating_count if profile and profile.rating_count else 0

    def get_receiver_rating_average(self, obj):
        profile = getattr(obj.receiver, "profile", None)
        return round(profile.rating_average, 1) if profile and profile.rating_average else 0.0

    def get_receiver_rating_count(self, obj):
        profile = getattr(obj.receiver, "profile", None)
        return profile.rating_count if profile and profile.rating_count else 0

    def get_skill_is_verified(self, obj):
        # The requested skill is taught by the receiver.
        return UserSkill.objects.filter(
            user=obj.receiver,
            skill=obj.skill,
            skill_type="teach",
            is_verified=True,
        ).exists()

    def validate(self, attrs):
        request = self.context.get("request")
        sender = request.user if request else None
        receiver = attrs.get("receiver")
        skill = attrs.get("skill")
        slot = attrs.get("selected_slot")

        # 1. Block sending requests to self
        if sender and receiver == sender:
            raise serializers.ValidationError({"receiver": "You cannot send a match request to yourself."})

        # 2. Ensure receiver actually teaches this skill
        receiver_teaches = UserSkill.objects.filter(
            user=receiver,
            skill=skill,
            skill_type="teach"
        ).exists()
        if not receiver_teaches:
            raise serializers.ValidationError({"skill": "The receiver does not offer this skill."})

        # 3. Ensure the availability slot belongs to the receiver
        if slot.user_id != receiver.id:
            raise serializers.ValidationError({"selected_slot": "The chosen slot does not belong to the receiver."})

        return attrs
