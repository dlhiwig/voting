"""Repeatable browser runs for owner-authorized Survey123 testing."""

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

URL = "https://survey123.arcgis.com/share/caee07c36a9c47ab87409e52d2b42447"
SPOOKIEST = "1208 Perseus Hill Ct"
MOST_FESTIVE = "8 S Main St"
BEST_BUSINESS = "42 N Main St"
SUCCESS_TEXT = "Your response was submitted successfully."


def save_report(folder, report):
    pending = folder / "results.json.tmp"
    pending.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pending.replace(folder / "results.json")
    confirmed = sum(run["status"].startswith("confirmed") for run in report["runs"])
    lines = ["# Survey run report", "", f"Status: **{report['status']}**",
             f"Confirmed: {confirmed}/{report['requested_runs']}", "",
             f"Survey: {report['url']}", "", "## Choices", ""]
    lines.extend(f"- {category}: {choice}" for category, choice in report["choices"].items())
    lines += ["", "## Runs", "", "| Run | Status | Confirmation time |", "|---|---|---|"]
    for run in report["runs"]:
        lines.append(f"| {run['iteration']} | {run['status']} | {run.get('confirmation_seconds', '—')} s |")
    lines += ["", "Times measure Submit through visible confirmation. Backend records and final vote counting are not independently verified. Uncertain submissions are never automatically retried."]
    for run in report["runs"]:
        for key in ("selection_screenshot", "confirmation_screenshot", "failure_screenshot"):
            if key in run:
                lines += ["", f"![Run {run['iteration']} {key.replace('_', ' ')}]({run[key]})"]
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_survey(*, url=URL, runs=3, headless=False, fresh_context=True,
               reset_cookies=False, delay=2, timeout_ms=20_000, output=None,
               spookiest=SPOOKIEST, most_festive=MOST_FESTIVE, best_business=BEST_BUSINESS):
    if runs < 1 or not math.isfinite(delay) or delay < 0 or timeout_ms < 1:
        raise ValueError("Runs and timeout must be positive; delay must be finite and nonnegative.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Supply an http:// or https:// survey URL.")
    folder = Path(output) if output else Path(__file__).parent / "output" / "playwright" / datetime.now().strftime("survey-%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True, exist_ok=False)
    choices = {"Spookiest": spookiest, "Most Festive": most_festive, "Best Business": best_business}
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "url": url,
              "requested_runs": runs, "fresh_context": fresh_context,
              "reset_cookies": reset_cookies, "headless": headless,
              "choices": choices, "status": "running", "runs": []}

    def log(message):
        print(message, flush=True)
        with (folder / "execution.log").open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")

    log(f"Evidence: {folder.resolve()}")
    save_report(folder, report)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = None
            try:
                for number in range(1, runs + 1):
                    run = {"iteration": number, "status": "preparing"}
                    report["runs"].append(run)
                    page = None
                    started = time.monotonic()
                    try:
                        if fresh_context or context is None:
                            context = browser.new_context(viewport={"width": 1280, "height": 900})
                        if reset_cookies:
                            # Cookie clearing leaves localStorage and other origin storage intact.
                            context.clear_cookies()
                        run["initial_cookie_count"] = len(context.cookies())
                        page = context.new_page()
                        page.set_default_timeout(timeout_ms)
                        page.goto(url, wait_until="domcontentloaded")
                        for category, choice in choices.items():
                            # Click visible labels: Survey123 overlays its native inputs.
                            page.get_by_text(choice, exact=True).click()
                            expect(page.get_by_role("radio", name=choice, exact=True)).to_be_checked(timeout=timeout_ms)
                            log(f"Run {number}: verified {category}: {choice}")
                        run["selected_choices"] = dict(choices)
                        filename = f"run-{number}-selections.png"
                        page.screenshot(path=str(folder / filename), full_page=True)
                        run["selection_screenshot"] = filename
                        run["status"] = "submission_attempted"
                        save_report(folder, report)
                        submitted = time.monotonic()
                        page.get_by_role("button", name="Submit", exact=True).click()
                        success = page.locator("#screenContent")
                        success.get_by_text(SUCCESS_TEXT, exact=True).wait_for(state="visible", timeout=timeout_ms)
                        success.get_by_text("Thank you.", exact=True).wait_for(state="visible", timeout=timeout_ms)
                        run["confirmation_seconds"] = round(time.monotonic() - submitted, 4)
                        run["status"] = "confirmed"
                        # Persist acceptance before optional evidence collection.
                        save_report(folder, report)
                        run["confirmation_text"] = success.inner_text()
                        filename = f"run-{number}-confirmation.png"
                        page.screenshot(path=str(folder / filename), full_page=True)
                        run["confirmation_screenshot"] = filename
                        run["total_seconds"] = round(time.monotonic() - started, 4)
                        log(f"Run {number}/{runs}: visible confirmation in {run['confirmation_seconds']:.4f}s")
                        save_report(folder, report)
                    except BaseException as exc:
                        previous = run["status"]
                        run["status"] = ("confirmed_evidence_error" if previous == "confirmed" else
                                         "unconfirmed" if previous == "submission_attempted" else "failed_before_submit")
                        run["error"] = f"{type(exc).__name__}: {exc}"
                        log(f"Run {number}: {run['status']}. Stopping without retrying.")
                        if page is not None:
                            try:
                                filename = f"run-{number}-failure.png"
                                page.screenshot(path=str(folder / filename), full_page=True)
                                run["failure_screenshot"] = filename
                            except Exception as screenshot_error:
                                run["screenshot_error"] = str(screenshot_error)
                        raise
                    finally:
                        if page is not None:
                            page.close()
                        if fresh_context and context is not None:
                            context.close()
                            context = None
                    if number < runs:
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
        save_report(folder, report)
    log(f"Finished: {runs}/{runs} visible confirmations. Report: {folder / 'report.md'}")
    return report


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Must be at least 1")
    return number


def nonnegative_float(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Must be a finite nonnegative number")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=URL)
    parser.add_argument("--runs", type=positive_int, default=3)
    parser.add_argument("--headless", action="store_true", help="Run without a browser window")
    parser.add_argument("--reuse-context", action="store_true", help="Reuse cookies and origin storage between runs")
    parser.add_argument("--reset-cookies", action="store_true", help="Clear cookies only; other storage remains")
    parser.add_argument("--delay", type=nonnegative_float, default=2, help="Seconds between runs")
    parser.add_argument("--timeout-ms", type=positive_int, default=20_000)
    parser.add_argument("--output", type=Path, help="New evidence directory; must not already exist")
    parser.add_argument("--spookiest", default=SPOOKIEST)
    parser.add_argument("--most-festive", default=MOST_FESTIVE)
    parser.add_argument("--best-business", default=BEST_BUSINESS)
    args = parser.parse_args(argv)
    return run_survey(url=args.url, runs=args.runs, headless=args.headless,
                      fresh_context=not args.reuse_context, reset_cookies=args.reset_cookies,
                      delay=args.delay, timeout_ms=args.timeout_ms, output=args.output,
                      spookiest=args.spookiest, most_festive=args.most_festive,
                      best_business=args.best_business)


if __name__ == "__main__":
    main()

