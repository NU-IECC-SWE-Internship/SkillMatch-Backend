from datetime import timedelta

from django.utils import timezone

from system_config.services import get_config, get_hours, get_seconds

from .models import PendingSkillQuiz, SkillQuizAttempt

# Must match QUESTION_SECONDS in the frontend quiz page.
SECONDS_PER_QUESTION = 20


def quiz_time_limit():
    """After this long an unsubmitted quiz can no longer be in progress."""
    return timedelta(
        seconds=get_config("quiz.question_count") * SECONDS_PER_QUESTION + 60
    )


def max_attempts():
    return get_config("quiz.max_attempts")


def attempt_window():
    return get_hours("quiz.attempt_window_hours")


def counted_attempt_times(user, skill):
    """Start times (oldest first) of attempts that count toward the current window."""
    return list(
        SkillQuizAttempt.objects
        .filter(
            user=user,
            skill=skill,
            excused=False,
            created_at__gt=timezone.now() - attempt_window(),
        )
        .order_by("created_at", "id")
        .values_list("created_at", flat=True)
    )


def attempts_left(user, skill):
    return max(max_attempts() - len(counted_attempt_times(user, skill)), 0)


def reset_attempts(user, skill):
    """Give the user a full set of attempts again; history is kept."""
    expire_abandoned_quiz(user, skill)
    return SkillQuizAttempt.objects.filter(user=user, skill=skill, excused=False).update(
        excused=True
    )


def start_grace():
    # Protects against double-clicks / React StrictMode re-sending Start.
    return get_seconds("quiz.start_grace_seconds")


def expire_abandoned_quiz(user, skill):
    """
    A pending quiz that was started but never submitted counts as a failed
    attempt (score 0) and uses up one of the user's attempts.
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


def expire_timed_out_quiz(user, skill):
    """Count a quiz that was started but ran out of time as a failed attempt."""
    timed_out = PendingSkillQuiz.objects.filter(
        user=user,
        skill=skill,
        created_at__lte=timezone.now() - quiz_time_limit(),
    ).exists()
    return expire_abandoned_quiz(user, skill) if timed_out else False


def latest_submitted_attempt(user, skill):
    """
    Most recent attempt the user actually submitted (abandoned ones are skipped).
    Attempts from before answers were stored have an empty `review`.
    """
    return (
        SkillQuizAttempt.objects
        .filter(user=user, skill=skill, abandoned=False)
        .order_by("-created_at", "-id")
        .first()
    )


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
    Users get `quiz.max_attempts` attempts per rolling window; once they are
    used up, `available_at` is when the oldest one drops out of the window.
    """
    if is_verified:
        return False, latest_quiz_attempt(user, skill), None

    expire_timed_out_quiz(user, skill)
    attempt = latest_quiz_attempt(user, skill)
    recent = counted_attempt_times(user, skill)
    limit = max_attempts()

    if len(recent) < limit:
        return True, attempt, None

    return False, attempt, recent[len(recent) - limit] + attempt_window()
