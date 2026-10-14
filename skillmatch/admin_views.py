"""Staff-only endpoints for the admin panel: overview stats and user management."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Min, ProtectedError, Q, Value
from django.db.models.functions import Coalesce, Lower, NullIf, TruncDate, TruncHour, TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from matching.models import MatchRequest
from meetings.models import Meeting, MeetingRating

from .models import Profile, Skill, SkillQuizAttempt, UserSkill
from .quiz_policy import attempts_left, max_attempts, quiz_availability, reset_attempts
from .serializers import AdminSkillSerializer
from .views import admin_skill_queryset


USERS_PAGE_SIZE = 20
SIGNUP_MONTHS = 12
TOP_SKILLS = 6
PERIODS = ("today", "week", "month")
EDITABLE_USER_FIELDS = ("username", "email", "first_name", "last_name")


def display_name(user):
    return user.get_full_name() or user.username


def error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


def period_start(period):
    """Local midnight at the start of today / this week (Monday) / this month; None = all time."""
    if period not in PERIODS:
        return None
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start -= timedelta(days=start.weekday())
    elif period == "month":
        start = start.replace(day=1)
    return start


def next_month(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def since(queryset, field, start):
    return queryset.filter(**{f"{field}__gte": start}) if start else queryset


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
        "first_name": user.first_name,
        "last_name": user.last_name,
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


NOT_ONBOARDED = Q(profile__isnull=True) | Q(profile__onboarding_completed=False)

# "onboarding" = can log in but hasn't finished setting up a profile (admins never onboard).
STATUS_FILTERS = {
    "active": Q(is_active=True) & (Q(is_staff=True) | ~NOT_ONBOARDED),
    "onboarding": Q(is_active=True, is_staff=False) & NOT_ONBOARDED,
    "inactive": Q(is_active=False),
}

ROLE_FILTERS = {
    "staff": Q(is_staff=True),
    "member": Q(is_staff=False),
}

SORT_ORDERS = {
    "newest": ["-date_joined", "-id"],
    "oldest": ["date_joined", "id"],
    "name": [
        Lower(Coalesce(NullIf("first_name", Value("")), "username")),
        Lower("last_name"),
        "id",
    ],
    "last_login": [F("last_login").desc(nulls_last=True), "-id"],
    "rating": ["-profile__rating_average", "-profile__rating_count", "-id"],
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


def superuser_guard(request, user):
    """Only a superuser may change another superuser's account."""
    if user.is_superuser and not request.user.is_superuser and user != request.user:
        return error("Only a superuser can change another superuser.", status.HTTP_403_FORBIDDEN)
    return None


class AdminOverviewView(APIView):
    """GET ?period=today|week|month|all (default week)"""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        period = request.query_params.get("period", "week")
        if period not in PERIODS:
            period = "all"
        start = period_start(period)

        users = User.objects.all()
        attempts = since(SkillQuizAttempt.objects.all(), "created_at", start)
        signups_unit, signups = self.signup_series(period, start)

        recent_users = (
            User.objects
            .select_related("profile")
            .order_by("-date_joined")[:6]
        )

        return Response({
            "period": period,
            "since": start,
            "users": {
                "total": users.count(),
                "active": users.filter(is_active=True).count(),
                "staff": users.filter(is_staff=True).count(),
                "onboarding": users.filter(STATUS_FILTERS["onboarding"]).count(),
            },
            "activity": {
                "new_users": since(users, "date_joined", start).count(),
                "signed_in": since(users.filter(last_login__isnull=False), "last_login", start).count(),
                "skills_added": since(Skill.objects.all(), "created_at", start).count(),
                "meetings_booked": since(Meeting.objects.all(), "created_at", start).count(),
                "meetings_completed": since(
                    Meeting.objects.filter(status="COMPLETED"), "end_time", start
                ).count(),
                "quizzes": {
                    "attempts": attempts.count(),
                    "passed": attempts.filter(passed=True).count(),
                    "failed": attempts.filter(passed=False, abandoned=False).count(),
                    "abandoned": attempts.filter(abandoned=True).count(),
                },
            },
            "signups": signups,
            "signups_unit": signups_unit,
            "skills": {
                "approved": Skill.objects.filter(is_approved=True).count(),
                "pending": Skill.objects.filter(is_approved=False).count(),
                "verified_teachers": UserSkill.objects.filter(is_verified=True).count(),
            },
            "top_skills": self.top_skills(),
            "requests": counts_by(MatchRequest.objects.all(), "status"),
            "meetings": counts_by(Meeting.objects.all(), "status"),
            "recent_users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "name": display_name(user),
                    "date_joined": user.date_joined,
                    "is_staff": user.is_staff,
                    "is_active": user.is_active,
                    "onboarding_completed": bool(
                        getattr(user, "profile", None) and user.profile.onboarding_completed
                    ),
                }
                for user in recent_users
            ],
        })

    @staticmethod
    def signup_series(period, start):
        """Sign-ups bucketed to fit the period: hours of today, days of this week/month, or months overall."""
        if period == "today":
            rows = (
                User.objects.filter(date_joined__gte=start)
                .annotate(bucket=TruncHour("date_joined"))
                .values("bucket")
                .annotate(total=Count("id"))
            )
            counts = {timezone.localtime(row["bucket"]).hour: row["total"] for row in rows}
            return "hour", [
                {"date": start + timedelta(hours=hour), "count": counts.get(hour, 0)}
                for hour in range(24)
            ]

        if period in ("week", "month"):
            first_day = start.date()
            if period == "week":
                last_day = first_day + timedelta(days=6)
            else:
                last_day = next_month(first_day) - timedelta(days=1)
            rows = (
                User.objects.filter(date_joined__gte=start)
                .annotate(bucket=TruncDate("date_joined"))
                .values("bucket")
                .annotate(total=Count("id"))
            )
            counts = {row["bucket"]: row["total"] for row in rows}
            return "day", [
                {"date": day, "count": counts.get(day, 0)}
                for day in (
                    first_day + timedelta(days=i)
                    for i in range((last_day - first_day).days + 1)
                )
            ]

        this_month = timezone.localdate().replace(day=1)
        first_joined = User.objects.aggregate(first=Min("date_joined"))["first"]
        first_month = (
            timezone.localtime(first_joined).date().replace(day=1) if first_joined else this_month
        )
        months = [first_month]
        while months[-1] < this_month:
            months.append(next_month(months[-1]))
        months = months[-SIGNUP_MONTHS:]

        rows = (
            User.objects.filter(date_joined__date__gte=months[0])
            .annotate(bucket=TruncMonth("date_joined"))
            .values("bucket")
            .annotate(total=Count("id"))
        )
        counts = {}
        for row in rows:
            bucket = row["bucket"]
            if hasattr(bucket, "tzinfo"):
                bucket = timezone.localtime(bucket).date() if timezone.is_aware(bucket) else bucket.date()
            key = bucket.replace(day=1)
            counts[key] = counts.get(key, 0) + row["total"]
        return "month", [{"date": month, "count": counts.get(month, 0)} for month in months]

    @staticmethod
    def top_skills():
        skills = (
            Skill.objects
            .filter(is_approved=True)
            .annotate(
                teachers=Count("users", filter=Q(users__skill_type="teach"), distinct=True),
                learners=Count("users", filter=Q(users__skill_type="learn"), distinct=True),
                verified=Count(
                    "users",
                    filter=Q(users__skill_type="teach", users__is_verified=True),
                    distinct=True,
                ),
            )
            .annotate(total=F("teachers") + F("learners"))
            .filter(total__gt=0)
            .order_by("-total", "name")[:TOP_SKILLS]
        )
        return [
            {
                "id": skill.id,
                "name": skill.name,
                "teachers": skill.teachers,
                "learners": skill.learners,
                "verified": skill.verified,
            }
            for skill in skills
        ]


class AdminUserListView(APIView):
    """
    GET ?search=&role=staff|member&status=active|onboarding|inactive
        &joined=today|week|month&seen=today|week|month
        &sort=newest|oldest|name|last_login|rating&page=1

    `counts` gives the number of users per role/status for the current search
    and date filters, so the filter tabs can show totals.
    """

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

        users = since(users, "date_joined", period_start(params.get("joined")))
        users = since(users, "last_login", period_start(params.get("seen")))

        counts = User.objects.filter(pk__in=users.values("pk")).aggregate(
            all=Count("id"),
            **{f"role_{key}": Count("id", filter=q) for key, q in ROLE_FILTERS.items()},
            **{f"status_{key}": Count("id", filter=q) for key, q in STATUS_FILTERS.items()},
        )

        role = params.get("role")
        if role in ROLE_FILTERS:
            users = users.filter(ROLE_FILTERS[role])

        account_status = params.get("status")
        if account_status in STATUS_FILTERS:
            users = users.filter(STATUS_FILTERS[account_status])

        sort = params.get("sort", "newest")
        users = users.order_by(*SORT_ORDERS.get(sort, SORT_ORDERS["newest"]))
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
            "counts": {
                "all": counts["all"],
                "role": {key: counts[f"role_{key}"] for key in ROLE_FILTERS},
                "status": {key: counts[f"status_{key}"] for key in STATUS_FILTERS},
            },
            "results": [user_row(u) for u in users[start:start + USERS_PAGE_SIZE]],
        })


def user_skill_row(user_skill):
    row = {
        "id": user_skill.id,
        "skill_id": user_skill.skill_id,
        "name": user_skill.skill.name,
        "type": user_skill.skill_type,
        "is_verified": user_skill.is_verified,
        "quiz_attempts_left": None,
        "quiz_available_at": None,
    }
    if user_skill.skill_type == "teach" and not user_skill.is_verified:
        can_take, _attempt, available_at = quiz_availability(user_skill.user, user_skill.skill)
        row["quiz_attempts_left"] = attempts_left(user_skill.user, user_skill.skill)
        row["quiz_available_at"] = None if can_take else available_at
    return row


def user_detail_payload(user_id):
    user = annotated_users().get(pk=user_id)
    profile = getattr(user, "profile", None)
    meetings = (
        user_meetings(user)
        .select_related("request__sender", "request__receiver", "request__skill")
        .order_by("-start_time")
    )

    return {
        **user_row(user),
        "bio": profile.bio if profile else "",
        "quiz_max_attempts": max_attempts(),
        "skills": [
            user_skill_row(us)
            for us in (
                user.user_skills
                .select_related("skill", "user")
                .order_by("skill_type", "skill__name")
            )
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
                "excused": a.excused,
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


class AdminUserDetailView(APIView):
    """
    GET full user details.
    PATCH is_active / is_staff, username / email / first_name / last_name, bio.
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk):
        get_object_or_404(User, pk=pk)
        return Response(user_detail_payload(pk))

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        data = request.data

        denied = superuser_guard(request, user)
        if denied:
            return denied
        if user == request.user and ("is_active" in data or "is_staff" in data):
            return error("You can't change your own account status or role.")

        changed = []
        for field in ("is_active", "is_staff"):
            if field in data:
                value = data[field]
                if not isinstance(value, bool):
                    return error(f"{field} must be true or false.")
                setattr(user, field, value)
                changed.append(field)

        for field in EDITABLE_USER_FIELDS:
            if field in data:
                setattr(user, field, str(data[field] or "").strip())
                changed.append(field)

        problem = self.validate(user, changed)
        if problem:
            return error(problem)

        if changed:
            user.save(update_fields=changed)

        if "bio" in data:
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.bio = str(data["bio"] or "").strip()
            profile.save(update_fields=["bio"])

        return Response(user_detail_payload(pk))

    @staticmethod
    def validate(user, changed):
        if "username" in changed:
            if not user.username:
                return "Username can't be empty."
            if User.objects.filter(username__iexact=user.username).exclude(pk=user.pk).exists():
                return "That username is already taken."
        if "email" in changed and user.email:
            if User.objects.filter(email__iexact=user.email).exclude(pk=user.pk).exists():
                return "Another account already uses this email."

        try:
            user.clean_fields(
                exclude=[f.name for f in User._meta.fields if f.name not in changed]
            )
        except ValidationError as exc:
            return next(iter(exc.message_dict.values()))[0]
        return None


class AdminUserSkillCreateView(APIView):
    """POST {skill_id, skill_type: teach|learn} adds a skill to a user's profile."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        denied = superuser_guard(request, user)
        if denied:
            return denied

        skill_type = request.data.get("skill_type")
        if skill_type not in ("teach", "learn"):
            return error("skill_type must be 'teach' or 'learn'.")
        try:
            skill = Skill.objects.get(pk=int(request.data.get("skill_id")))
        except (TypeError, ValueError, Skill.DoesNotExist):
            return error("Pick a skill to add.")

        _user_skill, created = UserSkill.objects.get_or_create(
            user=user, skill=skill, skill_type=skill_type
        )
        if not created:
            return error(f"{display_name(user)} already has {skill.name} as a {skill_type} skill.")
        return Response(user_detail_payload(pk), status=status.HTTP_201_CREATED)


class AdminUserSkillDetailView(APIView):
    """PATCH {is_verified} or DELETE one of a user's skills."""

    permission_classes = [permissions.IsAdminUser]

    def get_user_skill(self, request, pk):
        user_skill = get_object_or_404(UserSkill.objects.select_related("user", "skill"), pk=pk)
        return user_skill, superuser_guard(request, user_skill.user)

    def patch(self, request, pk):
        user_skill, denied = self.get_user_skill(request, pk)
        if denied:
            return denied

        if "is_verified" in request.data:
            value = request.data["is_verified"]
            if not isinstance(value, bool):
                return error("is_verified must be true or false.")
            if value and user_skill.skill_type != "teach":
                return error("Only teach skills can be verified.")
            user_skill.is_verified = value
            user_skill.save(update_fields=["is_verified"])

        return Response(user_detail_payload(user_skill.user_id))

    def delete(self, request, pk):
        user_skill, denied = self.get_user_skill(request, pk)
        if denied:
            return denied
        user_id = user_skill.user_id
        user_skill.delete()
        return Response(user_detail_payload(user_id))


class AdminUserSkillResetQuizView(APIView):
    """POST gives the user a full set of quiz attempts for this teach skill."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        user_skill = get_object_or_404(UserSkill.objects.select_related("user", "skill"), pk=pk)
        denied = superuser_guard(request, user_skill.user)
        if denied:
            return denied
        if user_skill.skill_type != "teach":
            return error("Only teach skills have a quiz.")
        reset_attempts(user_skill.user, user_skill.skill)
        return Response(user_detail_payload(user_skill.user_id))


class AdminSkillDetailView(APIView):
    """PATCH {name} renames a skill; DELETE removes it (and it disappears from profiles)."""

    permission_classes = [permissions.IsAdminUser]

    def patch(self, request, pk):
        skill = get_object_or_404(Skill, pk=pk)
        if "name" in request.data:
            name = " ".join(str(request.data["name"] or "").split())
            if not name:
                return error("Skill name can't be empty.")
            if len(name) > Skill._meta.get_field("name").max_length:
                return error("Skill name is too long.")
            if Skill.objects.filter(name__iexact=name).exclude(pk=pk).exists():
                return error(f'A skill called "{name}" already exists.')
            skill.name = name
            skill.save(update_fields=["name"])

        return Response(AdminSkillSerializer(admin_skill_queryset().get(pk=pk)).data)

    def delete(self, request, pk):
        skill = get_object_or_404(Skill, pk=pk)
        try:
            skill.delete()
        except ProtectedError:
            return error(
                "This skill is used by existing match requests and can't be deleted.",
                status.HTTP_409_CONFLICT,
            )
        return Response({"id": pk, "status": "deleted"})
