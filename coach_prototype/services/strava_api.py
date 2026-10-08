"""Small authenticated Strava API client for the isolated Coach database.

It deliberately does not persist short-lived access tokens. Strava rotates the
refresh token on refresh, so the encrypted latest refresh token is committed
before a client is returned.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import StravaConnection

TOKEN_URL = 'https://www.strava.com/oauth/token'
API_URL = 'https://www.strava.com/api/v3'


class StravaAPIError(RuntimeError):
    pass


@dataclass
class Stream:
    data: list


class StravaAPIClient:
    def __init__(self, access_token: str, timeout: float = 30.0):
        self.access_token = access_token
        self.timeout = timeout

    @property
    def headers(self):
        return {'Authorization': f'Bearer {self.access_token}'}

    def list_activities(self, *, per_page: int, page: int, after: int | None = None):
        params = {'per_page': per_page, 'page': page}
        if after is not None:
            params['after'] = after
        response = httpx.get(f'{API_URL}/athlete/activities', headers=self.headers,
                             params=params, timeout=self.timeout)
        try:
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StravaAPIError('Strava activity list request failed') from exc
        if not isinstance(result, list):
            raise StravaAPIError('Strava returned an invalid activity list')
        return result

    def get_activity_streams(self, strava_id, *, types, resolution='high'):
        """Fetch the requested channel set in exactly one high-res stream call."""
        response = httpx.get(
            f'{API_URL}/activities/{int(strava_id)}/streams',
            headers=self.headers,
            params={'keys': ','.join(types), 'key_by_type': 'true', 'resolution': resolution},
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StravaAPIError(f'Strava streams request failed for activity {strava_id}') from exc
        if not isinstance(payload, dict):
            raise StravaAPIError('Strava returned an invalid streams object')
        return {name: Stream(data=value.get('data', [])) if isinstance(value, dict) else Stream(data=value)
                for name, value in payload.items()}


def get_strava_client(db: Session, user_id: int) -> StravaAPIClient:
    """Refresh the current user's OAuth grant and return an authenticated client."""
    client_id = os.getenv('STRAVA_CLIENT_ID', '').strip()
    client_secret = os.getenv('STRAVA_CLIENT_SECRET', '').strip()
    key = os.getenv('STRAVA_TOKEN_FERNET_KEY', '').strip()
    if not client_id or not client_secret or not key:
        raise StravaAPIError('Strava credentials/token-encryption key are not configured')
    try:
        cipher = Fernet(key.encode('ascii'))
    except (ValueError, UnicodeEncodeError) as exc:
        raise StravaAPIError('Strava token-encryption key is invalid') from exc

    connection = db.scalar(select(StravaConnection).where(StravaConnection.user_id == user_id).with_for_update())
    if connection is None:
        raise StravaAPIError('No Strava athlete is connected to this Coach user')
    try:
        refresh_token = cipher.decrypt(connection.refresh_token_encrypted.encode('ascii')).decode('utf-8')
    except (InvalidToken, UnicodeEncodeError) as exc:
        raise StravaAPIError('Stored Strava refresh token cannot be decrypted') from exc

    try:
        response = httpx.post(TOKEN_URL, data={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise StravaAPIError('Strava token refresh failed; user must reconnect') from exc

    access_token = payload.get('access_token')
    rotated_refresh = payload.get('refresh_token')
    expires_at = payload.get('expires_at')
    if not access_token or not rotated_refresh or not expires_at:
        raise StravaAPIError('Strava token refresh response is incomplete')
    # Persist the latest rotating refresh credential in the caller's transaction.
    connection.refresh_token_encrypted = cipher.encrypt(rotated_refresh.encode('utf-8')).decode('ascii')
    connection.token_expires_at = datetime.fromtimestamp(int(expires_at), tz=timezone.utc)
    connection.updated_at = datetime.now(timezone.utc)
    # Strava invalidates the previous refresh token when rotating. Commit this
    # credential before any follow-up activity/stream calls can fail.
    db.commit()
    return StravaAPIClient(access_token)
