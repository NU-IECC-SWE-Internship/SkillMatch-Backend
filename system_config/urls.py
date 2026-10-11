from django.urls import path

from .views import PublicConfigView

urlpatterns = [
    path("config/", PublicConfigView.as_view(), name="public-config"),
]
