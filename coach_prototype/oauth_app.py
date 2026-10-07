"""Dedicated Strava OAuth service. Run only on 127.0.0.1:2024.

OAuth state is single-use and bound to the signed UI session. Refresh tokens
are encrypted at rest; provider credentials and tokens are never logged or
returned to the browser.
"""
import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app import COOKIE, Base, OAuthState, SessionLocal, StravaConnection, User, engine, verify_session

CLIENT_ID = os.getenv('STRAVA_CLIENT_ID', '').strip()
CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET', '').strip()
REDIRECT_URI = os.getenv('STRAVA_REDIRECT_URI', 'https://proto.fu19.org/auth/callback').strip()
TOKEN_FERNET_KEY = os.getenv('STRAVA_TOKEN_FERNET_KEY', '').strip()
AUTH_URL = 'https://www.strava.com/oauth/authorize'
TOKEN_URL = 'https://www.strava.com/oauth/token'
REQUIRED_SCOPES = {'activity:read_all', 'profile:read_all'}
STATE_LIFETIME = timedelta(minutes=10)


def state_digest(state: str) -> str:
    return hashlib.sha256(state.encode('utf-8')).hexdigest()


def get_fernet() -> Fernet:
    if not TOKEN_FERNET_KEY:
        raise HTTPException(status_code=503, detail='Strava token encryption is not configured')
    try:
        return Fernet(TOKEN_FERNET_KEY.encode('ascii'))
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(status_code=503, detail='Strava token encryption key is invalid') from exc


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _check_config() -> None:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=503, detail='Strava client credentials are not configured')
    if REDIRECT_URI != 'https://proto.fu19.org/auth/callback':
        raise HTTPException(status_code=503, detail='Strava redirect URI does not match this deployment')
    get_fernet()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same isolated coach_proto database; safe if either service starts first.
    Base.metadata.create_all(engine)
    yield


oauth_app = FastAPI(title='Coach Strava OAuth', lifespan=lifespan, docs_url=None, redoc_url=None)


@oauth_app.get('/health')
def health():
    return {'status': 'oauth-ready' if CLIENT_ID and CLIENT_SECRET and TOKEN_FERNET_KEY else 'oauth-not-configured'}


@oauth_app.get('/auth/strava')
def begin_authorization(request: Request):
    user_id = verify_session(request.cookies.get(COOKIE))
    if user_id is None:
        return RedirectResponse('/login', status_code=303)
    _check_config()

    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        if db.get(User, user_id) is None:
            return RedirectResponse('/login', status_code=303)
        db.query(OAuthState).filter(OAuthState.expires_at < now).delete(synchronize_session=False)
        db.add(OAuthState(state_hash=state_digest(state), user_id=user_id, expires_at=now + STATE_LIFETIME))

    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'approval_prompt': 'auto',
        'scope': 'read,activity:read_all,profile:read_all',
        'state': state,
    }
    return RedirectResponse(f'{AUTH_URL}?{urlencode(params)}', status_code=302)


@oauth_app.get('/auth/callback')
def authorization_callback(
    request: Request,
    code: str | None = Query(default=None, max_length=512),
    state: str | None = Query(default=None, max_length=256),
    error: str | None = Query(default=None, max_length=80),
):
    if error:
        return RedirectResponse('/app?strava=denied', status_code=303)
    if not code or not state:
        raise HTTPException(status_code=400, detail='OAuth callback is missing required parameters')
    _check_config()

    user_id = verify_session(request.cookies.get(COOKIE))
    if user_id is None:
        raise HTTPException(status_code=401, detail='Please log in again before connecting Strava')

    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        saved = db.scalar(select(OAuthState).where(OAuthState.state_hash == state_digest(state)).with_for_update())
        if saved is None or saved.user_id != user_id or _aware(saved.expires_at) <= now:
            raise HTTPException(status_code=400, detail='OAuth state is invalid, expired, or already used')
        db.delete(saved)  # one-time state; a failed exchange requires restarting OAuth

    try:
        response = httpx.post(
            TOKEN_URL,
            data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
                  'code': code, 'grant_type': 'authorization_code'},
            timeout=20.0,
        )
        response.raise_for_status()
        token_data = response.json()
    except (httpx.HTTPError, ValueError):
        # Never include provider response, authorization code, or credentials in logs/errors.
        raise HTTPException(status_code=502, detail='Strava token exchange failed; restart authorization')

    athlete = token_data.get('athlete') or {}
    refresh_token = token_data.get('refresh_token')
    expires_at = token_data.get('expires_at')
    scopes = set(str(token_data.get('scope', '')).replace(',', ' ').split())
    strava_id = athlete.get('id')
    if not refresh_token or not expires_at or not strava_id:
        raise HTTPException(status_code=502, detail='Strava response did not include required athlete credentials')
    if not REQUIRED_SCOPES.issubset(scopes):
        raise HTTPException(status_code=403, detail='Required Strava scopes were not granted; reconnect and approve activity/profile access')

    encrypted_refresh = get_fernet().encrypt(refresh_token.encode('utf-8')).decode('ascii')
    athlete_name = ' '.join(part for part in (athlete.get('firstname'), athlete.get('lastname')) if part).strip() or 'Strava athlete'
    profile_url = athlete.get('profile') or athlete.get('profile_medium')
    expiry = datetime.fromtimestamp(int(expires_at), tz=timezone.utc)
    with SessionLocal.begin() as db:
        owner = db.scalar(select(StravaConnection).where(StravaConnection.strava_athlete_id == int(strava_id)))
        if owner is not None and owner.user_id != user_id:
            raise HTTPException(status_code=409, detail='This Strava athlete is already linked to another account')
        connection = db.scalar(select(StravaConnection).where(StravaConnection.user_id == user_id))
        if connection is None:
            connection = StravaConnection(user_id=user_id, strava_athlete_id=int(strava_id),
                athlete_name=athlete_name, profile_pic_url=profile_url,
                refresh_token_encrypted=encrypted_refresh, token_expires_at=expiry,
                scopes=' '.join(sorted(scopes)))
            db.add(connection)
        else:
            connection.strava_athlete_id = int(strava_id)
            connection.athlete_name = athlete_name
            connection.profile_pic_url = profile_url
            connection.refresh_token_encrypted = encrypted_refresh
            connection.token_expires_at = expiry
            connection.scopes = ' '.join(sorted(scopes))
            connection.updated_at = now
    return RedirectResponse('/app?strava=connected', status_code=303)


@oauth_app.post('/auth/strava/refresh')
def refresh_connection(request: Request):
    """Refresh for the current user and persist Strava's newly rotated refresh token."""
    user_id = verify_session(request.cookies.get(COOKIE))
    if user_id is None:
        raise HTTPException(status_code=401, detail='Login required')
    _check_config()
    fernet = get_fernet()
    with SessionLocal.begin() as db:
        connection = db.scalar(select(StravaConnection).where(StravaConnection.user_id == user_id).with_for_update())
        if connection is None:
            raise HTTPException(status_code=404, detail='No Strava connection for this account')
        try:
            current_refresh = fernet.decrypt(connection.refresh_token_encrypted.encode('ascii')).decode('utf-8')
        except (InvalidToken, UnicodeEncodeError):
            raise HTTPException(status_code=500, detail='Stored Strava credential cannot be decrypted')
        try:
            response = httpx.post(TOKEN_URL, data={
                'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
                'grant_type': 'refresh_token', 'refresh_token': current_refresh,
            }, timeout=20.0)
            response.raise_for_status()
            token_data = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail='Strava refresh failed; reconnect the account')
        rotated_refresh = token_data.get('refresh_token')
        expiry = token_data.get('expires_at')
        if not rotated_refresh or not expiry:
            raise HTTPException(status_code=502, detail='Strava refresh response is incomplete')
        connection.refresh_token_encrypted = fernet.encrypt(rotated_refresh.encode('utf-8')).decode('ascii')
        connection.token_expires_at = datetime.fromtimestamp(int(expiry), tz=timezone.utc)
        connection.updated_at = datetime.now(timezone.utc)
        safe_expiry = connection.token_expires_at.isoformat()
    return {'status': 'refreshed', 'token_expires_at': safe_expiry}


@oauth_app.get('/auth/status')
def authorization_status(request: Request):
    user_id = verify_session(request.cookies.get(COOKIE))
    if user_id is None:
        raise HTTPException(status_code=401, detail='Login required')
    with SessionLocal() as db:
        connection = db.scalar(select(StravaConnection).where(StravaConnection.user_id == user_id))
        if connection is None:
            return {'connected': False}
        return {'connected': True, 'athlete_name': connection.athlete_name,
                'strava_athlete_id': connection.strava_athlete_id, 'scopes': connection.scopes,
                'token_expires_at': _aware(connection.token_expires_at).isoformat()}


# Dedicated systemd process listens on 127.0.0.1:2024.
app = oauth_app
