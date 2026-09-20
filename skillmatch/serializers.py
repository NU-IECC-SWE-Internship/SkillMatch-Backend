from django.contrib.auth.models import User
from rest_framework import serializers

from .models import (
    Profile,
    Skill,
    UserSkill,
    AvailabilitySlot,
)


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        source="user.username",
        read_only=True
    )

    class Meta:
        model = Profile
        fields = [
            "id",
            "user",
            "username",
            "bio",
            "onboarding_completed",
            "max_session_duration_minutes",
        ]

        read_only_fields = [
            "id",
            "user",
            "username",
        ]


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
        ]


class UserSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(
        source="skill.name",
        read_only=True
    )

    class Meta:
        model = UserSkill
        fields = [
            "id",
            "skill",
            "skill_name",
            "skill_type",
        ]


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilitySlot
        fields = [
            "id",
            "day",
            "start_time",
            "end_time",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=6
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "password",
        ]

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )

        Profile.objects.get_or_create(
            user=user
        )

        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
        ]