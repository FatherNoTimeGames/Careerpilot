import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DEFAULTS = {"salary_target": 50000, "interval_hours": 6, "enabled": True}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None):
    path = Path(path or os.environ.get("CAREERPILOT_DB", ".data/jobs.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=30)
    os.chmod(path, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript('''
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs(
      id INTEGER PRIMARY KEY, canonical_url TEXT UNIQUE NOT NULL,
      employer TEXT NOT NULL, title TEXT NOT NULL, location TEXT NOT NULL,
      description TEXT NOT NULL, data TEXT NOT NULL, fingerprint TEXT NOT NULL,
      first_seen TEXT NOT NULL, updated_at TEXT NOT NULL, last_seen TEXT NOT NULL,
      review_status TEXT NOT NULL DEFAULT 'discovered');
    CREATE TABLE IF NOT EXISTS listings(
      source TEXT NOT NULL, external_id TEXT NOT NULL, job_id INTEGER NOT NULL REFERENCES jobs(id),
      last_seen TEXT NOT NULL, missing_count INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(source, external_id));
    CREATE TABLE IF NOT EXISTS sources(
      id TEXT PRIMARY KEY, last_attempt TEXT, last_success TEXT,
      failures INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
      last_error TEXT, listing_count INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS runs(
      id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
      status TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL,
      job_id INTEGER REFERENCES jobs(id), details TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS worker_health(id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL NOT NULL, error TEXT);
    CREATE TABLE IF NOT EXISTS lease(id INTEGER PRIMARY KEY CHECK(id=1), until REAL NOT NULL);
    ''')
    for key, value in DEFAULTS.items():
        db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, json.dumps(value)))
    db.commit()
    return db


def settings(db):
    return {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM settings")}


def event(db, kind, job_id=None, details=""):
    db.execute("INSERT INTO events(created_at,kind,job_id,details) VALUES (?,?,?,?)",
               (now(), kind, job_id, details))
