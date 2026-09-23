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
def respond_to_request(request, request_id):
    try:
        match_request = MatchRequest.objects.get(
            id=request_id,
            receiver=request.user
        )
    except MatchRequest.DoesNotExist:
        return Response(
            {
                "detail": "Request not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    if match_request.status != "PENDING":
        return Response(
            {
                "detail": "This request has already been processed."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    action = request.data.get("action")

    if action == "accept":
        match_request.status = "ACCEPTED"

    elif action == "reject":
        match_request.status = "REJECTED"

    else:
        return Response(
            {
                "detail": "Action must be 'accept' or 'reject'."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    match_request.save(
        update_fields=["status"]
    )

    return Response(
        {
            "message": (
                "Request accepted successfully."
                if action == "accept"
                else "Request rejected successfully."
            ),
            "status": match_request.status,
        },
        status=status.HTTP_200_OK
    )