# Compensation and source-coverage checkpoint

CareerPilot retains employer-published pay evidence separately from its annual USD base figure. A missing annual figure means the annual amount could not be verified, not necessarily that no pay information exists. Cards show published rates and the specific unresolved information under **Pay evidence**.

## Sources

Thirteen configured employer boards use the public Greenhouse or Ashby job-board APIs. New boards in this checkpoint are Oscar Health, Omada Health, Flatiron Health, Rula, Headway and Ashby. All returned real nonempty job lists in live checks. A board can have zero relevant roles today; keeping it scheduled allows future roles to be discovered without another manual search. This is a curated starting set, not comprehensive market coverage.

The support-title filter now includes IT/endpoint engineering, IT coordination, and technical training/implementation titles. Discovery relevance is not qualification or eligibility confirmation. Onsite, hybrid, non-US and temporary/internship roles can be retained for audit but excluded from normal review. No job or salary data is seeded into the live database.

`sources.json` allows 1–20 boards in one installation. Edit and restart the worker to change coverage. Sources must use a supported provider, safe board slug and employer name. At the current six-hour schedule, there is one normal full-board request per source per run, with bounded retries for failures. Larger coverage needs a scheduler/batching change rather than silently unlimited polling.

Lever was investigated but its endpoint was denied by this environment's network proxy. No Lever adapter or unverified Lever source was activated, and its unused destination was removed from the draft. It remains a future integration, requiring supported access and live verification.

## Pay evidence and base-pay boundaries

- **Ashby:** parse typed `Salary` components and explicit `interval`, `currencyCode`, `minValue` and `maxValue`. Use individual compensation tiers; never substitute the aggregate summary's outer range. Bonus, commission and equity components do not contribute base pay. An OTE/total-cash label is not accepted as base pay.
- **Greenhouse:** convert `min_cents`/`max_cents` to currency units, retain the title/blurb, and require base-pay context plus an explicit interval. The API field alone does not establish an annual period. A matching explicit textual range can corroborate its period.
- **Posting text:** support explicit annual/hourly/weekly/monthly salary/base-pay/wage phrases, fixed amounts and ordinary ranges (including shared `k` suffixes). Reject estimated, non-base, mixed-currency, malformed and ambiguous ranges. A bare dollar symbol is only treated as USD with an explicitly US source location/country or a USD label.
- **Geography:** prioritize a clearly applicable state band. A national US band can be used when the other geographic bands are explicit, understood locations outside the saved work state (e.g. SF/NYC versus Texas). A state alone cannot select a city-specific band within that same state. Unexplained tiers or conflicting remaining ranges stay Unknown. No low/high endpoints are combined across geographic bands. Scope warnings remain visible; a published band is not an offer or proof of individual eligibility.
- **Currencies:** only verified USD base pay is used for the USD salary sections. Other published currencies are retained as evidence, never converted using an estimated exchange rate.

## Annualization without guessed schedules

| Published interval | Required evidence | Calculation |
|---|---|---|
| Year | Explicit annual period | Published amount |
| Hour | Explicit paid hours per year, or paid hours/week **and** paid weeks/year | Rate × paid annual hours |
| Week | Explicit paid weeks/year | Weekly rate × paid weeks |
| Month | Explicit paid months/year | Monthly rate × paid months |

“Full time” or “40 hours/week” alone does not establish 52 paid weeks. There is no automatic 40×52 or 12-month assumption. Conflicting/ranged schedules remain unresolved. Unsupported or missing periods do not become annual merely because the dollar amount looks large. Greenhouse or text listings previously interpreted as annual under that convention may therefore move to Salary Unknown; their published evidence and job history remain intact.

For example, $25–$30/hour with 35 paid hours/week and 48 paid weeks/year becomes $42,000–$50,400 annual base. It enters Primary with a warning that the minimum is below $50,000. Without the paid schedule, it stays Salary Unknown and still shows $25–$30/hour.

Calculations use decimal arithmetic and retain cents. A maximum of $49,999.60 stays under $50,000 and is displayed with cents. Threshold changes recategorize existing records rather than deleting them. No bonus or overtime amount is added.

## Reliability and preservation

Discovery renews its database lease between sources and after retrieval. If another worker takes over, stale fetched results are not committed and the old worker cannot delete the new owner's lease. An interrupted discovery returns a nonzero CLI result.

Source fingerprints cover normalized employer-source fields, not derived salary or matching output. Updating a parser does not manufacture a posting-change event. Legacy fingerprints are migrated without expiring an owner check when the source itself is unchanged. Actual posting changes still invalidate requirement reviews as before.

## Validation

Synthetic automated tests cover typed base pay, bonus exclusion, Greenhouse cents, explicit periods, fixed/ranged pay, paid calendars and conflicts, currencies, geographic ambiguity, Texas versus city bands, cents/threshold boundaries, preserved records, role coverage, bounded configuration, lease takeover, and parser-versus-source changes. They never populate the owner's job database.

Optional real mobile browser test:

```sh
PYTHONPATH=. python3 tests/browser_compensation.py
```

It checks annualized hourly pay, below-target minimum warnings, unknown-schedule rate display, cents, threshold changes and reload persistence. Matching and Résumé Studio browser checks remain separate regressions.

Live coverage evidence is recorded in VALIDATION.md. No employer eligibility, candidate qualification, production host availability or Sites capability is established merely by a successful feed retrieval.
