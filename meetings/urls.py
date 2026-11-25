from django.urls import path
from .views import (
    MeetingListCreateView,
    SingleMeetingDetailView,
    MeetingReviewsView,
    UserReviewsView,
)

urlpatterns = [
    path('api/meetings/', MeetingListCreateView.as_view(), name='meeting-list-create'),
    path('api/meetings/<int:pk>/', SingleMeetingDetailView.as_view(), name='single-meeting'),
    path('api/meetings/<int:pk>/reviews/', MeetingReviewsView.as_view(), name='meeting-reviews'),
    path('api/users/<int:user_id>/reviews/', UserReviewsView.as_view(), name='user-reviews'),
]

