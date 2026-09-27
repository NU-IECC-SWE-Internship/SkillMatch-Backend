from datetime import datetime, timedelta, timezone as dt_timezone
import zoneinfo
from django.db import transaction
from django.db.models import Q, Avg, Count
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from matching.models import MatchRequest
from .models import Meeting, MeetingRating
from .serializers import MeetingSerializer, MeetingRatingSerializer
from .video_service import DailyVideoService


def recalculate_user_rating(user):
    if not user:
        return
    user_id = user.id if hasattr(user, 'id') else user
    stats = MeetingRating.objects.filter(
        reviewed_user_id=user_id,
        is_revealed=True
    ).aggregate(
        avg_score=Avg('score'),
        total_reviews=Count('id')
    )

    from skillmatch.models import Profile
    profile, _ = Profile.objects.get_or_create(user_id=user_id)
    profile.rating_average = round(stats['avg_score'] or 0.0, 2)
    profile.rating_count = stats['total_reviews'] or 0
    profile.save(update_fields=['rating_average', 'rating_count'])


def process_expired_ratings():
    now = timezone.now()
    cutoff = now - timedelta(hours=48)
    affected_user_ids = set()

    unrevealed_meetings = Meeting.objects.filter(ratings__is_revealed=False).distinct()
    for m in unrevealed_meetings:
        ratings = list(MeetingRating.objects.filter(meeting_id=m.id))
        if len(ratings) >= 2 or (m.end_time and m.end_time <= cutoff):
            with transaction.atomic():
                MeetingRating.objects.filter(meeting_id=m.id).update(
                    is_revealed=True,
                    revealed_at=now
                )
                for r in ratings:
                    affected_user_ids.add(r.reviewed_user_id)

    for uid in affected_user_ids:
        recalculate_user_rating(uid)


def create_meeting_for_match_request(match_request, user_timezone=None):
    if hasattr(match_request, 'meeting'):
        return match_request.meeting, None

    slot = getattr(match_request, 'selected_slot', None)
    if not slot:
        return None, ({"error": "The match request does not have an availability slot attached."}, status.HTTP_400_BAD_REQUEST)

    tz_str = user_timezone or "UTC"
    try:
        user_tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        user_tz = zoneinfo.ZoneInfo("UTC")

    now_user = timezone.now().astimezone(user_tz)

    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
    }
    target_weekday = day_map.get(str(slot.day).lower(), 0)
    days_ahead = (target_weekday - now_user.weekday() + 7) % 7
    target_date = now_user.date() + timedelta(days=days_ahead)

    user_start = datetime.combine(target_date, slot.start_time).replace(tzinfo=user_tz)
    user_end = datetime.combine(target_date, slot.end_time).replace(tzinfo=user_tz)

    if user_start <= now_user:
        user_start += timedelta(days=7)
        user_end += timedelta(days=7)

    start_time_utc = user_start.astimezone(dt_timezone.utc)
    end_time_utc = user_end.astimezone(dt_timezone.utc)

    start_ts = int(start_time_utc.timestamp())
    end_ts = int(end_time_utc.timestamp())
    service = DailyVideoService()

    try:
        room_data = service.create_scheduled_room(start_ts, end_ts)
        token_sender = service.create_scheduled_token(
            room_data['name'], match_request.sender.username, start_ts, end_ts
        )
        token_receiver = service.create_scheduled_token(
            room_data['name'], match_request.receiver.username, start_ts, end_ts
        )
    except Exception as e:
        return None, ({"error": f"Video service error: {str(e)}"}, status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        meeting = Meeting.objects.create(
            request=match_request,
            start_time=start_time_utc,
            end_time=end_time_utc,
            status="SCHEDULED",
            room_url=room_data.get('url') or "",
            room_name=room_data.get('name') or "",
            token_sender=token_sender,
            token_receiver=token_receiver,
        )
    except Exception as e:
        return None, ({"error": f"Could not save meeting: {str(e)}"}, status.HTTP_500_INTERNAL_SERVER_ERROR)

    match_request.status = "ACCEPTED"
    match_request.rejection_reason = None
    match_request.save(update_fields=['status', 'rejection_reason'])

    return meeting, None


class MeetingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        process_expired_ratings()
        
        now = timezone.now()
        Meeting.objects.filter(
            status='SCHEDULED',
            end_time__lt=now
        ).update(status='COMPLETED')

        status_param = request.query_params.get('status')
        meetings = Meeting.objects.filter(
            Q(request__sender=request.user) | Q(request__receiver=request.user)
        ).select_related(
            'request__sender', 'request__receiver', 'request__skill'
        ).prefetch_related(
            'ratings'
        )

        if status_param and status_param.lower() != 'all':
            if status_param.lower() in ['accepted', 'scheduled']:
                meetings = meetings.filter(status='SCHEDULED')
            else:
                meetings = meetings.filter(status__iexact=status_param)

        meetings = meetings.order_by('start_time')
        serializer = MeetingSerializer(meetings, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        request_id = request.data.get('request_id')
        user_timezone = request.data.get('timezone') or request.headers.get('X-Timezone')
        if not request_id:
            return Response({"error": "request_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            match_request = MatchRequest.objects.select_related('sender', 'receiver', 'selected_slot').get(pk=request_id)
        except MatchRequest.DoesNotExist:
            return Response({"error": "Match request not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in (match_request.sender, match_request.receiver):
            return Response({"error": "You do not have permission to schedule this meeting."}, status=status.HTTP_403_FORBIDDEN)

        meeting, err = create_meeting_for_match_request(match_request, user_timezone=user_timezone)
        if err:
            err_data, err_status = err
            return Response(err_data, status=err_status)

        return Response(MeetingSerializer(meeting, context={'request': request}).data, status=status.HTTP_201_CREATED)


class SingleMeetingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        process_expired_ratings()

        try:
            meeting = Meeting.objects.select_related(
                'request__sender', 'request__receiver', 'request__skill'
            ).prefetch_related('ratings').get(pk=pk)
        except Meeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in (meeting.request.sender, meeting.request.receiver):
            return Response({"error": "You do not have permission to access this meeting."}, status=status.HTTP_403_FORBIDDEN)

        return Response(MeetingSerializer(meeting, context={'request': request}).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        try:
            meeting = Meeting.objects.select_related(
                'request__sender', 'request__receiver', 'request__skill'
            ).prefetch_related('ratings').get(pk=pk)
        except Meeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in (meeting.request.sender, meeting.request.receiver):
            return Response({"error": "You do not have permission to modify this meeting."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')
        if new_status:
            new_status = new_status.upper()
            if new_status not in dict(Meeting.STATUS_CHOICES):
                return Response({"error": f"Invalid status '{new_status}'."}, status=status.HTTP_400_BAD_REQUEST)
            if meeting.status == "CANCELLED":
                return Response({"error": "Cannot change status of a cancelled meeting."}, status=status.HTTP_400_BAD_REQUEST)
            meeting.status = new_status
            meeting.save(update_fields=['status'])

        return Response(MeetingSerializer(meeting, context={'request': request}).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        try:
            meeting = Meeting.objects.select_related(
                'request__sender', 'request__receiver', 'request__skill'
            ).get(pk=pk)
        except Meeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in (meeting.request.sender, meeting.request.receiver):
            return Response({"error": "You do not have permission to cancel this meeting."}, status=status.HTTP_403_FORBIDDEN)

        meeting.status = "CANCELLED"
        meeting.save(update_fields=['status'])
        meeting.request.status = "CANCELLED"
        meeting.request.save(update_fields=['status'])
        return Response({"message": "Meeting cancelled successfully."}, status=status.HTTP_200_OK)


class MeetingReviewsView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_meeting(self, pk, user):
        try:
            meeting = Meeting.objects.select_related(
                'request__sender', 'request__receiver'
            ).prefetch_related('ratings__reviewer', 'ratings__reviewed_user').get(pk=pk)
        except Meeting.DoesNotExist:
            return None, Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        if user not in (meeting.request.sender, meeting.request.receiver):
            return None, Response({"error": "You do not have permission to access reviews for this meeting."}, status=status.HTTP_403_FORBIDDEN)

        return meeting, None

    def get(self, request, pk):
        process_expired_ratings()
        meeting, error_response = self._get_meeting(pk, request.user)
        if error_response:
            return error_response

        ratings = meeting.ratings.all()
        serializer = MeetingRatingSerializer(
            ratings,
            many=True,
            context={'request': request, 'meeting': meeting}
        )
        return Response({
            "meeting_id": meeting.id,
            "is_revealed": any(r.is_revealed for r in ratings),
            "review_deadline_ts": int(meeting.review_deadline.timestamp() * 1000),
            "ratings": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, pk):
        process_expired_ratings()
        meeting, error_response = self._get_meeting(pk, request.user)
        if error_response:
            return error_response

        serializer = MeetingRatingSerializer(
            data=request.data,
            context={'request': request, 'meeting': meeting}
        )

        if not serializer.is_valid():
            first_err = next(iter(serializer.errors.values())) if serializer.errors else "Invalid data"
            err_msg = first_err[0] if isinstance(first_err, list) and first_err else str(first_err)
            return Response({"error": err_msg, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        rating = serializer.save()

        # Check reveal status
        meeting.refresh_from_db()
        if hasattr(meeting, '_prefetched_objects_cache'):
            meeting._prefetched_objects_cache.clear()
        if hasattr(meeting, '_cached_ratings'):
            delattr(meeting, '_cached_ratings')
        both_revealed = MeetingRating.objects.filter(meeting_id=meeting.id, is_revealed=True).exists()

        return Response({
            "message": "Both reviews submitted! Feedback is now revealed." if both_revealed else "Review submitted successfully and kept private until mutual review or 48 hours.",
            "is_revealed": both_revealed,
            "rating": MeetingRatingSerializer(rating, context={'request': request, 'meeting': meeting}).data,
            "meeting": MeetingSerializer(meeting, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)



