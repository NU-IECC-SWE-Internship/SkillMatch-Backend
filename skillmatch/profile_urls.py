from django.urls import path

from .views import (
    ProfileView,
    SkillListCreateView,
    UserSkillListCreateView,
    UserSkillDeleteView,
    AvailabilityListCreateView,
    AvailabilityUpdateDeleteView,
    SkillQuizView,
    SkillQuizStartView,
    SkillQuizSubmitView,
    UserAvailabilityView,
    UserSessionSettingsView,
    UserProfileView,
    AdminSkillListView,
    AdminSkillApproveView,
    AdminSkillDenyView,
    AdminSkillQuestionListCreateView,
    AdminSkillQuestionGenerateView,
    AdminQuizQuestionDetailView,
)
from .admin_views import AdminOverviewView, AdminUserDetailView, AdminUserListView


urlpatterns = [

    path(
        "profile/",
        ProfileView.as_view(),
        name="profile"
    ),

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

    path(
        "users/<int:user_id>/profile/",
        UserProfileView.as_view(),
        name="user-profile",
    ),

    path(
        "admin/skills/",
        AdminSkillListView.as_view(),
        name="admin-skills"
    ),

    path(
        "admin/skills/<int:pk>/approve/",
        AdminSkillApproveView.as_view(),
        name="admin-skill-approve"
    ),

    path(
        "admin/skills/<int:pk>/deny/",
        AdminSkillDenyView.as_view(),
        name="admin-skill-deny"
    ),

    path(
        "admin/skills/<int:skill_id>/questions/",
        AdminSkillQuestionListCreateView.as_view(),
        name="admin-skill-questions"
    ),

    path(
        "admin/skills/<int:skill_id>/questions/generate/",
        AdminSkillQuestionGenerateView.as_view(),
        name="admin-skill-questions-generate"
    ),

    path(
        "admin/questions/<int:pk>/",
        AdminQuizQuestionDetailView.as_view(),
        name="admin-question-detail"
    ),

    path(
        "admin/overview/",
        AdminOverviewView.as_view(),
        name="admin-overview"
    ),

    path(
        "admin/users/",
        AdminUserListView.as_view(),
        name="admin-users"
    ),

    path(
        "admin/users/<int:pk>/",
        AdminUserDetailView.as_view(),
        name="admin-user-detail"
    ),
]
