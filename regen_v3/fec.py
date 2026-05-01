"""FEC contributions source for regen_v3.

Wraps `categories.political` to produce candidate events from the FEC
individual-contributions API. Tracks political giving — which the v3 schema
treats as context (not charity), via the `political` event_role.

Cache: regen_v3/cache/fec/<sha256(name|cycles)>.json — same name + same
cycle list never re-hits the FEC unless `refresh=True`.

API key: reads FEC_API_KEY from the environment. With no key set, the
module returns [] and prints a one-line note (does not raise) so the
broader pipeline can keep going.

Reproducibility: FEC bulk data for closed cycles never changes. Open
cycles (e.g. the current 2026 cycle while in progress) will drift, so
runs across the open cycle will differ — that's a property of the data
source, not the cache.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "fec"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from regen_v3._atomic import atomic_write_json  # type: ignore
except Exception:  # pragma: no cover - in-package fallback
    from _atomic import atomic_write_json  # type: ignore

# Default election cycles to query. Override per-call if needed.
DEFAULT_CYCLES = (2024, 2022, 2020, 2018, 2016)


def _has_key() -> bool:
    return bool(os.environ.get("FEC_API_KEY"))


def _cache_key(name: str, cycles: tuple[int, ...]) -> str:
    raw = f"{name.strip().lower()}|{','.join(str(c) for c in sorted(cycles))}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(name: str, cycles: tuple[int, ...]) -> Path:
    return CACHE_DIR / f"{_cache_key(name, cycles)}.json"


def _load_cache(name: str, cycles: tuple[int, ...]) -> list[dict] | None:
    p = _cache_path(name, cycles)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("contributions")
    except Exception:
        return None


def _save_cache(name: str, cycles: tuple[int, ...], contributions: list[dict]) -> None:
    # Atomic write: cache key is sha(name|cycles); two subjects with the
    # same legal-name string (rare but possible — e.g. shared family
    # display names) would collide here.
    atomic_write_json(
        _cache_path(name, cycles),
        {
            "name": name,
            "cycles": list(cycles),
            "contributions": contributions,
        },
    )


def _names_to_search(record: dict) -> list[str]:
    """Names to query the FEC under. The display name is the primary; we
    also include the legal name when it differs (e.g. 'Henry Roberts Kravis')
    because the FEC contributor field uses the donor's legally-recorded name."""
    person = record.get("person") or {}
    out: list[str] = []
    seen: set[str] = set()
    for fld in ("name_display", "name_legal"):
        n = person.get(fld)
        if isinstance(n, str) and n.strip() and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n.strip())
    return out


def fetch_contributions(
    name: str,
    *,
    cycles: tuple[int, ...] = DEFAULT_CYCLES,
    refresh: bool = False,
    min_amount: int = 1000,
) -> list[dict]:
    """Return raw FEC contributions for a name (cached)."""
    if not refresh:
        cached = _load_cache(name, cycles)
        if cached is not None:
            return cached

    if not _has_key():
        # No live calls without a key. Cache the empty result so the same
        # query doesn't keep hitting this branch within a single run.
        _save_cache(name, cycles, [])
        return []

    # Defer the import so the module can be loaded without `requests` at
    # import-time issues, and so legacy categories.political only runs when
    # we actually have a key.
    from categories.political import search_fec_contributions  # noqa: E402

    contributions = search_fec_contributions(name, min_amount=min_amount, cycles=list(cycles))
    serial = [
        {
            "recipient": c.recipient,
            "recipient_type": c.recipient_type,
            "amount": c.amount,
            "date": c.date,
            "election_cycle": c.election_cycle,
            "source_url": c.source_url,
        }
        for c in contributions
    ]
    _save_cache(name, cycles, serial)
    time.sleep(0.5)  # Be polite to the FEC API.
    return serial


def _contribution_year(c: dict) -> int | None:
    d = c.get("date") or ""
    if len(d) >= 4 and d[:4].isdigit():
        return int(d[:4])
    cycle = c.get("election_cycle")
    return int(cycle) if isinstance(cycle, int) else None


def _aggregate_by_year(contributions: list[dict]) -> dict[int, dict]:
    """Sum contributions by calendar year. The v3 schema treats political
    giving as a single annual figure per donor — we aggregate to avoid
    emitting hundreds of $5k line-items."""
    by_year: dict[int, dict] = {}
    for c in contributions:
        y = _contribution_year(c)
        if not y:
            continue
        bucket = by_year.setdefault(y, {
            "year": y,
            "total": 0.0,
            "count": 0,
            "by_type": {},
        })
        amt = float(c.get("amount") or 0)
        bucket["total"] += amt
        bucket["count"] += 1
        rt = c.get("recipient_type") or "OTHER"
        bucket["by_type"][rt] = bucket["by_type"].get(rt, 0.0) + amt
    return by_year


def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return regen_v3 candidate events for FEC contributions, aggregated
    one event per year. Empty when no FEC_API_KEY is set."""
    name_display = (record.get("person") or {}).get("name_display") or ""
    candidates: list[dict] = []
    seen_keys: set[tuple[int, str]] = set()

    for name in _names_to_search(record):
        contributions = fetch_contributions(name, refresh=refresh)
        if not contributions:
            continue

        for year, agg in _aggregate_by_year(contributions).items():
            total = agg["total"]
            if total <= 0:
                continue
            key = (year, name.lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)

            type_blurb = ", ".join(
                f"{rt}=${amt/1e3:.0f}k" for rt, amt in sorted(agg["by_type"].items())
            )
            cycle = (year - 1) if (year % 2 == 1) else year
            source_url = (
                "https://www.fec.gov/data/receipts/individual-contributions/"
                f"?contributor_name={name.replace(' ', '+')}"
                f"&two_year_transaction_period={cycle}"
            )

            candidates.append({
                "event_role": "political",
                "year": year,
                "date_precision": "year",
                "donor_entity": name_display or name,
                "recipient": "Multiple federal committees (FEC aggregate)",
                "amount_usd": float(total),
                "source_type": "FEC API",
                "source_url": source_url,
                "confidence": "high",
                "note": (
                    f"FEC aggregate of {agg['count']} contributions in {year} "
                    f"matched to '{name}' (min $1k filter). Breakdown: {type_blurb}. "
                    "Political giving is tracked for context, not as charity."
                ),
                "regen_source": "fec",
            })

    candidates.sort(key=lambda c: c["year"])
    return candidates


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if not _has_key():
        print("[note] FEC_API_KEY not set — module will return cached results only.")

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_path.read_text())
    cands = collect_candidates(record, refresh=args.refresh)
    print(f"{args.subject}: {len(cands)} candidates")
    for c in cands:
        print(f"  {c['year']}  ${c['amount_usd']/1e6:>6.2f}M  {c['donor_entity']}  ({c['note'][:80]})")
