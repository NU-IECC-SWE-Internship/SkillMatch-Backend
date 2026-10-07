from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (
    Profile,
    Skill,
    UserSkill,
    AvailabilitySlot,
    SkillQuizAttempt,
    PendingSkillQuiz,
    SkillQuizQuestion,
)

from .serializers import (
    ProfileSerializer,
    ShowProfileSerializer,
    SkillSerializer,
    UserSkillSerializer,
    AvailabilitySlotSerializer,
    RegisterSerializer,
    UserSerializer,
    QuizSubmitSerializer,
    AdminSkillSerializer,
    AdminQuizQuestionSerializer,
)
from .quiz_bank import (
    bank_size,
    current_cycle,
    draw_quiz,
    split_by_difficulty,
    top_up_skill,
)
from .quiz_llm import QuizGenerationError
from .quiz_policy import (
    expire_abandoned_quiz,
    latest_submitted_attempt,
    quiz_availability,
    start_grace,
)
from system_config.services import get_config

# Must stay in sync with the suggested skills in the frontend (Profile / onboarding).
DEFAULT_SKILL_NAMES = {
    "python",
    "javascript",
    "react",
    "django",
    "machine learning",
    "data analysis",
    "figma",
    "ui/ux",
}

SKILL_PENDING_ERROR = "This skill is waiting for admin approval."


REVIEW_FIELDS = [
    "order",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "difficulty",
]


def build_review(questions, answer_map):
    """Full per-question record stored on the attempt (includes correct answers)."""
    review = []
    for q in sorted(questions, key=lambda item: int(item["order"])):
        selected = answer_map.get(int(q["order"]))
        review.append({
            **{field: q.get(field) for field in REVIEW_FIELDS},
            "correct_option": q.get("correct_option"),
            "selected": selected,
            "is_correct": selected is not None and selected == q.get("correct_option"),
        })
    return review


def public_review(review):
    """What the user may see; hides the right answer to missed questions if configured."""
    show_answers = get_config("quiz.review_show_answers")
    return [
        {
            **item,
            "correct_option": (
                item.get("correct_option")
                if show_answers or item.get("is_correct")
                else None
            ),
        }
        for item in review
    ]


def attempt_payload(attempt, *, include_review=False):
    if attempt is None:
        return None
    payload = {
        "score": attempt.score,
        "passed": attempt.passed,
        "abandoned": attempt.abandoned,
        "created_at": attempt.created_at,
    }
    if include_review:
        payload["review"] = public_review(attempt.review or [])
    return payload


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Same token type login uses (SimpleJWT), issued here directly
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, created = Profile.objects.get_or_create(
            user=self.request.user
        )
        return profile


class SkillListCreateView(generics.ListCreateAPIView):
    """
    Lists approved skills plus the user's own pending ones.
    New skills are auto-approved for staff and the default suggestions;
    anything else waits for an admin.
    """

    serializer_class = SkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return (
            Skill.objects
            .filter(
                Q(is_approved=True)
                | Q(created_by=user)
                | Q(users__user=user)
            )
            .distinct()
            .order_by("name")
        )

    def create(self, request, *args, **kwargs):
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response(
                {"name": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = Skill.objects.filter(name__iexact=name).first()
        if existing:
            return Response(SkillSerializer(existing).data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data={"name": name})
        serializer.is_valid(raise_exception=True)
        skill = serializer.save(
            created_by=request.user,
            is_approved=(
                request.user.is_staff
                or name.lower() in DEFAULT_SKILL_NAMES
            ),
        )
        return Response(SkillSerializer(skill).data, status=status.HTTP_201_CREATED)


class UserSkillListCreateView(generics.ListCreateAPIView):
    serializer_class = UserSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserSkill.objects.filter(
            user=self.request.user
        )

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            is_verified=False,
        )


class UserSkillDeleteView(generics.DestroyAPIView):
    serializer_class = UserSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserSkill.objects.filter(
            user=self.request.user
        )


class SkillQuizView(APIView):
    """GET quiz status only — questions are generated when the user starts."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, skill_id):
        skill = get_object_or_404(Skill, pk=skill_id)

        user_skill = UserSkill.objects.filter(
            user=request.user,
            skill=skill,
            skill_type="teach",
        ).first()
        if not user_skill:
            return Response(
                {"error": "Add this skill as a teach skill before taking the quiz."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not skill.is_approved:
            return Response(
                {"error": SKILL_PENDING_ERROR},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Coming back to the quiz page means any started quiz was abandoned.
        if not user_skill.is_verified:
            expire_abandoned_quiz(request.user, skill)

        can_take, attempt, available_at = quiz_availability(
            request.user,
            skill,
            is_verified=user_skill.is_verified,
        )

        return Response(
            {
                "skill_id": skill.id,
                "skill_name": skill.name,
                "pass_score": get_config("quiz.pass_score"),
                "question_count": get_config("quiz.question_count"),
                "can_take": can_take,
                "has_attempt": attempt is not None,
                "available_at": available_at,
                "cooldown_hours": get_config("quiz.cooldown_hours"),
                "attempt": attempt_payload(attempt, include_review=True),
                "questions": [],
            }
        )


class SkillQuizStartView(APIView):
    """Draw a random quiz from the skill's question bank when the user starts."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, skill_id):
        skill = get_object_or_404(Skill, pk=skill_id)

        user_skill = UserSkill.objects.filter(
            user=request.user,
            skill=skill,
            skill_type="teach",
        ).first()
        if not user_skill:
            return Response(
                {"error": "Add this skill as a teach skill before taking the quiz."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not skill.is_approved:
            return Response(
                {"error": SKILL_PENDING_ERROR},
                status=status.HTTP_403_FORBIDDEN,
            )

        pending = PendingSkillQuiz.objects.filter(
            user=request.user,
            skill=skill,
        ).first()

        # A duplicate Start right after the first one gets the same questions.
        if (
            pending
            and pending.questions
            and timezone.now() - pending.created_at < start_grace()
        ):
            return Response(
                {
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "pass_score": get_config("quiz.pass_score"),
                    "questions": pending.public_questions(),
                }
            )

        # Any older unfinished quiz counts as a failed attempt.
        if not user_skill.is_verified:
            expire_abandoned_quiz(request.user, skill)

        can_take, attempt, available_at = quiz_availability(
            request.user,
            skill,
            is_verified=user_skill.is_verified,
        )
        if not can_take:
            if user_skill.is_verified:
                return Response(
                    {"error": "This skill is already verified."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {
                    "error": (
                        "Quiz cooldown active. You can try again after "
                        f"{get_config('quiz.cooldown_hours')} hours."
                    ),
                    "available_at": available_at,
                    "last_score": attempt.score if attempt else None,
                    "attempt": attempt_payload(attempt),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            generated = draw_quiz(skill, get_config("quiz.question_count"))
        except QuizGenerationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        pending, _ = PendingSkillQuiz.objects.update_or_create(
            user=request.user,
            skill=skill,
            defaults={"questions": generated},
        )

        return Response(
            {
                "skill_id": skill.id,
                "skill_name": skill.name,
                "pass_score": get_config("quiz.pass_score"),
                "questions": pending.public_questions(),
            },
            status=status.HTTP_201_CREATED,
        )


class SkillQuizReviewView(APIView):
    """Read-only review of the user's latest submitted attempt for a skill."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, skill_id):
        skill = get_object_or_404(Skill, pk=skill_id)
        attempt = latest_submitted_attempt(request.user, skill)
        if attempt is None:
            return Response(
                {"error": "You don't have a quiz attempt to review for this skill yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user_skill = UserSkill.objects.filter(
            user=request.user,
            skill=skill,
            skill_type="teach",
        ).first()
        is_verified = bool(user_skill and user_skill.is_verified)
        can_take, _latest, available_at = quiz_availability(
            request.user,
            skill,
            is_verified=is_verified,
        )

        return Response(
            {
                "skill_id": skill.id,
                "skill_name": skill.name,
                "score": attempt.score,
                # Older attempts didn't store questions; they were always out of the quiz length.
                "total": len(attempt.review) or get_config("quiz.question_count"),
                "has_details": bool(attempt.review),
                "passed": attempt.passed,
                "created_at": attempt.created_at,
                "pass_score": get_config("quiz.pass_score"),
                "is_verified": is_verified,
                "can_take": bool(user_skill) and skill.is_approved and can_take,
                "available_at": None if can_take else available_at,
                "review": public_review(attempt.review),
            }
        )


class SkillQuizSubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, skill_id):
        skill = get_object_or_404(Skill, pk=skill_id)

        user_skill = UserSkill.objects.filter(
            user=request.user,
            skill=skill,
            skill_type="teach",
        ).first()
        if not user_skill:
            return Response(
                {"error": "Add this skill as a teach skill before taking the quiz."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        can_take, attempt, available_at = quiz_availability(
            request.user,
            skill,
            is_verified=user_skill.is_verified,
        )
        if not can_take:
            if user_skill.is_verified:
                return Response(
                    {"error": "This skill is already verified."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {
                    "error": (
                        "Quiz cooldown active. You can try again after "
                        f"{get_config('quiz.cooldown_hours')} hours."
                    ),
                    "available_at": available_at,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        pending = PendingSkillQuiz.objects.filter(
            user=request.user,
            skill=skill,
        ).first()
        if not pending or not pending.questions:
            return Response(
                {"error": "Start the quiz first so questions can be generated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = QuizSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data["answers"]

        questions = pending.questions
        expected_ids = {int(q["order"]) for q in questions}
        answer_map = {}
        for item in answers:
            qid = int(item["question_id"])
            if qid in answer_map:
                return Response(
                    {"error": "Duplicate answer for a question."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            answer_map[qid] = item["selected"]

        if set(answer_map.keys()) != expected_ids:
            return Response(
                {"error": "Answer every quiz question exactly once."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review = build_review(questions, answer_map)
        score = sum(1 for item in review if item["is_correct"])

        pass_score = get_config("quiz.pass_score")
        passed = score >= pass_score

        SkillQuizAttempt.objects.create(
            user=request.user,
            skill=skill,
            score=score,
            passed=passed,
            review=review,
        )
        pending.delete()

        if passed:
            user_skill.is_verified = True
            user_skill.save(update_fields=["is_verified"])

        return Response(
            {
                "score": score,
                "total": len(questions),
                "passed": passed,
                "is_verified": user_skill.is_verified,
                "pass_score": pass_score,
                "can_retry": not passed,
                "cooldown_hours": get_config("quiz.cooldown_hours"),
                "review": public_review(review),
            }
        )


class AvailabilityListCreateView(generics.ListCreateAPIView):
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AvailabilitySlot.objects.filter(
            user=self.request.user
        )

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user
        )


class UserAvailabilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id):
        slots = AvailabilitySlot.objects.filter(user_id=user_id)
        serializer = AvailabilitySlotSerializer(slots, many=True)
        return Response(serializer.data)


class UserSessionSettingsView(APIView):
    """
    Information needed when another user
    wants to request a session.

    Returns:
    - username
    - maximum session duration
    - availability slots
    """

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        user_id
    ):

        try:
            user = User.objects.get(
                id=user_id
            )

        except User.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "User not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )


        profile, created = (
            Profile.objects.get_or_create(
                user=user
            )
        )


        slots = (
            AvailabilitySlot.objects.filter(
                user=user
            ).order_by(
                "day",
                "start_time"
            )
        )


        slots_serializer = (
            AvailabilitySlotSerializer(
                slots,
                many=True
            )
        )


        return Response(
            {
                "user": user.id,
                "username": user.username,

                "max_session_duration_minutes":
                    profile.max_session_duration_minutes,

                "availability":
                    slots_serializer.data,
            }
        )

class AvailabilityUpdateDeleteView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AvailabilitySlot.objects.filter(
            user=self.request.user
        )


# =========================================================
# ADMIN — SKILL APPROVAL
# =========================================================

def admin_skill_queryset():
    return (
        Skill.objects
        .select_related("created_by")
        .annotate(
            user_count=Count("users__user", distinct=True),
            question_count=Count(
                "quiz_questions",
                filter=Q(quiz_questions__cycle=current_cycle()),
                distinct=True,
            ),
        )
    )


class AdminSkillListView(APIView):
    """GET ?status=pending (default) | approved"""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        approved = request.query_params.get("status", "pending") == "approved"
        skills = (
            admin_skill_queryset()
            .filter(is_approved=approved)
            .order_by("-created_at", "name")
        )
        return Response(AdminSkillSerializer(skills, many=True).data)


class AdminSkillApproveView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        skill = get_object_or_404(Skill, pk=pk)
        if not skill.is_approved:
            skill.is_approved = True
            skill.save(update_fields=["is_approved"])
        return Response(
            AdminSkillSerializer(admin_skill_queryset().get(pk=pk)).data
        )


class AdminSkillDenyView(APIView):
    """Denying removes the pending skill (and it disappears from users' profiles)."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        skill = get_object_or_404(Skill, pk=pk)
        if skill.is_approved:
            return Response(
                {"error": "Only pending skills can be denied."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            skill.delete()
        except ProtectedError:
            return Response(
                {"error": "This skill is used by existing requests and can't be removed."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"id": pk, "status": "denied"})


# =========================================================
# ADMIN — QUESTION BANK
# =========================================================

def question_bank_payload(skill):
    questions = SkillQuizQuestion.objects.filter(skill=skill).order_by("-cycle", "-id")
    current = questions.filter(cycle=current_cycle())
    difficulty_counts = {level: 0 for level in SkillQuizQuestion.DIFFICULTY_ORDER}
    for row in current.values("difficulty").annotate(total=Count("id")):
        difficulty_counts[row["difficulty"]] = row["total"]
    return {
        "skill_id": skill.id,
        "skill_name": skill.name,
        "cycle": current_cycle(),
        "bank_size": bank_size(),
        "current_count": current.count(),
        "difficulty_counts": difficulty_counts,
        "difficulty_targets": split_by_difficulty(bank_size()),
        "questions": AdminQuizQuestionSerializer(questions, many=True).data,
    }


class AdminSkillQuestionListCreateView(APIView):
    """GET a skill's question bank; POST adds a question to the current cycle."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, skill_id):
        skill = get_object_or_404(Skill, pk=skill_id)
        return Response(question_bank_payload(skill))

    def post(self, request, skill_id):
        skill = get_object_or_404(Skill, pk=skill_id)
        cycle = current_cycle()
        size = bank_size()
        if SkillQuizQuestion.objects.filter(skill=skill, cycle=cycle).count() >= size:
            return Response(
                {"error": f"This month's bank is full ({size} questions). Delete one first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminQuizQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(skill=skill, cycle=cycle)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminQuizQuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = SkillQuizQuestion.objects.all()
    serializer_class = AdminQuizQuestionSerializer
    permission_classes = [permissions.IsAdminUser]


class AdminSkillQuestionGenerateView(APIView):
    """Generate one batch now with Groq (ignores the once-a-day limit)."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, skill_id):
        skill = get_object_or_404(Skill, pk=skill_id)
        try:
            added = top_up_skill(skill, force=True)
        except QuizGenerationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"added": added, **question_bank_payload(skill)})


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id):
        try:
            profile = Profile.objects.select_related("user").get(
                user_id=user_id
            )
        except Profile.DoesNotExist:
            return Response(
                {"detail": "User profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ShowProfileSerializer(profile)

        return Response(serializer.data)
