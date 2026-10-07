"""Account creation/login and per-user timeline tests on isolated SQLite."""
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
_tmpdir = tempfile.TemporaryDirectory()
os.environ['TESTING'] = '1'
os.environ['DATABASE_URL'] = f"sqlite:///{Path(_tmpdir.name) / 'coach_test.db'}"
os.environ['SESSION_SECRET'] = 'test-secret-not-for-production-change-me-12345678'
os.environ['DEMO_MODE'] = '1'
os.environ['ALLOW_SIGNUP'] = '1'

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
import app as coach  # noqa: E402


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(coach.app, base_url='https://testserver')
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def signup(self, email='pilot@example.com'):
        page = self.client.get('/signup')
        self.assertEqual(page.status_code, 200)
        match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertIsNotNone(match)
        return self.client.post('/signup', data={
            'csrf_token': match.group(1), 'email': email, 'name': 'Pilot Athlete',
            'password': 'a-long-test-password-987', 'password_confirm': 'a-long-test-password-987',
        }, follow_redirects=False)

    def test_signup_login_and_user_timeline(self):
        self.assertEqual(self.client.get('/app', follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get('/api/timeline').status_code, 401)
        response = self.signup()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/app')
        self.assertIn('httponly', response.headers['set-cookie'].lower())
        self.assertIn('secure', response.headers['set-cookie'].lower())

        with coach.SessionLocal.begin() as db:
            user = db.scalar(select(coach.User).where(coach.User.email == 'pilot@example.com'))
            self.assertIsNotNone(user)
            self.assertIsNone(db.scalar(select(coach.User).where(coach.User.email == 'fake_user@test.local')))
            db.add_all([
                coach.Activity(user_id=user.id, title='Test ride', occurred_at=datetime.now(timezone.utc),
                               sport='Ride', duration_minutes=40, distance_km=15.5, avg_watts=120),
                coach.Artifact(user_id=user.id, title='Test plan', created_at=datetime.now(timezone.utc),
                               category='training_plan', markdown='# Test plan'),
            ])
        page = self.client.get('/app')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Activités et documents', page.text)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)
        entries = self.client.get('/api/timeline').json()
        self.assertEqual(len(entries), 2)
        self.assertEqual({item['type'] for item in entries}, {'activity', 'artifact'})
        for item in entries:
            self.assertEqual(self.client.get(f"/api/timeline/{item['type']}/{item['id']}").status_code, 200)
        self.assertEqual(self.client.get('/api/timeline/invalid/1').status_code, 404)
        self.assertEqual(self.client.post('/logout', follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get('/api/me').status_code, 401)

    def test_signup_validates_password_csrf_and_duplicate_email(self):
        page = self.client.get('/signup')
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        invalid = self.client.post('/signup', data={
            'csrf_token': csrf, 'email': 'pilot@example.com', 'name': 'Pilot',
            'password': 'short', 'password_confirm': 'short',
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('12', invalid.text)
        self.assertEqual(self.signup().status_code, 303)
        duplicate_page = self.client.get('/signup')
        duplicate_csrf = re.search(r'name="csrf_token" value="([^"]+)"', duplicate_page.text).group(1)
        duplicate = self.client.post('/signup', data={
            'csrf_token': duplicate_csrf, 'email': 'PILOT@example.com', 'name': 'Other',
            'password': 'a-long-test-password-987', 'password_confirm': 'a-long-test-password-987',
        })
        self.assertEqual(duplicate.status_code, 409)
        bad_csrf = self.client.post('/signup', data={
            'csrf_token': 'wrong', 'email': 'other@example.com', 'name': 'Other',
            'password': 'a-long-test-password-987', 'password_confirm': 'a-long-test-password-987',
        })
        self.assertEqual(bad_csrf.status_code, 403)

    def test_signup_can_be_closed_after_bootstrap(self):
        previous = coach.ALLOW_SIGNUP
        coach.ALLOW_SIGNUP = False
        try:
            self.assertEqual(self.client.get('/signup').status_code, 403)
        finally:
            coach.ALLOW_SIGNUP = previous

    def test_other_users_records_are_not_visible(self):
        self.assertEqual(self.signup('owner@example.com').status_code, 303)
        with coach.SessionLocal.begin() as db:
            other = coach.User(email='other@example.com', name='Other',
                               password_hash=coach.hash_password('another-long-password-123'),
                               credit_tokens=0, model_choice='demo')
            db.add(other)
            db.flush()
            record = coach.Artifact(user_id=other.id, title='Private', created_at=datetime.now(timezone.utc),
                                    markdown='# Private', category='note')
            db.add(record)
            db.flush()
            hidden_id = record.id
        self.assertEqual(self.client.get(f'/api/timeline/artifact/{hidden_id}').status_code, 404)
        self.assertNotIn('Private', [item['title'] for item in self.client.get('/api/timeline').json()])


if __name__ == '__main__':
    unittest.main()
