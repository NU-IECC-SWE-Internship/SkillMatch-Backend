from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import SkillSwapMeeting
from .serializers import (
    MeetingDetailSerializer,
)
from .video_service import DailyVideoService


class MeetingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_param = request.query_params.get('status')
        meetings = SkillSwapMeeting.objects.filter(
            Q(participant_a=request.user) | Q(participant_b=request.user)
        )
        if status_param:
            meetings = meetings.filter(status=status_param)

        meetings = meetings.order_by('start_time')
        serializer = MeetingDetailSerializer(meetings, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request): #write post method for creating pending meeting.
        pass

class SingleMeetingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            meeting = SkillSwapMeeting.objects.get(pk=pk)
        except SkillSwapMeeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        if meeting.participant_a != request.user and meeting.participant_b != request.user:
            return Response(
                {"error": "You do not have permission to view this meeting."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = MeetingDetailSerializer(meeting, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        return self.patch(request, pk)

    def patch(self, request, pk):
        try:
            meeting = SkillSwapMeeting.objects.get(pk=pk)
        except SkillSwapMeeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        if meeting.participant_a != request.user and meeting.participant_b != request.user:
            return Response(
                {"error": "You do not have permission to modify this meeting."},
                status=status.HTTP_403_FORBIDDEN
            )

        new_status = request.data.get('status')
        valid_statuses = [
            SkillSwapMeeting.STATUS_ACCEPTED,
            SkillSwapMeeting.STATUS_REJECTED,
            SkillSwapMeeting.STATUS_CANCELLED,
        ]
        if new_status not in valid_statuses:
            return Response(
                {"error": f"Invalid status '{new_status}'. Allowed values: {valid_statuses}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status == SkillSwapMeeting.STATUS_ACCEPTED:
            if request.user != meeting.participant_b:
                return Response(
                    {"error": "Only the invited partner (User B) can accept this meeting request."},
                    status=status.HTTP_403_FORBIDDEN
                )

            if meeting.status != SkillSwapMeeting.STATUS_PENDING:
                return Response(
                    {"error": f"Cannot accept a meeting with status '{meeting.status}'. Only 'pending' requests can be accepted."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            overlapping_meetings = SkillSwapMeeting.objects.filter(
                Q(participant_a=meeting.participant_b) | Q(participant_b=meeting.participant_b),
                status=SkillSwapMeeting.STATUS_ACCEPTED,
                start_time__lt=meeting.end_time,
                end_time__gt=meeting.start_time
            ).exclude(pk=meeting.pk)

            if overlapping_meetings.exists():
                conflicting = overlapping_meetings.first()
                return Response(
                    {
                        "error": "You already have another accepted meeting overlapping with this time window.",
                        "conflicting_meeting_id": conflicting.id,
                        "conflicting_start": conflicting.start_time.isoformat(),
                        "conflicting_end": conflicting.end_time.isoformat(),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            start_ts = int(meeting.start_time.timestamp())
            end_ts = int(meeting.end_time.timestamp())

            service = DailyVideoService()
            try:
                room_data = service.create_scheduled_room(start_ts, end_ts)
                room_name = room_data['name']

                token_a = service.create_scheduled_token(
                    room_name, meeting.participant_a.username, start_ts, end_ts
                )
                token_b = service.create_scheduled_token(
                    room_name, meeting.participant_b.username, start_ts, end_ts
                )
            except Exception as e:
                return Response(
                    {"error": f"Video service error: {str(e)}"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            meeting.room_url = room_data['url']
            meeting.token_a = token_a
            meeting.token_b = token_b
            meeting.status = SkillSwapMeeting.STATUS_ACCEPTED
            meeting.save()

        elif new_status == SkillSwapMeeting.STATUS_REJECTED:
            if request.user != meeting.participant_b:
                return Response(
                    {"error": "Only the invited partner (User B) can reject this meeting request."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if meeting.status != SkillSwapMeeting.STATUS_PENDING:
                return Response(
                    {"error": f"Cannot reject a meeting with status '{meeting.status}'."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            meeting.status = SkillSwapMeeting.STATUS_REJECTED
            meeting.save()

        elif new_status == SkillSwapMeeting.STATUS_CANCELLED:
            if request.user != meeting.participant_a:
                return Response(
                    {"error": "Only the meeting requester can cancel this meeting."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if meeting.status not in [SkillSwapMeeting.STATUS_PENDING, SkillSwapMeeting.STATUS_ACCEPTED]:
                return Response(
                    {"error": f"Cannot cancel a meeting with status '{meeting.status}'."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            meeting.status = SkillSwapMeeting.STATUS_CANCELLED
            meeting.save()

        output_serializer = MeetingDetailSerializer(meeting, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk): #write delete method for deleting meeting.
        pass