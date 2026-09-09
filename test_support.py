"""Shared LateBump test fixtures."""
from __future__ import annotations

import os
import tempfile
import unittest

_FD, _DB = tempfile.mkstemp(suffix=".db")
os.close(_FD)
os.environ["DATABASE_PATH"] = _DB
os.environ["OWNER_PASSWORD"] = "testpass"
os.environ["BUSINESS_NAME"] = "Harbor HVAC"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8080"
os.environ["MARKETING_URL"] = ""
os.environ["SECRET_KEY"] = "test-secret"
os.environ.pop("SMTP_HOST", None)
os.environ.pop("TWILIO_ACCOUNT_SID", None)
os.environ.pop("TWILIO_AUTH_TOKEN", None)
os.environ.pop("TWILIO_FROM_NUMBER", None)
os.environ.pop("BUSINESS_PHONE", None)

import helpers as H  # noqa: E402
from app import app  # noqa: E402


class LateBumpCase(unittest.TestCase):
    def setUp(self):
        if os.path.exists(_DB):
            os.remove(_DB)
        with app.app_context():
            db = H.connect_db()
            H.init_schema(db)
            db.close()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        if os.path.exists(_DB):
            try:
                os.remove(_DB)
            except OSError:
                pass

    def _login(self):
        return self.client.post(
            "/login",
            data={"password": "testpass"},
            follow_redirects=False,
        )

    def _create_job(self, name="Jordan Smith", phone="+15551234567", email="j@example.com"):
        self._login()
        resp = self.client.post(
            "/jobs/new",
            data={
                "customer_name": name,
                "customer_phone": phone or "",
                "customer_email": email or "",
                "title": "Furnace tune-up",
                "job_ref": "JOB-1",
                "scheduled_window": "1-3pm",
                "site_label": "123 Oak",
                "notes": "gate code later",
            },
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers["Location"]
        job_id = int(loc.rstrip("/").split("/")[-1])
        return job_id
