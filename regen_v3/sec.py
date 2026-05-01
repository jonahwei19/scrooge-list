"""SEC Form 4 (gift transactions) source for regen_v3.

Wraps `categories.securities` to produce candidate events from SEC EDGAR
Form 4 filings, filtered to transaction code "G" (bona fide gift). These
correspond to stock transferred from the insider to a foundation (or
charitable trust) — the only programmatic window into insider charitable
transfers, since direct gifts to charity are exempt from Form 4.

Subject → CIK lookup uses `categories.securities.KNOWN_CIKS` (hand-curated)
plus an opportunistic SEC EDGAR atom-feed search by name. Subjects with no
public-company insider role (private fund managers, family offices, etc.)
return zero candidates.

Cache: regen_v3/cache/sec/<cik>.json — same CIK never re-parses Form 4s
unless `refresh=True`. Each cache file is a list of gift-transaction dicts.

Reproducibility: SEC filings are append-only and historical filings never
change, so a cached run always reproduces.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "sec"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from categories.securities import (  # noqa: E402
    KNOWN_CIKS,
    get_form4_filings,
    lookup_cik,
    parse_form4_for_gifts,
)

try:
    from regen_v3._atomic import atomic_write_json  # type: ignore
except Exception:  # pragma: no cover - in-package fallback
    from _atomic import atomic_write_json  # type: ignore

# Price lookup for Form 4 G-transactions (which report $0/share).
# Self-contained: if yfinance / network are unavailable, value_gift()
# returns None and we keep the legacy `reference_only` behavior.
try:
    from regen_v3.sec_pricing import value_gift as _value_gift  # type: ignore
except Exception:  # pragma: no cover - fall back to in-package import
    try:
        from sec_pricing import value_gift as _value_gift  # type: ignore
    except Exception:
        _value_gift = None  # type: ignore

_FORM4_LIMIT = 100  # how many recent filings to scan per CIK
_GIFT_PARSE_LIMIT = 60  # how many of those to parse for code-G transactions


def _cache_path(cik: str) -> Path:
    return CACHE_DIR / f"{cik}.json"


def _load_cache(cik: str) -> list[dict] | None:
    p = _cache_path(cik)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_cache(cik: str, gifts: list[dict]) -> None:
    # Atomic write: two subjects who share a CIK (co-founders, family
    # members at the same issuer) can race on this cache.
    atomic_write_json(_cache_path(cik), gifts)


def _resolve_cik(record: dict) -> str | None:
    """Find a CIK for the subject. Order: explicit override on the record,
    KNOWN_CIKS (legacy hand-curated), then SEC name search."""
    name = (record.get("person") or {}).get("name_display") or ""
    if not name:
        return None

    # 1. Allow records to declare a CIK explicitly under detected_vehicles.
    sec_block = (record.get("detected_vehicles") or {}).get("sec_filings") or {}
    if isinstance(sec_block, dict):
        explicit = sec_block.get("cik")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().zfill(10)

    # 2. KNOWN_CIKS (None means "private — skip").
    known = KNOWN_CIKS.get(name.lower(), "__missing__")
    if known is None:
        return None
    if known != "__missing__":
        return known

    # 3. Opportunistic name search.
    return lookup_cik(name)


def _gift_dedupe_key(g: dict) -> tuple:
    """Identify the same Form 4 G-transaction across `nonDerivativeTransaction`
    and `derivativeTransaction` blocks within a single filing."""
    return (
        g.get("transaction_date") or "",
        round(float(g.get("shares") or 0)),
        (g.get("company") or "").strip().lower(),
        g.get("source_url") or "",
    )


def fetch_gifts(cik: str, *, refresh: bool = False) -> list[dict]:
    """Return all Form 4 gift transactions for a CIK (cached, deduped).

    Form 4 reports the same gift in both `nonDerivativeTransaction` and
    `derivativeTransaction` blocks when an executive holds both classes.
    The legacy parser yields both — we collapse them to one event per
    `(transaction_date, shares, company, source_url)` here so the cache
    file itself is canonical.
    """
    if not refresh:
        cached = _load_cache(cik)
        if cached is not None:
            return cached

    filings = get_form4_filings(cik, limit=_FORM4_LIMIT)
    seen: set[tuple] = set()
    all_gifts: list[dict] = []
    for filing in filings[:_GIFT_PARSE_LIMIT]:
        gifts = parse_form4_for_gifts(cik, filing["accession"])
        for g in gifts:
            d = asdict(g)
            d["filing_date"] = filing["filing_date"]
            key = _gift_dedupe_key(d)
            if key in seen:
                continue
            seen.add(key)
            all_gifts.append(d)
        time.sleep(0.15)  # SEC fair-use rate

    _save_cache(cik, all_gifts)
    return all_gifts


def _gift_year(gift: dict) -> int | None:
    for fld in ("transaction_date", "filing_date"):
        d = gift.get(fld) or ""
        if len(d) >= 4 and d[:4].isdigit():
            return int(d[:4])
    return None


def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return regen_v3 candidate events for every Form 4 G-transaction."""
    cik = _resolve_cik(record)
    if not cik:
        return []

    gifts = fetch_gifts(cik, refresh=refresh)
    name = (record.get("person") or {}).get("name_display") or ""
    candidates: list[dict] = []

    for g in gifts:
        shares = g.get("shares") or 0
        if shares <= 0:
            continue
        year = _gift_year(g)
        if not year:
            continue

        value = g.get("total_value") or 0
        # Form 4 G-transactions almost always report $0/share (gifts have
        # no consideration). Try to value them via historical close price
        # of the issuer on the transaction date (sec_pricing). If that
        # succeeds we promote the event to `direct_gift`; if not we fall
        # back to `reference_only`, which the merge layer routes to
        # sources_all (a citation-only entry, not a dollar-bearing event).
        priced_via_close = False
        if value <= 0 and _value_gift is not None:
            try:
                priced = _value_gift(g)
            except Exception:
                priced = None
            if priced and priced > 0:
                value = float(priced)
                priced_via_close = True

        if value > 0:
            event_role = "direct_gift"
            amount_usd = float(value)
            # Reported-on-the-filing values stay "medium"; close-price
            # estimates are slightly less precise (intraday vs close).
            confidence = "low" if priced_via_close else "medium"
            if priced_via_close:
                amount_blurb = f"${value/1e6:.1f}M (valued at issuer close on transaction date)"
            else:
                amount_blurb = f"${value/1e6:.1f}M"
        else:
            event_role = "reference_only"
            amount_usd = None
            confidence = "low"
            amount_blurb = "amount not reported (Form 4 G-transactions report $0/share; price lookup unavailable)"

        candidates.append({
            "event_role": event_role,
            "year": year,
            "date_precision": "day" if (g.get("transaction_date") or "")[:10] else "year",
            "donor_entity": name,
            "recipient": g.get("recipient") or "Foundation (Form 4 unspecified)",
            "amount_usd": amount_usd,
            "source_type": "SEC Form 4",
            "source_url": g.get("source_url"),
            "confidence": confidence,
            "note": (
                f"SEC Form 4 code G — {shares:,.0f} shares of "
                f"{g.get('company') or 'issuer'} on "
                f"{g.get('transaction_date') or 'unknown date'} ({amount_blurb}). "
                "Direct gifts to charity are exempt from Form 4 reporting."
            ),
            "regen_source": "sec",
        })

    candidates.sort(key=lambda c: (c["year"], c["amount_usd"] or 0))
    return candidates


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_path.read_text())
    cands = collect_candidates(record, refresh=args.refresh)
    print(f"{args.subject}: {len(cands)} candidates")
    for c in cands[:20]:
        amt = c["amount_usd"]
        amt_s = f"${amt/1e6:>8.2f}M" if amt else "    (n/a)"
        print(f"  {c['year']}  {amt_s}  {c['donor_entity']}  {c['note'][:80]}")
