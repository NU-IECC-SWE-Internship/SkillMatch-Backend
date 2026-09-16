from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import RegisterView, MeView

urlpatterns = [
    # create account
    path('register/', RegisterView.as_view(), name='register'),

    # login: send {"username": "...", "password": "..."}
    # get back {"access": "...", "refresh": "..."}
    path('login/', TokenObtainPairView.as_view(), name='login'),

    # send {"refresh": "..."} to get a new access token
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # needs header: Authorization: Bearer <access>
    path('me/', MeView.as_view(), name='me'),
]
