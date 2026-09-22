from rest_framework import serializers
from .models import MatchRequest
from skillmatch.models import UserSkill


class MatchSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    teach_me = serializers.ListField(child=serializers.CharField())
    teach_them = serializers.ListField(child=serializers.CharField())


class MatchRequestSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    receiver_username = serializers.CharField(source="receiver.username", read_only=True)
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    selected_slot_day = serializers.CharField(source="selected_slot.day", read_only=True)
    selected_slot_start_time = serializers.TimeField(source="selected_slot.start_time", read_only=True, format="%H:%M")
    selected_slot_end_time = serializers.TimeField(source="selected_slot.end_time", read_only=True, format="%H:%M")
    receiver_skill_name = serializers.CharField(source="receiver_skill.name", read_only=True)
    sender_teach_skills = serializers.SerializerMethodField()

    class Meta:
        model = MatchRequest
        fields = [
            "id",
            "sender",
            "sender_username",
            "receiver",
            "receiver_username",
            "skill",
            "skill_name",
            "selected_slot",
            "selected_slot_day",
            "selected_slot_start_time",
            "selected_slot_end_time",
            "status",
            "rejection_reason",
            "receiver_skill_name",
            "sender_teach_skills",
        ]
        read_only_fields = [
            "id",
            "sender",
            "sender_username",
            "receiver_username",
            "skill_name",
            "selected_slot_day",
            "selected_slot_start_time",
            "selected_slot_end_time",
            "status",
            "rejection_reason",
            "receiver_skill_name",
            "sender_teach_skills",
        ]

    def get_sender_teach_skills(self, obj):
        receiver_learn_skill_ids = set(
            UserSkill.objects.filter(
                user=obj.receiver,
                skill_type="learn"
            ).values_list("skill_id", flat=True)
        )

        user_skills = UserSkill.objects.filter(
            user=obj.sender,
            skill_type="teach",
            skill_id__in=receiver_learn_skill_ids,
        ).select_related("skill").order_by("skill__name")

        return [
            {"id": item.skill_id, "name": item.skill.name}
            for item in user_skills
        ]

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
