"""OAuth route smoke tests; deliberately make no requests to Strava."""
import os
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


if __name__ == '__main__':
    unittest.main()
