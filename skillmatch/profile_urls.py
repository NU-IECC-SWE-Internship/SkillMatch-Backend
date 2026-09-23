from django.urls import path

from .views import (
    ProfileView,
    SkillListCreateView,
    UserSkillListCreateView,
    UserSkillDeleteView,
    AvailabilityListCreateView,
    AvailabilityUpdateDeleteView,
    UserAvailabilityView,
    UserSessionSettingsView,
)


urlpatterns = [

    path(
        "profile/",
        ProfileView.as_view(),
        name="profile"
    ),

    path(
        "skills/",
        SkillListCreateView.as_view(),
        name="skills"
    ),

    path(
        "my-skills/",
        UserSkillListCreateView.as_view(),
        name="my-skills"
    ),

    path(
        "my-skills/<int:pk>/",
        UserSkillDeleteView.as_view(),
        name="my-skill-delete"
    ),

    path(
        "availability/",
        AvailabilityListCreateView.as_view(),
        name="availability"
    ),

    path(
        "availability/<int:pk>/",
        AvailabilityUpdateDeleteView.as_view(),
        name="availability-detail"
    ),

    path(
        "users/<int:user_id>/availability/",
        UserAvailabilityView.as_view(),
        name="user-availability"
    ),

    path(
        "users/<int:user_id>/session-settings/",
        UserSessionSettingsView.as_view(),
        name="user-session-settings"
    ),
]