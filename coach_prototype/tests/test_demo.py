"""Isolated smoke tests: SQLite is used only under TESTING=1."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
_tmpdir = tempfile.TemporaryDirectory()
os.environ['TESTING'] = '1'
os.environ['DATABASE_URL'] = f"sqlite:///{Path(_tmpdir.name) / 'coach_test.db'}"
os.environ['SESSION_SECRET'] = 'test-secret-not-for-production-change-me-12345678'
os.environ['DEMO_MODE'] = '1'
os.environ['DEMO_PASSWORD'] = '1234'

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
import app as coach  # noqa: E402


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(coach.app, base_url='https://testserver')
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def login(self):
        response = self.client.post('/login', data={'email': 'fake_user@test.local', 'password': '1234'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('httponly', response.headers['set-cookie'].lower())
        self.assertIn('secure', response.headers['set-cookie'].lower())

    def test_login_and_isolated_demo_timeline(self):
        self.assertEqual(self.client.get('/app', follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get('/api/timeline').status_code, 401)
        self.assertEqual(self.client.post('/login', data={'email': 'fake_user@test.local', 'password': 'wrong'}).status_code, 401)
        self.login()
        page = self.client.get('/app')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Activités et documents', page.text)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)
        entries = self.client.get('/api/timeline').json()
        self.assertEqual(len(entries), 4)
        self.assertEqual({item['type'] for item in entries}, {'activity', 'artifact'})
        self.assertEqual(entries[0]['date'], max(item['date'] for item in entries))
        for item in entries:
            detail = self.client.get(f"/api/timeline/{item['type']}/{item['id']}")
            self.assertEqual(detail.status_code, 200)
        self.assertIn('# Exemple de séance', self.client.get('/api/timeline/artifact/1').json()['markdown'])
        self.assertEqual(self.client.get('/api/timeline/invalid/1').status_code, 404)
        self.assertEqual(self.client.post('/logout', follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get('/api/me').status_code, 401)

    def test_other_users_records_are_not_visible(self):
        self.login()
        with coach.SessionLocal.begin() as db:
            other = coach.User(email='other@example.test', name='Other', password_hash=coach.hash_password('not-a-demo-password'), credit_tokens=0, model_choice='demo')
            db.add(other)
            db.flush()
            record = coach.Artifact(user_id=other.id, title='Private', created_at=coach.datetime.now(coach.timezone.utc), markdown='# Private', category='note')
            db.add(record)
            db.flush()
            hidden_id = record.id
        self.assertEqual(self.client.get(f'/api/timeline/artifact/{hidden_id}').status_code, 404)
        self.assertNotIn('Private', [item['title'] for item in self.client.get('/api/timeline').json()])


if __name__ == '__main__':
    unittest.main()
