# Classroom Automation Exercise: Form Submission & Verification

## Repeatable owner-authorized survey runs

`survey_vote_demo.py` runs the configured survey three times by default with
the three saved address choices, using a fresh isolated browser context per run.

```powershell
python survey_vote_demo.py --runs 3 --headless
```

Omit `--headless` to watch the browser. Override the configured Survey123 URL
with `--url`, and choices with `--spookiest`, `--most-festive`, and `--best-business`.
Use `--reuse-context` to keep storage between runs; `--reset-cookies` clears
cookies only. Fresh contexts isolate storage without erasing existing profiles.

Each execution creates a timestamped folder under `output/playwright/` with
`report.md`, `results.json`, `execution.log`, selected-choice screenshots, and
confirmation screenshots. `--output` names a new folder explicitly. `--delay`
controls seconds between runs; `--timeout-ms` controls UI timeouts.

Use hosted surveys only for owner-authorized testing. Failures stop execution
with a nonzero exit status, preserving available evidence. Uncertain submissions
are never automatically retried. Visible confirmations do not independently
verify backend records or final vote counting.

## Three-run local survey verification

Run `python run_test_survey.py` to start an isolated local test survey, submit
three responses in the same browser session, and verify each database record.
No hosted contest survey is accessed. Reports, timings, selected-choice and
confirmation screenshots, and the separate test database are saved under
`output/playwright/local-survey-<timestamp>/`. The temporary server stops when
verification finishes.

To use the test survey manually, run `python test_survey.py` and open
`http://127.0.0.1:8001/survey`. Multiple submissions are enabled; its records use
`test-survey.db`, separate from the original poll's `votes.db`.

The interactive `vote_demo.py` and configurable `survey_vote_demo.py` target
an external survey by default; use `run_test_survey.py` for local classroom
verification. Run `python -m unittest -v test_survey_runner` to check the
configurable runner locally, including failure handling, without live submissions.

This project demonstrates automated end-to-end (E2E) form testing using **Playwright** against a local mock polling application.

---

## Project Structure

- `server.py`: Standard library HTTP + SQLite server running a mock poll on `http://localhost:8000/poll`.
- `vote_demo.py`: Legacy interactive helper for one external survey submission.
- `survey_vote_demo.py`: Configurable owner-authorized survey runner with evidence and reports.
- `test_survey.py`: Separate local survey with multiple submissions enabled.
- `run_test_survey.py`: Three-run local verification with database checks.
- `requirements.txt`: Python package dependencies (`playwright`).

---

## 1. Setup & Installation

Ensure you have Python 3.8+ installed. Install the requirements and download the Chromium browser binary:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

---

## 2. Running the Classroom Demonstration

### Step A: Start the Mock Web Server
Open a terminal in this directory and start the local server:
```bash
python server.py
```
The poll will be available at: `http://localhost:8000/poll`

### Step B: Run the Separate Local Survey Verification
Run the following in this directory. It starts its own separate local survey
and database, completes three browser runs, saves evidence, and stops its server:
```bash
python run_test_survey.py
```

---

## Educational Concepts to Explain to Students

### The 4 Stages of the Automation Loop
1. **Locate the controls**: `page.get_by_label("Option A", exact=True)`
2. **Select an option**: `.check()`
3. **Submit the form**: `page.get_by_role("button", name="Vote", exact=True).click()`
4. **Observable confirmation**: `page.get_by_text("Thank you for voting", exact=True).wait_for(state="visible")`

### Verification: Client Confirmation vs. Database Truth
- The automation script reports **"confirmation displayed"**, not **"vote recorded"**.
- The local three-run verifier checks the stored choices and response count after every submission. Its report and database are saved under `output/playwright/`. The original Option A/B/C poll remains available for manual exploration at `http://localhost:8000/poll`.

### Anti-Abuse and Integrity Defenses in Web Applications
In real-world web architecture, applications prevent repeated or automated submission abuse using:
- **Rate Limiting**: Throttling requests per IP or session window.
- **CSRF Tokens & One-time nonces**: Ensuring forms cannot be forged.
- **Bot Detection & CAPTCHAs**: Distinguishing human interactions from script engines.
- **Session/Cookie Tracking**: Preventing duplicate votes per device or account.
