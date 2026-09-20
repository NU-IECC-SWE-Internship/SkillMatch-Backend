from django.urls import path
from .views import find_matches, create_request, get_requests, respond_to_request

urlpatterns = [
    path("matches/", find_matches, name="matches"),
    path("requests/", create_request, name="create-request"),
    path("requests/incoming/", get_requests, name="incoming-requests"),
    path("requests/<int:pk>/respond/", respond_to_request, name="respond-request"),
]
