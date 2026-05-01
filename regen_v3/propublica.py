"""ProPublica 990-PF source for regen_v3.

Wraps the legacy `categories.foundations` module to produce candidate events
in the shape `regen_v3/merge.py` expects.

For each EIN attached to a subject's record (under
`detected_vehicles.foundations_active[].ein` plus optional fallback to the
hand-curated `categories.foundations.KNOWN_FOUNDATIONS`), we fetch all
available 990-PF filings and emit one `grant_out` candidate per fiscal year.

Cache: regen_v3/cache/propublica/<ein-9digits>.json — same EIN never
hits ProPublica twice unless `refresh=True`.

Reproducibility: ProPublica returns historical filings; output is stable for
fiscal years that have already closed.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "propublica"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from categories.foundations import (  # noqa: E402
    KNOWN_FOUNDATIONS,
    get_990_data,
    normalize_ein,
)

try:
    from regen_v3._atomic import atomic_write_json  # type: ignore
except Exception:  # pragma: no cover - in-package fallback
    from _atomic import atomic_write_json  # type: ignore


def _ein_digits(ein: str) -> str:
    return normalize_ein(ein).replace("-", "")


def _cache_path(ein: str) -> Path:
    return CACHE_DIR / f"{_ein_digits(ein)}.json"


def _load_cache(ein: str) -> list[dict] | None:
    p = _cache_path(ein)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_cache(ein: str, filings: list[dict]) -> None:
    # Atomic write: two workers sharing an EIN (e.g. Walton family) can
    # race here. tmp + os.replace prevents half-written cache files.
    atomic_write_json(_cache_path(ein), filings)


_RECIPIENT_PHRASES = (
    re.compile(r"\brecipient\s+of\b", re.IGNORECASE),     # "RECIPIENT of CZI grants"
    re.compile(r"\(\s*recipient\b", re.IGNORECASE),       # "(RECIPIENT, not donor)"
    re.compile(r"\bnot\s+a\s+donor\b", re.IGNORECASE),    # "not a donor vehicle"
    re.compile(r"\bnon[\-\s]donor\b", re.IGNORECASE),     # "non-donor"
)
_RECIPIENT_ROLE_TOKENS = re.compile(r"^(recipient|grantee)\b", re.IGNORECASE)
_NON_CHARITY_PHRASES = (
    re.compile(r"\b501\s*\(\s*c\s*\)\s*\(\s*4\s*\)", re.IGNORECASE),  # 501(c)(4)
    re.compile(r"\b501c4\b", re.IGNORECASE),
    re.compile(r"\bsocial\s+welfare\b", re.IGNORECASE),
)
_DO_NOT_ATTRIBUTE_PHRASE = re.compile(r"\bdo\s+not\s+attribute\b", re.IGNORECASE)


def _is_excluded_by_record(f: dict) -> str | None:
    """Return a reason string if a foundation entry should NOT be attributed
    to the subject; None if it's a legitimate donor vehicle.

    Uses word-boundary regex over canonical phrases instead of bare
    substring matches, so a foundation whose record text incidentally
    contains the substring `recipient` (e.g. discussing past grant
    recipients) is NOT silently dropped.
    """
    if not isinstance(f, dict):
        return "not_a_dict"

    # 1. Explicit structured override (preferred, future-friendly).
    if f.get("attribute") is False:
        return "attribute_false"

    # 2. Structured `role` field. Records use whole-word values like
    #    "recipient" / "grantee" / "donor"; we only match when the field
    #    *starts with* a non-donor token.
    role = (f.get("role") or "").strip()
    if role and _RECIPIENT_ROLE_TOKENS.match(role):
        return f"role_recipient:{role[:40]}"

    # 3. Free-text status field carries inline annotations like
    #    "active (RECIPIENT of CZI grants, not a donor vehicle)". Match
    #    on the canonical phrases that signal "this is a recipient, not
    #    a donor", not the bare token.
    status = f.get("status") or ""
    for pat in _RECIPIENT_PHRASES:
        if pat.search(status):
            return f"status_recipient:{status[:60]}"

    # 4. 501(c)(4) and other non-charitable shells should not be aggregated
    #    into "grants_paid" — they're advocacy / civic-league vehicles.
    tax_status = f.get("tax_status") or ""
    for pat in _NON_CHARITY_PHRASES:
        if pat.search(tax_status):
            return f"non_charity_tax_status:{tax_status[:60]}"

    # 5. Free-text note can carry "Do NOT attribute" guidance.
    note = f.get("note") or ""
    if _DO_NOT_ATTRIBUTE_PHRASE.search(note):
        return "note_do_not_attribute"
    for pat in _RECIPIENT_PHRASES:
        if pat.search(note):
            return "note_recipient_phrase"

    return None


def _eins_for_subject(record: dict) -> list[tuple[str, str]]:
    """Return [(ein, foundation_name)] from the record + KNOWN_FOUNDATIONS.

    Skips foundations the record marks as do-not-attribute (recipient
    vehicles, 501(c)(4) shells, parent/relative foundations, etc.). Records
    can list these in `detected_vehicles.foundations_related_not_attributed`
    or annotate them inline via `attribute`, `role`, `status`, `tax_status`,
    or `note` fields.

    De-duped by 9-digit EIN. Order: record-declared EINs first, then any
    additional EINs from the hand-curated map.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    vehicles = record.get("detected_vehicles") or {}

    # Build the do-not-attribute EIN blocklist FIRST so it suppresses both
    # record-declared and KNOWN_FOUNDATIONS entries below.
    blocked: set[str] = set()
    for f in vehicles.get("foundations_related_not_attributed") or []:
        if isinstance(f, dict):
            ein = f.get("ein")
            if ein:
                blocked.add(_ein_digits(ein))

    for fld in ("foundations_active", "foundations_terminated"):
        for f in vehicles.get(fld) or []:
            if not isinstance(f, dict):
                continue
            ein = f.get("ein")
            if not ein:
                continue
            digits = _ein_digits(ein)
            if digits in blocked:
                continue
            reason = _is_excluded_by_record(f)
            if reason is not None:
                blocked.add(digits)
                continue
            if digits in seen:
                continue
            seen.add(digits)
            out.append((ein, f.get("name") or "Unknown"))

    name_display = (record.get("person") or {}).get("name_display") or ""
    name_key = name_display.lower()
    for ein, fname in KNOWN_FOUNDATIONS.get(name_key, []):
        digits = _ein_digits(ein)
        if digits in seen or digits in blocked:
            continue
        seen.add(digits)
        out.append((ein, fname))

    return out


def _filings_to_dicts(filings) -> list[dict]:
    """Convert FoundationFiling dataclasses into JSON-serializable dicts."""
    out = []
    for f in filings:
        out.append({
            "ein": f.ein,
            "name": f.name,
            "fiscal_year": f.fiscal_year,
            "total_assets": f.total_assets,
            "grants_paid": f.grants_paid,
            "contributions_received": f.contributions_received,
            "total_expenses": f.total_expenses,
            "payout_rate": f.payout_rate,
            "source_url": f.source_url,
        })
    return out


def fetch_filings(ein: str, *, refresh: bool = False) -> list[dict]:
    """Return raw filings (cached) for an EIN."""
    if not refresh:
        cached = _load_cache(ein)
        if cached is not None:
            return cached
    filings = get_990_data(ein)
    serial = _filings_to_dicts(filings)
    _save_cache(ein, serial)
    return serial


def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return regen_v3 candidate events for every 990-PF filing attached to
    the subject's EINs. One candidate per (EIN, fiscal_year)."""
    candidates: list[dict] = []

    for ein, fname in _eins_for_subject(record):
        filings = fetch_filings(ein, refresh=refresh)
        for f in filings:
            grants = f.get("grants_paid") or 0
            year = f.get("fiscal_year")
            if not year or grants <= 0:
                continue
            candidates.append({
                "event_role": "grant_out",
                "year": int(year),
                "date_precision": "year",
                "donor_entity": f.get("name") or fname,
                "donor_ein": normalize_ein(ein),
                "recipient": "Various (990-PF aggregate; recipient detail not parsed)",
                "amount_usd": float(grants),
                "source_type": "990-PF",
                "source_url": f.get("source_url"),
                "confidence": "high",
                "note": (
                    f"ProPublica 990-PF aggregate for fiscal-year {year}; "
                    f"end-year assets ${(f.get('total_assets') or 0)/1e6:.1f}M; "
                    f"payout rate {f.get('payout_rate') or 0:.1f}%."
                ),
                "regen_source": "propublica",
            })

    candidates.sort(key=lambda c: (c["donor_ein"], c["year"]))
    return candidates


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True, help="Subject id (e.g. henry_kravis)")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_path.read_text())
    cands = collect_candidates(record, refresh=args.refresh)
    print(f"{args.subject}: {len(cands)} candidates")
    for c in cands:
        print(f"  {c['year']}  {c['donor_ein']}  ${c['amount_usd']/1e6:.1f}M  {c['donor_entity']}")
