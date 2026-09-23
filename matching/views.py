from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from skillmatch.models import UserSkill
from .serializers import MatchSerializer
from .models import MatchRequest
from .serializers import MatchRequestSerializer

def skill_verification_payload(queryset):
    """Unique {name, is_verified} entries, preferring verified when duplicates exist."""
    by_name = {}
    for row in queryset.values("skill__name", "is_verified"):
        name = row["skill__name"]
        if not name:
            continue
        existing = by_name.get(name)
        if existing is None or (row["is_verified"] and not existing["is_verified"]):
            by_name[name] = {
                "name": name,
                "is_verified": bool(row["is_verified"]),
            }
    return sorted(by_name.values(), key=lambda item: item["name"].lower())


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
            matched_user = UserSkill.objects.filter(user_id=user_id).select_related('user__profile').first().user
            profile = getattr(matched_user, 'profile', None)
            matches.append({
                "user_id": user_id,
                "username": matched_user.username,
                # Skills they teach you — use their verification status
                "teach_me": skill_verification_payload(
                    UserSkill.objects.filter(
                        user_id=user_id,
                        skill_type="teach",
                        skill_id__in=teach_me,
                    )
                ),
                # Skills you teach them — use your verification status
                "teach_them": skill_verification_payload(
                    UserSkill.objects.filter(
                        user=current_user,
                        skill_type="teach",
                        skill_id__in=teach_them,
                    )
                ),
                "rating_average": profile.rating_average if profile else 0.0,
                "rating_count": profile.rating_count if profile else 0,
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
    from meetings.views import process_expired_ratings
    process_expired_ratings()

    requests = MatchRequest.objects.filter(
        receiver=request.user
    ).select_related(
        "sender__profile",
        "receiver__profile",
        "skill",
        "selected_slot",
    ).order_by("-id")

    serializer = MatchRequestSerializer(requests, many=True)

    return Response(serializer.data)

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

    if match_req.status != "PENDING":
        return Response(
            {"error": "This request has already been processed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    action = str(
        request.data.get("action", "")
    ).strip().lower()

    if action == "reject":

        rejection_reason = str(
            request.data.get("rejection_reason", "")
        ).strip()

        if not rejection_reason:
            return Response(
                {
                    "error": "A rejection reason is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        match_req.status = "REJECTED"
        match_req.rejection_reason = rejection_reason
        match_req.save(
            update_fields=[
                "status",
                "rejection_reason",
            ]
        )

        return Response(
            {
                "message": "Request rejected.",
                "status": "REJECTED",
                "rejection_reason": rejection_reason,
            },
            status=status.HTTP_200_OK,
        )

    if action == "accept":
        # Do NOT mark ACCEPTED until the meeting is created successfully.
        # Otherwise the UI shows an error while the DB already changed.
        from meetings.views import create_meeting_for_match_request

        user_timezone = request.data.get("timezone") if request.data else None
        meeting, err = create_meeting_for_match_request(
            match_req,
            user_timezone=user_timezone,
        )
        if err:
            err_data, err_status = err
            return Response(err_data, status=err_status)

        return Response(
            {
                "message": "Request accepted and meeting scheduled successfully.",
                "status": "ACCEPTED",
                "meeting_id": meeting.id,
                "room_url": meeting.room_url,
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {
            "error": "Invalid action.",
        },
        status=status.HTTP_400_BAD_REQUEST,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_sent_requests(request):
    from meetings.views import process_expired_ratings
    process_expired_ratings()

    requests = MatchRequest.objects.filter(
        sender=request.user
    ).select_related(
        "sender__profile",
        "receiver__profile",
        "skill",
        "selected_slot",
    ).order_by("-id")

    serializer = MatchRequestSerializer(
        requests,
        many=True
    )

    return Response(serializer.data)
