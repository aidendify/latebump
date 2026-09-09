"""LateBump tests part A."""
from __future__ import annotations
from test_support import LateBumpCase, app, H
import os
import pathlib


class LateBumpTests(LateBumpCase):
    def test_01_health_public_smtp_sms_false(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIs(data["smtp_configured"], False)
        self.assertIs(data["sms_configured"], False)

    def test_02_auth_gates_index_health_public(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)

    def test_03_create_job_running_late_draft(self):
        job_id = self._create_job()
        resp = self.client.post(
            f"/jobs/{job_id}/bump",
            data={"delay_minutes": "30"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Jordan", html)
        self.assertIn("Harbor HVAC", html)
        self.assertIn("running behind", html.lower())
        self.assertIn('id="draft-body"', html)
        self.assertIn("arrive around", html)

    def test_04_copy_logs_bump_channel_copy_ok(self):
        job_id = self._create_job()
        self.client.post(f"/jobs/{job_id}/bump", data={"delay_minutes": "30"})
        detail = self.client.get(f"/jobs/{job_id}")
        html = detail.get_data(as_text=True)
        self.assertIn("draft-body", html)
        resp = self.client.post(
            f"/jobs/{job_id}/copy",
            data={
                "delay_minutes": "30",
                "new_eta_text": "3:45 PM",
                "body": "Hi Jordan — this is Harbor HVAC. We're running behind and now expect to arrive around 3:45 PM. Sorry for the wait.",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        with app.app_context():
            bumps = H.list_job_bumps(job_id)
            self.assertTrue(len(bumps) >= 1)
            b = bumps[0]
            self.assertEqual(b["channel"], "copy")
            self.assertEqual(b["ok"], 1)
            job = H.get_job(job_id)
            self.assertEqual(job["status"], "delayed")

    def test_05_offer_reschedule_adds_language(self):
        os.environ["BUSINESS_PHONE"] = "555-0100"
        job_id = self._create_job()
        resp = self.client.post(
            f"/jobs/{job_id}/bump",
            data={"delay_minutes": "45", "offer_reschedule": "1"},
            follow_redirects=True,
        )
        html = resp.get_data(as_text=True)
        self.assertIn("reschedule", html.lower())
        self.assertIn("555-0100", html)
        os.environ.pop("BUSINESS_PHONE", None)

        job_id2 = self._create_job(name="Alex Lee")
        resp2 = self.client.post(
            f"/jobs/{job_id2}/bump",
            data={"delay_minutes": "15", "offer_reschedule": "1"},
            follow_redirects=True,
        )
        html2 = resp2.get_data(as_text=True)
        self.assertIn("reply to this message", html2.lower())

    def test_06_send_controls_disabled_without_twilio_smtp(self):
        job_id = self._create_job()
        self.client.post(f"/jobs/{job_id}/bump", data={"delay_minutes": "30"})
        resp = self.client.get(f"/jobs/{job_id}")
        html = resp.get_data(as_text=True)
        self.assertIn("Send SMS", html)
        self.assertIn("Send email", html)
        self.assertIn("disabled", html)
        r2 = self.client.post(
            f"/jobs/{job_id}/send-sms",
            data={
                "delay_minutes": "30",
                "new_eta_text": "4:00 PM",
                "body": "test body",
            },
            follow_redirects=True,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertIn("not configured", r2.get_data(as_text=True).lower())


if __name__ == "__main__":
    import unittest
    unittest.main()
