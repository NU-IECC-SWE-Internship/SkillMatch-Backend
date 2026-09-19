import os
import requests
from django.conf import settings

class DailyVideoService:
    def __init__(self):
        self.api_key = getattr(settings, 'DAILY_API_KEY', '') or os.environ.get('DAILY_API_KEY', '')
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.base_url = "https://api.daily.co/v1"

    def create_scheduled_room(self, start_timestamp, end_timestamp):
        payload = {
            "privacy": "private",
            "properties": {
                "max_participants": 2,
                "nbf": start_timestamp - 600,
                "exp": end_timestamp + 600,
                "enable_screenshare": True,
            }
        }
        response = requests.post(f"{self.base_url}/rooms", headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def create_scheduled_token(self, room_name, user_name, start_timestamp, end_timestamp):
        payload = {
            "properties": {
                "room_name": room_name,
                "user_name": user_name,
                "is_owner": False,
                "nbf": start_timestamp - 600,
                "exp": end_timestamp + 600,
            }
        }
        response = requests.post(f"{self.base_url}/meeting-tokens", headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()["token"]
