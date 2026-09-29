from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils.dateparse import parse_time
from skillmatch.models import Skill, UserSkill, AvailabilitySlot
from .models import MatchRequest
from .serializers import MatchRequestSerializer, MatchSerializer


def approved_user_skills():
    """UserSkills whose catalog skill has been approved by an admin."""
    return UserSkill.objects.filter(skill__is_approved=True)


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


# =========================================================
# FIND MATCHES
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def find_matches(request):
    current_user = request.user

    teach = set(
        approved_user_skills().filter(
            user=current_user,
            skill_type="teach"
        ).values_list(
            "skill_id",
            flat=True
        )
    )

    learn = set(
        approved_user_skills().filter(
            user=current_user,
            skill_type="learn"
        ).values_list(
            "skill_id",
            flat=True
        )
    )

    matches = []

    result_users = (
        approved_user_skills()
        .exclude(user=current_user)
        .values_list(
            "user",
            flat=True
        )
        .distinct()
    )

    for user_id in result_users:

        their_teach = set(
            approved_user_skills().filter(
                user_id=user_id,
                skill_type="teach"
            ).values_list(
                "skill_id",
                flat=True
            )
        )

        their_learn = set(
            approved_user_skills().filter(
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
                approved_user_skills()
                .filter(user_id=user_id)
                .select_related("user__profile")
                .first()
            )

            if not first_user_skill:
                continue

            matched_user = first_user_skill.user
            profile = getattr(matched_user, "profile", None)

            matches.append({
                "user_id": user_id,
                "username": matched_user.username,
                # Skills they teach you — use their verification status
                "teach_me": skill_verification_payload(
                    approved_user_skills().filter(
                        user_id=user_id,
                        skill_type="teach",
                        skill_id__in=teach_me,
                    )
                ),
                # Skills you teach them — use your verification status
                "teach_them": skill_verification_payload(
                    approved_user_skills().filter(
                        user=current_user,
                        skill_type="teach",
                        skill_id__in=teach_them,
                    )
                ),
                "teach_me_ids": sorted(teach_me),
                "teach_them_ids": sorted(teach_them),
                "rating_average": profile.rating_average if profile else 0.0,
                "rating_count": profile.rating_count if profile else 0,
            })

    return Response(MatchSerializer(matches, many=True).data)


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
            "receiver_skill",
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
            "receiver_selected_slot",
            "skill",
            "receiver_skill",
        ),
        pk=pk,
        receiver=request.user,
    )

    action = str(request.data.get("action", "")).strip().lower()

    if action == "reject":
        if match_req.status != "PENDING":
            return Response(
                {"error": "This request has already been processed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rejection_reason = str(
            request.data.get("rejection_reason", "")
        ).strip()

        if not rejection_reason:
            return Response(
                {"error": "A rejection reason is required."},
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
        if match_req.status != "PENDING":
            return Response(
                {"error": "This request has already been processed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        receiver_skill_id = request.data.get("receiver_skill")

        schedule_mode = str(
            request.data.get("schedule_mode", "later")
        ).strip().lower()

        receiver_skill = None

        if receiver_skill_id not in (None, ""):
            try:
                receiver_skill = Skill.objects.get(
                    pk=receiver_skill_id,
                    is_approved=True,
                )
            except (Skill.DoesNotExist, ValueError, TypeError):
                return Response(
                    {"error": "Selected skill is invalid."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            sender_teaches_skill = UserSkill.objects.filter(
                user=match_req.sender,
                skill=receiver_skill,
                skill_type="teach",
            ).exists()

            if not sender_teaches_skill:
                return Response(
                    {
                        "error": "The requester does not teach the selected return skill."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            receiver_wants_skill = UserSkill.objects.filter(
                user=match_req.receiver,
                skill=receiver_skill,
                skill_type="learn",
            ).exists()

            if not receiver_wants_skill:
                return Response(
                    {
                        "error": "The selected return skill is not in your learning list."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if receiver_skill and schedule_mode not in ("now", "later"):
            return Response(
                {"error": "Schedule mode must be now or later."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        receiver_slot = None
        receiver_start_time = None
        receiver_end_time = None

        if receiver_skill and schedule_mode == "now":
            receiver_slot_id = request.data.get(
                "receiver_selected_slot"
            )

            if not receiver_slot_id:
                return Response(
                    {"error": "Please select an available time slot."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                receiver_slot = AvailabilitySlot.objects.get(
                    pk=receiver_slot_id,
                    user=match_req.sender,
                )
            except (
                AvailabilitySlot.DoesNotExist,
                ValueError,
                TypeError,
            ):
                return Response(
                    {
                        "error": "The selected slot does not belong to the requester."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            start_value = request.data.get(
                "receiver_requested_start_time"
            )

            end_value = request.data.get(
                "receiver_requested_end_time"
            )

            if bool(start_value) != bool(end_value):
                return Response(
                    {
                        "error": "Both start time and end time must be provided."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if start_value and end_value:
                receiver_start_time = parse_time(
                    str(start_value)
                )

                receiver_end_time = parse_time(
                    str(end_value)
                )

                if not receiver_start_time or not receiver_end_time:
                    return Response(
                        {"error": "Invalid meeting time."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        from meetings.views import create_meeting_for_match_request

        user_timezone = request.data.get("timezone")

        first_meeting, err = create_meeting_for_match_request(
            match_req,
            user_timezone=user_timezone,
            session_type="REQUESTED_SKILL",
        )

        if err:
            err_data, err_status = err
            return Response(
                err_data,
                status=err_status,
            )

        match_req.receiver_skill = receiver_skill
        match_req.rejection_reason = None

        if receiver_skill is None:
            match_req.status = "ACCEPTED"

            match_req.save(
                update_fields=[
                    "receiver_skill",
                    "status",
                    "rejection_reason",
                ]
            )

            return Response(
                {
                    "message": "Request accepted successfully.",
                    "status": "ACCEPTED",
                    "meeting_id": first_meeting.id,
                    "room_url": first_meeting.room_url,
                    "receiver_skill": None,
                    "receiver_skill_name": None,
                },
                status=status.HTTP_200_OK,
            )

        if schedule_mode == "later":
            match_req.status = "SCHEDULING"

            match_req.save(
                update_fields=[
                    "receiver_skill",
                    "status",
                    "rejection_reason",
                ]
            )

            return Response(
                {
                    "message": "Request accepted. Choose a time for your return session later.",
                    "status": "SCHEDULING",
                    "meeting_id": first_meeting.id,
                    "room_url": first_meeting.room_url,
                    "receiver_skill": receiver_skill.id,
                    "receiver_skill_name": receiver_skill.name,
                },
                status=status.HTTP_200_OK,
            )

        match_req.receiver_selected_slot = receiver_slot
        match_req.receiver_requested_start_time = receiver_start_time
        match_req.receiver_requested_end_time = receiver_end_time
        match_req.status = "SCHEDULING"

        match_req.save(
            update_fields=[
                "receiver_skill",
                "receiver_selected_slot",
                "receiver_requested_start_time",
                "receiver_requested_end_time",
                "status",
                "rejection_reason",
            ]
        )

        return_meeting, return_err = create_meeting_for_match_request(
            match_req,
            user_timezone=user_timezone,
            session_type="RETURN_SKILL",
        )

        if return_err:
            err_data, _ = return_err

            return Response(
                {
                    "message": "The request was accepted, but the return session could not be scheduled.",
                    "status": "SCHEDULING",
                    "meeting_id": first_meeting.id,
                    "receiver_skill": receiver_skill.id,
                    "receiver_skill_name": receiver_skill.name,
                    "return_meeting_error": err_data.get(
                        "error",
                        "Could not schedule return session.",
                    ),
                },
                status=status.HTTP_200_OK,
            )

        match_req.status = "ACCEPTED"
        match_req.save(update_fields=["status"])

        return Response(
            {
                "message": "Swap accepted and both sessions scheduled successfully.",
                "status": "ACCEPTED",
                "meeting_id": first_meeting.id,
                "return_meeting_id": return_meeting.id,
                "receiver_skill": receiver_skill.id,
                "receiver_skill_name": receiver_skill.name,
            },
            status=status.HTTP_200_OK,
        )

    if action == "schedule_return":
        if match_req.status != "SCHEDULING":
            return Response(
                {
                    "error": "This request is not waiting for return-session scheduling."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not match_req.receiver_skill:
            return Response(
                {"error": "No return skill was selected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        receiver_slot_id = request.data.get(
            "receiver_selected_slot"
        )

        if not receiver_slot_id:
            return Response(
                {"error": "Please select an available time slot."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            receiver_slot = AvailabilitySlot.objects.get(
                pk=receiver_slot_id,
                user=match_req.sender,
            )
        except (
            AvailabilitySlot.DoesNotExist,
            ValueError,
            TypeError,
        ):
            return Response(
                {
                    "error": "The selected slot does not belong to the requester."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_value = request.data.get(
            "receiver_requested_start_time"
        )

        end_value = request.data.get(
            "receiver_requested_end_time"
        )

        if bool(start_value) != bool(end_value):
            return Response(
                {
                    "error": "Both start time and end time must be provided."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        receiver_start_time = None
        receiver_end_time = None

        if start_value and end_value:
            receiver_start_time = parse_time(
                str(start_value)
            )

            receiver_end_time = parse_time(
                str(end_value)
            )

            if not receiver_start_time or not receiver_end_time:
                return Response(
                    {"error": "Invalid meeting time."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        match_req.receiver_selected_slot = receiver_slot
        match_req.receiver_requested_start_time = receiver_start_time
        match_req.receiver_requested_end_time = receiver_end_time

        match_req.save(
            update_fields=[
                "receiver_selected_slot",
                "receiver_requested_start_time",
                "receiver_requested_end_time",
            ]
        )

        from meetings.views import create_meeting_for_match_request

        user_timezone = request.data.get("timezone")

        return_meeting, err = create_meeting_for_match_request(
            match_req,
            user_timezone=user_timezone,
            session_type="RETURN_SKILL",
        )

        if err:
            err_data, err_status = err
            return Response(
                err_data,
                status=err_status,
            )

        match_req.status = "ACCEPTED"
        match_req.save(update_fields=["status"])

        return Response(
            {
                "message": "Return session scheduled successfully.",
                "status": "ACCEPTED",
                "return_meeting_id": return_meeting.id,
                "receiver_skill": match_req.receiver_skill.id,
                "receiver_skill_name": match_req.receiver_skill.name,
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {"error": "Invalid action."},
        status=status.HTTP_400_BAD_REQUEST,
    )


# =========================================================
# GET SENT REQUESTS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_sent_requests(request):

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
            "receiver_skill",
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
# GET TEACHERS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_teachers(request):
    user = request.user

    my_learning_skills = approved_user_skills().filter(
        user=user,
        skill_type="learn"
    ).select_related("skill")

    learning_skill_ids = [
        user_skill.skill_id
        for user_skill in my_learning_skills
    ]

    skill_id = request.query_params.get("skill")

    teaching_skills = approved_user_skills().filter(
        skill_type="teach",
        skill_id__in=learning_skill_ids
    ).select_related("user__profile", "skill")

    if skill_id:
        teaching_skills = teaching_skills.filter(
            skill_id=skill_id
        )

    teachers = {}

    for user_skill in teaching_skills:
        teacher = user_skill.user

        if teacher.id == user.id:
            continue

        if teacher.id not in teachers:
            profile = getattr(teacher, "profile", None)
            teachers[teacher.id] = {
                "user_id": teacher.id,
                "username": teacher.username,
                "rating_average": profile.rating_average if profile else 0.0,
                "rating_count": profile.rating_count if profile else 0,
                "skills": []
            }

        teachers[teacher.id]["skills"].append({
            "id": user_skill.skill.id,
            "name": user_skill.skill.name,
            "is_verified": user_skill.is_verified,
        })

    return Response({
        "learning_skills": [
            {
                "id": user_skill.skill.id,
                "name": user_skill.skill.name
            }
            for user_skill in my_learning_skills
        ],
        "teachers": list(teachers.values())
    })
