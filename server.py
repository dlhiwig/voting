import http.server
import socketserver
import urllib.parse
import sqlite3
import os
from http.cookies import SimpleCookie

PORT = 8000
DB_FILE = os.path.join(os.path.dirname(__file__), "votes.db")

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                choice TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def record_vote(choice):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO votes (choice) VALUES (?)", (choice,))
        conn.commit()

def get_results():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("SELECT choice, count(*) FROM votes GROUP BY choice")
        counts = dict(cursor.fetchall())
        cursor = conn.execute("SELECT count(*) FROM votes")
        total = cursor.fetchone()[0]
        return counts, total

def reset_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM votes")
        conn.commit()

class PollHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["/", "/poll"]:
            self.render_poll()
        elif parsed.path == "/results":
            self.render_results()
        elif parsed.path == "/reset":
            reset_db()
            self.send_response(303)
            # Clear any session/voting cookies for the local poll demo
            self.send_header("Set-Cookie", "voted=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
            self.send_header("Location", "/poll")
            self.end_headers()
        else:
            self.send_error(404, "Page Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["/", "/poll", "/vote"]:
            cookies = SimpleCookie()
            cookies.load(self.headers.get("Cookie", ""))
            if "voted" in cookies and cookies["voted"].value == "1":
                self.send_error(409, "You have already taken this poll. Reset the local demo to test again.")
                return
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length).decode("utf-8")
            params = urllib.parse.parse_qs(post_body)
            choice = params.get("choice", ["Option A"])[0]
            record_vote(choice)
            self.render_poll(submitted=True, chosen=choice)
        else:
            self.send_error(404, "Endpoint Not Found")

    def render_poll(self, submitted=False, chosen=""):
        counts, total = get_results()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if submitted:
            self.send_header("Set-Cookie", "voted=1; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()

        confirmation_html = ""
        if submitted:
            confirmation_html = """
            <div class="alert-success">
                <strong>Thank you for voting</strong>
                <p>Your response for <em>{chosen}</em> was recorded.</p>
            </div>
            """.format(chosen=chosen)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Classroom Poll Demo</title>
    <style>
        :root {{
            --primary: #4f46e5;
            --primary-hover: #4338ca;
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --success: #10b981;
            --success-bg: rgba(16, 185, 129, 0.15);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.4);
            width: 100%;
            max-width: 480px;
            padding: 32px;
        }}
        h1 {{
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 8px;
            color: #ffffff;
        }}
        .subtitle {{
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-bottom: 24px;
        }}
        .alert-success {{
            background: var(--success-bg);
            border: 1px solid var(--success);
            color: #6ee7b7;
            padding: 14px 18px;
            border-radius: 10px;
            margin-bottom: 24px;
            font-size: 0.95rem;
        }}
        .alert-success strong {{
            display: block;
            font-size: 1.05rem;
            margin-bottom: 2px;
        }}
        .options-group {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 28px;
        }}
        .option-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            padding: 14px 16px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .option-item:hover {{
            border-color: var(--primary);
            background: rgba(79, 70, 229, 0.1);
        }}
        .option-item input[type="radio"] {{
            width: 18px;
            height: 18px;
            accent-color: var(--primary);
            cursor: pointer;
        }}
        .option-item label {{
            cursor: pointer;
            font-size: 1rem;
            flex-grow: 1;
            font-weight: 500;
        }}
        button[type="submit"] {{
            background: var(--primary);
            color: #ffffff;
            font-weight: 600;
            border: none;
            padding: 12px 24px;
            width: 100%;
            border-radius: 10px;
            font-size: 1rem;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button[type="submit"]:hover {{
            background: var(--primary-hover);
        }}
        .footer-stats {{
            margin-top: 28px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}
        .reset-link {{
            color: #f87171;
            text-decoration: none;
            font-size: 0.8rem;
        }}
        .reset-link:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Classroom Automation Poll</h1>
        <p class="subtitle">E2E Automated Testing Demonstration Target</p>

        {confirmation_html}

        <form method="POST" action="/poll">
            <div class="options-group">
                <div class="option-item">
                    <input type="radio" id="optA" name="choice" value="Option A" checked>
                    <label for="optA">Option A</label>
                </div>
                <div class="option-item">
                    <input type="radio" id="optB" name="choice" value="Option B">
                    <label for="optB">Option B</label>
                </div>
                <div class="option-item">
                    <input type="radio" id="optC" name="choice" value="Option C">
                    <label for="optC">Option C</label>
                </div>
            </div>

            <button type="submit">Vote</button>
        </form>

        <div class="footer-stats">
            <span>Database Total Votes: <strong style="color: #ffffff;">{total}</strong> (A: {counts.get('Option A', 0)})</span>
            <a href="/reset" class="reset-link">Reset DB</a>
        </div>
    </div>
</body>
</html>
"""
        self.wfile.write(html.encode("utf-8"))

    def render_results(self):
        counts, total = get_results()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        import json
        payload = json.dumps({"total": total, "counts": counts})
        self.wfile.write(payload.encode("utf-8"))

def run():
    init_db()
    with socketserver.TCPServer(("", PORT), PollHandler) as httpd:
        print(f"Poll server running at http://localhost:{PORT}/poll")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    run()
