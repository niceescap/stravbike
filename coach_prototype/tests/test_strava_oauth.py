"""OAuth route smoke tests; deliberately make no requests to Strava."""
import os
import secrets
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

_test_db = tempfile.TemporaryDirectory()
os.environ.setdefault('TESTING', '1')
os.environ.setdefault('DATABASE_URL', f"sqlite:///{_test_db.name}/oauth.db")
os.environ.setdefault('SESSION_SECRET', 'oauth-tests-only-session-secret-0123456789abcdef')
os.environ.setdefault('DEMO_MODE', '1')
os.environ.setdefault('DEMO_PASSWORD', 'test-password')
os.environ.setdefault('STRAVA_CLIENT_ID', '123456')
os.environ.setdefault('STRAVA_CLIENT_SECRET', 'test-client-secret-not-real')
os.environ.setdefault('STRAVA_REDIRECT_URI', 'https://proto.fu19.org/auth/callback')
os.environ.setdefault('STRAVA_TOKEN_FERNET_KEY', Fernet.generate_key().decode('ascii'))

from fastapi.testclient import TestClient  # noqa: E402
import app as coach  # noqa: E402
import oauth_app as oauth  # noqa: E402


class StravaOAuthRouteTests(unittest.TestCase):
    def setUp(self):
        coach.seed_demo()
        with coach.SessionLocal() as db:
            self.user_id = db.scalar(coach.select(coach.User.id).where(coach.User.email == 'fake_user@test.local'))
        self.client_context = TestClient(oauth.oauth_app, base_url='https://testserver')
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        with coach.SessionLocal.begin() as db:
            db.query(coach.OAuthState).filter(coach.OAuthState.user_id == self.user_id).delete(synchronize_session=False)
            db.query(coach.StravaConnection).filter(coach.StravaConnection.user_id == self.user_id).delete(synchronize_session=False)

    def test_authorize_requires_local_login(self):
        response = self.client.get('/auth/strava', follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/login')

    def test_authorize_uses_domain_callback_and_persisted_one_time_state(self):
        self.client.cookies.set(coach.COOKIE, coach.sign_session(self.user_id), secure=True)
        response = self.client.get('/auth/strava', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        location = urlparse(response.headers['location'])
        query = parse_qs(location.query)
        self.assertEqual(location.scheme, 'https')
        self.assertEqual(location.netloc, 'www.strava.com')
        self.assertEqual(query['redirect_uri'], ['https://proto.fu19.org/auth/callback'])
        self.assertEqual(query['client_id'], ['123456'])
        self.assertIn('activity:read_all', query['scope'][0])
        with coach.SessionLocal() as db:
            state_row = db.scalar(coach.select(coach.OAuthState).where(
                coach.OAuthState.state_hash == oauth.state_digest(query['state'][0])))
            self.assertIsNotNone(state_row)
            self.assertEqual(state_row.user_id, self.user_id)

    def test_invalid_state_fails_before_external_token_exchange(self):
        self.client.cookies.set(coach.COOKIE, coach.sign_session(self.user_id), secure=True)
        response = self.client.get('/auth/callback?code=not-used&state=invalid', follow_redirects=False)
        self.assertEqual(response.status_code, 400)

    def test_refresh_token_encryption_round_trip(self):
        fernet = oauth.get_fernet()
        token = 'synthetic-refresh-token-never-sent-to-provider'
        encrypted = fernet.encrypt(token.encode()).decode()
        self.assertNotIn(token, encrypted)
        self.assertEqual(fernet.decrypt(encrypted.encode()).decode(), token)


    def test_callback_stores_only_encrypted_refresh_token(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import Mock, patch
        raw_state = 'test-state-bound-to-this-user'
        with coach.SessionLocal.begin() as db:
            db.add(coach.OAuthState(state_hash=oauth.state_digest(raw_state), user_id=self.user_id,
                                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
        expires = int((datetime.now(timezone.utc) + timedelta(hours=6)).timestamp())
        response_payload = {
            'access_token': 'access-token-test-only',
            'refresh_token': 'refresh-token-test-only',
            'expires_at': expires,
            'scope': 'read,activity:read_all,profile:read_all',
            'athlete': {'id': 987654321, 'firstname': 'Demo', 'lastname': 'Rider', 'profile': 'https://example.test/avatar.jpg'},
        }
        mocked_response = Mock()
        mocked_response.raise_for_status.return_value = None
        mocked_response.json.return_value = response_payload
        self.client.cookies.set(coach.COOKIE, coach.sign_session(self.user_id), secure=True)
        with patch.object(oauth.httpx, 'post', return_value=mocked_response) as provider_call:
            callback = self.client.get('/auth/callback', params={'code': 'one-use-code', 'state': raw_state}, follow_redirects=False)
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(callback.headers['location'], '/app?strava=connected')
        provider_call.assert_called_once()
        with coach.SessionLocal() as db:
            connection = db.scalar(coach.select(coach.StravaConnection).where(coach.StravaConnection.user_id == self.user_id))
            self.assertIsNotNone(connection)
            self.assertEqual(connection.strava_athlete_id, 987654321)
            self.assertNotIn('refresh-token-test-only', connection.refresh_token_encrypted)
            self.assertEqual(oauth.get_fernet().decrypt(connection.refresh_token_encrypted.encode()).decode(), 'refresh-token-test-only')
            self.assertNotIn('access_token', connection.__dict__)

    def test_refresh_persists_rotated_refresh_and_returns_no_token(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import Mock, patch
        fernet = oauth.get_fernet()
        with coach.SessionLocal.begin() as db:
            db.add(coach.StravaConnection(user_id=self.user_id, strava_athlete_id=987654321,
                athlete_name='Demo Rider', refresh_token_encrypted=fernet.encrypt(b'old-refresh').decode(),
                token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), scopes='activity:read_all profile:read_all'))
        expires = int((datetime.now(timezone.utc) + timedelta(hours=6)).timestamp())
        mocked_response = Mock()
        mocked_response.raise_for_status.return_value = None
        mocked_response.json.return_value = {'access_token': 'not-persisted', 'refresh_token': 'rotated-refresh', 'expires_at': expires}
        self.client.cookies.set(coach.COOKIE, coach.sign_session(self.user_id), secure=True)
        with patch.object(oauth.httpx, 'post', return_value=mocked_response):
            result = self.client.post('/auth/strava/refresh', follow_redirects=False)
        self.assertEqual(result.status_code, 303)
        self.assertEqual(result.headers['location'], '/app?strava=refreshed')
        with coach.SessionLocal() as db:
            connection = db.scalar(coach.select(coach.StravaConnection).where(coach.StravaConnection.user_id == self.user_id))
            self.assertEqual(fernet.decrypt(connection.refresh_token_encrypted.encode()).decode(), 'rotated-refresh')
            self.assertNotIn('rotated-refresh', result.text)

if __name__ == '__main__':
    unittest.main()
