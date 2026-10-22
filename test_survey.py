"""Local test survey with repeat submissions enabled and its own database."""

import argparse
import html
import json
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


OPTIONS = {
    "Spookiest": ["77 Wood Green Dr", "204 S Cypress St", "1208 Perseus Hill Ct", "352 Vintage Point Ln", "917 Groveview Wynd"],
    "Most Festive": ["8 S Main St", "273 Tumbling River Dr", "725 Jasmine St", "251 Shadow Falls Dr", "219 N Hollybrook Rd", "1217 Pavo Path", "1603 Sandy Prairie Dr", "1624 Tunnel St", "416 Underhill Way", "223 Mayors Ln", "1525 Silver Elm Ln"],
    "Best Business": ["21 N Main St", "3124 Wendell Blvd", "42 N Main St"],
}
SUCCESS_TEXT = "Your response was submitted successfully."


def make_server(database, port=0):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, choices TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_content(self, status, content, content_type="text/html; charset=utf-8"):
            data = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/survey"):
                self.render()
            elif path == "/results":
                with closing(sqlite3.connect(database)) as conn:
                    rows = conn.execute("SELECT id, choices, created_at FROM responses ORDER BY id").fetchall()
                self.send_content(200, json.dumps({"total": len(rows), "responses": [
                    {"id": row[0], "choices": json.loads(row[1]), "created_at": row[2]}
                    for row in rows
                ]}), "application/json")
            else:
                self.send_error(404)

        def do_POST(self):
            if urlparse(self.path).path != "/survey":
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Invalid body size")
                values = parse_qs(self.rfile.read(size).decode("utf-8"), keep_blank_values=True)
                if set(values) != set(OPTIONS):
                    raise ValueError("One selection is required for every category")
                choices = {}
                for category, options in OPTIONS.items():
                    if len(values[category]) != 1 or values[category][0] not in options:
                        raise ValueError("Invalid selection")
                    choices[category] = values[category][0]
            except (ValueError, UnicodeError) as exc:
                self.send_error(400, str(exc))
                return
            with closing(sqlite3.connect(database)) as conn:
                cursor = conn.execute("INSERT INTO responses (choices) VALUES (?)", (json.dumps(choices),))
                response_id = cursor.lastrowid
                conn.commit()
            self.render(choices, response_id)

        def render(self, choices=None, response_id=None):
            content = ""
            if choices:
                selections = "".join(f"<li><b>{html.escape(category)}:</b> {html.escape(value)}</li>" for category, value in choices.items())
                content = f'<section id="screenContent"><h2>Thank you.</h2><p>{SUCCESS_TEXT}</p><p>Test response ID: <strong id="response-id">{response_id}</strong></p><ul>{selections}</ul><a href="/survey">Start another test response</a></section>'
            else:
                for group, (category, options) in enumerate(OPTIONS.items()):
                    content += f"<fieldset><legend>{html.escape(category)} *</legend>"
                    for index, option in enumerate(options):
                        content += f'<label for="r-{group}-{index}"><input required type="radio" id="r-{group}-{index}" name="{html.escape(category)}" value="{html.escape(option, quote=True)}"> {html.escape(option)}</label>'
                    content += "</fieldset>"
                content = f'<form method="post" action="/survey">{content}<button type="submit">Submit</button></form>'
            # Hidden duplicate reproduces the live survey's confirmation ambiguity.
            hidden = f'<div id="formPage" hidden><p>Thank you.</p><p>{SUCCESS_TEXT}</p></div>'
            self.send_content(200, f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Local Test Survey</title>
<style>body{{font:16px system-ui;background:#101827;color:#eff6ff;margin:0;padding:24px}}main{{max-width:680px;margin:auto;background:#1e293b;padding:28px;border-radius:16px}}h1{{margin-top:0}}.notice{{background:#134e4a;padding:16px;border-radius:8px}}fieldset{{border:1px solid #64748b;border-radius:8px;margin:24px 0}}legend{{font-weight:bold}}label{{display:block;padding:9px;cursor:pointer}}input{{accent-color:#60a5fa;margin-right:8px}}button,a{{background:#2563eb;color:white;padding:12px 20px;border:0;border-radius:6px;display:inline-block}}li{{margin:12px 0}}#screenContent{{background:#134e4a;padding:20px;margin-top:24px;border-radius:8px}}</style>
<main><h1>Local Test Survey</h1><p class="notice">Test environment — multiple submissions enabled.<br>Responses are stored locally, separately from the contest.</p>{hidden}{content}</main></html>''')

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--database", type=Path, default=Path(__file__).parent / "test-survey.db")
    args = parser.parse_args()
    with make_server(args.database, args.port) as server:
        print(f"Local test survey: http://127.0.0.1:{server.server_port}/survey", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
