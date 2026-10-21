# CareerPilot

Private, mobile-first job discovery with public employer ATS APIs, SQLite persistence and a server-side scheduler. Python 3.12+ with local document-processing libraries for Résumé Studio. No paid AI services, subscriptions, scraping, emails or submission integrations.

## Run

From the checkout root:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
.venv/bin/python -m careerpilot init
.venv/bin/python -m careerpilot serve --worker
```

Initialization creates a random owner password in `.data/owner-password` with mode 0600, without printing its value. Read it securely on your host when signing in as `careerpilot`; never paste it into chat or commit it. Existing passwords are preserved on repeated initialization. `CAREERPILOT_PASSWORD` overrides the local password file.

The web server binds to loopback port 8000. The worker starts automatically, checks its persisted schedule every 30 seconds, and retrieves all configured sources every six hours by default. The browser can be closed. A **persistent host must remain running**; a development task is not a production hosting guarantee.

Other commands:

```sh
.venv/bin/python -m careerpilot discover  # One live retrieval; nonzero exit on any source failure
.venv/bin/python -m careerpilot worker    # Worker-only process (web server optional)
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
node --check static/studio.js
```

`--db /persistent/path/jobs.sqlite3` and `--sources /path/sources.json` are available on every command. Alternatively use `CAREERPILOT_DB`. Do not run multiple versions of the application against one database. A database lease prevents overlapping discovery runs in one installation. Keep the machine clock accurate.

## Hosting verification and privacy

The Codex session has Python, writable storage, outbound HTTPS and local Chromium testing. No Sites deployment API or verified Sites storage, background execution, managed authentication, AI execution, browser automation or notification capability is available here. These capabilities **have not been verified for ChatGPT Sites**; local browser tests do not establish Sites hosting support. There is no Sites URL or published production deployment. A static-only host cannot run this application or its scheduler. No paid services have been introduced.

A persistent Linux server is a supported deployment target. `deploy/careerpilot.service` is an example, not an installed service: create a dedicated `careerpilot` account, place the checkout in `/opt/careerpilot`, create `/var/lib/careerpilot` owned by that account, and install/enable the unit with your host's administrator. Use Python 3.12+ on Linux, install the pinned dependencies into `/opt/careerpilot/.venv`, and run initialization as the service account with `--db /var/lib/careerpilot/jobs.sqlite3`. Keep it behind a TLS reverse proxy with access restricted to you; do not expose port 8000 directly. Configure the reverse proxy to preserve the Host header and use HTTPS externally.

Use the generated private owner password or set a strong `CAREERPILOT_PASSWORD` (16+ characters) in the host's secret manager or protected environment file. HTTP Basic username: `careerpilot`. This protects **all** UI and API routes when set. Loopback access without any initialized password is only available for the discovery UI; all Résumé Studio routes refuse access until owner authentication is configured. Non-loopback binding refuses to start without a long password. Application Basic authentication is only safe externally with HTTPS. No external credentials are stored. There is no multi-user isolation or account recovery yet.

SQLite lives in ignored `.data/` by default, with directory mode 0700 and database mode 0600 when created by the application. Use host disk encryption and encrypted backups for production; SQLite is not encrypted by this app. Back up using SQLite's online backup API while the service runs, or stop the service before copying its database. Never commit databases, environment files or candidate documents. Original candidate documents, extracted text, profile revisions, résumé versions and generated exports are stored privately in this SQLite database. The owner-password file is separate; protect and back it up with the database. See [Résumé Studio](docs/resume-studio.md) for workflow details and limitations.

Required outbound hosts: `boards-api.greenhouse.io`, `api.ashbyhq.com`. GitHub is needed only for repository operations. Public board reads need no credentials. Source URLs are constructed from validated board slugs; no arbitrary URL fetch or employer form automation is implemented.

## Discovery behavior

- `sources.json` contains employer boards, not sample job results. Employers can move ATS providers; source health exposes failures. Edit sources and restart the worker to change coverage. Employer coverage is a starting set, not a comprehensive search of the market.
- Greenhouse Job Board API: `/v1/boards/{board}/jobs?content=true&pay_transparency=true`.
- Ashby public posting API: `/posting-api/job-board/{board}?includeCompensation=true`.
- Requests use TLS verification, a 25-second timeout and up to three attempts for transient network/HTTP 429/5xx failures. Rate limits with long retry windows defer instead of retrying early. Failures get persisted exponential backoff (5 minutes to 24 hours), applied on subsequent scheduled runs. No CAPTCHA or authentication bypass.
- A complete source response is validated before an atomic ingest. Invalid or failed snapshots never retire existing listings. Two consecutive successful snapshots without a listing mark it removed from that source. This indicates removal from a feed, **not independently confirmed expiration**. A fresh listing from another source keeps the opportunity active. Changed descriptions and reopened listings get audit events; reviews are preserved.
- Duplicate source IDs and exact canonical posting URLs are deduplicated. Tracking query parameters are stripped, identity-bearing fields preserved. Different URLs on unrelated providers are **not fuzzily merged**, since similar titles can represent different requisitions. Cross-provider duplicate review remains a known limitation.
- All locally relevant support titles are stored, including exclusions. Hybrid/onsite postings, explicit non-US country locations, certain travel requirements and non-full-time titles/types are excluded from the normal queue. A source `workplaceType` of Hybrid/OnSite overrides `isRemote: true` (a contradiction observed in live Ashby data).
- Unknown facts are not treated as satisfied requirements. Review cards distinguish confirmed source location data from unresolved eligibility. US location does not establish eligibility in every state. Benefits, internal versus external support, travel, certifications and schedule still need human verification. Deterministic triage is not comprehensive natural-language verification.
- Salary categories are computed when read, so changing the target preserves and recategorizes jobs. Explicit employer-published USD annual base ranges are extracted conservatively with evidence. Ranges crossing the threshold appear in Primary with a warning. Unclear currencies, geographic bands, bonuses and ambiguous compensation remain Unknown. No estimates are displayed. The normalization helper supports hourly pay only with explicit paid hours and paid weeks; live hourly/monthly/weekly and structured compensation extraction is not yet implemented.
- There is no compatibility percentage or learned ranking yet. Jobs are shown newest first. “Interested” and “Skip” persist; neither authorizes preparation or submission. The API rejects submitted and other unsupported status transitions.

## Milestones

**Prototype 1 implemented:** public Greenhouse/Ashby adapters, persisted discovery, server-side scheduling, source-health/error logs, updates/removal tracking, conservative remote/salary triage, mobile dashboard, salary sections, review bookmarks, configurable thresholds/interval/pause, private access controls and tests.

**Remaining before production:** choose/verify a persistent host (Sites capability unknown), activate service supervision and encrypted backups, verify externally private HTTPS access, then verify unattended operation across host restarts. Cloud environment instruction drafts do not deploy an app.

**Prototype 2 — Résumé Studio implemented:** private PDF/DOCX import and original retention, correctable unverified extraction, editable versioned career profile, explicit verification, manual revision comparison with deterministic checks, rendered PDF preview, approved PDF/DOCX downloads, separate master-replacement approval and job-specific version selection. AI rewriting is unavailable without an approved provider. See [the Studio guide](docs/resume-studio.md) and [Prototype 2 requirements](docs/prototype-2.md).

**Next checkpoint — remaining Prototype 2 matching:** evidence-based weighted matching, benefits/schedule/certification verification, more relevant employer coverage, stronger salary normalization, configurable scoring and resettable learned preferences. Full application preparation remains a later milestone. Do not invent qualifications. Distinguish professional from personal experience.

**Later:** truthful application packages after job-specific preparation authorization; separate final-review and submission authorization; supported submission confirmation; notifications, briefings and email integration only with authorization. There is no Prepare or Submit button pretending those capabilities exist in this prototype.

Test fixtures are synthetic and only enter isolated temporary test databases. The application never seeds example jobs.
