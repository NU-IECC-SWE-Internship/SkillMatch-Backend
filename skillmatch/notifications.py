import logging
from .models import Notification

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
        return notification
    except Exception as exc:
        logger.error("Failed to create notification for %s: %s", getattr(recipient, 'username', 'Unknown'), exc)
        return None
