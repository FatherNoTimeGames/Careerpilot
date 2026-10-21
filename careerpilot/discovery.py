import hashlib
import json
import sqlite3
import time
import urllib.error
from email.utils import parsedate_to_datetime
from .store import connect, now, settings, event
from .providers import retrieve, source_id
from .matching import relevant, salary, assess


def source_fingerprint(job):
    raw={key:value for key,value in job.items() if key not in {'salary','assessment','salary_details'}}
    return hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()


def ingest(db, source, jobs):
    """Atomic complete snapshots; failures never retire listings or erase review history."""
    sid, stamp = source_id(source), now()
    counts = {"new": 0, "updated": 0, "removed": 0, "relevant": 0, "fetched": len(jobs)}
    seen = []
    with db:
        for job in jobs:
            if not relevant(job):
                continue
            counts["relevant"] += 1
            ident = job["external_id"]
            seen.append(ident)
            data = {**job, "salary": salary(job), "assessment": assess(job)}
            fingerprint = source_fingerprint(job)
            # Stable provider IDs keep review history if an employer changes its URL.
            old = db.execute('''SELECT j.* FROM jobs j JOIN listings l ON j.id=l.job_id
                                WHERE l.source=? AND l.external_id=?''', (sid, ident)).fetchone()
            if old is None:
                old = db.execute("SELECT * FROM jobs WHERE canonical_url=?", (job["url"],)).fetchone()
            if old is None:
                cursor = db.execute('''INSERT INTO jobs(canonical_url, employer,title,location,description,
                    data,fingerprint,first_seen,updated_at,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (job["url"], job["employer"], job["title"], job["location"], job["description"],
                     json.dumps(data), fingerprint, stamp, stamp, stamp))
                jid = cursor.lastrowid
                counts["new"] += 1
                event(db, "discovered", jid, sid)
            else:
                jid = old["id"]
                changed = source_fingerprint(json.loads(old['data'])) != fingerprint
                if not changed and old['fingerprint'] != fingerprint:
                    # Migrate legacy fingerprints without invalidating an unchanged source review.
                    db.execute('UPDATE job_verifications SET fingerprint=? WHERE job_id=? AND fingerprint=?',
                               (fingerprint,jid,old['fingerprint']))
                db.execute('''UPDATE jobs SET canonical_url=?,employer=?,title=?,location=?,description=?,data=?,
                           fingerprint=?,updated_at=?,last_seen=? WHERE id=?''',
                           (job["url"], job["employer"], job["title"], job["location"], job["description"],
                            json.dumps(data), fingerprint, stamp if changed else old["updated_at"], stamp, jid))
                if changed:
                    counts["updated"] += 1
                    event(db, "updated", jid, sid)
                previous = db.execute("SELECT missing_count FROM listings WHERE source=? AND external_id=?", (sid, ident)).fetchone()
                if previous and previous[0] >= 2:
                    event(db, "reopened", jid, sid)
            db.execute('''INSERT INTO listings(source,external_id,job_id,last_seen,missing_count)
                       VALUES (?,?,?,?,0) ON CONFLICT(source,external_id)
                       DO UPDATE SET last_seen=excluded.last_seen, missing_count=0''', (sid, ident, jid, stamp))
        # A complete snapshot, including zero listings, counts as one missing observation.
        for listing in db.execute("SELECT * FROM listings WHERE source=?", (sid,)).fetchall():
            if listing["external_id"] not in seen:
                db.execute("UPDATE listings SET missing_count=missing_count+1 WHERE source=? AND external_id=?",
                           (sid, listing["external_id"]))
                if listing["missing_count"] == 1:
                    counts["removed"] += 1
                    event(db, "removed_from_source", listing["job_id"], sid)
        db.execute('''INSERT INTO sources(id,last_attempt,last_success,failures,next_attempt,last_error,listing_count)
                    VALUES (?,?,?,0,0,NULL,?) ON CONFLICT(id) DO UPDATE SET last_attempt=excluded.last_attempt,
                    last_success=excluded.last_success,failures=0,next_attempt=0,last_error=NULL,
                    listing_count=excluded.listing_count''', (sid, stamp, stamp, len(jobs)))
    return counts


def discover(db, sources, fetcher=retrieve):
    clock = time.time()
    with db:
        acquired = db.execute('''INSERT INTO lease VALUES (1,?) ON CONFLICT(id) DO UPDATE SET until=excluded.until
                              WHERE lease.until < ?''', (clock+1800, clock)).rowcount
    if not acquired:
        return {"status": "already_running"}
    result = {"sources": {}, "errors": {}}
    lease_until=clock+1800
    def renew():
        nonlocal lease_until
        next_until=time.time()+1800
        with db:
            changed=db.execute("UPDATE lease SET until=? WHERE id=1 AND until=?",(next_until,lease_until)).rowcount
        if changed:lease_until=next_until
        return bool(changed)
    def interrupted(rid):
        result['status']='interrupted'
        result['errors']['lease']='Discovery lease lost; incomplete retrieval was not applied'
        with db:
            db.execute("UPDATE runs SET finished_at=?,status=?,summary=? WHERE id=?",(now(),'interrupted',json.dumps(result),rid))
        return result
    try:
        with db:
            db.execute("UPDATE runs SET status='interrupted', finished_at=? WHERE status='running'", (now(),))
            rid = db.execute("INSERT INTO runs(started_at,status) VALUES (?,'running')", (now(),)).lastrowid
        for source in sources:
            if not renew():return interrupted(rid)
            sid = source_id(source)
            state = db.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
            if state and state["next_attempt"] > time.time():
                result["sources"][sid] = {"status": "backoff", "retry_at": state["next_attempt"]}
                continue
            try:
                fetched=fetcher(source)
                if not renew():return interrupted(rid)
                result["sources"][sid] = ingest(db, source, fetched)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                # Error summaries contain no request headers, auth or API response bodies.
                message = f"{type(exc).__name__}: {str(exc)[:300]}"
                failures = (state["failures"] if state else 0)+1
                delay = min(86400, 300*2**min(failures-1, 8))
                if isinstance(exc, urllib.error.HTTPError):
                    retry = exc.headers.get("Retry-After", "")
                    try:
                        requested = int(retry) if retry.isdigit() else parsedate_to_datetime(retry).timestamp()-time.time()
                        delay = max(delay, requested)
                    except (ValueError, TypeError, OverflowError):
                        pass
                with db:
                    db.execute('''INSERT INTO sources(id,last_attempt,failures,next_attempt,last_error)
                      VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_attempt=excluded.last_attempt,
                      failures=excluded.failures,next_attempt=excluded.next_attempt,last_error=excluded.last_error''',
                      (sid, now(), failures, time.time()+delay, message))
                    event(db, "source_failure", details=sid + " " + message)
                result["errors"][sid] = message
        if not renew():return interrupted(rid)
        successful = any("fetched" in value for value in result["sources"].values())
        result["status"] = "partial" if result["errors"] and successful else "failed" if result["errors"] else "completed" if successful else "deferred"
        with db:
            db.execute("UPDATE runs SET finished_at=?,status=?,summary=? WHERE id=?",
                       (now(), result["status"], json.dumps(result), rid))
        return result
    finally:
        with db:
            db.execute("DELETE FROM lease WHERE id=1 AND until=?",(lease_until,))


def worker(path, sources, stop, poll_seconds=30):
    db = connect(path)
    try:
        while not stop.is_set():
            with db:
                db.execute("INSERT INTO worker_health VALUES (1,?,NULL) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat", (time.time(),))
            config = settings(db)
            last = db.execute("SELECT started_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            from datetime import datetime
            due = not last or time.time()-datetime.fromisoformat(last[0]).timestamp() >= config["interval_hours"]*3600
            if config["enabled"] and due:
                try:
                    discover(db, sources)
                    with db:
                        db.execute("UPDATE worker_health SET error=NULL WHERE id=1")
                except Exception as exc:
                    # Keep the worker alive; unexpected errors are visible and retried next poll.
                    with db:
                        message = type(exc).__name__ + ": discovery interrupted"
                        db.execute("UPDATE worker_health SET error=? WHERE id=1", (message,))
                        event(db, "worker_failure", details=message)
            stop.wait(poll_seconds)
    finally:
        with db:
            db.execute("UPDATE worker_health SET heartbeat=0 WHERE id=1")
        db.close()
