from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from skillmatch.models import UserSkill
from .serializers import MatchSerializer
from .models import MatchRequest
from .serializers import MatchRequestSerializer

def unique_skill_names(skill_names):
    return sorted({skill_name for skill_name in skill_names if skill_name})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def find_matches(request):
    current_user = request.user

    teach = set(
        UserSkill.objects.filter(
            user=current_user,
            skill_type="teach"
        ).values_list("skill_id", flat=True)
    )

    learn = set(
        UserSkill.objects.filter(
            user=current_user,
            skill_type="learn"
        ).values_list("skill_id", flat=True)
    )

    matches = []

    result_users = (
        UserSkill.objects
        .exclude(user=current_user)
        .values_list("user", flat=True)
        .distinct()
    )

    for user_id in result_users:

        their_teach = set(
            UserSkill.objects.filter(
                user_id=user_id,
                skill_type="teach"
            ).values_list("skill_id", flat=True)
        )

        their_learn = set(
            UserSkill.objects.filter(
                user_id=user_id,
                skill_type="learn"
            ).values_list("skill_id", flat=True)
        )

        teach_me = learn & their_teach
        teach_them = teach & their_learn

        if teach_me and teach_them:
            matches.append({
                "user_id": user_id,
                "username": UserSkill.objects
                    .filter(user_id=user_id)
                    .first()
                    .user.username,
                "teach_me": unique_skill_names(
                    UserSkill.objects
                    .filter(user_id=user_id, skill_id__in=teach_me)
                    .values_list("skill__name", flat=True)
                    .distinct()
                ),
                "teach_them": unique_skill_names(
                    UserSkill.objects
                    .filter(user_id=user_id, skill_id__in=teach_them)
                    .values_list("skill__name", flat=True)
                    .distinct()
                ),
            })

    return Response(MatchSerializer(matches, many=True).data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_request(request):
    serializer = MatchRequestSerializer(
        data=request.data,
        context={"request": request}
    )

    if serializer.is_valid():
        match_request = serializer.save(sender=request.user)
        return Response(
            MatchRequestSerializer(match_request).data,
            status=status.HTTP_201_CREATED
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_requests(request):

    requests = MatchRequest.objects.filter(
        receiver=request.user
    )

    serializer = MatchRequestSerializer(requests, many=True)

    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_to_request(request, pk):
    try:
        match_request = MatchRequest.objects.select_related(
            "sender", "receiver", "selected_slot"
        ).get(pk=pk)
    except MatchRequest.DoesNotExist:
        return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.user != match_request.receiver:
        return Response({"error": "Only the receiver can respond to this request."}, status=status.HTTP_403_FORBIDDEN)

    raw_action = request.data.get("action") if request.data else None
    action = str(raw_action).lower() if raw_action else "reject"

    if action in ["accept", "accepted"]:
        from meetings.views import create_meeting_for_match_request
        user_timezone   = request.data.get("timezone") if request.data else None
        meeting, err = create_meeting_for_match_request(match_request, user_timezone=user_timezone)
        if err:
            err_data, err_status = err
            return Response(err_data, status=err_status)
        return Response({
            "message": "Request accepted and meeting scheduled.",
            "status": "ACCEPTED",
            "meeting_id": meeting.id,
        }, status=status.HTTP_200_OK)

    if action in ["reject", "decline"]:
        match_request.status = "REJECTED"
        match_request.save(update_fields=["status"])
        return Response({"message": "Request declined.", "status": "REJECTED"}, status=status.HTTP_200_OK)

    return Response({"error": f"Invalid action '{raw_action}'."}, status=status.HTTP_400_BAD_REQUEST)
