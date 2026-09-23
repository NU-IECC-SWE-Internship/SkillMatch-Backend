from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404

from .models import (
    Profile,
    Skill,
    UserSkill,
    AvailabilitySlot,
    SkillQuizAttempt,
    PendingSkillQuiz,
)

from .serializers import (
    ProfileSerializer,
    SkillSerializer,
    UserSkillSerializer,
    AvailabilitySlotSerializer,
    RegisterSerializer,
    UserSerializer,
    QuizSubmitSerializer,
)
from .quiz_llm import QuizGenerationError, generate_quiz_questions
from .quiz_policy import quiz_availability

PASS_SCORE = 7
QUIZ_QUESTION_COUNT = 10


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
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer
    permission_classes = [permissions.IsAuthenticated]


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

        can_take, attempt, available_at = quiz_availability(
            request.user,
            skill,
            is_verified=user_skill.is_verified,
        )

        return Response(
            {
                "skill_id": skill.id,
                "skill_name": skill.name,
                "pass_score": PASS_SCORE,
                "question_count": QUIZ_QUESTION_COUNT,
                "can_take": can_take,
                "has_attempt": attempt is not None,
                "available_at": available_at,
                "cooldown_hours": 24,
                "attempt": (
                    None
                    if attempt is None
                    else {
                        "score": attempt.score,
                        "passed": attempt.passed,
                        "created_at": attempt.created_at,
                    }
                ),
                "questions": [],
            }
        )


class SkillQuizStartView(APIView):
    """Generate a fresh Groq quiz for this user+skill when they start."""

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
                        "Quiz cooldown active. You can try again after 24 hours."
                    ),
                    "available_at": available_at,
                    "last_score": attempt.score if attempt else None,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        pending = PendingSkillQuiz.objects.filter(
            user=request.user,
            skill=skill,
        ).first()

        # Reuse an unfinished pending quiz only if there is no newer attempt
        # after it was created (i.e. still the same "session").
        if pending and pending.questions:
            if attempt is None or pending.created_at > attempt.created_at:
                return Response(
                    {
                        "skill_id": skill.id,
                        "skill_name": skill.name,
                        "pass_score": PASS_SCORE,
                        "questions": pending.public_questions(),
                    }
                )
            pending.delete()

        try:
            generated = generate_quiz_questions(
                skill.name,
                count=QUIZ_QUESTION_COUNT,
            )
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
                "pass_score": PASS_SCORE,
                "questions": pending.public_questions(),
            },
            status=status.HTTP_201_CREATED,
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
                        "Quiz cooldown active. You can try again after 24 hours."
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

        score = 0
        for q in questions:
            order = int(q["order"])
            if answer_map.get(order) == q.get("correct_option"):
                score += 1

        passed = score >= PASS_SCORE

        SkillQuizAttempt.objects.create(
            user=request.user,
            skill=skill,
            score=score,
            passed=passed,
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
                "pass_score": PASS_SCORE,
                "can_retry": not passed,
                "cooldown_hours": 24,
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


class AvailabilityUpdateDeleteView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AvailabilitySlot.objects.filter(
            user=self.request.user
        )
