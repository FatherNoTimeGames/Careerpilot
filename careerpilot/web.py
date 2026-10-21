import base64
import hmac
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .store import connect, settings, event
from .matching import category
from . import studio
from .security import owner_password

STATIC = Path(__file__).resolve().parent.parent / "static"


def snapshot(db):
    config = settings(db)
    jobs = []
    for row in db.execute('''SELECT j.*, EXISTS(SELECT 1 FROM listings l WHERE l.job_id=j.id
                           AND l.missing_count<2) AS active FROM jobs j ORDER BY j.first_seen DESC, j.id DESC'''):
        job = dict(row)
        data = json.loads(job.pop("data"))
        job.update({"salary": data["salary"], "assessment": data["assessment"],
                    "category": category(data["salary"], config["salary_target"])})
        job.pop("fingerprint")
        jobs.append(job)
    health = db.execute("SELECT * FROM worker_health WHERE id=1").fetchone()
    lease = db.execute("SELECT until FROM lease WHERE id=1").fetchone()
    worker_active = bool(health and (health["heartbeat"] > time.time()-90 or (lease and lease[0] > time.time())))
    return {"jobs": jobs, "settings": config,
            "worker": {"active": worker_active, "error": health["error"] if health else None},
            "sources": [dict(r) for r in db.execute("SELECT * FROM sources ORDER BY id")],
            "runs": [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 20")],
            "events": [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")]}


def server(path, host="127.0.0.1", port=8000):
    password = owner_password(path)
    if password and len(password) < 16:
        raise ValueError("Owner password must contain at least 16 characters")
    if host not in {"127.0.0.1", "::1", "localhost"} and len(password) < 16:
        raise ValueError("Non-loopback hosting requires CAREERPILOT_PASSWORD (at least 16 characters) and a TLS reverse proxy")

    class Handler(BaseHTTPRequestHandler):
        server_version = "CareerPilot"

        def log_message(self, fmt, *args):
            # No paths, headers or candidate information in HTTP logs.
            pass

        def authorized(self):
            if not password:
                return True
            try:
                scheme, value = self.headers.get("Authorization", "").split(" ", 1)
                credentials = base64.b64decode(value, validate=True)
                return scheme == "Basic" and hmac.compare_digest(credentials, ("careerpilot:" + password).encode())
            except (ValueError, UnicodeDecodeError):
                return False

        def respond(self, code, body, content_type="application/json", download=None):
            raw = json.dumps(body).encode() if content_type == "application/json" else body
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            if download:
                self.send_header("Content-Disposition", 'attachment; filename="' + download + '"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if code == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="CareerPilot", charset="UTF-8"')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.authorized():
                return self.respond(401, {"error": "Authentication required"})
            path_only = urlsplit(self.path).path
            if path_only.startswith('/api/studio'):
                if not password:
                    return self.respond(403, {'error': 'Resume Studio requires owner authentication. Run initialization to create a private owner password, or configure CAREERPILOT_PASSWORD securely, then restart the server.'})
                db = connect(path)
                try:
                    if path_only == '/api/studio':
                        return self.respond(200, studio.state(db))
                    parts = path_only.strip('/').split('/')
                    if len(parts) == 5 and parts[:3] == ['api', 'studio', 'documents'] and parts[4] == 'original':
                        ident = int(parts[3])
                        row = db.execute('SELECT kind,original FROM resume_documents WHERE id=?', (ident,)).fetchone()
                        if row:
                            mime = 'application/pdf' if row['kind'] == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                            return self.respond(200, row['original'], mime, f'original-{ident}.' + row['kind'])
                    if len(parts) == 5 and parts[:3] == ['api', 'studio', 'versions'] and parts[4] in {'pdf', 'docx'}:
                        ident, kind = int(parts[3]), parts[4]
                        row = db.execute("SELECT e.pdf,e.docx FROM resume_exports e JOIN resume_versions v ON e.version_id=v.id WHERE v.id=? AND v.status='approved' AND e.edit_revision=v.edit_revision", (ident,)).fetchone()
                        if row:
                            mime = 'application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                            return self.respond(200, row[kind], mime, f'resume-v{ident}.' + kind)
                    if len(parts) == 6 and parts[:3] == ['api', 'studio', 'versions'] and parts[4] == 'pages':
                        row = db.execute('SELECT png FROM resume_pages WHERE version_id=? AND page=?', (int(parts[3]), int(parts[5]))).fetchone()
                        if row:
                            return self.respond(200, row[0], 'image/png')
                    return self.respond(404, {'error': 'Document or approved export not found'})
                except ValueError:
                    return self.respond(400, {'error': 'Invalid document/version ID'})
                finally:
                    db.close()
            if path_only == "/api/state":
                db = connect(path)
                try:
                    return self.respond(200, snapshot(db))
                finally:
                    db.close()
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8"),
                     "/studio.js": ("studio.js", "text/javascript; charset=utf-8")}
            if path_only not in files:
                return self.respond(404, {"error": "Not found"})
            name, mime = files[path_only]
            self.respond(200, (STATIC / name).read_bytes(), mime)

        def do_POST(self):
            if not self.authorized():
                return self.respond(401, {"error": "Authentication required"})
            # Custom header + JSON prevents cross-origin form submissions; no CORS allowed.
            if self.headers.get("X-CareerPilot") != "1" or self.headers.get("Content-Type") != "application/json":
                return self.respond(403, {"error": "Same-origin JSON request required"})
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self.respond(403, {"error": "Origin mismatch"})
            is_studio = self.path.startswith('/api/studio/')
            if is_studio and not password:
                return self.respond(403, {'error': 'Initialize the private owner password or configure CAREERPILOT_PASSWORD before using Resume Studio'})
            db = connect(path)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > (7 * 1024 * 1024 if self.path == '/api/studio/import' else 1024 * 1024 if is_studio else 8192):
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Object required")
                if is_studio:
                    action = self.path.removeprefix('/api/studio/')
                    if action not in studio.ACTIONS:
                        return self.respond(404, {'error': 'Unknown Studio action'})
                    return self.respond(200, studio.ACTIONS[action](db, body))
                if self.path == "/api/settings":
                    allowed = {"salary_target", "interval_hours", "enabled"}
                    if set(body)-allowed:
                        raise ValueError("Unknown setting")
                    if "salary_target" in body and (type(body["salary_target"]) is not int or not 1 <= body["salary_target"] <= 1000000):
                        raise ValueError("Salary target must be 1–1,000,000")
                    if "interval_hours" in body and (type(body["interval_hours"]) is not int or not 1 <= body["interval_hours"] <= 168):
                        raise ValueError("Discovery interval must be 1–168 hours")
                    if "enabled" in body and type(body["enabled"]) is not bool:
                        raise ValueError("Enabled must be boolean")
                    with db:
                        for key, value in body.items():
                            db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(value), key))
                        event(db, "settings_changed", details=",".join(sorted(body)))
                elif self.path == "/api/review":
                    if type(body.get("id")) is not int:
                        raise ValueError("Numeric job ID required")
                    if not isinstance(body.get("status"), str) or body.get("status") not in {"discovered", "interested", "skipped"}:
                        raise ValueError("Unsupported review action")
                    with db:
                        cursor = db.execute("UPDATE jobs SET review_status=? WHERE id=?", (body["status"], body.get("id")))
                        if cursor.rowcount != 1:
                            raise ValueError("Job not found")
                        event(db, body["status"], body["id"])
                else:
                    return self.respond(404, {"error": "Not found"})
                self.respond(200, {"ok": True})
            except studio.Conflict as exc:
                self.respond(409, {"error": str(exc)})
            except (ValueError, TypeError) as exc:
                self.respond(400, {"error": str(exc) if is_studio and type(exc) is ValueError else "Invalid request or unsupported action"})
            finally:
                db.close()

    return ThreadingHTTPServer((host, port), Handler)
