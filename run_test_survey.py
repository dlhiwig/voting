"""Run exactly three local survey submissions and save evidence."""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from test_survey import SUCCESS_TEXT, make_server


CHOICES = {
    "Spookiest": "1208 Perseus Hill Ct",
    "Most Festive": "8 S Main St",
    "Best Business": "42 N Main St",
}


def main():
    folder = Path(__file__).parent / "output" / "playwright" / datetime.now().strftime("local-survey-%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    server = make_server(folder / "responses.db")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "environment": "local test survey", "url": base + "/survey", "multiple_submissions": True, "same_browser_context": True, "choices": CHOICES, "runs": []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                # Reuse one context with no cookie resets: repeat submissions are enabled.
                context = browser.new_context(viewport={"width": 1000, "height": 1000})
                page = context.new_page()
                page.set_default_timeout(10_000)
                for number in range(1, 4):
                    run = {"iteration": number, "status": "started"}
                    report["runs"].append(run)
                    started = time.monotonic()
                    try:
                        page.goto(base + "/survey", wait_until="domcontentloaded")
                        for category, choice in CHOICES.items():
                            group = page.get_by_role("group", name=category + " *", exact=True)
                            group.get_by_text(choice, exact=True).click()
                            expect(group.get_by_role("radio", name=choice, exact=True)).to_be_checked()
                        run["selected_choices"] = dict(CHOICES)
                        run["selection_screenshot"] = f"run-{number}-selections.png"
                        page.screenshot(path=str(folder / run["selection_screenshot"]), full_page=True)
                        submitted = time.monotonic()
                        run["status"] = "submission attempted"
                        page.get_by_role("button", name="Submit", exact=True).click()
                        success = page.locator("#screenContent")
                        success.get_by_text(SUCCESS_TEXT, exact=True).wait_for(state="visible")
                        success.get_by_text("Thank you.", exact=True).wait_for(state="visible")
                        run["submit_to_confirmation_seconds"] = round(time.monotonic() - submitted, 4)
                        run["response_id"] = int(page.locator("#response-id").inner_text())
                        run["confirmation_text"] = success.inner_text()
                        run["confirmation_screenshot"] = f"run-{number}-confirmation.png"
                        page.screenshot(path=str(folder / run["confirmation_screenshot"]), full_page=True)
                        response = context.request.get(base + "/results")
                        assert response.ok, "Could not retrieve local results"
                        results = response.json()
                        assert results["total"] == number, results
                        assert results["responses"][-1]["choices"] == CHOICES, results
                        assert results["responses"][-1]["id"] == run["response_id"], results
                        run["database_total"] = results["total"]
                        run["status"] = "confirmed and stored"
                        run["total_seconds"] = round(time.monotonic() - started, 4)
                        print(f"Run {number}/3: confirmed and stored; response {run['response_id']}; confirmation {run['submit_to_confirmation_seconds']:.4f}s", flush=True)
                    except Exception as exc:
                        run["error"] = str(exc)
                        page.screenshot(path=str(folder / f"run-{number}-failure.png"), full_page=True)
                        raise
                report["results"] = results
                report["status"] = "passed"
            finally:
                browser.close()
    except Exception:
        report["status"] = "failed; no automatic resubmission"
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        (folder / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        rows = ["# Local survey verification", "", f"Status: **{report['status']}**", "", "Three runs in the same browser context, with multiple submissions enabled. Only the local test server was used. The test server stops after the run; start test_survey.py to open it manually.", "", "## Selected choices", ""]
        rows.extend(f"- {category}: {choice}" for category, choice in CHOICES.items())
        rows += ["", "## Results", "", "| Run | Status | Response ID | Confirmation time | Stored responses |", "|---|---|---|---|---|"]
        for run in report["runs"]:
            rows.append(f"| {run['iteration']} | {run['status']} | {run.get('response_id', '—')} | {run.get('submit_to_confirmation_seconds', '—')} s | {run.get('database_total', '—')} |")
        rows += ["", "Confirmation times measure Submit through visible confirmation, excluding screenshot capture. Database records were checked after every submission.", "", "This validates the local browser-to-database workflow. It does not validate the hosted Survey123 service or its repeat-vote restrictions."]
        for run in report["runs"]:
            if "confirmation_screenshot" in run:
                rows += ["", f"![Run {run['iteration']} confirmation]({run['confirmation_screenshot']})"]
        (folder / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"Evidence: {folder}", flush=True)


if __name__ == "__main__":
    main()
