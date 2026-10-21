"""Conservative discovery triage, not a personalized compatibility percentage."""
import re

TARGET = re.compile(r"(?:\b(?:IT|desktop|endpoint|help\s?desk|service\s?desk|application|technical|technology|systems?)\b.{0,35}\b(?:support|technician|analyst|operations|specialist|administrator)\b|\bsupport\b.{0,25}\b(?:IT|desktop|endpoint|technician|analyst|engineer)\b)", re.I)


def relevant(job):
    return bool(TARGET.search(job["title"]))


def annualize(low, high, period, hours_per_week=None, paid_weeks=None):
    factors = {"year": 1, "month": 12}
    if period == "hour":
        if hours_per_week is None or paid_weeks is None:
            return None
        factor = hours_per_week * paid_weeks
    elif period == "week":
        if paid_weeks is None:
            return None
        factor = paid_weeks
    elif period in factors:
        factor = factors[period]
    else:
        return None
    if low < 0 or high < low:
        return None
    return {"min": round(low * factor), "max": round(high * factor), "currency": "USD"}


def salary(job):
    text = job["description"]
    # Only employer-published USD annual BASE ranges with explicit pay context.
    # Ambiguous amounts, non-USD, bonuses and hourly assumptions stay unknown.
    pattern = re.compile(
        r"(?:base\s+(?:salary|pay|compensation)|annual\s+(?:base\s+)?salary|salary\s+range)"
        r"[^.!?]{0,100}?(?:USD\s*|\$)([\d,]+(?:\.\d+)?)\s*([kK]?)\s*"
        r"(?:-|–|—|to)\s*(?:USD\s*|\$)?([\d,]+(?:\.\d+)?)\s*([kK]?)", re.I)
    ranges = []
    for match in pattern.finditer(text):
        low = float(match[1].replace(",", "")) * (1000 if match[2] else 1)
        high = float(match[3].replace(",", "")) * (1000 if match[4] else 1)
        context = text[max(0, match.start()-60):match.end()+100].lower()
        if re.search(r"(?:per\s+hour|hourly|/hr|\b(?:cad|aud|canadian|ote)\b|total compensation)", context):
            continue
        if 10000 <= low <= high <= 1000000:
            ranges.append((low, high, match[0]))
    # Multiple geographic bands are not combined into a fictitious single range.
    if len(set((a, b) for a, b, _ in ranges)) == 1:
        low, high, evidence = ranges[0]
        return {**annualize(low, high, "year"), "evidence": evidence,
                "basis": "Employer-published annual base range; geographic eligibility needs review"}
    return None


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
    if re.search(r"\b(?:contract|part[- ]time|temporary|internship)\b", str(job.get("employment_type") or "").lower() + " " + title):
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
