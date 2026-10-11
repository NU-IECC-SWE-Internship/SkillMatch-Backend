import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification
from .serializers import NotificationSerializer

logger = logging.getLogger(__name__)


def create_notification(recipient, title: str, message: str = "", notification_type: str = "general", link: str = ""):
    if not recipient:
        return None

    try:
        notification = Notification.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link,
        )
        logger.info("Notification created for user %s: %s", recipient.username, title)

        # Broadcast via WebSocket
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                unread_count = Notification.objects.filter(recipient=recipient, is_read=False).count()
                serialized = NotificationSerializer(notification).data
                async_to_sync(channel_layer.group_send)(
                    f"notifications_user_{recipient.id}",
                    {
                        "type": "notification_message",
                        "notification": serialized,
                        "unread_count": unread_count,
                    },
                )
        except Exception as ws_exc:
            logger.warning("Failed to push notification over WebSocket: %s", ws_exc)

        return notification
    except Exception as exc:
        logger.error("Failed to create notification for %s: %s", getattr(recipient, 'username', 'Unknown'), exc)
        return None

