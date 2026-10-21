import argparse
import json
import os
import signal
import sqlite3
import threading
from .store import connect
from .providers import load_sources
from .discovery import discover, worker
from .web import server
from .security import initialize_password


def main():
    parser = argparse.ArgumentParser(description="CareerPilot private job discovery")
    parser.add_argument("command", choices=["init", "discover", "worker", "serve", "backup", "verify-backup"])
    parser.add_argument("--db", default=os.environ.get("CAREERPILOT_DB", ".data/jobs.sqlite3"))
    parser.add_argument("--sources", default="sources.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--worker", action="store_true", help="Run scheduled discovery alongside the web app")
    parser.add_argument("--output", help="New private snapshot path for backup (never overwritten)")
    args = parser.parse_args()
    os.umask(0o077)
    if args.command in {"backup", "verify-backup"}:
        from .backup import create_backup, verify_backup
        if args.command == "backup" and not args.output:
            parser.error("backup requires --output")
        try:
            counts = (create_backup(args.db, args.output) if args.command == "backup"
                      else verify_backup(args.db))
        except (OSError, ValueError, sqlite3.Error) as error:
            parser.exit(1, f"Backup check failed: {error}\n")
        print(json.dumps({"status": "verified", "records": counts}))
        return
    sources = load_sources(args.sources)
    db = connect(args.db)
    if args.command == "init":
        db.close()
        password_file = initialize_password(args.db)
        print(f"Database initialized. Private owner password stored at {password_file}; value never logged.")
        return
    if args.command == "discover":
        try:
            result = discover(db, sources)
            print(json.dumps(result, indent=2))
            if result["status"] in {"failed", "partial", "interrupted"}:
                raise SystemExit(1)
        finally:
            db.close()
        return
    db.close()
    stop = threading.Event()
    if args.command == "worker":
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        worker(args.db, sources, stop)
        return
    httpd = server(args.db, args.host, args.port)
    background = None
    if args.worker:
        background = threading.Thread(target=worker, args=(args.db, sources, stop), daemon=True)
        background.start()
    print(f"CareerPilot listening on {args.host}:{httpd.server_port}; scheduled discovery: {bool(background)}", flush=True)
    # Signal interrupts serve_forever; orderly worker shutdown preserves in-flight writes.
    def terminate(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()
        if background:
            background.join(timeout=300)


if __name__ == "__main__":
    main()
