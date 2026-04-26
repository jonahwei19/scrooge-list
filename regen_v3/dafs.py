"""DAF-transfer detection source for regen_v3.

A foundation grant TO a donor-advised-fund (DAF) sponsor parks money in
an opaque downstream channel: the DAF sponsor (Fidelity Charitable,
Vanguard Charitable, Schwab Charitable, NCF, JCF, etc.) does NOT
disclose the eventual end-recipient. The transfer itself is the only
observable event. We treat each foundation→DAF transfer as a *lower
bound*: money was moved into the opaque channel, even though we can't
see where it ultimately lands.

Source: ProPublica Nonprofit Explorer renders the IRS 990-PF Part XV
(Supplementary Information — Grants and Contributions Paid) as HTML
text at:
    https://projects.propublica.org/nonprofits/full_text/<object_id>/IRS990PF

The summary 990 endpoint already wired into `regen_v3/propublica.py`
does NOT expose Schedule I, so this module fetches the org's filing
list page, extracts (fiscal_year, object_id) pairs, then pulls the
full text per filing and parses recipient names + amounts.

Cache:
  regen_v3/cache/dafs/<ein-9digits>_org.json
      list of {fiscal_year, object_id} for the EIN
  regen_v3/cache/dafs/<ein-9digits>_<fiscal_year>.json
      list of {recipient, amount_usd, foundation_status, purpose}
      parsed from Schedule I for that filing

Reproducibility: ProPublica's rendered Part XV is deterministic for
fiscal years that have already closed. Re-runs against the same cache
produce identical candidates.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "dafs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from categories.foundations import normalize_ein  # noqa: E402
from regen_v3.propublica import _eins_for_subject  # noqa: E402

# ---------------------------------------------------------------------------
# Canonical DAF sponsor list. Names checked via case-insensitive substring;
# EINs checked exact (after normalization to 9-digit). The most common DAF
# sponsors by AUM in 2024-2025, per NPT/Giving USA reports.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DAFSponsor:
    name: str            # canonical display name
    ein: str             # 9-digit EIN (normalized, no dash)
    name_patterns: tuple[str, ...]  # lowercase substrings — any match flags it


DAF_SPONSORS: tuple[DAFSponsor, ...] = (
    DAFSponsor(
        name="Fidelity Investments Charitable Gift Fund",
        ein="110303001",
        name_patterns=("fidelity charitable", "fidelity investments charitable"),
    ),
    DAFSponsor(
        name="Vanguard Charitable Endowment Program",
        ein="232888152",
        name_patterns=("vanguard charitable",),
    ),
    DAFSponsor(
        name="Schwab Charitable Fund",
        ein="311640316",
        name_patterns=("schwab charitable",),
    ),
    DAFSponsor(
        name="National Christian Foundation",
        ein="581493949",
        name_patterns=("national christian foundation", "national christian charitable"),
    ),
    DAFSponsor(
        name="Jewish Communal Fund",
        ein="237174404",
        name_patterns=("jewish communal fund",),
    ),
    DAFSponsor(
        name="Goldman Sachs Philanthropy Fund",
        ein="261265506",
        name_patterns=("goldman sachs philanthropy", "goldman sachs phil fd"),
    ),
    DAFSponsor(
        name="Silicon Valley Community Foundation",
        ein="205205488",
        name_patterns=("silicon valley community foundation",),
    ),
    DAFSponsor(
        name="Greater Kansas City Community Foundation",
        ein="431890218",
        name_patterns=("greater kansas city community foundation",),
    ),
    DAFSponsor(
        name="National Philanthropic Trust",
        ein="232017646",
        name_patterns=("national philanthropic trust",),
    ),
    DAFSponsor(
        name="American Endowment Foundation",
        ein="341747398",
        name_patterns=("american endowment foundation",),
    ),
    DAFSponsor(
        name="Renaissance Charitable Foundation",
        ein="352129262",
        name_patterns=("renaissance charitable foundation",),
    ),
    DAFSponsor(
        name="T. Rowe Price Program for Charitable Giving",
        ein="311709466",
        name_patterns=("t rowe price program for charitable", "trowe price program for charitable"),
    ),
    DAFSponsor(
        name="Morgan Stanley Global Impact Funding Trust",
        ein="311678701",
        name_patterns=("morgan stanley global impact", "morgan stanley gift fund"),
    ),
    DAFSponsor(
        name="Bank of America Charitable Gift Fund",
        ein="043345408",
        name_patterns=("bank of america charitable gift", "boa charitable gift"),
    ),
    DAFSponsor(
        name="The Signatry",
        ein="431890218",   # Note: shares an EIN window with GKCCF; keep as name-only signal
        name_patterns=("the signatry", "signatry global"),
    ),
)

# Quick lookup tables
_SPONSOR_EINS: dict[str, DAFSponsor] = {s.ein: s for s in DAF_SPONSORS}
_SPONSOR_NAME_PATTERNS: tuple[tuple[str, DAFSponsor], ...] = tuple(
    (pat, s) for s in DAF_SPONSORS for pat in s.name_patterns
)


# ---------------------------------------------------------------------------
# Cache + HTTP
# ---------------------------------------------------------------------------

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_REQ_TIMEOUT = 30
_REQ_PAUSE = 0.4  # courtesy delay between live ProPublica fetches


def _ein_digits(ein: str) -> str:
    return normalize_ein(ein).replace("-", "")


def _org_cache_path(ein: str) -> Path:
    return CACHE_DIR / f"{_ein_digits(ein)}_org.json"


def _filing_cache_path(ein: str, fiscal_year: int) -> Path:
    return CACHE_DIR / f"{_ein_digits(ein)}_{fiscal_year}.json"


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2))


def _http_get(url: str) -> str:
    """Fetch a URL with a browser UA. ProPublica's CDN serves a different
    response shape if the request looks bot-like, but the URL pattern we hit
    is plain HTML with gzip; we deliberately omit `br` from Accept-Encoding
    so we don't depend on the optional `brotli` module — `requests` already
    handles gzip + deflate transparently."""
    resp = requests.get(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=_REQ_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Step 1 — discover (fiscal_year, object_id) pairs for an EIN
# ---------------------------------------------------------------------------

_FILING_SECTION_RE = re.compile(
    r"<section class=\"single-filing-period\" id='filing(\d{4})'>(.*?)"
    r"(?=<section class=\"single-filing-period\"|<div class=\"about-new)",
    re.DOTALL,
)
_OBJECT_ID_RE = re.compile(r"/nonprofits/organizations/\d+/(\d{18})")


def _discover_filings(ein: str, *, refresh: bool = False) -> list[dict]:
    """Return [{fiscal_year, object_id}] for an EIN, oldest first.

    Scrapes ProPublica's organization page — the only place that maps
    fiscal years to electronic-filing object_ids.
    """
    cache_p = _org_cache_path(ein)
    if not refresh:
        cached = _load_json(cache_p)
        if cached is not None:
            return cached

    url = (
        f"https://projects.propublica.org/nonprofits/organizations/"
        f"{_ein_digits(ein)}"
    )
    try:
        html = _http_get(url)
    except requests.RequestException:
        _save_json(cache_p, [])
        return []

    out: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for m in _FILING_SECTION_RE.finditer(html):
        fy = int(m.group(1))
        for oid in _OBJECT_ID_RE.findall(m.group(2)):
            key = (fy, oid)
            if key in seen:
                continue
            seen.add(key)
            out.append({"fiscal_year": fy, "object_id": oid})

    out.sort(key=lambda r: (r["fiscal_year"], r["object_id"]))
    _save_json(cache_p, out)
    return out


# ---------------------------------------------------------------------------
# Step 2 — parse Schedule I (Part XV) grants from the rendered IRS990PF page
# ---------------------------------------------------------------------------

# Each grant row in the rendered HTML contains a span with this id pattern
# that wraps the recipient business-name text. We anchor the row to that
# span and then pull the matching Amt[1] span by group index.
_GRANT_NAME_RE = re.compile(
    r'GrantOrContributionPdDurYrGrp\[(\d+)\]/RecipientBusinessName\[1\]/'
    r'BusinessNameLine1Txt\[1\]"[^>]*>([^<]+)</span>'
)
_GRANT_AMT_RE_TMPL = (
    r'GrantOrContributionPdDurYrGrp\[{idx}\]/Amt\[1\]"[^>]*>([0-9,]+)</span>'
)
_GRANT_STATUS_RE_TMPL = (
    r'GrantOrContributionPdDurYrGrp\[{idx}\]/RecipientFoundationStatusTxt\[1\]"'
    r'[^>]*>([^<]+)</span>'
)
_GRANT_PURPOSE_RE_TMPL = (
    r'GrantOrContributionPdDurYrGrp\[{idx}\]/GrantOrContributionPurposeTxt\[1\]"'
    r'[^>]*>([^<]+)</span>'
)


def _parse_amount(s: str) -> float:
    return float(s.replace(",", "").strip() or 0)


def _fetch_grants(
    ein: str, fiscal_year: int, object_id: str, *, refresh: bool = False
) -> list[dict]:
    """Return parsed Schedule I grants for one (EIN, fiscal_year)."""
    cache_p = _filing_cache_path(ein, fiscal_year)
    if not refresh:
        cached = _load_json(cache_p)
        if cached is not None:
            return cached

    url = (
        f"https://projects.propublica.org/nonprofits/full_text/"
        f"{object_id}/IRS990PF"
    )
    try:
        html = _http_get(url)
    except requests.RequestException:
        _save_json(cache_p, [])
        return []

    grants: list[dict] = []
    for nm_m in _GRANT_NAME_RE.finditer(html):
        idx = nm_m.group(1)
        recipient = (nm_m.group(2) or "").strip()
        if not recipient:
            continue
        amt_m = re.search(_GRANT_AMT_RE_TMPL.format(idx=idx), html)
        if not amt_m:
            continue
        amount = _parse_amount(amt_m.group(1))
        if amount <= 0:
            continue
        status_m = re.search(_GRANT_STATUS_RE_TMPL.format(idx=idx), html)
        purpose_m = re.search(_GRANT_PURPOSE_RE_TMPL.format(idx=idx), html)
        grants.append({
            "recipient": recipient,
            "amount_usd": amount,
            "foundation_status": (status_m.group(1).strip() if status_m else ""),
            "purpose": (purpose_m.group(1).strip() if purpose_m else ""),
        })

    _save_json(cache_p, grants)
    return grants


# ---------------------------------------------------------------------------
# Step 3 — match a grant against the canonical DAF sponsor list
# ---------------------------------------------------------------------------

def _match_daf_sponsor(recipient_name: str) -> DAFSponsor | None:
    """Case-insensitive substring match on canonical name patterns. Order
    matters only when patterns overlap; no current overlaps."""
    n = (recipient_name or "").lower()
    if not n:
        return None
    for pat, sponsor in _SPONSOR_NAME_PATTERNS:
        if pat in n:
            return sponsor
    return None


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return regen_v3 candidate events for foundation→DAF transfers.

    For each EIN attached to the subject:
      1. Discover all (fiscal_year, object_id) pairs from ProPublica.
      2. For each filing, parse Schedule I (Part XV) grants.
      3. Match recipients against `DAF_SPONSORS` (substring on name).
      4. Aggregate matching grants by (foundation, sponsor, fiscal_year)
         and emit one `grant_out` candidate per group, with an explicit
         "→DAF (opaque downstream)" note.
    """
    candidates: list[dict] = []

    for ein, fname in _eins_for_subject(record):
        ein_norm = normalize_ein(ein)
        ein_digits = _ein_digits(ein)
        try:
            filings = _discover_filings(ein, refresh=refresh)
        except Exception:
            continue
        if not filings:
            continue

        # Avoid re-scraping the same fiscal year twice if multiple object_ids
        # appear (rare — usually only the "latest" filing per FY is shown).
        seen_fy: set[int] = set()
        for f in filings:
            fy = int(f["fiscal_year"])
            object_id = f["object_id"]
            if fy in seen_fy:
                continue
            seen_fy.add(fy)

            try:
                grants = _fetch_grants(ein, fy, object_id, refresh=refresh)
            except Exception:
                continue
            time.sleep(_REQ_PAUSE)

            # Aggregate by sponsor for this (foundation, fiscal year).
            agg: dict[str, dict] = {}  # sponsor.name -> {amount, count, ein}
            for g in grants:
                sponsor = _match_daf_sponsor(g.get("recipient") or "")
                if sponsor is None:
                    continue
                slot = agg.setdefault(
                    sponsor.name,
                    {"amount_usd": 0.0, "count": 0, "ein": sponsor.ein},
                )
                slot["amount_usd"] += float(g.get("amount_usd") or 0)
                slot["count"] += 1

            for sponsor_name, slot in sorted(agg.items()):
                if slot["amount_usd"] <= 0:
                    continue
                candidates.append({
                    "event_role": "grant_out",
                    "year": fy,
                    "date_precision": "year",
                    "donor_entity": fname,
                    "donor_ein": ein_norm,
                    "recipient": sponsor_name,
                    "amount_usd": float(slot["amount_usd"]),
                    "source_type": "990-PF",
                    "source_url": (
                        f"https://projects.propublica.org/nonprofits/"
                        f"organizations/{ein_digits}/{object_id}/full"
                    ),
                    "confidence": "high",
                    "note": (
                        f"{fname} → {sponsor_name} (DAF sponsor EIN "
                        f"{slot['ein'][:2]}-{slot['ein'][2:]}); "
                        f"{slot['count']} grant line(s) on 990-PF Part XV "
                        f"for FY {fy}; →DAF (opaque downstream — "
                        f"end-recipient not disclosed by sponsor)."
                    ),
                    "regen_source": "dafs",
                })

    candidates.sort(key=lambda c: (c["donor_ein"], c["year"], c["recipient"]))
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
    print(f"{args.subject}: {len(cands)} DAF-transfer candidates")
    for c in cands:
        print(
            f"  {c['year']}  {c['donor_ein']}  "
            f"${c['amount_usd']/1e6:>7.2f}M  "
            f"{c['donor_entity'][:38]:<38}  →  {c['recipient']}"
        )
