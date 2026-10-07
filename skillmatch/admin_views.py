"""Staff-only endpoints for the admin panel: overview stats and user management."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from matching.models import MatchRequest
from meetings.models import Meeting, MeetingRating

from .models import Skill, SkillQuizAttempt, UserSkill


USERS_PAGE_SIZE = 20


def display_name(user):
    return user.get_full_name() or user.username


def counts_by(queryset, field):
    return {
        row[field]: row["total"]
        for row in queryset.values(field).annotate(total=Count("id"))
    }


def user_meetings(user):
    return Meeting.objects.filter(
        Q(request__sender=user) | Q(request__receiver=user)
    )


def user_row(user):
    profile = getattr(user, "profile", None)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.get_full_name(),
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        "onboarding_completed": bool(profile and profile.onboarding_completed),
        "rating_average": profile.rating_average if profile else 0,
        "rating_count": profile.rating_count if profile else 0,
        "teach_count": user.teach_count,
        "learn_count": user.learn_count,
        "verified_count": user.verified_count,
    }


def annotated_users():
    return (
        User.objects
        .select_related("profile")
        .annotate(
            teach_count=Count(
                "user_skills",
                filter=Q(user_skills__skill_type="teach"),
                distinct=True,
            ),
            learn_count=Count(
                "user_skills",
                filter=Q(user_skills__skill_type="learn"),
                distinct=True,
            ),
            verified_count=Count(
                "user_skills",
                filter=Q(user_skills__is_verified=True),
                distinct=True,
            ),
        )
    )


class AdminOverviewView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        week_ago = timezone.now() - timedelta(days=7)
        users = User.objects.all()
        attempts = SkillQuizAttempt.objects.filter(created_at__gte=week_ago)
        attempt_total = attempts.count()

        recent_users = User.objects.order_by("-date_joined")[:6]

        return Response({
            "users": {
                "total": users.count(),
                "active": users.filter(is_active=True).count(),
                "staff": users.filter(is_staff=True).count(),
                "new_this_week": users.filter(date_joined__gte=week_ago).count(),
            },
            "skills": {
                "approved": Skill.objects.filter(is_approved=True).count(),
                "pending": Skill.objects.filter(is_approved=False).count(),
                "verified_teachers": UserSkill.objects.filter(is_verified=True).count(),
            },
            "requests": counts_by(MatchRequest.objects.all(), "status"),
            "meetings": counts_by(Meeting.objects.all(), "status"),
            "quizzes_this_week": {
                "attempts": attempt_total,
                "passed": attempts.filter(passed=True).count(),
            },
            "recent_users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "name": display_name(user),
                    "date_joined": user.date_joined,
                    "is_staff": user.is_staff,
                }
                for user in recent_users
            ],
        })


class AdminUserListView(APIView):
    """GET ?search=&role=staff|member&status=active|inactive&page=1"""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        params = request.query_params
        users = annotated_users()

        search = params.get("search", "").strip()
        if search:
            users = users.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        role = params.get("role")
        if role == "staff":
            users = users.filter(is_staff=True)
        elif role == "member":
            users = users.filter(is_staff=False)

        account_status = params.get("status")
        if account_status == "active":
            users = users.filter(is_active=True)
        elif account_status == "inactive":
            users = users.filter(is_active=False)

        users = users.order_by("-date_joined", "-id")
        total = users.count()

        try:
            page = max(int(params.get("page", 1)), 1)
        except ValueError:
            page = 1
        start = (page - 1) * USERS_PAGE_SIZE

        return Response({
            "count": total,
            "page": page,
            "page_size": USERS_PAGE_SIZE,
            "results": [user_row(u) for u in users[start:start + USERS_PAGE_SIZE]],
        })


class AdminUserDetailView(APIView):
    """GET full user details; PATCH is_active / is_staff."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk):
        user = get_object_or_404(annotated_users(), pk=pk)
        return Response(self.payload(user))

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        if user == request.user:
            return Response(
                {"error": "You can't change your own account status or role."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.is_superuser and not request.user.is_superuser:
            return Response(
                {"error": "Only a superuser can change another superuser."},
                status=status.HTTP_403_FORBIDDEN,
            )

        changed = []
        for field in ("is_active", "is_staff"):
            if field in request.data:
                value = request.data[field]
                if not isinstance(value, bool):
                    return Response(
                        {"error": f"{field} must be true or false."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(user, field, value)
                changed.append(field)

        if changed:
            user.save(update_fields=changed)

        return Response(self.payload(annotated_users().get(pk=pk)))

    def payload(self, user):
        profile = getattr(user, "profile", None)
        meetings = (
            user_meetings(user)
            .select_related("request__sender", "request__receiver", "request__skill")
            .order_by("-start_time")
        )

        return {
            **user_row(user),
            "bio": profile.bio if profile else "",
            "skills": [
                {
                    "id": us.id,
                    "skill_id": us.skill_id,
                    "name": us.skill.name,
                    "type": us.skill_type,
                    "is_verified": us.is_verified,
                }
                for us in user.user_skills.select_related("skill").order_by("skill_type", "skill__name")
            ],
            "stats": {
                "requests_sent": MatchRequest.objects.filter(sender=user).count(),
                "requests_received": MatchRequest.objects.filter(receiver=user).count(),
                "meetings": counts_by(meetings, "status"),
                "quiz_attempts": user.quiz_attempts.count(),
            },
            "quiz_attempts": [
                {
                    "id": a.id,
                    "skill": a.skill.name,
                    "score": a.score,
                    "passed": a.passed,
                    "abandoned": a.abandoned,
                    "created_at": a.created_at,
                }
                for a in user.quiz_attempts.select_related("skill")[:10]
            ],
            "meetings": [
                {
                    "id": m.id,
                    "partner": display_name(
                        m.request.receiver if m.request.sender_id == user.id else m.request.sender
                    ),
                    "skill": m.request.skill.name,
                    "start_time": m.start_time,
                    "status": m.status,
                }
                for m in meetings[:10]
            ],
            "reviews": [
                {
                    "id": r.id,
                    "reviewer": display_name(r.reviewer),
                    "score": r.score,
                    "feedback": r.feedback,
                    "created_at": r.created_at,
                }
                for r in (
                    MeetingRating.objects
                    .filter(reviewed_user=user, is_revealed=True)
                    .select_related("reviewer")
                    .order_by("-created_at")[:10]
                )
            ],
        }
