"""Smoke tests for the phase-one conversational preview (no Strava/LLM calls)."""
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app_multi

ROOT = Path(__file__).resolve().parents[1]


class CoachPreviewTests(unittest.TestCase):
    def setUp(self):
        self.original_cwd = Path.cwd()
        os.chdir(ROOT)
        self.user = SimpleNamespace(id=1)
        self.athlete = SimpleNamespace(
            firstname="Test", lastname="Athlete", profile_pic_url=None,
            ftp_watts=150, weight_kg=30, ytd_distance_km=None,
        )
        app_multi.app.dependency_overrides[app_multi.require_user] = lambda: self.user
        app_multi.app.dependency_overrides[app_multi.get_db] = lambda: object()
        self.original_lookup = app_multi.get_user_athlete
        app_multi.get_user_athlete = lambda db, user: self.athlete
        self.client = TestClient(app_multi.app)

    def tearDown(self):
        self.client.close()
        app_multi.get_user_athlete = self.original_lookup
        app_multi.app.dependency_overrides.clear()
        os.chdir(self.original_cwd)

    def test_chat_is_conversational_preview_without_client_secret(self):
        response = self.client.get('/chat')
        self.assertEqual(response.status_code, 200)
        self.assertIn('settings-panel', response.text)
        self.assertIn('Test Athlete', response.text)
        self.assertIn('disabled', response.text)
        if app_multi.SERVICE_KEY:
            self.assertNotIn(app_multi.SERVICE_KEY, response.text)

    def test_static_assets_are_served(self):
        self.assertEqual(self.client.get('/static/css/coach.css').status_code, 200)
        self.assertEqual(self.client.get('/static/js/coach.js').status_code, 200)


if __name__ == '__main__':
    unittest.main()
