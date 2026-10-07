from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import public_config


class PublicConfigView(APIView):
    """Config values the frontend is allowed to read (is_public=True)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(public_config())
