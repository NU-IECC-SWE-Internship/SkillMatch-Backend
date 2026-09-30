from datetime import timedelta

from django.utils import timezone

from .models import PendingSkillQuiz, SkillQuizAttempt

QUIZ_COOLDOWN = timedelta(hours=24)
# Protects against double-clicks / React StrictMode re-sending Start.
START_GRACE = timedelta(seconds=10)


def expire_abandoned_quiz(user, skill):
    """
    A pending quiz that was started but never submitted counts as a failed
    attempt (score 0), which starts the normal cooldown.
    Returns True when an abandoned quiz was converted.
    """
    pending = PendingSkillQuiz.objects.filter(user=user, skill=skill).first()
    if pending is None:
        return False

    SkillQuizAttempt.objects.create(
        user=user,
        skill=skill,
        score=0,
        passed=False,
        abandoned=True,
    )
    pending.delete()
    return True


def latest_quiz_attempt(user, skill):
    return (
        SkillQuizAttempt.objects
        .filter(user=user, skill=skill)
        .order_by("-created_at", "-id")
        .first()
    )


def quiz_availability(user, skill, *, is_verified: bool = False):
    """
    Returns (can_take, latest_attempt, available_at).
    Verified skills don't need another quiz.
    After any attempt, wait QUIZ_COOLDOWN before retrying.
    """
    attempt = latest_quiz_attempt(user, skill)

    if is_verified:
        return False, attempt, None

    if attempt is None:
        return True, None, None

    available_at = attempt.created_at + QUIZ_COOLDOWN
    if timezone.now() >= available_at:
        return True, attempt, available_at

    return False, attempt, available_at
