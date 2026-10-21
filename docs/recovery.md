# Private backups and recovery

The `backup` command uses SQLite's online backup API, so committed data in an active WAL is included without stopping discovery. It checks integrity, foreign-key references and required tables before publishing a standalone snapshot. Output is created atomically with mode 0600 and an existing destination is never overwritten. A failed validation leaves no published snapshot. Only record counts are logged, never candidate content or passwords.

From the checkout root, using a directory on protected storage:

```sh
.venv/bin/python -m careerpilot backup --db .data/jobs.sqlite3 --output /protected/backups/careerpilot-2026-10-21.sqlite3
.venv/bin/python -m careerpilot verify-backup --db /protected/backups/careerpilot-2026-10-21.sqlite3
```

Use a unique filename each time. The commands do not load source configuration, initialize a missing database or run schema migrations. Verification is read-only. Backups include documents, profiles, résumé versions, jobs, settings and audit records; **they are not encrypted by the application**. Store them on encrypted storage, keep an encrypted off-host copy, and configure retention for your chosen host. No backup service, host scheduler or encryption key is configured automatically. Do not commit snapshots or upload them to public storage.

The owner password is separate from the database and is intentionally not copied. Preserve it in protected secret storage, or generate a new local password during recovery. A `CAREERPILOT_PASSWORD` environment override remains authoritative and must be managed separately. Back up customized `sources.json` and record the deployed Git revision as well.

## Recovery drill

1. Stop the web service and any separate workers. Keep the original database and its WAL/SHM files together; do not overwrite or delete them.
2. Verify the snapshot using the application revision that created it. A successful check establishes SQLite consistency, not that every candidate fact is correct.
3. Restore into a **new, empty private directory**. Copy only the verified standalone snapshot, set directory mode 0700 and database mode 0600. Do not place an old WAL or SHM beside the restored file.
4. Run `init --db /new/private/directory/jobs.sqlite3` using the pinned environment. This preserves the restored data and creates a new owner-password file if absent. Recover the old password separately only if desired. Never print it into logs or chat.
5. Start one server against the restored database with no `--worker` initially, behind the same private HTTPS access controls. Check job counts, profile facts, original résumé downloads, approved versions and settings. Do not expose the recovery server publicly.
6. Once reviewed, stop the recovery server and switch the supervised service to that restored path. Enable one scheduled worker. A restored discovery lease may delay the next run until its stored expiry; do not force-delete a lease while any old process may still run.
7. Confirm a scheduled retrieval completes and inspect source-health logs. Keep the original installation until recovery is confirmed. Document the recovery date and snapshot used.

Automated tests exercise a live WAL snapshot, byte-identical original-document recovery, profile retention, permissions, refusal to overwrite, invalid/missing inputs and broken-reference rejection. Production restart, encrypted off-host backup and operator recovery drills still require an actual persistent host.
