from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from skillmatch.models import Skill, AvailabilitySlot, Notification
from matching.models import MatchRequest

User = get_user_model()


class ReturnSessionNotificationsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_sender = User.objects.create_user(username="req_sender", password="password123")
        self.user_receiver = User.objects.create_user(username="req_receiver", password="password123")

        self.skill_a = Skill.objects.create(name="Python", is_approved=True)
        self.skill_b = Skill.objects.create(name="Design", is_approved=True)

        self.slot_receiver = AvailabilitySlot.objects.create(
            user=self.user_receiver,
            day="Wednesday",
            start_time="10:00:00",
            end_time="11:00:00",
        )
        self.slot_sender = AvailabilitySlot.objects.create(
            user=self.user_sender,
            day="Thursday",
            start_time="15:00:00",
            end_time="16:00:00",
        )

        self.match_request = MatchRequest.objects.create(
            sender=self.user_sender,
            receiver=self.user_receiver,
            skill=self.skill_a,
            selected_slot=self.slot_receiver,
            status="SCHEDULING",
            receiver_skill=self.skill_b,
        )

    def test_schedule_return_notifies_sender(self):
        self.client.force_authenticate(user=self.user_receiver)
        response = self.client.post(
            f"/api/requests/{self.match_request.id}/respond/",
            data={
                "action": "schedule_return",
                "receiver_selected_slot": self.slot_sender.id,
                "receiver_requested_start_time": "15:00:00",
                "receiver_requested_end_time": "16:00:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        notif = Notification.objects.filter(
            recipient=self.user_sender,
            notification_type="return_session_proposed",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("req_receiver", notif.title)
        self.assertIn("Design", notif.message)

    def test_decline_return_notifies_receiver(self):
        self.match_request.status = "CONFIRMING"
        self.match_request.receiver_selected_slot = self.slot_sender
        self.match_request.save()

        self.client.force_authenticate(user=self.user_sender)
        response = self.client.post(
            f"/api/requests/{self.match_request.id}/respond/",
            data={"action": "decline_return"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        notif = Notification.objects.filter(
            recipient=self.user_receiver,
            notification_type="return_session_declined",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("req_sender", notif.message)

