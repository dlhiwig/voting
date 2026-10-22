"""Browser-to-database checks; only a temporary localhost survey is used."""

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from survey_vote_demo import run_survey
from test_survey import make_server


class SurveyRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.server = make_server(self.root / "responses.db")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/survey"
        self.output = self.root / "evidence"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def stored_choices(self):
        with closing(sqlite3.connect(self.root / "responses.db")) as conn:
            return [json.loads(row[0]) for row in conn.execute("SELECT choices FROM responses ORDER BY id")]

    def run_local(self, **options):
        return run_survey(url=self.url, headless=True, delay=0, timeout_ms=800,
                          output=self.output, **options)

    def test_three_fresh_context_runs_match_database_and_save_evidence(self):
        report = self.run_local(runs=3)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(self.stored_choices(), [report["choices"]] * 3)
        self.assertEqual(len(list(self.output.glob("*.png"))), 6)
        for run in report["runs"]:
            self.assertEqual(run["status"], "confirmed")
            self.assertEqual(run["initial_cookie_count"], 0)
            self.assertEqual(run["selected_choices"], report["choices"])
            self.assertIn("Your response was submitted successfully.", run["confirmation_text"])
            self.assertGreaterEqual(run["confirmation_seconds"], 0)
        saved = json.loads((self.output / "results.json").read_text())
        self.assertEqual(saved, report)
        self.assertTrue((self.output / "execution.log").is_file())
        self.assertTrue((self.output / "report.md").is_file())

    def test_post_submit_timeout_stops_without_duplicate_retry(self):
        handler = self.server.RequestHandlerClass
        original = handler.send_content

        def hide_confirmation(request, status, content, content_type="text/html; charset=utf-8"):
            if request.command == "POST":
                content = content.replace('id="screenContent"', 'id="missingConfirmation"')
            return original(request, status, content, content_type)

        with patch.object(handler, "send_content", new=hide_confirmation):
            with self.assertRaises(PlaywrightTimeout):
                self.run_local(runs=3)
        report = json.loads((self.output / "results.json").read_text())
        self.assertEqual(report["status"], "stopped")
        self.assertEqual(len(report["runs"]), 1)
        self.assertEqual(report["runs"][0]["status"], "unconfirmed")
        self.assertEqual(len(self.stored_choices()), 1)
        self.assertTrue((self.output / "run-1-failure.png").is_file())

    def test_screenshot_error_preserves_confirmed_status_and_stops(self):
        original = Page.screenshot

        def fail_confirmation_screenshot(page, **kwargs):
            if str(kwargs.get("path", "")).endswith("-confirmation.png"):
                raise OSError("Simulated screenshot storage failure")
            return original(page, **kwargs)

        with patch.object(Page, "screenshot", new=fail_confirmation_screenshot):
            with self.assertRaises(OSError):
                self.run_local(runs=3)
        report = json.loads((self.output / "results.json").read_text())
        self.assertEqual(len(self.stored_choices()), 1)
        self.assertEqual(len(report["runs"]), 1)
        self.assertEqual(report["runs"][0]["status"], "confirmed_evidence_error")
        self.assertIn("Confirmed: 1/3", (self.output / "report.md").read_text())

    def test_invalid_run_count_fails_before_creating_evidence(self):
        with self.assertRaises(ValueError):
            self.run_local(runs=0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.stored_choices(), [])


if __name__ == "__main__":
    unittest.main()
