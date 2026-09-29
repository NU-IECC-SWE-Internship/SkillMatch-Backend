from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def user_from_token(raw_token):
    try:
        token = AccessToken(raw_token)
        return get_user_model().objects.get(
            pk=token['user_id'],
            is_active=True,
        )
    except (InvalidToken, TokenError, KeyError, get_user_model().DoesNotExist):
        return AnonymousUser()


class JwtAuthMiddleware:
    """Read the same short-lived access token used by the REST API."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get('query_string', b'').decode())
        token = query.get('token', [''])[0]
        scope['user'] = await user_from_token(token) if token else AnonymousUser()
        return await self.app(scope, receive, send)
