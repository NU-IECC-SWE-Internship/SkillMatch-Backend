import logging
from celery import shared_task

from datetime import timedelta
from django.utils import timezone
from .models import Meeting
from skillmatch.notifications import create_notification
from skillmatch.emails import send_session_ended_rating_prompt

logger = logging.getLogger(__name__)


@shared_task(name="meetings.tasks.send_upcoming_meeting_reminders_task")
def send_upcoming_meeting_reminders_task():
    """
    Checks for scheduled meetings starting in the next 15-25 minutes
    and sends in-app + web push reminders to both participants.
    """
    now = timezone.now()
    window_end = now + timedelta(minutes=25)

    upcoming_meetings = Meeting.objects.filter(
        status="SCHEDULED",
        reminder_sent=False,
        start_time__gte=now,
        start_time__lte=window_end,
    ).select_related("request__sender", "request__receiver", "request__skill")

    count = 0
    for meeting in upcoming_meetings:
        sender = meeting.request.sender
        receiver = meeting.request.receiver
        skill_name = meeting.request.skill.name if meeting.request.skill else "Skill Exchange"
        mins_left = max(1, int((meeting.start_time - now).total_seconds() // 60))

        create_notification(
            recipient=sender,
            title=f"Session starting in {mins_left} mins! ⏰",
            message=f"Your {skill_name} session with {receiver.username} starts shortly. Click to join!",
            notification_type="meeting_reminder",
            link="/meetings",
        )

        create_notification(
            recipient=receiver,
            title=f"Session starting in {mins_left} mins! ⏰",
            message=f"Your {skill_name} session with {sender.username} starts shortly. Click to join!",
            notification_type="meeting_reminder",
            link="/meetings",
        )

        meeting.reminder_sent = True
        meeting.save(update_fields=["reminder_sent"])
        count += 1

    return count


@shared_task(name="meetings.tasks.complete_concluded_meetings_and_prompt_ratings_task")
def complete_concluded_meetings_and_prompt_ratings_task():
    """
    Finds meetings whose end_time has passed, marks them COMPLETED,
    and sends rating prompts to both participants.
    """
    now = timezone.now()
    Meeting.objects.filter(
        status="SCHEDULED",
        end_time__lt=now,
    ).update(status="COMPLETED")

    completed_meetings = Meeting.objects.filter(
        status="COMPLETED",
        rating_prompt_sent=False,
        end_time__lt=now,
    ).select_related("request__sender", "request__receiver", "request__skill")

    count = 0
    for meeting in completed_meetings:
        send_session_ended_rating_prompt(meeting)
        meeting.rating_prompt_sent = True
        meeting.save(update_fields=["rating_prompt_sent"])
        count += 1

    return count


@shared_task(name="meetings.tasks.process_expired_ratings_task")
def process_expired_ratings_task():
    """
    Periodic Celery task that checks for unrevealed meeting ratings
    whose review window has passed (or where both parties have submitted)
    and reveals them, updating affected users' average rating and review counts.
    """
    logger.info("Celery: Starting process_expired_ratings_task...")
    try:
        from .views import process_expired_ratings
        count = process_expired_ratings()
        logger.info("Celery: process_expired_ratings_task completed successfully. Processed %s meeting(s).", count)
        return count
    except Exception as exc:
        logger.error("Celery: Error executing process_expired_ratings_task: %s", exc)
        raise exc
