from django.contrib.auth.models import User

from rest_framework import (
    generics,
    permissions,
    status,
)

from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Profile,
    Skill,
    UserSkill,
    AvailabilitySlot,
)

from .serializers import (
    ProfileSerializer,
    SkillSerializer,
    UserSkillSerializer,
    AvailabilitySlotSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):

    serializer_class = RegisterSerializer
    permission_classes = [
        permissions.AllowAny
    ]

    def create(
        self,
        request,
        *args,
        **kwargs
    ):

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        refresh = RefreshToken.for_user(
            user
        )

        return Response(
            {
                "access": str(
                    refresh.access_token
                ),
                "refresh": str(
                    refresh
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request
    ):

        serializer = UserSerializer(
            request.user
        )

        return Response(
            serializer.data
        )


class ProfileView(
    generics.RetrieveUpdateAPIView
):

    serializer_class = ProfileSerializer

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get_object(self):

        profile, created = (
            Profile.objects.get_or_create(
                user=self.request.user
            )
        )

        return profile


class SkillListCreateView(
    generics.ListCreateAPIView
):

    queryset = Skill.objects.all()

    serializer_class = SkillSerializer

    permission_classes = [
        permissions.IsAuthenticated
    ]


class UserSkillListCreateView(
    generics.ListCreateAPIView
):

    serializer_class = UserSkillSerializer

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get_queryset(self):

        return UserSkill.objects.filter(
            user=self.request.user
        )

    def perform_create(
        self,
        serializer
    ):

        serializer.save(
            user=self.request.user
        )


class UserSkillDeleteView(
    generics.DestroyAPIView
):

    serializer_class = UserSkillSerializer

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get_queryset(self):

        return UserSkill.objects.filter(
            user=self.request.user
        )


class AvailabilityListCreateView(
    generics.ListCreateAPIView
):

    serializer_class = (
        AvailabilitySlotSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get_queryset(self):

        return (
            AvailabilitySlot.objects.filter(
                user=self.request.user
            )
        )

    def perform_create(
        self,
        serializer
    ):

        serializer.save(
            user=self.request.user
        )


class UserAvailabilityView(APIView):

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get(
        self,
        request,
        user_id
    ):

        slots = (
            AvailabilitySlot.objects.filter(
                user_id=user_id
            )
        )

        serializer = (
            AvailabilitySlotSerializer(
                slots,
                many=True
            )
        )

        return Response(
            serializer.data
        )


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

    serializer_class = (
        AvailabilitySlotSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated
    ]

    def get_queryset(self):

        return (
            AvailabilitySlot.objects.filter(
                user=self.request.user
            )
        )