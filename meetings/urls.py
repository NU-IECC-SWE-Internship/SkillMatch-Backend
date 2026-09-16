from django.urls import path
from .views import MeetingListCreateView, SingleMeetingDetailView, AvailablePartnersView

urlpatterns = [
    path('api/meetings/', MeetingListCreateView.as_view(), name='meeting-list-create'),
    path('api/meetings/users/', AvailablePartnersView.as_view(), name='available-partners'),
    path('api/meetings/<int:pk>/', SingleMeetingDetailView.as_view(), name='single-meeting'),
]