"""State charity registration source for regen_v3.

Surfaces state-level charity registrations for billionaire subjects from
the two highest-concentration domiciles:

  CA — Registry of Charitable Trusts (rct.doj.ca.gov)
        ASP.NET form. We POST a search by `full_name` and parse the
        results table (org name, status, RCT number, FEIN, city).
  NY — Charities Bureau (charities-search.ag.ny.gov)
        React SPA backed by a clean JSON API at
        charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch.

We treat each registry hit as a `reference_only` candidate (lands in
`sources_all`, never in dollar-bearing event slots). The presence of a
state registration is a *pointer* — confirming a vehicle exists in that
domicile, with status (e.g. Current/Dissolved/Delinquent). Dollar
amounts are not parsed at the search level; the deep link points the
human reader at the underlying detail page if they want to dig further.

Confidence:
  - "high"   if the FEIN on the registry record matches an EIN already
             attached to the subject's `detected_vehicles.foundations_*`.
  - "medium" otherwise (name-only match — the org name contains a
             searched token, but FEIN didn't reconcile).

Cache:
  regen_v3/cache/state_charities/<sha>.json
  Key = sha256(state + "|" + lowercased search term). Same subject +
  same caches → identical output. Failures (WAF / 403 / timeout) write
  an empty cache so re-runs don't hammer the registry; pass
  `refresh=True` to bypass.

Fallback:
  If a network call fails AND no usable cache exists, we still emit a
  single deep-link `reference_only` candidate per (subject, state) so
  downstream readers get a "go check this" pointer. Confidence "low".
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


# CA's rct.doj.ca.gov serves a legacy ASP.NET stack on a TLS endpoint
# that OpenSSL's default cipher policy (SECLEVEL=2) refuses to handshake
# with. We build a one-off SSL context with SECLEVEL=1 specifically for
# that host. urllib (stdlib) lets us inject a context cleanly; using
# requests would require subclassing HTTPAdapter for the same effect.
def _legacy_tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


_CA_TLS_CTX = _legacy_tls_context()

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "state_charities"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from categories.foundations import normalize_ein  # noqa: E402

try:
    from regen_v3._atomic import atomic_write_json  # type: ignore
except Exception:  # pragma: no cover - in-package fallback
    from _atomic import atomic_write_json  # type: ignore

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 25
_PAUSE = 0.6   # courtesy delay between live calls
_MAX_HITS_PER_TERM = 12  # cap so a generic surname doesn't flood sources_all

# Public landing pages used as `source_url` for emitted candidates. The
# CA detail navigation is intra-form (__doPostBack), so the stable
# anchor is the search URL with the org's name pre-filled.
_CA_SEARCH_PAGE = "https://rct.doj.ca.gov/Verification/Web/Search.aspx?facility=Y"
_NY_SEARCH_PAGE_TMPL = (
    "https://charities-search.ag.ny.gov/RegistrySearch?searchValue={q}&searchType=name"
)
_NY_API_TMPL = (
    "https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch"
    "?orgName={q}&searchType=organization"
)
_NY_DETAIL_TMPL = (
    "https://charities-search.ag.ny.gov/RegistryDetail?orgID={oid}"
)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_key(state: str, term: str) -> str:
    return hashlib.sha256(f"{state.upper()}|{term.strip().lower()}".encode()).hexdigest()


def _cache_path(state: str, term: str) -> Path:
    return CACHE_DIR / f"{_cache_key(state, term)}.json"


def _load_cache(state: str, term: str) -> dict | None:
    p = _cache_path(state, term)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_cache(state: str, term: str, payload: dict) -> None:
    # Atomic write: cache key is sha(state|term); two subjects sharing
    # a surname or org-prefix search term will race here.
    atomic_write_json(_cache_path(state, term), payload)


# ---------------------------------------------------------------------------
# Subject -> search terms
# ---------------------------------------------------------------------------

_STOPWORDS = {"the", "a", "an", "of", "and", "&"}


def _surname(name: str) -> str:
    """Last alphabetic token of a personal name — used as the surname
    anchor when filtering registry results."""
    parts = re.findall(r"[A-Za-z][A-Za-z\-']+", name or "")
    return parts[-1].lower() if parts else ""


def _prefix_token(name: str, n: int = 2) -> str:
    """First n significant tokens of a foundation/org name. CA + NY both
    do prefix-style matching (`Bloomberg Family Foundation` searches as
    that exact prefix and finds nothing if the registered name uses a
    different word order); shorter prefixes are far more recall-friendly
    and we filter by surname anchor afterwards."""
    tokens = [t for t in re.findall(r"[A-Za-z][A-Za-z\-']+", name or "")
              if t.lower() not in _STOPWORDS]
    return " ".join(tokens[:n])


def _terms_for_subject(record: dict) -> list[str]:
    """Search terms for CA + NY registries.

    Both registries prefix-match, so we emit:
      1. Surname alone (broadest — caught by surname anchor on results)
      2. First-1 and first-2 significant tokens of each foundation name
      3. Full personal display name (last resort)
      4. Full foundation name (only useful if registry mirrors it exactly)
    Order matters: cheapest/highest-recall queries first so we hit
    rate-limits on the noisier ones if anything.
    """
    out: list[str] = []
    seen: set[str] = set()

    person = record.get("person") or {}
    name_display = person.get("name_display") or ""
    surname = _surname(name_display)
    if surname and surname not in seen:
        out.append(surname.title())
        seen.add(surname)

    vehicles = record.get("detected_vehicles") or {}
    foundations: list[str] = []
    for fld in ("foundations_active", "foundations_terminated"):
        for f in vehicles.get(fld) or []:
            if isinstance(f, dict):
                fname = f.get("name")
                if isinstance(fname, str) and fname.strip():
                    foundations.append(fname.strip())

    for fname in foundations:
        for n in (1, 2):
            t = _prefix_token(fname, n)
            if t and t.lower() not in seen:
                out.append(t)
                seen.add(t.lower())

    for fld in ("name_display", "name_legal"):
        n = person.get(fld)
        if isinstance(n, str) and n.strip() and n.lower() not in seen:
            out.append(n.strip())
            seen.add(n.lower())

    for fname in foundations:
        if fname.lower() not in seen:
            out.append(fname)
            seen.add(fname.lower())

    return out


def _matches_subject(org_name: str, surname: str, foundation_names: list[str]) -> bool:
    """Surname-anchored match: the registry org name MUST contain the
    subject's surname OR substring-match a known foundation name. Drops
    every "Bloomberg, John Q. (no relation)" registry hit."""
    if not org_name:
        return False
    on = org_name.lower()
    if surname and surname in on:
        return True
    for fname in foundation_names:
        if fname and fname.lower() in on:
            return True
        # Match foundation name's first 2 significant tokens too
        prefix2 = _prefix_token(fname, 2).lower()
        if prefix2 and prefix2 in on:
            return True
    return False


def _subject_eins(record: dict) -> set[str]:
    """9-digit EINs attached to the subject — used to upgrade match
    confidence from medium to high when the registry FEIN matches."""
    out: set[str] = set()
    vehicles = record.get("detected_vehicles") or {}
    for fld in ("foundations_active", "foundations_terminated"):
        for f in vehicles.get(fld) or []:
            if isinstance(f, dict):
                ein = f.get("ein")
                if ein:
                    digits = normalize_ein(ein).replace("-", "")
                    if digits:
                        out.add(digits)
    return out


# ---------------------------------------------------------------------------
# CA — ASP.NET form scrape
# ---------------------------------------------------------------------------

_VS_RE = re.compile(r'name="__VIEWSTATE"[^>]*value="([^"]+)"')
_EV_RE = re.compile(r'name="__EVENTVALIDATION"[^>]*value="([^"]+)"')
_VSG_RE = re.compile(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]+)"')


def _ca_http(url: str, *, data: bytes | None = None, cookie: str | None = None) -> tuple[str, str | None]:
    """GET or POST against rct.doj.ca.gov using the legacy TLS context.
    Returns (body_text, set_cookie_value) or raises on failure."""
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, headers=headers, method=("POST" if data else "GET"))
    with urllib.request.urlopen(req, context=_CA_TLS_CTX, timeout=_TIMEOUT) as resp:
        body = resp.read().decode("utf-8", "ignore")
        new_cookie = resp.headers.get("Set-Cookie")
        # Keep only cookie name=value pairs (strip attributes).
        if new_cookie:
            new_cookie = "; ".join(c.split(";", 1)[0].strip() for c in new_cookie.split(",") if "=" in c.split(";", 1)[0])
        return body, new_cookie


def _ca_search(term: str) -> tuple[bool, list[dict]]:
    """POST the CA Registry search form for `term`. Returns
    (network_ok, rows). network_ok=False means the registry was not
    reachable (caller may emit a deep-link fallback); True with empty
    rows means the registry confirmed zero hits."""
    if BeautifulSoup is None:
        return False, []
    landing = _CA_SEARCH_PAGE
    try:
        body0, cookie = _ca_http(landing)
    except (urllib.error.URLError, ssl.SSLError, OSError):
        return False, []
    vs = _VS_RE.search(body0)
    ev = _EV_RE.search(body0)
    vsg = _VSG_RE.search(body0)
    if not (vs and ev and vsg):
        return False, []
    form = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": vs.group(1),
        "__VIEWSTATEGENERATOR": vsg.group(1),
        "__EVENTVALIDATION": ev.group(1),
        "t_web_lookup__full_name": term,
        "t_web_lookup__doing_business_as": "",
        "t_web_lookup__charter_number": "",
        "t_web_lookup__federal_id": "",
        "t_web_lookup__license_no": "",
        "t_web_lookup__license_status_name": "",
        "t_web_lookup__license_type_name": "",
        "t_web_lookup__profession_name": "",
        "t_web_lookup__addr_city": "",
        "t_web_lookup__addr_county": "",
        "t_web_lookup__addr_state": "",
        "t_web_lookup__addr_zipcode": "",
        "sch_button": "Search",
    }
    encoded = urllib.parse.urlencode(form).encode("utf-8")
    try:
        body, _ = _ca_http(landing, data=encoded, cookie=cookie)
    except (urllib.error.URLError, ssl.SSLError, OSError):
        return False, []
    soup = BeautifulSoup(body, "html.parser")
    rows: list[dict] = []
    # The results datagrid has 7-column rows: NAME, RECORD TYPE, STATUS,
    # RCT NUMBER, FEIN, CITY, ST. Header rows use the same <td> tag and
    # carry the literal text "ORGANIZATION NAME" in cell 0; we skip
    # those. The instructional preamble lives in a single-cell row.
    for table in soup.find_all("table"):
        # Identify the results datagrid: the only table with multiple
        # 7-cell <td> rows. Header is in <th> (so excluded from this
        # search) — every 7-cell row is a data row.
        candidate_rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all("td")]
            if len(cells) == 7:
                candidate_rows.append(cells)
        if len(candidate_rows) < 1:
            continue
        # Sanity: skip tables whose header (when present in <th>) doesn't
        # mention "ORGANIZATION", e.g. unrelated layout tables.
        ths = [c.get_text(strip=True) for c in table.find_all("th")]
        if ths and not any("ORGANIZATION" in t.upper() for t in ths):
            continue
        for cells in candidate_rows:
            name, rec_type, status, rct, fein, city, st = cells
            if not name or "ORGANIZATION" in name.upper():
                # Defensive: skip header rows that ever leak as <td>.
                continue
            rows.append({
                "name": name,
                "status": status,
                "rct_number": rct,
                "fein": re.sub(r"\D", "", fein or ""),
                "city": city,
                "state": st,
            })
        break
    return True, rows[:_MAX_HITS_PER_TERM]


# ---------------------------------------------------------------------------
# NY — JSON API
# ---------------------------------------------------------------------------

def _ny_search(term: str) -> tuple[bool, list[dict]]:
    """GET the NY Charities Bureau JSON API. Returns (network_ok, rows)
    where rows = {orgName, ein, orgID, city, state, regType}."""
    if requests is None:
        return False, []
    url = _NY_API_TMPL.format(q=quote_plus(term))
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "application/json",
                "Origin": "https://charities-search.ag.ny.gov",
                "Referer": "https://charities-search.ag.ny.gov/",
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException:
        return False, []
    try:
        body = r.json()
    except ValueError:
        return False, []
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        # API returned a successful HTTP response but unexpected shape —
        # treat as reachable, just no usable rows.
        return True, []
    out: list[dict] = []
    for row in data[:_MAX_HITS_PER_TERM]:
        if not isinstance(row, dict):
            continue
        out.append({
            "name": (row.get("orgName") or "").strip(),
            "ein": re.sub(r"\D", "", row.get("ein") or ""),
            "org_id": row.get("orgID") or "",
            "city": row.get("city") or "",
            "state": row.get("state") or "",
            "reg_type": row.get("regType") or "",
        })
    return True, out


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------

def _ca_candidate(subject_name: str, row: dict, term: str, subject_eins: set[str]) -> dict:
    fein = row.get("fein") or ""
    confidence = "high" if (fein and fein in subject_eins) else "medium"
    status = row.get("status") or "unknown"
    note = (
        f"CA Registry of Charitable Trusts — {row['name']}; status={status}; "
        f"RCT#={row.get('rct_number') or 'n/a'}; FEIN={fein or 'n/a'}; "
        f"city={row.get('city') or 'n/a'} (search term: {term!r})"
    )
    return {
        "event_role": "reference_only",
        "year": None,
        "donor_entity": subject_name,
        "recipient": row["name"],
        "amount_usd": None,
        "source_type": "state_charity_registry",
        # Search page is the only stable URL — detail nav is __doPostBack.
        "source_url": _CA_SEARCH_PAGE,
        "confidence": confidence,
        "note": note,
        "regen_source": "state_charities",
    }


def _ny_candidate(subject_name: str, row: dict, term: str, subject_eins: set[str]) -> dict:
    ein = row.get("ein") or ""
    confidence = "high" if (ein and ein in subject_eins) else "medium"
    detail_url = (
        _NY_DETAIL_TMPL.format(oid=quote_plus(row["org_id"]))
        if row.get("org_id")
        else _NY_SEARCH_PAGE_TMPL.format(q=quote_plus(term))
    )
    note = (
        f"NY Charities Bureau — {row['name']}; reg_type={row.get('reg_type') or 'n/a'}; "
        f"orgID={row.get('org_id') or 'n/a'}; EIN={ein or 'n/a'}; "
        f"city={row.get('city') or 'n/a'} (search term: {term!r})"
    )
    return {
        "event_role": "reference_only",
        "year": None,
        "donor_entity": subject_name,
        "recipient": row["name"],
        "amount_usd": None,
        "source_type": "state_charity_registry",
        "source_url": detail_url,
        "confidence": confidence,
        "note": note,
        "regen_source": "state_charities",
    }


def _deeplink_fallback(state: str, subject_name: str, term: str) -> dict:
    """Emitted when network failed AND no cache was usable. Points the
    reader at the registry's own search UI for the term."""
    if state == "CA":
        url = _CA_SEARCH_PAGE
        label = "CA Registry of Charitable Trusts"
    else:
        url = _NY_SEARCH_PAGE_TMPL.format(q=quote_plus(term))
        label = "NY Charities Bureau"
    return {
        "event_role": "reference_only",
        "year": None,
        "donor_entity": subject_name,
        "recipient": term,
        "amount_usd": None,
        "source_type": "state_charity_registry",
        "source_url": url,
        "confidence": "low",
        "note": (
            f"{label} — registry search not reachable from automation; "
            f"check manually for term {term!r}."
        ),
        "regen_source": "state_charities",
    }


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

def _fetch_state(state: str, term: str, *, refresh: bool) -> dict:
    """Return cached payload {ok, rows} for (state, term). Live call on
    miss or refresh; failures cache as {ok: False, rows: []} so reruns
    don't re-hammer the registry. The collector emits a deep-link
    fallback iff *every* term for a state failed to reach the registry."""
    if not refresh:
        cached = _load_cache(state, term)
        if cached is not None:
            return cached
    if state == "CA":
        ok, rows = _ca_search(term)
    elif state == "NY":
        ok, rows = _ny_search(term)
    else:
        ok, rows = False, []
    payload = {"ok": ok, "rows": rows}
    _save_cache(state, term, payload)
    return payload


def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return regen_v3 reference_only candidates for state charity hits.

    For each search term × {CA, NY}, search the registry, dedupe across
    terms by (state, registration id), and emit one candidate per match.
    Sorted deterministically.
    """
    subject_name = (record.get("person") or {}).get("name_display") or ""
    terms = _terms_for_subject(record)
    if not terms:
        return []
    subject_eins = _subject_eins(record)

    surname = _surname(subject_name)
    foundation_names = []
    vehicles = record.get("detected_vehicles") or {}
    for fld in ("foundations_active", "foundations_terminated"):
        for f in vehicles.get(fld) or []:
            if isinstance(f, dict) and isinstance(f.get("name"), str):
                foundation_names.append(f["name"])

    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (state, dedupe_id)
    network_ok: dict[str, bool] = {"CA": False, "NY": False}

    for state in ("CA", "NY"):
        for i, term in enumerate(terms):
            if i > 0:
                time.sleep(_PAUSE)
            payload = _fetch_state(state, term, refresh=refresh)
            if payload.get("ok"):
                network_ok[state] = True
            rows = payload.get("rows") or []
            for row in rows:
                if not _matches_subject(row.get("name") or "", surname, foundation_names):
                    continue
                if state == "CA":
                    dedupe = row.get("rct_number") or f"{row.get('fein','')}|{row['name'].lower()}"
                    cand = _ca_candidate(subject_name, row, term, subject_eins)
                else:
                    dedupe = row.get("org_id") or f"{row.get('ein','')}|{row['name'].lower()}"
                    cand = _ny_candidate(subject_name, row, term, subject_eins)
                key = (state, dedupe)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(cand)

    # If a state surfaced zero hits across all terms AND we have no
    # evidence the network call worked, emit one deep-link fallback per
    # state so a human reader still gets a "go check this" pointer.
    primary_term = terms[0]
    for state, ok in network_ok.items():
        if ok:
            continue
        candidates.append(_deeplink_fallback(state, subject_name, primary_term))

    candidates.sort(key=lambda c: (c["regen_source"], c["source_url"], c["recipient"]))
    return candidates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True, help="Subject id (e.g. larry_ellison)")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_path.read_text())
    cands = collect_candidates(record, refresh=args.refresh)
    print(f"{args.subject}: {len(cands)} state-charity candidates")
    for c in cands:
        conf = c["confidence"]
        rcp = c["recipient"][:60]
        url = c["source_url"]
        print(f"  [{conf:<6}] {rcp:<60}  {url[:80]}")
