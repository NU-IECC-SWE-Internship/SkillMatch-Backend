from django.urls import path

from .views import (
    create_request,
    find_matches,
    get_requests,
    get_sent_requests,
    get_teachers,
    respond_to_request,
)

urlpatterns = [
    path(
        "matches/",
        find_matches,
        name="matches",
    ),
    path(
        "teachers/",
        get_teachers,
        name="get-teachers",
    ),
    path(
        "requests/",
        create_request,
        name="create-request",
    ),
    path(
        "requests/incoming/",
        get_requests,
        name="incoming-requests",
    ),
    path(
        "requests/<int:pk>/respond/",
        respond_to_request,
        name="respond-request",
    ),
    path(
        "requests/sent/",
        get_sent_requests,
        name="sent-requests",
    ),
]