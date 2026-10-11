import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time user notifications.
    Each authenticated user joins their personal group: notifications_user_<user_id>.
    """

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            logger.warning("Rejecting unauthenticated WebSocket connection to notifications.")
            await self.close(code=4401)
            return

        self.group_name = f"notifications_user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("User %s connected to notifications WebSocket.", self.user.id)

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name') and self.channel_layer:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info("User %s disconnected from notifications WebSocket.", getattr(self.user, 'id', 'Unknown'))

    async def notification_message(self, event):
        """Pushes a newly created notification to the client."""
        await self.send(text_data=json.dumps({
            "type": "new_notification",
            "notification": event["notification"],
            "unread_count": event.get("unread_count"),
        }))

    async def notification_read(self, event):
        """Notifies connected clients that a specific notification was marked as read."""
        await self.send(text_data=json.dumps({
            "type": "notification_read",
            "id": event.get("id"),
            "unread_count": event.get("unread_count"),
        }))

    async def notification_all_read(self, event):
        """Notifies connected clients that all notifications were marked as read."""
        await self.send(text_data=json.dumps({
            "type": "notification_all_read",
            "unread_count": 0,
        }))
