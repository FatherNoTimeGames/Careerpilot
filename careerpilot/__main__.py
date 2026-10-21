import argparse
import json
import os
import signal
import threading
from .store import connect
from .providers import load_sources
from .discovery import discover, worker
from .web import server


def main():
    parser = argparse.ArgumentParser(description="CareerPilot private job discovery")
    parser.add_argument("command", choices=["init", "discover", "worker", "serve"])
    parser.add_argument("--db", default=os.environ.get("CAREERPILOT_DB", ".data/jobs.sqlite3"))
    parser.add_argument("--sources", default="sources.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--worker", action="store_true", help="Run scheduled discovery alongside the web app")
    args = parser.parse_args()
    os.umask(0o077)
    sources = load_sources(args.sources)
    db = connect(args.db)
    if args.command == "init":
        db.close()
        print("Database initialized")
        return
    if args.command == "discover":
        try:
            result = discover(db, sources)
            print(json.dumps(result, indent=2))
            if result["status"] in {"failed", "partial"}:
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
