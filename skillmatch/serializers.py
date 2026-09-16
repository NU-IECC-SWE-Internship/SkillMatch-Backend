from rest_framework import serializers
from .models import Profile, Skill, UserSkill, AvailabilitySlot

from django.contrib.auth.models import User

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["id", "user", "bio"]
        read_only_fields = ["id", "user"]


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["id", "name"]


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
            "skill_type"
        ]


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilitySlot
        fields = [
            "id",
            "day",
            "start_time",
            "end_time"
        ]



class RegisterSerializer(serializers.ModelSerializer):
    # write_only = True means password is accepted as input,
    # but never returned in the API response
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']

    def create(self, validated_data):
        # create_user hashes the password for you
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

