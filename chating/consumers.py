import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from .models import Message


@database_sync_to_async
def save_message(sender_id, receiver_id, content):
    User = get_user_model()
    try:
        receiver = User.objects.get(pk=receiver_id, is_active=True)
    except (User.DoesNotExist, TypeError, ValueError):
        return None
    if sender_id == receiver.id or not content.strip():
        return None

    message = Message.objects.create(
        sender_id=sender_id,
        receiver=receiver,
        content=content.strip(),
    )
    return {
        'id': message.id,
        'sender_id': sender_id,
        'sender_username': message.sender.username,
        'receiver_id': receiver.id,
        'receiver_username': receiver.username,
        'content': message.content,
        'created_at': message.created_at.isoformat(),
        'is_read': message.is_read,
    }


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.user_group = f'chat_user_{self.user.id}'
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or '{}')
            receiver_id = int(data.get('receiver_id'))
            content = data.get('content', '')
            if not isinstance(content, str) or not content.strip():
                return
        except (json.JSONDecodeError, TypeError, ValueError):
            return

        message = await save_message(self.user.id, receiver_id, content)
        if message is None:
            return

        event = {'type': 'chat.message', 'message': message}
        await self.channel_layer.group_send(f'chat_user_{self.user.id}', event)
        await self.channel_layer.group_send(f'chat_user_{receiver_id}', event)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event['message']))
