from django.utils import timezone
from rest_framework import serializers
from .models import Meeting, MeetingRating


class MeetingRatingSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source='reviewer.username', read_only=True)
    reviewed_username = serializers.CharField(source='reviewed_user.username', read_only=True)
    score = serializers.IntegerField(min_value=1, max_value=5)
    feedback = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = MeetingRating
        fields = [
            'id',
            'meeting_id',
            'reviewer_id',
            'reviewer_username',
            'reviewed_user_id',
            'reviewed_username',
            'score',
            'feedback',
            'is_revealed',
            'revealed_at',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'meeting_id',
            'reviewer_id',
            'reviewer_username',
            'reviewed_user_id',
            'reviewed_username',
            'is_revealed',
            'revealed_at',
            'created_at',
        ]

    def validate(self, attrs):
        request = self.context.get('request')
        meeting = self.context.get('meeting')
        user = request.user if request else None

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        if not meeting:
            raise serializers.ValidationError("Meeting context is required.")

        if user not in (meeting.request.sender, meeting.request.receiver):
            raise serializers.ValidationError("You were not a participant in this meeting.")

        if meeting.status == "CANCELLED":
            raise serializers.ValidationError("Cannot rate a cancelled meeting.")

        now = timezone.now()
        if now < meeting.start_time:
            raise serializers.ValidationError("You cannot rate a meeting before it starts.")

        if now > meeting.review_deadline:
            raise serializers.ValidationError("The 48-hour review window for this meeting has expired.")

        if MeetingRating.objects.filter(meeting=meeting, reviewer=user).exists():
            raise serializers.ValidationError("You have already submitted a review for this meeting.")

        return attrs

    def create(self, validated_data):
        from django.db import transaction
        from .views import recalculate_user_rating

        request = self.context['request']
        meeting = self.context['meeting']
        user = request.user

        reviewed_user = meeting.request.receiver if user == meeting.request.sender else meeting.request.sender

        rating = MeetingRating.objects.create(
            meeting=meeting,
            reviewer=user,
            reviewed_user=reviewed_user,
            score=validated_data['score'],
            feedback=validated_data.get('feedback', '').strip(),
            is_revealed=False
        )

        if meeting.status == "SCHEDULED":
            meeting.status = "COMPLETED"
            meeting.save(update_fields=['status'])

        # Trigger 1: Did both users submit reviews?
        all_ratings = list(meeting.ratings.all())
        if len(all_ratings) >= 2:
            reveal_now = timezone.now()
            with transaction.atomic():
                meeting.ratings.update(is_revealed=True, revealed_at=reveal_now)
                for r in all_ratings:
                    recalculate_user_rating(r.reviewed_user)

            rating.refresh_from_db()

        return rating

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None

        # Blind review masking: if not revealed and viewer is not author
        if not instance.is_revealed and (not user or instance.reviewer_id != user.id):
            data['score'] = None
            data['feedback'] = "Review is private until both participants review or 48 hours pass."

        return data



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
    partner_id = serializers.SerializerMethodField()
    partner_name = serializers.SerializerMethodField()
    is_requester = serializers.SerializerMethodField()
    my_token = serializers.SerializerMethodField()
    start_time_ts = serializers.SerializerMethodField()
    end_time_ts = serializers.SerializerMethodField()

    # Blind Review Fields
    has_user_rated = serializers.SerializerMethodField()
    has_partner_rated = serializers.SerializerMethodField()
    is_revealed = serializers.SerializerMethodField()
    review_deadline_ts = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    user_review = serializers.SerializerMethodField()
    partner_review = serializers.SerializerMethodField()

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
            'partner_id',
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
            'has_user_rated',
            'has_partner_rated',
            'is_revealed',
            'review_deadline_ts',
            'can_review',
            'user_review',
            'partner_review',
        ]

    def _get_ratings(self, obj):
        if not hasattr(obj, '_cached_ratings'):
            obj._cached_ratings = list(obj.ratings.all())
        return obj._cached_ratings

    def get_partner_id(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if user and obj.request.sender_id == user.id:
            return obj.request.receiver_id
        return obj.request.sender_id

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

    def get_has_user_rated(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        ratings = self._get_ratings(obj)
        return any(r.reviewer_id == user.id for r in ratings)

    def get_has_partner_rated(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        ratings = self._get_ratings(obj)
        return any(r.reviewer_id != user.id for r in ratings)

    def get_is_revealed(self, obj):
        ratings = self._get_ratings(obj)
        return any(r.is_revealed for r in ratings)

    def get_review_deadline_ts(self, obj):
        return int(obj.review_deadline.timestamp() * 1000)

    def get_can_review(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated or obj.status == "CANCELLED":
            return False
        now = timezone.now()
        if now < obj.start_time:
            return False
        if now > obj.review_deadline:
            return False
        return not self.get_has_user_rated(obj)

    def get_user_review(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return None
        ratings = self._get_ratings(obj)
        for r in ratings:
            if r.reviewer_id == user.id:
                return {
                    "id": r.id,
                    "score": r.score,
                    "feedback": r.feedback,
                    "is_revealed": r.is_revealed,
                    "created_at": r.created_at.isoformat(),
                }
        return None

    def get_partner_review(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return None
        ratings = self._get_ratings(obj)
        for r in ratings:
            if r.reviewer_id != user.id:
                if r.is_revealed:
                    return {
                        "id": r.id,
                        "score": r.score,
                        "feedback": r.feedback,
                        "is_revealed": True,
                        "created_at": r.created_at.isoformat(),
                    }
                else:
                    return {
                        "id": r.id,
                        "score": None,
                        "feedback": "Review is private until both participants review or 48 hours pass.",
                        "is_revealed": False,
                        "created_at": r.created_at.isoformat(),
                    }
        return None
