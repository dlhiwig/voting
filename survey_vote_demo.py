"""Run an authorized Survey123 flow with evidence and failure-safe reporting."""

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

URL = "https://survey123.arcgis.com/share/caee07c36a9c47ab87409e52d2b42447"
OPTIONS = {
    "Spookiest": "1208 Perseus Hill Ct",
    "Most Festive": "8 S Main St",
    "Best Business": "42 N Main St",
}
SUCCESS_PHRASE = "Your response was submitted successfully."


def write_report(folder, report):
    (folder / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    confirmed = sum(item["status"].startswith("confirmed") for item in report["runs"])
    lines = [
        "# Survey run report", "", f"Status: **{report['status']}**",
        f"Confirmed: {confirmed}/{report['requested_runs']}", "",
        f"URL: {report['url']}", "", "## Selected choices", "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in report["choices"].items())
    lines += ["", "## Runs", "", "| Run | Status | Confirmation time |", "|---:|---|---:|"]
    for item in report["runs"]:
        lines.append(f"| {item['iteration']} | {item['status']} | {item.get('confirmation_seconds', '—')} s |")
    lines += ["", "The runner stops after an uncertain submission and never retries it automatically. Visible confirmation does not independently verify backend records or final counting."]
    for item in report["runs"]:
        for key in ("selection_screenshot", "confirmation_screenshot", "failure_screenshot"):
            if key in item:
                lines += ["", f"![Run {item['iteration']} {key.replace('_', ' ')}]({item[key]})"]
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_survey(url=URL, runs=1, *, headless=False, delay=2, timeout_ms=20_000,
               output=None, choices=None):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must be an http or https URL")
    if runs < 1 or timeout_ms < 1 or not math.isfinite(delay) or delay < 0:
        raise ValueError("runs and timeout_ms must be positive; delay must be finite and nonnegative")
    choices = dict(choices or OPTIONS)
    folder = Path(output) if output else Path(__file__).parent / "output" / "playwright" / datetime.now().strftime("survey-%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True, exist_ok=False)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(), "url": url,
        "requested_runs": runs, "headless": headless, "choices": choices,
        "status": "running", "runs": [],
    }
    (folder / "execution.log").write_text("", encoding="utf-8")

    def log(message):
        print(message, flush=True)
        with (folder / "execution.log").open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")

    log(f"Evidence: {folder.resolve()}")
    write_report(folder, report)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                for iteration in range(1, runs + 1):
                    item = {"iteration": iteration, "status": "before_submit"}
                    report["runs"].append(item)
                    page = None
                    context = browser.new_context(viewport={"width": 1280, "height": 900})
                    started = time.monotonic()
                    try:
                        page = context.new_page()
                        page.set_default_timeout(timeout_ms)
                        item["initial_cookie_count"] = len(context.cookies())
                        page.goto(url, wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                        for category, choice in choices.items():
                            radio = page.get_by_role("radio", name=choice, exact=True)
                            # Survey123 overlays the native input with a clickable label.
                            page.get_by_text(choice, exact=True).click()
                            expect(radio).to_be_checked(timeout=timeout_ms)
                            log(f"Run {iteration}: selected {category}: {choice}")
                        item["selected_choices"] = choices
                        item["selection_screenshot"] = f"run-{iteration}-selections.png"
                        page.screenshot(path=str(folder / item["selection_screenshot"]), full_page=True)
                        item["status"] = "submission_attempted"
                        write_report(folder, report)
                        submitted = time.monotonic()
                        page.get_by_role("button", name="Submit", exact=True).click()
                        success_area = page.locator("#screenContent")
                        success_area.get_by_text(SUCCESS_PHRASE, exact=True).wait_for(state="visible", timeout=timeout_ms)
                        expect(success_area).to_contain_text("Thank you.", timeout=timeout_ms)
                        item["confirmation_seconds"] = round(time.monotonic() - submitted, 4)
                        item["confirmation_text"] = success_area.inner_text()
                        item["status"] = "confirmed"
                        # Persist confirmation before optional screenshot capture.
                        write_report(folder, report)
                        item["confirmation_screenshot"] = f"run-{iteration}-confirmation.png"
                        page.screenshot(path=str(folder / item["confirmation_screenshot"]), full_page=True)
                        write_report(folder, report)
                        log(f"Run {iteration}/{runs}: confirmed in {item['confirmation_seconds']:.4f}s")
                    except BaseException as exc:
                        prior = item["status"]
                        item["status"] = ("confirmed_evidence_error" if prior == "confirmed" else
                                           "unconfirmed" if prior == "submission_attempted" else "failed_before_submit")
                        item["error"] = f"{type(exc).__name__}: {exc}"
                        log(f"Run {iteration}: {item['status']}; stopping without retry")
                        if page is not None:
                            try:
                                item["failure_screenshot"] = f"run-{iteration}-failure.png"
                                page.screenshot(path=str(folder / item["failure_screenshot"]), full_page=True)
                            except Exception as screenshot_error:
                                item["screenshot_error"] = str(screenshot_error)
                        raise
                    finally:
                        if page is not None:
                            page.close()
                        context.close()
                    if iteration < runs:
                        time.sleep(delay)
                report["status"] = "completed"
            finally:
                browser.close()
    except BaseException as exc:
        report["status"] = "stopped"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_report(folder, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=URL)
    parser.add_argument("--runs", type=int, default=1, help="Explicit number of submissions; defaults to one")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    return 0 if run_survey(args.url, args.runs, headless=args.headless, delay=args.delay,
                            timeout_ms=args.timeout_ms, output=args.output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
