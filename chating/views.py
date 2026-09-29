from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Message
from .serializers import MessageSerializer


class ConversationMessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user_id = int(request.query_params.get('user_id', ''))
        except (TypeError, ValueError):
            raise ValidationError({'user_id': 'A valid user ID is required.'})

        if user_id == request.user.id:
            raise ValidationError({'user_id': 'You cannot chat with yourself.'})

        User = get_user_model()
        try:
            other_user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            raise NotFound('User not found.')

        messages = Message.objects.filter(
            Q(sender=request.user, receiver=other_user)
            | Q(sender=other_user, receiver=request.user)
        ).select_related('sender', 'receiver')
        return Response(MessageSerializer(messages, many=True).data)
