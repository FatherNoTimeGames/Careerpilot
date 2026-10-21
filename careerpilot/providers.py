"""Only documented public ATS job-board APIs. No scraping or application submission."""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from email.utils import parsedate_to_datetime


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plaintext(value):
    parser = Text()
    parser.feed(html.unescape(value or ""))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def canonical_url(value):
    p = urllib.parse.urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("Posting URL must be public HTTPS")
    # Keep identity-bearing query fields (e.g. gh_jid); drop only known tracking.
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
             if not k.lower().startswith("utm_") and k.lower() not in {"source", "gh_src", "ref"}]
    return urllib.parse.urlunsplit(("https", p.netloc.lower(), p.path.rstrip("/"),
                                   urllib.parse.urlencode(sorted(query)), ""))


def fetch_json(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CareerPilot/0.1 (personal job discovery)",
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read(25_000_001)
                if len(raw) > 25_000_000:
                    raise ValueError("Source exceeds 25 MB safety limit")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry = exc.headers.get("Retry-After", "")
            delay = 2 ** attempt
            if retry.isdigit():
                delay = int(retry)
            elif retry:
                try:
                    delay = max(0, parsedate_to_datetime(retry).timestamp() - time.time())
                except (ValueError, TypeError, OverflowError):
                    pass
            if delay > 30:
                raise  # Persisted backoff must respect long Retry-After windows.
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def source_id(source):
    return source["provider"] + ":" + source["board"]


def load_sources(path):
    with open(path) as f:
        sources = json.load(f)
    if not isinstance(sources,list) or not 1<=len(sources)<=20:
        raise ValueError("Configure 1–20 employer boards per installation")
    ids = set()
    for source in sources:
        if not isinstance(source,dict) or not isinstance(source.get("employer"),str) or not source["employer"].strip():
            raise ValueError("Every board requires an employer name")
        if source.get("provider") not in {"greenhouse", "ashby"}:
            raise ValueError("Unsupported provider")
        if not isinstance(source.get("board"),str) or not re.fullmatch(r"[A-Za-z0-9_-]+", source["board"]):
            raise ValueError("Invalid board identifier")
        if source_id(source) in ids:
            raise ValueError("Duplicate source")
        ids.add(source_id(source))
    return sources


def retrieve(source, fetch=fetch_json):
    board = source["board"]
    provider = source["provider"]
    if provider == "greenhouse":
        payload = fetch(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true&pay_transparency=true")
    else:
        payload = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Invalid source snapshot: jobs array missing")
    jobs = []
    for raw in payload["jobs"]:
        if not isinstance(raw, dict):
            raise ValueError("Malformed job; refusing partial snapshot")
        if provider == "ashby" and raw.get("isListed") is False:
            continue
        title, ident = raw.get("title"), raw.get("id")
        url = raw.get("absolute_url") if provider == "greenhouse" else raw.get("jobUrl")
        if not title or ident is None or not url:
            raise ValueError("Malformed job; refusing partial snapshot")
        location = raw.get("location", {})
        if isinstance(location, dict):
            location = location.get("name", "")
        description = plaintext(raw.get("content") if provider == "greenhouse"
                                else raw.get("descriptionHtml") or raw.get("descriptionPlain"))
        jobs.append({"external_id": str(ident), "url": canonical_url(url),
                     "employer": source["employer"], "title": title,
                     "location": location or "", "description": description,
                     "employment_type": raw.get("employmentType"),
                     "is_remote": raw.get("isRemote"),
                     "workplace_type": raw.get("workplaceType"),
                     "country": ((raw.get("address") or {}).get("postalAddress") or {}).get("addressCountry"),
                     "compensation": raw.get("compensation"),
                     "pay_input_ranges": raw.get("pay_input_ranges"),
                     "source_updated_at": raw.get("updated_at") or raw.get("publishedAt")})
    if len({j["external_id"] for j in jobs}) != len(jobs):
        raise ValueError("Duplicate source IDs; refusing snapshot")
    return jobs
