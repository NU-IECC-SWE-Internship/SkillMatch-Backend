import logging
import threading
from .tasks import send_rendered_email_task
from .notifications import create_notification

logger = logging.getLogger(__name__)


def should_send_email_to(user) -> bool:
    if not user or not getattr(user, 'email', None):
        return False

    profile = getattr(user, 'profile', None)
    if profile is not None and not profile.email_notifications_enabled:
        return False

    return True


def _dispatch_email(subject: str, template_name: str, context: dict, recipient_list: list):
    try:
        send_rendered_email_task.delay(subject, template_name, context, recipient_list)
    except Exception as exc:
        logger.warning(
            "Could not dispatch email '%s' via Celery (%s). Executing fallback in background thread.",
            subject,
            exc,
        )
        try:
            send_rendered_email_task.apply(args=[subject, template_name, context, recipient_list], throw=False)
        except Exception as fallback_exc:
            logger.error("Failed to execute email fallback: %s", fallback_exc)


def _send_async_rendered_email(subject: str, template_name: str, context: dict, recipient_list: list):
    if not recipient_list:
        return

    # Dispatch in a daemon thread so the HTTP request returns immediately without hanging
    thread = threading.Thread(
        target=_dispatch_email,
        args=(subject, template_name, context, recipient_list),
        daemon=True,
    )
    thread.start()


def send_match_request_received_email(match_request):
    receiver = match_request.receiver
    sender = match_request.sender
    skill_name = match_request.skill.name if match_request.skill else "General Skill Exchange"

    # Always create an in-app notification
    create_notification(
        recipient=receiver,
        title=f"New match request from {sender.username}!",
        message=f"{sender.username} sent you a request to practice {skill_name}.",
        notification_type="match_request",
        link="/requests",
    )

    if not should_send_email_to(receiver):
        return

    requested_slot = ""
    if getattr(match_request, 'selected_slot', None):
        slot = match_request.selected_slot
        day_str = str(slot.day).capitalize()
        start_str = slot.start_time.strftime('%I:%M %p') if hasattr(slot.start_time, 'strftime') else str(slot.start_time)
        end_str = slot.end_time.strftime('%I:%M %p') if hasattr(slot.end_time, 'strftime') else str(slot.end_time)
        requested_slot = f"{day_str} ({start_str} - {end_str})"

    context = {
        "receiver": {"username": receiver.username},
        "sender": {"username": sender.username},
        "skill_name": skill_name,
        "requested_slot": requested_slot,
        "message": getattr(match_request, "message", "") or "",
    }

    _send_async_rendered_email(
        subject=f"New SkillMatch Request from {sender.username}!",
        template_name="emails/match_request_received.html",
        context=context,
        recipient_list=[receiver.email],
    )


def send_match_request_accepted_email(match_request, meeting=None):
    sender = match_request.sender
    receiver = match_request.receiver
    skill_name = match_request.skill.name if match_request.skill else "General Skill Exchange"

    # Always create an in-app notification
    create_notification(
        recipient=sender,
        title=f"Match Request Accepted by {receiver.username}! 🎉",
        message=f"{receiver.username} accepted your match request for {skill_name}.",
        notification_type="match_accepted",
        link="/meetings",
    )

    if not should_send_email_to(sender):
        return

    scheduled_time = "Scheduled soon"
    if meeting and meeting.start_time:
        scheduled_time = meeting.start_time.strftime("%A, %B %d, %Y at %I:%M %p UTC")

    context = {
        "sender": {"username": sender.username},
        "receiver": {"username": receiver.username},
        "skill_name": skill_name,
        "meeting": {"room_url": getattr(meeting, 'room_url', '')} if meeting else {},
        "scheduled_time": scheduled_time,
    }

    _send_async_rendered_email(
        subject=f"Match Request Accepted by {receiver.username}! 🎉",
        template_name="emails/match_request_accepted.html",
        context=context,
        recipient_list=[sender.email],
    )


def send_match_request_rejected_email(match_request):
    sender = match_request.sender
    receiver = match_request.receiver
    skill_name = match_request.skill.name if match_request.skill else "General Skill Exchange"

    # Always create an in-app notification
    create_notification(
        recipient=sender,
        title=f"Match Request Update from {receiver.username}",
        message=f"{receiver.username} was unable to accept your request for {skill_name}.",
        notification_type="match_rejected",
        link="/my-requests",
    )

    if not should_send_email_to(sender):
        return

    context = {
        "sender": {"username": sender.username},
        "receiver": {"username": receiver.username},
        "skill_name": skill_name,
        "rejection_reason": match_request.rejection_reason or "",
    }

    _send_async_rendered_email(
        subject=f"Update on your SkillMatch request to {receiver.username}",
        template_name="emails/match_request_rejected.html",
        context=context,
        recipient_list=[sender.email],
    )


def send_meeting_cancelled_email(meeting, cancelled_by):
    request_obj = getattr(meeting, 'request', None)
    if not request_obj:
        return

    recipient = (
        request_obj.receiver
        if cancelled_by == request_obj.sender
        else request_obj.sender
    )

    skill_name = request_obj.skill.name if request_obj.skill else "Skill Session"

    # Always create an in-app notification
    create_notification(
        recipient=recipient,
        title=f"Meeting Cancelled: {skill_name} ⚠️",
        message=f"Your session with {cancelled_by.username} was cancelled.",
        notification_type="meeting_cancelled",
        link="/meetings",
    )

    if not should_send_email_to(recipient):
        return

    scheduled_time = meeting.start_time.strftime("%A, %B %d, %Y at %I:%M %p UTC") if meeting.start_time else "Scheduled Session"

    context = {
        "recipient": {"username": recipient.username},
        "cancelled_by": {"username": cancelled_by.username},
        "skill_name": skill_name,
        "scheduled_time": scheduled_time,
    }

    _send_async_rendered_email(
        subject=f"Meeting Cancelled: {skill_name} with {cancelled_by.username}",
        template_name="emails/meeting_cancelled.html",
        context=context,
        recipient_list=[recipient.email],
    )
