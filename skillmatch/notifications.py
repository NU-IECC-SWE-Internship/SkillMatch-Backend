import json
import logging
import os
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from pywebpush import webpush, WebPushException

from .models import Notification, PushSubscription
from .serializers import NotificationSerializer

logger = logging.getLogger(__name__)


def send_web_push(recipient, payload: dict):
    """
    Sends WebPush notifications to all registered browser/mobile push subscriptions for the recipient.
    Automatically purges expired/revoked subscriptions (HTTP 404 / 410).
    """
    if not recipient:
        return

    private_key_path = getattr(settings, "VAPID_PRIVATE_KEY_PATH", "")
    admin_email = getattr(settings, "VAPID_ADMIN_EMAIL", "mailto:admin@skillmatch.com")

    if not private_key_path or not os.path.exists(private_key_path):
        return

    subscriptions = PushSubscription.objects.filter(user=recipient)
    if not subscriptions.exists():
        return

    data = json.dumps(payload)
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth,
                    },
                },
                data=data,
                vapid_private_key=private_key_path,
                vapid_claims={"sub": admin_email},
                ttl=86400,
            )
        except WebPushException as ex:
            if ex.response is not None and ex.response.status_code in (404, 410):
                logger.info("Purging expired push subscription %s for %s", sub.id, recipient.username)
                sub.delete()
            else:
                logger.warning("WebPush error for user %s: %s", recipient.username, ex)
        except Exception as exc:
            logger.warning("Unexpected error sending WebPush to %s: %s", recipient.username, exc)


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

        # Broadcast via WebSocket (Real-time in-app)
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

        # Broadcast via WebPush (Mobile/Browser background push)
        try:
            send_web_push(
                recipient,
                {
                    "title": title,
                    "message": message,
                    "link": link or "/",
                    "notification_type": notification_type,
                },
            )
        except Exception as wp_exc:
            logger.warning("Failed to dispatch WebPush: %s", wp_exc)

        return notification
    except Exception as exc:
        logger.error("Failed to create notification for %s: %s", getattr(recipient, 'username', 'Unknown'), exc)
        return None


