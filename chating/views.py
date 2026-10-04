from django.contrib.auth import get_user_model
from django.db.models import Count, Q
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


class RecentChatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        messages = Message.objects.filter(
            Q(sender=request.user) | Q(receiver=request.user)
        ).select_related('sender', 'receiver').order_by('-created_at', '-id')
        unread_by_sender = dict(
            Message.objects.filter(receiver=request.user, is_read=False)
            .values('sender_id')
            .annotate(total=Count('id'))
            .values_list('sender_id', 'total')
        )

        recent_chats = []
        seen_user_ids = set()
        for message in messages:
            other_user = message.receiver if message.sender_id == request.user.id else message.sender
            if other_user.id in seen_user_ids:
                continue
            seen_user_ids.add(other_user.id)
            recent_chats.append({
                'user_id': other_user.id,
                'username': other_user.username,
                'last_message': message.content,
                'last_message_at': message.created_at,
                'unread_count': unread_by_sender.get(other_user.id, 0),
            })

        return Response(recent_chats)


class MarkChatReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if user_id == request.user.id:
            raise ValidationError({'user_id': 'You cannot mark your own messages as read.'})

        User = get_user_model()
        try:
            other_user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            raise NotFound('User not found.')

        Message.objects.filter(
            sender=other_user,
            receiver=request.user,
            is_read=False,
        ).update(is_read=True)
        return Response({'marked_read': True})
