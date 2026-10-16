from django.core.management.base import BaseCommand
from meetings.views import process_expired_ratings


class Command(BaseCommand):
    help = "Process unrevealed meeting ratings where the review window has expired or both parties submitted."

    def handle(self, *args, **options):
        self.stdout.write("Checking for expired or mutually submitted meeting ratings...")
        count = process_expired_ratings()
        self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} meeting(s)."))
