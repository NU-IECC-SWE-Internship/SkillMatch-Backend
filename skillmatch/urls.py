from django.urls import path

from .views import (
    ProfileView,
    SkillListCreateView,
    UserSkillListCreateView,
    UserSkillDeleteView,
    AvailabilityListCreateView,
    AvailabilityUpdateDeleteView,
)


urlpatterns = [
    
    path("profile/", ProfileView.as_view(), name="profile"),

    path("skills/", SkillListCreateView.as_view(), name="skills"),
    path("my-skills/", UserSkillListCreateView.as_view(), name="my-skills"),
    path(
        "my-skills/<int:pk>/",
        UserSkillDeleteView.as_view(),
        name="delete-user-skill"
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
]