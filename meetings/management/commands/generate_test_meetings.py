import datetime
import uuid
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from meetings.models import SkillSwapMeeting
from meetings.video_service import DailyVideoService


class Command(BaseCommand):
    help = "Generate test Skill Swap meetings for frontend and backend testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing meetings before generating new ones.",
        )
        parser.add_argument(
            "--mock",
            action="store_true",
            help="Generate mock room URLs and tokens without contacting Daily.co API.",
        )
        parser.add_argument(
            "--user-a",
            type=str,
            default=None,
            help="Username for Participant A (default: first existing user).",
        )
        parser.add_argument(
            "--user-b",
            type=str,
            default=None,
            help="Username for Participant B (default: second existing user).",
        )
        parser.add_argument(
            "--set-password",
            type=str,
            default=None,
            help="Optionally set the same password for test users to make login easy (e.g. --set-password testpass123).",
        )
        parser.add_argument(
            "--scenario",
            type=str,
            choices=["all", "live", "upcoming", "ended"],
            default="all",
            help="Types of meetings to generate: all (default), live, upcoming, or ended.",
        )

    def handle(self, *args, **options):
        clear = options["clear"]
        use_mock = options["mock"]
        user_a_name = options["user_a"]
        user_b_name = options["user_b"]
        new_password = options["set_password"]
        scenario = options["scenario"]

        self.stdout.write(self.style.MIGRATE_HEADING("=== SkillMatch Test Meeting Generator ==="))

        if clear:
            deleted_count, _ = SkillSwapMeeting.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted_count} existing meetings."))

        # 1. Resolve or create test users
        user_a, user_b, user_c = self._get_or_create_users(user_a_name, user_b_name, new_password)

        self.stdout.write(
            f"Test Users: "
            f"A: [id={user_a.id}] {user_a.username} ({user_a.email}) | "
            f"B: [id={user_b.id}] {user_b.username} ({user_b.email})"
            + (f" | C: [id={user_c.id}] {user_c.username} ({user_c.email})" if user_c else "")
        )

        daily_service = DailyVideoService() if not use_mock else None
        now = timezone.now()

        # 2. Define meeting specs to create
        meetings_to_create = []

        if scenario in ["all", "live"]:
            # Live Meeting: started 5 minutes ago, ends in 55 minutes (can join right now!)
            meetings_to_create.append({
                "label": "LIVE NOW (Participant A & B)",
                "p_a": user_a,
                "p_b": user_b,
                "start": now - datetime.timedelta(minutes=5),
                "end": now + datetime.timedelta(minutes=55),
                "allow_daily": True,
            })
            if user_c:
                # Another live meeting between user_a and user_c
                meetings_to_create.append({
                    "label": "LIVE NOW (Participant A & C)",
                    "p_a": user_a,
                    "p_b": user_c,
                    "start": now - datetime.timedelta(minutes=2),
                    "end": now + datetime.timedelta(minutes=45),
                    "allow_daily": True,
                })

        if scenario in ["all", "upcoming"]:
            # Upcoming Meeting 1: In 2 hours today
            meetings_to_create.append({
                "label": "UPCOMING TODAY (+2 hours)",
                "p_a": user_a,
                "p_b": user_b,
                "start": now + datetime.timedelta(hours=2),
                "end": now + datetime.timedelta(hours=3),
                "allow_daily": True,
            })
            # Upcoming Meeting 2: Tomorrow
            meetings_to_create.append({
                "label": "UPCOMING TOMORROW (+24 hours)",
                "p_a": user_b,
                "p_b": user_a,
                "start": now + datetime.timedelta(days=1),
                "end": now + datetime.timedelta(days=1, hours=1),
                "allow_daily": True,
            })

        if scenario in ["all", "ended"]:
            # Ended Meeting: Yesterday (Daily doesn't allow past rooms, so this always uses mock)
            meetings_to_create.append({
                "label": "ENDED (Yesterday)",
                "p_a": user_a,
                "p_b": user_b,
                "start": now - datetime.timedelta(days=1, hours=2),
                "end": now - datetime.timedelta(days=1, hours=1),
                "allow_daily": False,
            })

        # 3. Create meetings
        created_meetings = []
        for spec in meetings_to_create:
            meeting = self._create_meeting(spec, daily_service, use_mock)
            created_meetings.append((spec["label"], meeting))

        # 4. Print Summary
        self.stdout.write("\n" + self.style.SUCCESS("--- Successfully Generated Meetings ---"))
        for label, m in created_meetings:
            self.stdout.write(
                f"\n* ID: {m.id} [{label}]\n"
                f"  Participants : {m.participant_a.username} <-> {m.participant_b.username}\n"
                f"  Start Time   : {m.start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"  End Time     : {m.end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"  Room URL     : {m.room_url}\n"
                f"  Token A      : {m.token_a[:25]}...\n"
                f"  Token B      : {m.token_b[:25]}..."
            )

        self.stdout.write("\n" + self.style.MIGRATE_LABEL("=== Testing Instructions ==="))
        self.stdout.write(
            f"1. Login to the frontend with user '{user_a.username}'\n"
            f"2. In an incognito / second browser window, login with user '{user_b.username}'\n"
            f"3. Navigate to the Meetings page (/meetings) on both accounts.\n"
            f"4. Click 'Join Room' on the LIVE meeting to start 1-on-1 video swap testing!"
        )

    def _get_or_create_users(self, username_a, username_b, set_password):
        users = list(User.objects.all().order_by("id"))

        user_a = None
        user_b = None
        user_c = None

        if username_a:
            user_a, _ = User.objects.get_or_create(username=username_a, defaults={"email": f"{username_a}@example.com"})
        elif len(users) >= 1:
            user_a = users[0]
        else:
            user_a = User.objects.create_user(username="Mohanned", email="mohanned@example.com", password="password123")

        if username_b:
            user_b, _ = User.objects.get_or_create(username=username_b, defaults={"email": f"{username_b}@example.com"})
        elif len(users) >= 2:
            # pick second user that is not user_a
            candidate = next((u for u in users if u.id != user_a.id), None)
            user_b = candidate if candidate else users[1]
        else:
            user_b = User.objects.create_user(username="Mohanned1", email="mohanned1@example.com", password="password123")

        # Check if there is a 3rd user in the database
        other_users = [u for u in users if u.id not in (user_a.id, user_b.id)]
        if other_users:
            user_c = other_users[0]

        if set_password:
            for u in [user_a, user_b, user_c]:
                if u:
                    u.set_password(set_password)
                    u.save()
            self.stdout.write(self.style.WARNING(f"Password for test users set to: '{set_password}'"))

        return user_a, user_b, user_c

    def _create_meeting(self, spec, daily_service, use_mock):
        start_time = spec["start"]
        end_time = spec["end"]
        p_a = spec["p_a"]
        p_b = spec["p_b"]
        allow_daily = spec.get("allow_daily", True) and not use_mock

        room_url = None
        token_a = None
        token_b = None

        if allow_daily and daily_service:
            start_ts = int(start_time.timestamp())
            end_ts = int(end_time.timestamp())
            try:
                room_data = daily_service.create_scheduled_room(start_ts, end_ts)
                room_name = room_data["name"]
                room_url = room_data["url"]
                token_a = daily_service.create_scheduled_token(room_name, p_a.username, start_ts, end_ts)
                token_b = daily_service.create_scheduled_token(room_name, p_b.username, start_ts, end_ts)
                self.stdout.write(self.style.SUCCESS(f"  [+] Created real Daily.co room: {room_url}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  [!] Daily.co API failed ({e}), falling back to mock room/tokens."))
                allow_daily = False

        if not allow_daily or not room_url:
            mock_id = uuid.uuid4().hex[:12]
            room_url = f"https://skillmatch-test.daily.co/test-room-{mock_id}"
            token_a = f"mock_token_{p_a.username}_{mock_id}"
            token_b = f"mock_token_{p_b.username}_{mock_id}"

        meeting = SkillSwapMeeting.objects.create(
            participant_a=p_a,
            participant_b=p_b,
            start_time=start_time,
            end_time=end_time,
            room_url=room_url,
            token_a=token_a,
            token_b=token_b,
        )
        return meeting
