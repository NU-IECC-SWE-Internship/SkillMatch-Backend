from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/  -> create a new user"""
    serializer_class = RegisterSerializer
    # anyone can register (no token needed)
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    """GET /api/auth/me/  -> return the logged-in user"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # request.user comes from the JWT token
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
