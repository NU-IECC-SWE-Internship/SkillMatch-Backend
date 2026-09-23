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
            "rating_average",
            "rating_count",
        ]

        read_only_fields = [
            "id",
            "user",
            "username",
            "rating_average",
            "rating_count",
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
    has_quiz_attempt = serializers.SerializerMethodField()
    quiz_score = serializers.SerializerMethodField()
    can_take_quiz = serializers.SerializerMethodField()
    quiz_available_at = serializers.SerializerMethodField()

    class Meta:
        model = UserSkill

        fields = [
            "id",
            "skill",
            "skill_name",
            "skill_type",
            "is_verified",
            "has_quiz_attempt",
            "quiz_score",
            "can_take_quiz",
            "quiz_available_at",
        ]
        read_only_fields = [
            "id",
            "skill_name",
            "is_verified",
            "has_quiz_attempt",
            "quiz_score",
            "can_take_quiz",
            "quiz_available_at",
        ]

    def _availability(self, obj):
        cache = self.context.setdefault("_quiz_availability_cache", {})
        key = (obj.user_id, obj.skill_id, obj.is_verified)
        if key not in cache:
            from .quiz_policy import quiz_availability
            cache[key] = quiz_availability(
                obj.user,
                obj.skill,
                is_verified=obj.is_verified,
            )
        return cache[key]

    def get_has_quiz_attempt(self, obj):
        _can_take, attempt, _available_at = self._availability(obj)
        return attempt is not None

    def get_quiz_score(self, obj):
        _can_take, attempt, _available_at = self._availability(obj)
        return attempt.score if attempt else None

    def get_can_take_quiz(self, obj):
        if obj.skill_type != "teach":
            return False
        can_take, _attempt, _available_at = self._availability(obj)
        return can_take

    def get_quiz_available_at(self, obj):
        can_take, _attempt, available_at = self._availability(obj)
        if can_take or available_at is None:
            return None
        return available_at



class QuizAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected = serializers.ChoiceField(choices=["A", "B", "C", "D"])


class QuizSubmitSerializer(serializers.Serializer):
    answers = QuizAnswerSerializer(many=True)


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
            email=validated_data.get(
                "email",
                ""
            ),
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
