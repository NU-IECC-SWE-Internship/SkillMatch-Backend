"""
Weekly times already taken by open requests.

A request asks for a recurring weekly time (slot day + requested start/end).
While it's open, nobody else may request an overlapping time from the same
person, and neither participant may book another overlapping time.
"""

from django.db.models import Q

from .models import MatchRequest

OPEN_STATUSES = ["PENDING", "SCHEDULING", "CONFIRMING"]


def _sessions(request):
    """(day, start, end) for each session a request reserves."""
    sessions = []
    if request.selected_slot_id:
        sessions.append((
            request.selected_slot.day.lower(),
            request.requested_start_time or request.selected_slot.start_time,
            request.requested_end_time or request.selected_slot.end_time,
        ))
    # Return session proposed in the sender's availability.
    if request.receiver_selected_slot_id:
        sessions.append((
            request.receiver_selected_slot.day.lower(),
            request.receiver_requested_start_time or request.receiver_selected_slot.start_time,
            request.receiver_requested_end_time or request.receiver_selected_slot.end_time,
        ))
    return sessions


def requested_times(user, exclude_request_id=None):
    """Weekly times reserved by open requests the user is part of."""
    requests = (
        MatchRequest.objects
        .filter(status__in=OPEN_STATUSES)
        .filter(Q(sender=user) | Q(receiver=user))
        .select_related("selected_slot", "receiver_selected_slot")
    )
    if exclude_request_id:
        requests = requests.exclude(pk=exclude_request_id)

    times = []
    for request in requests:
        times.extend(_sessions(request))
    return times


def overlaps(day, start, end, times):
    """True if day/start-end overlaps any (day, start, end) in times."""
    day = day.lower()
    return any(
        day == busy_day and start < busy_end and end > busy_start
        for busy_day, busy_start, busy_end in times
    )
