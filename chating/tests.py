from django.test import TestCase
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from chating.consumers import save_message
from skillmatch.models import Notification

User = get_user_model()


class ChatNotificationTest(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="chat_sender", password="password123")
        self.user_b = User.objects.create_user(username="chat_receiver", password="password123")

    def test_save_message_creates_notification_for_receiver(self):
        msg = async_to_sync(save_message)(self.user_a.id, self.user_b.id, "Hello, are you ready for our skill swap?")
        self.assertIsNotNone(msg)
        notif = Notification.objects.filter(recipient=self.user_b, notification_type="chat_message").first()
        self.assertIsNotNone(notif)
        self.assertIn("chat_sender", notif.title)
        self.assertIn("Hello, are you ready", notif.message)
        self.assertEqual(notif.link, "/chat")

