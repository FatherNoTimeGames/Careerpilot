# Prototype 2 requirements

Status: planned, not implemented. Preserve the working discovery pipeline while adding these features in small, testable milestones.

## Résumé Studio — required before full application preparation

Provide a dedicated, mobile-friendly Résumé Studio for importing, verifying, revising, comparing, exporting and reusing résumés. Full application preparation depends on this capability and the verified master career profile.

### Import and correction

- Accept PDF and DOCX résumé uploads and preserve each original document unchanged in private storage.
- Extract and organize employment history, education, skills, dates and accomplishments. Retain source references so extracted claims can be compared with the original.
- Flag missing, outdated, ambiguous or contradictory information. Extraction is not confirmation; unsupported or unreadable content must be reported rather than silently omitted or invented.
- Allow manual correction of extracted information before approving it for the career profile.

### Master career profile

- Maintain a persistent, editable profile independent of document formatting. Allow facts and supporting evidence to be added or updated without reuploading a résumé.
- Distinguish confirmed facts, inferred details and information awaiting verification. Inferred or unverified claims must not silently become confirmed facts or appear as verified qualifications in exports.
- Never invent responsibilities, metrics, experience, certifications or accomplishments. Keep professional qualifications separate from personal technical experience.
- After initial verification, reuse the approved profile for future application preparation without repeated uploads or extensive manual editing.

### AI revision and optimization

- Rewrite using clear, natural, professional language while preserving the candidate's authentic experience and voice.
- Avoid generic AI-sounding phrases, exaggerated accomplishments, repetitive sentence structures, unnecessary buzzwords and keyword stuffing.
- Optimize readability and ATS compatibility. Tailor emphasis and terminology to a particular job description only when supported by verified candidate facts.
- Run proofreading and consistency checks before presenting a revision, including dates, employment history and unsupported claims.
- Display original and revised content together with explanations of significant changes. Preserve the original and let the user edit, approve or reject revisions.
- Isolate AI processing behind a replaceable interface. Verify the available execution capability before integrating it. Do not assume ChatGPT subscription access includes API access, and do not use separately billed AI APIs without explicit authorization.
- If no approved AI execution path is available, retain import, profile editing, deterministic checks, comparison and export. Clearly identify AI rewriting as unavailable and support a user-mediated revision workflow without pretending AI processing occurred.

### Export and version management

- Generate professional, ATS-compatible PDF and editable DOCX files using a simple single-column layout, standard headings, selectable text and conventional formatting.
- Verify PDF readability, completeness and layout before declaring an export ready. Check text extraction against approved content and inspect rendered pages for clipping, overflow, missing sections and page-break defects. A successful file-generation command alone is insufficient.
- Save approved résumé versions for reuse, downloading and selection for specific applications. Preserve the profile revision, source document and any target job associated with each version.
- Require explicit approval before replacing the master résumé. Revision generation, export and approval of a job-specific version must not implicitly replace the master.
- Clearly identify which résumé version was prepared or selected for each job. Later profile edits must not silently modify already approved versions.

### Acceptance checkpoints

1. Import a PDF and DOCX, retain originals, review extracted fields and warnings, manually correct them, and persist a verified profile across restarts. Include unreadable documents and contradictory dates in validation.
2. Add new verified information without another upload. Demonstrate that inferred and unverified details cannot silently become approved résumé claims.
3. Produce a revision through an approved AI path or clearly identified manual fallback; show the comparison, change explanations and proofreading/consistency results without adding qualifications.
4. Export PDF and DOCX from approved content. Verify PDF text completeness and rendered layout, including a multi-page résumé. Confirm both downloads preserve the selected version.
5. Approve and reuse a version for a specific job, confirm master replacement requires separate approval, and confirm later profile edits preserve prior approved versions.

Candidate documents and personal profile data must remain outside Git and public assets, with authenticated access and private persistent storage. Do not add paid services or transmit documents to an external processor without authorization.

## Other Prototype 2 features

- Evidence-based weighted matching with a documented scoring method and adjustable priorities.
- Qualification strengths, gaps, confidence and unresolved requirements based on verified profile facts.
- Better verification of benefits, schedules, certifications, internal versus external support and US remote eligibility.
- Expanded relevant employer coverage and stronger salary normalization without inventing compensation or deleting jobs when thresholds change.
- Feedback-based ranking adjustments with reset and override controls.

## Boundary with later prototypes

Résumé Studio revision or job tailoring is not authorization to prepare a complete application package. Full application preparation still requires authorization for the specific job. Master résumé approval, application preparation approval, final application approval and permission to submit are separate decisions. Never submit or mark an application submitted merely because a résumé was exported or an employer page was opened.
