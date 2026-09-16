import datetime
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import SkillSwapMeeting
from .serializers import (
    MeetingDetailSerializer,
    ScheduleMeetingInputSerializer,
    UserOptionSerializer
)
from .video_service import DailyVideoService


class MeetingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Only return meetings where the logged-in user is a participant
        meetings = SkillSwapMeeting.objects.filter(
            Q(participant_a=request.user) | Q(participant_b=request.user)
        ).order_by('start_time')
        serializer = MeetingDetailSerializer(meetings, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        input_serializer = ScheduleMeetingInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        participant_a = request.user

        if data['user_b_id'] == participant_a.id:
            return Response(
                {"error": "You cannot schedule a swap meeting with yourself."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            participant_b = User.objects.get(id=data['user_b_id'])
        except User.DoesNotExist:
            return Response({"error": "Partner user was not found."}, status=status.HTTP_404_NOT_FOUND)

        start_time = data['start_iso']
        end_time = start_time + datetime.timedelta(minutes=data['duration_minutes'])

        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())

        service = DailyVideoService()
        try:
            room_data = service.create_scheduled_room(start_ts, end_ts)
            room_name = room_data['name']

            token_a = service.create_scheduled_token(room_name, participant_a.username, start_ts, end_ts)
            token_b = service.create_scheduled_token(room_name, participant_b.username, start_ts, end_ts)
        except Exception as e:
            return Response(
                {"error": f"Video service error: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        meeting = SkillSwapMeeting.objects.create(
            participant_a=participant_a,
            participant_b=participant_b,
            start_time=start_time,
            end_time=end_time,
            room_url=room_data['url'],
            token_a=token_a,
            token_b=token_b
        )

        output_serializer = MeetingDetailSerializer(meeting, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class SingleMeetingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            meeting = SkillSwapMeeting.objects.get(pk=pk)
        except SkillSwapMeeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        # Ensure requesting user is a participant
        if meeting.participant_a != request.user and meeting.participant_b != request.user:
            return Response({"error": "You do not have permission to view this meeting."}, status=status.HTTP_403_FORBIDDEN)

        serializer = MeetingDetailSerializer(meeting, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AvailablePartnersView(APIView):
    """Returns users available to schedule a meeting with (excluding the current user)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        partners = User.objects.exclude(id=request.user.id).order_by('username')
        serializer = UserOptionSerializer(partners, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)