from django.urls import path
from .views import find_matches

urlpatterns = [
    path("matches/", find_matches, name="matches"),
]