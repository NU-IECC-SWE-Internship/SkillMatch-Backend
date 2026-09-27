import logging
import threading
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def should_send_email_to(user) -> bool:
    """
    Check if a user is eligible and has opted in to receive email notifications.
    """
    if not user or not getattr(user, 'email', None):
        return False

    profile = getattr(user, 'profile', None)
    if profile is not None and not profile.email_notifications_enabled:
        return False

    return True


def _send_async_rendered_email(subject: str, template_name: str, context: dict, recipient_list: list):
    """
    Renders an HTML email with plain-text fallback and sends it asynchronously in a background thread.
    """
    if not recipient_list:
        return

    # Add global site_url if not explicitly provided
    if 'site_url' not in context:
        context['site_url'] = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')

    def task():
        try:
            html_content = render_to_string(template_name, context)
            text_content = strip_tags(html_content)

            email_msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipient_list,
            )
            email_msg.attach_alternative(html_content, "text/html")
            email_msg.send(fail_silently=False)
            logger.info("Email '%s' successfully dispatched to %s", subject, recipient_list)
        except Exception as e:
            logger.error("Failed to send email '%s' to %s: %s", subject, recipient_list, str(e))
            print(f"[SkillMatch Email Error] Could not send '{subject}' to {recipient_list}: {str(e)}")

    thread = threading.Thread(target=task, daemon=True)
    thread.start()


def send_match_request_received_email(match_request):
    """
    Notifies the receiver that a new match request was submitted.
    """
    receiver = match_request.receiver
    if not should_send_email_to(receiver):
        return

    sender = match_request.sender
    skill_name = match_request.skill.name if match_request.skill else "General Skill Exchange"

    requested_slot = ""
    if getattr(match_request, 'selected_slot', None):
        slot = match_request.selected_slot
        day_str = str(slot.day).capitalize()
        start_str = slot.start_time.strftime('%I:%M %p') if hasattr(slot.start_time, 'strftime') else str(slot.start_time)
        end_str = slot.end_time.strftime('%I:%M %p') if hasattr(slot.end_time, 'strftime') else str(slot.end_time)
        requested_slot = f"{day_str} ({start_str} - {end_str})"

    context = {
        "receiver": receiver,
        "sender": sender,
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
    """
    Notifies the sender that their request was accepted and a session was scheduled.
    """
    sender = match_request.sender
    if not should_send_email_to(sender):
        return

    receiver = match_request.receiver
    skill_name = match_request.skill.name if match_request.skill else "General Skill Exchange"

    scheduled_time = "Scheduled soon"
    if meeting and meeting.start_time:
        scheduled_time = meeting.start_time.strftime("%A, %B %d, %Y at %I:%M %p UTC")

    context = {
        "sender": sender,
        "receiver": receiver,
        "skill_name": skill_name,
        "meeting": meeting,
        "scheduled_time": scheduled_time,
    }

    _send_async_rendered_email(
        subject=f"Match Request Accepted by {receiver.username}! 🎉",
        template_name="emails/match_request_accepted.html",
        context=context,
        recipient_list=[sender.email],
    )


def send_match_request_rejected_email(match_request):
    """
    Notifies the sender that their match request was declined.
    """
    sender = match_request.sender
    if not should_send_email_to(sender):
        return

    receiver = match_request.receiver
    skill_name = match_request.skill.name if match_request.skill else "General Skill Exchange"

    context = {
        "sender": sender,
        "receiver": receiver,
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
    """
    Notifies the other participant when a scheduled meeting is cancelled.
    """
    request_obj = getattr(meeting, 'request', None)
    if not request_obj:
        return

    recipient = (
        request_obj.receiver
        if cancelled_by == request_obj.sender
        else request_obj.sender
    )

    if not should_send_email_to(recipient):
        return

    skill_name = request_obj.skill.name if request_obj.skill else "Skill Session"
    scheduled_time = meeting.start_time.strftime("%A, %B %d, %Y at %I:%M %p UTC") if meeting.start_time else "Scheduled Session"

    context = {
        "recipient": recipient,
        "cancelled_by": cancelled_by,
        "skill_name": skill_name,
        "scheduled_time": scheduled_time,
    }

    _send_async_rendered_email(
        subject=f"Meeting Cancelled: {skill_name} with {cancelled_by.username}",
        template_name="emails/meeting_cancelled.html",
        context=context,
        recipient_list=[recipient.email],
    )
