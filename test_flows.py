"""LateBump tests part B."""
from __future__ import annotations
from test_support import LateBumpCase, app, H
import os
import pathlib


class LateBumpFlowTests(LateBumpCase):
    def test_07_audit_on_job_detail(self):
        job_id = self._create_job()
        self.client.post(
            f"/jobs/{job_id}/copy",
            data={
                "delay_minutes": "60",
                "new_eta_text": "5:00 PM",
                "body": "Hi Jordan — this is Harbor HVAC. We're running behind and now expect to arrive around 5:00 PM. Sorry for the wait.",
            },
            follow_redirects=True,
        )
        resp = self.client.get(f"/jobs/{job_id}")
        html = resp.get_data(as_text=True)
        self.assertIn("Audit", html)
        self.assertIn("copy", html.lower())
        self.assertIn("5:00 PM", html)

    def test_08_no_reminder_cron_as_core(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parent
        text = "".join((root / n).read_text() for n in ("app.py", "helpers.py", "helpers_core.py", "helpers_io.py") if (root / n).exists())
        for bad in ("APScheduler", "celery", "CronTrigger", "night_before", "reminder_drip"):
            self.assertNotIn(bad, text)

    def test_09_no_sibling_clones(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parent
        product_names = (
            "app.py",
            "helpers.py",
            "helpers_core.py",
            "helpers_io.py",
            "README.md",
            "base.html",
            "index.html",
            "job_detail.html",
            "new_job.html",
            "login.html",
            "404.html",
            "style.css",
        )
        text = ""
        for name in product_names:
            for p in root.rglob(name):
                if ".venv" in p.parts:
                    continue
                text += p.read_text(errors="ignore")
        for bad in (
            "OpenPing",
            "PartPing",
            "HomeReady",
            "SkyHold",
            "ChangeSlip",
            "AfterJob",
            "FormFirst",
            "live GPS",
            "weather_sensitive",
            "checklist_send",
        ):
            self.assertNotIn(bad, text)

    def test_10_empty_marketing_url_no_powered_by(self):
        self._login()
        resp = self.client.get("/")
        html = resp.get_data(as_text=True)
        self.assertNotIn("Powered by LateBump", html)

    def test_11_copy_buttons_not_truncated_onclick(self):
        job_id = self._create_job()
        self.client.post(f"/jobs/{job_id}/bump", data={"delay_minutes": "30"})
        resp = self.client.get(f"/jobs/{job_id}")
        html = resp.get_data(as_text=True)
        self.assertNotIn('onclick="copyText("', html)
        self.assertIn("copyFromDraft", html)
        self.assertIn('id="draft-body"', html)

    def test_12_custom_eta_and_index_recent(self):
        job_id = self._create_job()
        self.client.post(
            f"/jobs/{job_id}/bump",
            data={"custom_eta": "6:15 PM"},
            follow_redirects=True,
        )
        self.client.post(
            f"/jobs/{job_id}/copy",
            data={
                "custom_eta": "6:15 PM",
                "new_eta_text": "6:15 PM",
                "body": "Hi Jordan — this is Harbor HVAC. We're running behind and now expect to arrive around 6:15 PM. Sorry for the wait.",
            },
            follow_redirects=True,
        )
        index = self.client.get("/")
        html = index.get_data(as_text=True)
        self.assertIn("Recent bumps", html)
        self.assertIn("Jordan", html)
        self.assertIn("delayed", html.lower())


if __name__ == "__main__":
    import unittest
    unittest.main()
