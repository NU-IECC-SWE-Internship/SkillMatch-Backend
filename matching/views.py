from django.shortcuts import get_object_or_404

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

        teach_me = (
            learn
            & their_teach
        )

        teach_them = (
            teach
            & their_learn
        )

        if teach_me and teach_them:

            first_user_skill = (
                UserSkill.objects
                .filter(
                    user_id=user_id
                )
                .select_related(
                    "user__profile"
                )
                .first()
            )

            if not first_user_skill:
                continue

            matched_user = (
                first_user_skill.user
            )

            profile = getattr(
                matched_user,
                "profile",
                None
            )

            matches.append(
                {
                    "user_id":
                        user_id,

                    "username":
                        matched_user.username,

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

                    "rating_average":
                        (
                            profile.rating_average
                            if profile
                            else 0.0
                        ),

                    "rating_count":
                        (
                            profile.rating_count
                            if profile
                            else 0
                        ),
                }
            )

    return Response(
        MatchSerializer(
            matches,
            many=True
        ).data
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

    # Keep rating-expiration handling from main
    from meetings.views import process_expired_ratings

    process_expired_ratings()

    requests = (
        MatchRequest.objects
        .filter(
            receiver=request.user
        )
        .select_related(
            "sender__profile",
            "receiver__profile",
            "skill",
            "selected_slot",
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

    match_req = get_object_or_404(
        MatchRequest.objects.select_related(
            "sender",
            "receiver",
            "selected_slot",
            "skill",
        ),
        pk=pk,
        receiver=request.user,
    )

    # Prevent handling the same request more than once
    if match_req.status != "PENDING":
        return Response(
            {
                "error":
                    "This request has already been processed."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    action = str(
        request.data.get(
            "action",
            ""
        )
    ).strip().lower()

    # =====================================================
    # REJECT
    # =====================================================

    if action == "reject":

        rejection_reason = str(
            request.data.get(
                "rejection_reason",
                ""
            )
        ).strip()

        if not rejection_reason:
            return Response(
                {
                    "error":
                        "A rejection reason is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        match_req.status = "REJECTED"

        match_req.rejection_reason = (
            rejection_reason
        )

        match_req.save(
            update_fields=[
                "status",
                "rejection_reason",
            ]
        )

        return Response(
            {
                "message":
                    "Request rejected.",

                "status":
                    "REJECTED",

                "rejection_reason":
                    rejection_reason,
            },
            status=status.HTTP_200_OK,
        )

    # =====================================================
    # ACCEPT
    # =====================================================

    if action == "accept":

        # Do not mark it accepted until meeting creation succeeds
        from meetings.views import (
            create_meeting_for_match_request
        )

        user_timezone = (
            request.data.get(
                "timezone"
            )
            if request.data
            else None
        )

        meeting, err = (
            create_meeting_for_match_request(
                match_req,
                user_timezone=user_timezone,
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
                    "Request accepted and meeting scheduled successfully.",

                "status":
                    "ACCEPTED",

                "meeting_id":
                    meeting.id,

                "room_url":
                    meeting.room_url,
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {
            "error":
                "Invalid action."
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


# =========================================================
# GET SENT REQUESTS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_sent_requests(request):

    # Keep rating-expiration handling from main
    from meetings.views import process_expired_ratings

    process_expired_ratings()

    requests = (
        MatchRequest.objects
        .filter(
            sender=request.user
        )
        .select_related(
            "sender__profile",
            "receiver__profile",
            "skill",
            "selected_slot",
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