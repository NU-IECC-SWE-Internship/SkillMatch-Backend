from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from skillmatch.models import UserSkill
from .models import MatchRequest
from .serializers import MatchSerializer, MatchRequestSerializer


def unique_skill_names(skill_names):
    return sorted(
        {
            skill_name
            for skill_name in skill_names
            if skill_name
        }
    )


# =========================================================
# FIND MATCHES
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def find_matches(request):
    current_user = request.user

    teach = set(
        UserSkill.objects.filter(
            user=current_user,
            skill_type="teach"
        ).values_list(
            "skill_id",
            flat=True
        )
    )

    learn = set(
        UserSkill.objects.filter(
            user=current_user,
            skill_type="learn"
        ).values_list(
            "skill_id",
            flat=True
        )
    )

    matches = []

    result_users = (
        UserSkill.objects
        .exclude(user=current_user)
        .values_list(
            "user",
            flat=True
        )
        .distinct()
    )

    for user_id in result_users:

        their_teach = set(
            UserSkill.objects.filter(
                user_id=user_id,
                skill_type="teach"
            ).values_list(
                "skill_id",
                flat=True
            )
        )

        their_learn = set(
            UserSkill.objects.filter(
                user_id=user_id,
                skill_type="learn"
            ).values_list(
                "skill_id",
                flat=True
            )
        )

        teach_me = learn & their_teach
        teach_them = teach & their_learn

        if teach_me and teach_them:

            first_user_skill = (
                UserSkill.objects
                .filter(user_id=user_id)
                .first()
            )

            if not first_user_skill:
                continue

            matches.append(
                {
                    "user_id": user_id,

                    "username":
                        first_user_skill.user.username,

                    "teach_me":
                        unique_skill_names(
                            UserSkill.objects
                            .filter(
                                user_id=user_id,
                                skill_id__in=teach_me
                            )
                            .values_list(
                                "skill__name",
                                flat=True
                            )
                            .distinct()
                        ),

                    "teach_them":
                        unique_skill_names(
                            UserSkill.objects
                            .filter(
                                user_id=user_id,
                                skill_id__in=teach_them
                            )
                            .values_list(
                                "skill__name",
                                flat=True
                            )
                            .distinct()
                        ),
                }
            )

    serializer = MatchSerializer(
        matches,
        many=True
    )

    return Response(
        serializer.data
    )


# =========================================================
# CREATE MATCH REQUEST
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_request(request):

    serializer = MatchRequestSerializer(
        data=request.data,
        context={
            "request": request
        }
    )

    if serializer.is_valid():

        match_request = serializer.save(
            sender=request.user
        )

        return Response(
            MatchRequestSerializer(
                match_request
            ).data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


# =========================================================
# GET INCOMING REQUESTS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_requests(request):

    requests = (
        MatchRequest.objects
        .filter(
            receiver=request.user
        )
        .order_by("-id")
    )

    serializer = MatchRequestSerializer(
        requests,
        many=True
    )

    return Response(
        serializer.data
    )


# =========================================================
# ACCEPT / REJECT REQUEST
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_to_request(request, pk):

    try:
        match_request = (
            MatchRequest.objects
            .select_related(
                "sender",
                "receiver",
                "selected_slot"
            )
            .get(pk=pk)
        )

    except MatchRequest.DoesNotExist:

        return Response(
            {
                "error":
                    "Request not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    # Only the receiver can respond
    if request.user != match_request.receiver:

        return Response(
            {
                "error":
                    "Only the receiver can respond to this request."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    # Prevent responding more than once
    if match_request.status != "PENDING":

        return Response(
            {
                "error":
                    "This request has already been processed."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    raw_action = (
        request.data.get("action")
        if request.data
        else None
    )

    action = (
        str(raw_action).lower()
        if raw_action
        else ""
    )


    # =====================================================
    # ACCEPT REQUEST
    # =====================================================

    if action in [
        "accept",
        "accepted"
    ]:

        from meetings.views import (
            create_meeting_for_match_request
        )

        user_timezone = (
            request.data.get("timezone")
            if request.data
            else None
        )

        meeting, err = (
            create_meeting_for_match_request(
                match_request,
                user_timezone=user_timezone
            )
        )

        if err:

            err_data, err_status = err

            return Response(
                err_data,
                status=err_status
            )

        return Response(
            {
                "message":
                    "Request accepted and meeting scheduled.",

                "status":
                    "ACCEPTED",

                "meeting_id":
                    meeting.id,
            },
            status=status.HTTP_200_OK
        )


    # =====================================================
    # REJECT REQUEST
    # =====================================================

    if action in [
        "reject",
        "decline"
    ]:

        rejection_reason = (
            request.data.get(
                "rejection_reason",
                ""
            )
            if request.data
            else ""
        )

        rejection_reason = (
            str(rejection_reason).strip()
            if rejection_reason
            else ""
        )

        match_request.status = (
            "REJECTED"
        )

        match_request.rejection_reason = (
            rejection_reason
            or None
        )

        match_request.save(
            update_fields=[
                "status",
                "rejection_reason",
            ]
        )

        return Response(
            {
                "message":
                    "Request declined.",

                "status":
                    "REJECTED",

                "rejection_reason":
                    match_request.rejection_reason,
            },
            status=status.HTTP_200_OK
        )


    # =====================================================
    # INVALID ACTION
    # =====================================================

    return Response(
        {
            "error":
                f"Invalid action '{raw_action}'."
        },
        status=status.HTTP_400_BAD_REQUEST
    )