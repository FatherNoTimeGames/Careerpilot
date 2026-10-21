# Prototype 1 validation

See the final entries below for the measured live discovery outcome. Local runtime evidence is not proof of production deployment or a Sites capability.

Automated coverage (`python3 -m unittest discover -s tests -v`):
- Provider normalization and malformed-response rejection.
- Idempotent ingest, content updates, removal and reopening without losing review history.
- Exact cross-source URL deduplication and independent listing removal.
- Rate-limit failure preservation and persisted backoff after reconnecting to the database.
- Concurrent-run lease.
- Salary threshold changes and unknown/ambiguous compensation.
- Conflicting Ashby remote/hybrid metadata.
- Accelerated unattended worker runs using explicitly synthetic fixtures in a temporary database.
- HTTP authentication, cross-origin rejection, settings/review persistence, and refusal to mark unsupported submitted status.

Frontend JavaScript syntax is checked with Node. No interactive browser or Android-device test has been performed. Live test databases and provider responses are excluded from Git.

## Live run — October 21, 2026
The server was launched with `serve --worker --db .data/unattended.sqlite3 --port 8001` against a fresh database. No discovery CLI command or browser request initiated the retrieval. Its worker completed the first due run automatically. A subsequent HTTP request read the already completed persisted results.
- 7 successful public employer boards; 1221 real listings fetched.
- 15 support-title candidates persisted; 9 excluded by the current triage rules.
- 4 candidates had explicit remote and US source locations. These are not verified full qualification matches; schedules, responsibilities and other requirements still need review.
- Actual feed examples include GitLab People Technology Analyst - Workday and Support Engineer (AMER). Source URLs, published salary evidence and retrieval dates are stored locally, not simulated.
- Known hybrid listings with contradictory remote booleans were excluded. Unavailable boards were removed from the configured source list after live validation.
- Authentication/HTTP contract tests and JavaScript syntax checks passed. External deployment, Android browser behavior and execution after a production host restart remain unverified.

Restart check: stopped the server gracefully, used SQLite online backup to retain the verified live database at the default `.data/jobs.sqlite3` path, and restarted with the documented `python3 -m careerpilot serve --worker` command. HTTP state retained all 15 listings and its one completed run; no duplicate early run occurred.
