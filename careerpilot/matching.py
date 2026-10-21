"""Conservative discovery triage, not a personalized compatibility percentage."""
import re
from .compensation import annualize, salary

TARGET = re.compile(r"(?:\b(?:IT|desktop|endpoint|help\s?desk|service\s?desk|application|technical|technology|systems?)\b.{0,35}\b(?:support|technician|analyst|operations|specialist|administrator)\b|\bsupport\b.{0,25}\b(?:IT|desktop|endpoint|technician|analyst|engineer)\b)", re.I)


ADDITIONAL_TARGET = re.compile(r"\b(?:IT|desktop|endpoint|end[- ]user(?: computing)?)\s+(?:(?:systems?|support|operations|services)\s+)?(?:engineer|coordinator)\b|\b(?:technical|IT)\s+(?:trainer|training specialist|implementation (?:support|specialist))\b", re.I)


def relevant(job):
    return bool(TARGET.search(job["title"]) or ADDITIONAL_TARGET.search(job["title"]))


def category(pay, target):
    if not pay:
        return "unknown"
    return "primary" if pay["max"] >= target else "secondary"


def assess(job):
    loc = job["location"].lower()
    text = job["description"].lower()
    title = job["title"].lower()
    reasons, verify = [], []
    remote = "verified" if job.get("is_remote") is True or "remote" in loc or str(job.get("workplace_type", "")).lower() == "remote" else "unknown"
    workplace = str(job.get("workplace_type") or "").lower()
    if workplace in {"hybrid", "onsite", "on-site"} or re.search(r"\b(?:hybrid|on[- ]site|not remote)\b", loc) or job.get("is_remote") is False:
        remote = "rejected"
        reasons.append("Posting location requires on-site or hybrid work")
    elif remote == "unknown":
        verify.append("Fully remote status not established by source location")
    us = "verified" if re.search(r"\b(?:united states|usa|u\.s\.|us)\b", loc) else "unknown"
    if str(job.get("country") or "").lower() in {"us", "usa", "united states"}:
        us = "verified"
    if us == "unknown" and re.search(r"\b(?:canada|united kingdom|ireland|india|south korea|australia|germany|france)\b", loc):
        reasons.append("Source location lists a non-US country without US eligibility")
    if us == "unknown":
        verify.append("US hiring eligibility and allowed states")
    if re.search(r"\b(?:contract|part[- ]time|temporary|internship|intern)\b", str(job.get("employment_type") or "").lower() + " " + title):
        reasons.append("Not a permanent full-time position")
    if re.search(r"\b(?:travel (?:is )?required|must (?:be able to )?travel)\b", text) and not re.search(r"\bno travel (?:is )?required\b", text):
        reasons.append("Required travel stated; inspect posting")
    if re.search(r"\b(?:call cent(?:er|re)|sales representative|customer service representative)\b", title):
        reasons.append("Customer service or sales dominated title")
    if not re.search(r"\bfull[ -]?time\b", str(job.get("employment_type") or "").lower() + " " + text):
        verify.append("Full-time employment")
    if not re.search(r"\b(?:health insurance|medical insurance|healthcare benefits|medical, dental)\b", text):
        verify.append("Benefits")
    if re.search(r"\b(?:certification|certified|comptia|ccna|itil)\b", text):
        verify.append("Certification requirement versus preference; no certifications held")
    verify.extend(["Schedule, on-call duties, travel and internal versus customer support",
                   "Experience requirements and technical responsibilities"])
    if re.search(r"\b(?:senior|sr\.?|lead|principal|manager|director)\b", title):
        verify.append("Seniority may exceed verified experience")
    return {"remote": remote, "us": us, "rejected_reasons": reasons,
            "verification_needed": verify,
            "eligibility": "excluded" if reasons else "needs_review",
            "confidence": "Partial: source facts and keyword triage; human verification required"}
