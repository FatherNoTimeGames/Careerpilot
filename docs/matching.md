# Personalized matching v1

Local, deterministic scoring; no AI API or paid service. This describes a review aid, not a hiring probability, a substitute for reading the posting or an independent credential check.

## Verified profile boundary

Personalized scores require the current career profile to be explicitly verified in Résumé Studio. Only Confirmed professional employment, skills, accomplishments and certifications contribute technical evidence. Pending/inferred facts and Personal Technical Experience do not become professional qualifications. Negative statements and disclaimers are excluded where recognized. Basic Active Directory/account support is distinct from advanced domain-controller/forest/group-policy-design topics; basic networking is distinct from network engineering. Profile changes immediately recompute scores without changing old approved résumé files.

If the profile is unverified, cards show “Profile verification needed” and no score. Do not confirm candidate facts on the owner's behalf to enable scoring.

## Hard requirements, separately from scores

Eight checks cover fully remote work, US hiring, work-state eligibility, full-time employment, benefits, no required travel, no additional certification before applying, and suitable IT/support responsibilities. Each check is Pass, Fail or Unknown with posting evidence or a dated owner-verification note.

- Any Fail excludes the opportunity from the default review queue regardless of its score. Explicit call-center/sales/customer-service representative titles are excluded. Other external technical-support roles need owner judgment about whether customer service dominates.
- Any Unknown leaves the job in Needs verification. Silence never satisfies a requirement. Only when all checks pass is the label Requirements verified displayed; other qualification/schedule questions can still remain.
- Explicit hybrid/onsite obligations override a generic remote boolean. A US location does not establish eligibility in every state. Work-state preferences are private and editable; unknown restrictions remain flagged. State checks recognize specific supported phrasing; complex restrictions still need review.
- Certification mentions, ambiguous preferred/required language and after-hire requirements remain for owner review rather than fabricated assumptions. A minimum number of years is flagged, not an automatic rejection.
- Under a card's evidence details, the owner may correct/verify checks using an official posting or employer confirmation. Each requires a quote or note and explicit acknowledgment. These attestations are scoped to the posting fingerprint, profile revision and work state. Posting/profile/state changes stop applying old checks and display a stale-review warning.

Extraction uses conservative vocabulary and patterns. Unrecognized wording, long/complex descriptions, exceptions, optional skills and unusual schedules can be misclassified; the source and owner checks remain available. “Requirements verified” does not guarantee that every qualification or allowed-state rule was understood by the parser.

## Documented score

| Criterion | Default relative weight | Evidence value |
|---|---:|---|
| Verified technical overlap | 35 | Supported recognized technical topics / all recognized posting technical topics |
| Healthcare/teaching transfer | 10 | Fraction of detected healthcare or staff-training connections supported by confirmed professional employment |
| Annualized base pay | 20 | 1 if published minimum reaches target; 0.5 if range crosses target; 0 below; unknown if not verified |
| Working hours | 10 | 1 for recognized explicit hours within 7 AM–5 PM Central; 0 for recognized incompatible hours/shifts; unknown otherwise |
| Internal employee support | 10 | 1 internal-only evidence; 0.5 mixed internal/external; 0 external-only; unknown without evidence |
| On-call | 10 | 1 explicit no-on-call; 0 recognized required rotation; unknown if absent or conflicting |
| Career development | 5 | 1 explicit growth/mentorship/training evidence; unknown if absent |

`score = 100 × sum(weight × evidence value) / sum(weights)`.

Unknown values earn zero points; they are not treated as neutral/positive evidence. Displayed evidence coverage is `100 × known criterion weights / all weights`, separate from the score. It is a completeness measure, not probability or independent accuracy. Nonzero coverage means a criterion could be evaluated, not that every claimed skill is possessed. Each criterion shows its evidence, weight and points. Recognized posting terms are potential requirements; a gap is “not established in confirmed facts,” not proof the candidate lacks it. The vocabulary is finite and cannot cover every job requirement.

Weights are editable from 0–100 relative units, with at least one positive. They are normalized automatically; changing priorities never modifies job records, salary categories, profile facts or résumé versions. Scores use a snapshot's current target and verified facts. Pay uses the published annual interval or explicit-calendar normalization described in [compensation rules](compensation.md); an unknown annual amount earns no salary points even when an hourly rate is published. A high preference score cannot remove an exclusion.

## Ordering and feedback

Salary sections remain Primary / Secondary / Unknown using the configured threshold. Within a section, requirements-verified jobs come first, followed by unresolved jobs and then exclusions if shown. Rank next uses match points plus the separate bounded feedback adjustment; new discoveries break ties.

Each job contributes at most one current feedback record:

- Interested supplies positive preference evidence. A reason can narrow the learned dimension.
- Skip supplies negative preference evidence only when the owner selects a reason. Unexplained skips do not teach a salary/schedule preference. Qualification-gap feedback never invents missing skills or changes scoring rules.
- Restore removes that job's learning record. Repeated clicks on one job cannot amplify its contribution.

For each preference trait, `signal = 5 × (interested − reasoned skips) / max(3, number of examples)`. The adjustment is the mean of matching trait signals, clamped to ±5 ranking points. Sparse feedback therefore has a smaller effect. Trait counts and the resulting adjustment are visible on the card. It does not alter the base score, qualifications, hard filters or salary section, and exclusions get no adjustment.

Learning can be disabled to ignore signals or reset to start a new learning epoch. Reset preserves job review history and old feedback records but excludes old-epoch examples from ranking. Application-outcome learning is deferred until real outcome tracking exists; no submission/interview outcome is inferred from opening a page or approving a résumé.

## Recurring gaps

The overview counts up to five recurring technical topics among active, nonexcluded primary jobs that have not been skipped. Recommendations link only to optional documentation/local practice or suggest asking the employer about training. No paid certification, course or subscription is recommended. No gap report is generated before profile verification.

## Validation

The automated suite covers exact score math, unknown evidence, Texas rules, negation, conflicting remote flags, credential/profile boundaries, salary bands, source/state/profile invalidation, bounded/deduplicated/resettable feedback, private payloads and gap aggregation.

Optional actual mobile browser regression:

```sh
PYTHONPATH=. python3 tests/browser_matching.py
```

It uses isolated synthetic jobs and a verified synthetic profile to exercise scores, evidence, requirement review, feedback, stale state checks, weights, learning controls and reload persistence. Real candidate facts are not auto-verified by this check.
