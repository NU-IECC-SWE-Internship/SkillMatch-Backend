from django.urls import path

from .views import (
    ProfileView,
    SkillListCreateView,
    UserSkillListCreateView,
    UserSkillDeleteView,
    AvailabilityListCreateView,
    UserAvailabilityView,
    AvailabilityUpdateDeleteView,
    SkillQuizView,
    SkillQuizStartView,
    SkillQuizSubmitView,
)


urlpatterns = [
    path("profile/", ProfileView.as_view(), name="profile"),

    path("skills/", SkillListCreateView.as_view(), name="skills"),

    path(
        "skills/<int:skill_id>/quiz/",
        SkillQuizView.as_view(),
        name="skill-quiz",
    ),
    path(
        "skills/<int:skill_id>/quiz/start/",
        SkillQuizStartView.as_view(),
        name="skill-quiz-start",
    ),
    path(
        "skills/<int:skill_id>/quiz/submit/",
        SkillQuizSubmitView.as_view(),
        name="skill-quiz-submit",
    ),

    path("my-skills/", UserSkillListCreateView.as_view(), name="my-skills"),

    path(
        "my-skills/<int:pk>/",
        UserSkillDeleteView.as_view(),
        name="delete-user-skill",
    ),

    path(
        "availability/",
        AvailabilityListCreateView.as_view(),
        name="availability",
    ),

    path(
        "users/<int:user_id>/availability/",
        UserAvailabilityView.as_view(),
        name="user-availability",
    ),

    path(
        "availability/<int:pk>/",
        AvailabilityUpdateDeleteView.as_view(),
        name="availability-detail",
    ),
]
