from datetime import datetime, timedelta
from django.db.models import Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from matching.models import MatchRequest
from .models import Meeting
from .serializers import MeetingSerializer
from .video_service import DailyVideoService


def create_meeting_for_match_request(match_request):
    """
    Creates a Meeting instance for the given MatchRequest by calculating start/end
    time from the attached selected_slot and provisioning a Daily room.
    Returns (meeting, None) on success, or (None, (error_dict, status_code)) on failure.
    """
    if hasattr(match_request, 'meeting'):
        return match_request.meeting, None

    slot = getattr(match_request, 'selected_slot', None)
    if not slot:
        return None, ({"error": "The match request does not have an availability slot attached."}, status.HTTP_400_BAD_REQUEST)

    # Calculate next occurrence of this slot on backend
    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
    }
    now = timezone.now()
    target_weekday = day_map.get(slot.day.lower(), 0)
    days_ahead = (target_weekday - now.weekday() + 7) % 7
    target_date = now.date() + timedelta(days=days_ahead)
    start_time = timezone.make_aware(datetime.combine(target_date, slot.start_time))
    end_time = timezone.make_aware(datetime.combine(target_date, slot.end_time))

    if start_time <= now:
        start_time += timedelta(days=7)
        end_time += timedelta(days=7)

    start_ts = int(start_time.timestamp())
    end_ts = int(end_time.timestamp())
    service = DailyVideoService()

    try:
        room_data = service.create_scheduled_room(start_ts, end_ts)
        token_sender = service.create_scheduled_token(room_data['name'], match_request.sender.username, start_ts, end_ts)
        token_receiver = service.create_scheduled_token(room_data['name'], match_request.receiver.username, start_ts, end_ts)
    except Exception as e:
        return None, ({"error": f"Video service error: {str(e)}"}, status.HTTP_503_SERVICE_UNAVAILABLE)

    meeting = Meeting.objects.create(
        request=match_request,
        start_time=start_time,
        end_time=end_time,
        status="SCHEDULED",
        room_url=room_data['url'],
        room_name=room_data['name'],
        token_sender=token_sender,
        token_receiver=token_receiver,
    )

    match_request.status = "ACCEPTED"
    match_request.save(update_fields=['status'])

    return meeting, None


class MeetingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_param = request.query_params.get('status')
        meetings = Meeting.objects.filter(
            Q(request__sender=request.user) | Q(request__receiver=request.user)
        ).select_related('request__sender', 'request__receiver', 'request__skill')

        if status_param:
            if status_param.lower() in ['accepted', 'scheduled']:
                meetings = meetings.filter(status='SCHEDULED')
            else:
                meetings = meetings.filter(status__iexact=status_param)

        meetings = meetings.order_by('start_time')
        serializer = MeetingSerializer(meetings, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        request_id = request.data.get('request_id')
        if not request_id:
            return Response({"error": "request_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            match_request = MatchRequest.objects.select_related('sender', 'receiver', 'selected_slot').get(pk=request_id)
        except MatchRequest.DoesNotExist:
            return Response({"error": "Match request not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in (match_request.sender, match_request.receiver):
            return Response({"error": "You do not have permission to schedule this meeting."}, status=status.HTTP_403_FORBIDDEN)

        meeting, err = create_meeting_for_match_request(match_request)
        if err:
            err_data, err_status = err
            return Response(err_data, status=err_status)

        return Response(MeetingSerializer(meeting, context={'request': request}).data, status=status.HTTP_201_CREATED)


class SingleMeetingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            meeting = Meeting.objects.select_related(
                'request__sender', 'request__receiver', 'request__skill'
            ).get(pk=pk)
        except Meeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in (meeting.request.sender, meeting.request.receiver):
            return Response({"error": "You do not have permission to access this meeting."}, status=status.HTTP_403_FORBIDDEN)

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
