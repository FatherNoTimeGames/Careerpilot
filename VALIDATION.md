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

## Résumé Studio checkpoint — October 21, 2026

- 20 automated tests pass: all 10 discovery/HTTP tests plus 10 Studio cases covering local PDF/DOCX extraction, byte-identical original retention, image-only and malformed documents, unverified/inferred claim exclusion, date contradictions, stale updates, immutable approved versions, separate master approval, job selection without application status changes, private access and multi-page export integrity.
- Pinned document dependencies are installed in `.venv` using the existing local packages. No paid service or AI execution path is configured.
- A real Chromium run at 393×851 completed import → profile confirmation/verification → manual wording comparison → saved checks → rendered preview → approval → PDF download → explicit master replacement → reload persistence. No JavaScript errors or horizontal overflow. A subsequent extended check also covers unsaved wording across navigation and selecting a version for a job.
- Inspected all three rendered pages of a synthetic multi-page PDF: readable single-column text, intact margins, no clipped or missing content. Programmatic PDF text completeness, DOCX round-trip and rendered-margin checks also passed. Original/revised mobile UI inspected.
- Synthetic browser/test data uses isolated temporary databases. No real candidate résumé has been uploaded or revised. Scanned-PDF OCR, AI rewriting and Word-specific visual rendering remain unsupported. Production Sites hosting remains unverified.

## Personalized matching checkpoint — October 21, 2026

- 31 automated tests pass, preserving discovery and Résumé Studio coverage. Eleven new matching tests cover documented score math, missing evidence, professional-versus-personal/uncertain facts, Texas restrictions, schedule conversion, high-score exclusions, salary bands, stale verification, safe private payloads, gap summaries and bounded/resettable feedback.
- Real Chromium matching flow at 393×851 passed: score breakdown, owner requirement review, feedback adjustment, work-state change invalidating old review, weight/learning controls, reset and reload persistence. The existing Studio browser regression also passed. No JS errors or horizontal overflow; matching settings inspected visually.
- The live development instance retains all 15 real saved listings and its running discovery worker. Texas is stored as the owner's work-state preference. The six brief-based profile facts remain pending; no personalized score is fabricated before owner verification. No real job requirement was owner-verified and no feedback was invented by these tests.
- Setup/startup configuration drafts updated for matching validation. Sites hosting, broader employer coverage, comprehensive compensation parsing, semantic requirement verification and application-outcome learning remain outstanding as documented in docs/matching.md and README.md.

## Expanded coverage and compensation — October 21, 2026

- Live server-side worker, launched against a fresh validation database without browser input, completed retrieval from 13 employer boards: 1,702 real listings fetched and 20 support-title candidates saved. The existing owner database also retains those 20 records (five new since the prior 15); these are not 20 confirmed matches.
- Five additional healthcare boards and Ashby were verified and configured. Boards with no currently relevant openings remain scheduled for future discovery. Unsupported/blocked Lever integration was deferred without an activated source or unused network destination.
- All prior 31 automated tests remain, plus 12 compensation/coverage/reliability tests. Cases include paid-calendar conversions, structured base pay versus bonuses, cents, geographic conflicts, Texas versus city-specific bands, title filtering and lease takeover. Test/browsing data remains isolated and synthetic.
- Published base ranges without an explicit period now stay Salary Unknown rather than assuming a year; actual hourly/other rates remain visible. No paid AI/API service, application authorization, résumé upload or candidate verification was introduced. Production hosting and full semantic eligibility verification remain unverified.
- Final compensation, matching and Résumé Studio Chromium mobile flows all passed with no JavaScript errors or horizontal overflow. Pay UI checks include $42,000–$50,400 from an explicit paid calendar, $30–$35/hour retained without an invented annual amount, and $49,999.60 staying below $50,000. Inspected the rendered pay-evidence card.
- A repeat live retrieval added zero duplicate jobs. The current authenticated server confirms 13 healthy sources, 20 saved public listings, Texas retained, and no personalized scores while the six owner-profile facts remain pending. All 43 automated tests passed; the extra legacy-fingerprint assertion also passed in the targeted compensation suite.
