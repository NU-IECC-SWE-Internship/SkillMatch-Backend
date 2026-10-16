from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from matching.models import MatchRequest
from skillmatch.models import Skill, AvailabilitySlot, Profile
from meetings.models import Meeting, MeetingRating
from meetings.tasks import process_expired_ratings_task

User = get_user_model()


class ProcessExpiredRatingsTaskTest(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a", password="password123")
        self.user_b = User.objects.create_user(username="user_b", password="password123")

        self.skill = Skill.objects.create(name="Python", is_approved=True)
        self.slot = AvailabilitySlot.objects.create(
            user=self.user_b,
            day="Monday",
            start_time="10:00:00",
            end_time="11:00:00",
        )
        self.match_request = MatchRequest.objects.create(
            sender=self.user_a,
            receiver=self.user_b,
            skill=self.skill,
            selected_slot=self.slot,
            status="ACCEPTED",
        )

    def test_process_expired_ratings_task_reveals_past_deadline(self):
        # Meeting ended 50 hours ago (beyond the 48 hour review window)
        now = timezone.now()
        end_time = now - timedelta(hours=50)
        start_time = end_time - timedelta(hours=1)

        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start_time,
            end_time=end_time,
            status="COMPLETED",
        )

        rating = MeetingRating.objects.create(
            meeting=meeting,
            reviewer=self.user_a,
            reviewed_user=self.user_b,
            score=5,
            feedback="Great session!",
            is_revealed=False,
        )

        # Run the periodic Celery task
        revealed_count = process_expired_ratings_task()
        self.assertEqual(revealed_count, 1)

        rating.refresh_from_db()
        self.assertTrue(rating.is_revealed)
        self.assertIsNotNone(rating.revealed_at)

        # Profile rating stats should be updated
        profile_b = Profile.objects.get(user=self.user_b)
        self.assertEqual(profile_b.rating_average, 5.0)
        self.assertEqual(profile_b.rating_count, 1)

    def test_process_expired_ratings_task_keeps_recent_single_review_private(self):
        # Meeting ended 2 hours ago (within 48 hour window)
        now = timezone.now()
        end_time = now - timedelta(hours=2)
        start_time = end_time - timedelta(hours=1)

        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start_time,
            end_time=end_time,
            status="COMPLETED",
        )

        rating = MeetingRating.objects.create(
            meeting=meeting,
            reviewer=self.user_a,
            reviewed_user=self.user_b,
            score=4,
            feedback="Nice session",
            is_revealed=False,
        )

        # Run task
        revealed_count = process_expired_ratings_task()
        self.assertEqual(revealed_count, 0)

        rating.refresh_from_db()
        self.assertFalse(rating.is_revealed)
        self.assertIsNone(rating.revealed_at)

        profile_b = Profile.objects.filter(user=self.user_b).first()
        if profile_b:
            self.assertEqual(profile_b.rating_count, 0)

    def test_process_expired_ratings_task_reveals_when_both_rated(self):
        # Meeting ended 1 hour ago, but both users submitted reviews
        now = timezone.now()
        end_time = now - timedelta(hours=1)
        start_time = end_time - timedelta(hours=1)

        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start_time,
            end_time=end_time,
            status="COMPLETED",
        )

        rating_a = MeetingRating.objects.create(
            meeting=meeting,
            reviewer=self.user_a,
            reviewed_user=self.user_b,
            score=5,
            feedback="Awesome!",
            is_revealed=False,
        )
        rating_b = MeetingRating.objects.create(
            meeting=meeting,
            reviewer=self.user_b,
            reviewed_user=self.user_a,
            score=4,
            feedback="Helpful!",
            is_revealed=False,
        )

        # Run task
        revealed_count = process_expired_ratings_task()
        self.assertEqual(revealed_count, 1)

        rating_a.refresh_from_db()
        rating_b.refresh_from_db()
        self.assertTrue(rating_a.is_revealed)
        self.assertTrue(rating_b.is_revealed)

        profile_a = Profile.objects.get(user=self.user_a)
        profile_b = Profile.objects.get(user=self.user_b)
        self.assertEqual(profile_a.rating_average, 4.0)
        self.assertEqual(profile_b.rating_average, 5.0)

    def test_send_upcoming_meeting_reminders_task(self):
        from meetings.tasks import send_upcoming_meeting_reminders_task
        from skillmatch.models import Notification

        now = timezone.now()
        start_time = now + timedelta(minutes=10)
        end_time = start_time + timedelta(hours=1)

        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start_time,
            end_time=end_time,
            status="SCHEDULED",
            reminder_sent=False,
        )

        count = send_upcoming_meeting_reminders_task()
        self.assertEqual(count, 1)

        meeting.refresh_from_db()
        self.assertTrue(meeting.reminder_sent)

        reminders = Notification.objects.filter(notification_type="meeting_reminder")
        self.assertEqual(reminders.count(), 2)

    def test_complete_concluded_meetings_and_prompt_ratings_task(self):
        from meetings.tasks import complete_concluded_meetings_and_prompt_ratings_task
        from skillmatch.models import Notification

        now = timezone.now()
        end_time = now - timedelta(minutes=10)
        start_time = end_time - timedelta(hours=1)

        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start_time,
            end_time=end_time,
            status="SCHEDULED",
            rating_prompt_sent=False,
        )

        count = complete_concluded_meetings_and_prompt_ratings_task()
        self.assertEqual(count, 1)

        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "COMPLETED")
        self.assertTrue(meeting.rating_prompt_sent)

        prompts = Notification.objects.filter(notification_type="rating_prompt")
        self.assertEqual(prompts.count(), 2)


class MeetingCancellationRulesTest(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.user_a = User.objects.create_user(username="canceller_a", password="password123")
        self.user_b = User.objects.create_user(username="canceller_b", password="password123")
        self.stranger = User.objects.create_user(username="stranger", password="password123")

        self.skill = Skill.objects.create(name="Django", is_approved=True)
        self.slot = AvailabilitySlot.objects.create(
            user=self.user_b,
            day="Tuesday",
            start_time="14:00:00",
            end_time="15:00:00",
        )
        self.match_request = MatchRequest.objects.create(
            sender=self.user_a,
            receiver=self.user_b,
            skill=self.skill,
            selected_slot=self.slot,
            status="ACCEPTED",
        )

    def test_cancel_future_meeting_outside_notice_window_with_reason(self):
        now = timezone.now()
        start = now + timedelta(hours=5)
        end = start + timedelta(hours=1)
        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start,
            end_time=end,
            status="SCHEDULED",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(
            f"/api/meetings/{meeting.id}/",
            data={"reason": "Sudden emergency at work"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "CANCELLED")
        self.assertEqual(meeting.cancellation_reason, "Sudden emergency at work")
        self.assertEqual(meeting.cancelled_by, self.user_a)
        self.assertIsNotNone(meeting.cancelled_at)
        self.assertEqual(meeting.request.status, "CANCELLED")

    def test_cannot_cancel_without_reason(self):
        now = timezone.now()
        start = now + timedelta(hours=5)
        end = start + timedelta(hours=1)
        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start,
            end_time=end,
            status="SCHEDULED",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(
            f"/api/meetings/{meeting.id}/",
            data={"reason": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("reason is required", response.data.get("error", "").lower())
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "SCHEDULED")

    def test_cannot_cancel_within_notice_window(self):
        now = timezone.now()
        start = now + timedelta(hours=1)
        end = start + timedelta(hours=1)
        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start,
            end_time=end,
            status="SCHEDULED",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(
            f"/api/meetings/{meeting.id}/",
            data={"reason": "Late conflict"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("within 2 hours", response.data.get("error", "").lower())
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, "SCHEDULED")

    def test_cannot_cancel_past_or_in_progress_meeting(self):
        now = timezone.now()
        start = now - timedelta(minutes=15)
        end = now + timedelta(minutes=45)
        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start,
            end_time=end,
            status="SCHEDULED",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(
            f"/api/meetings/{meeting.id}/",
            data={"reason": "Started already"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already started", response.data.get("error", "").lower())

    def test_cannot_cancel_completed_meeting(self):
        now = timezone.now()
        start = now - timedelta(hours=2)
        end = now - timedelta(hours=1)
        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start,
            end_time=end,
            status="COMPLETED",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(
            f"/api/meetings/{meeting.id}/",
            data={"reason": "Want to cancel old"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot cancel a completed meeting", response.data.get("error", "").lower())

    def test_cannot_cancel_already_cancelled_meeting(self):
        now = timezone.now()
        start = now + timedelta(hours=5)
        end = start + timedelta(hours=1)
        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start,
            end_time=end,
            status="CANCELLED",
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(
            f"/api/meetings/{meeting.id}/",
            data={"reason": "Again"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already been cancelled", response.data.get("error", "").lower())

    def test_stranger_cannot_cancel_meeting(self):
        now = timezone.now()
        start = now + timedelta(hours=5)
        end = start + timedelta(hours=1)
        meeting = Meeting.objects.create(
            request=self.match_request,
            session_type="REQUESTED_SKILL",
            start_time=start,
            end_time=end,
            status="SCHEDULED",
        )

        self.client.force_authenticate(user=self.stranger)
        response = self.client.delete(
            f"/api/meetings/{meeting.id}/",
            data={"reason": "I am a stranger"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)


