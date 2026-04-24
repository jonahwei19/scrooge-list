#!/usr/bin/env python3
"""
Aggregates all data/*.v3.json files into docs/scrooge_latest_v3.json.

Only reads v3 schema records (not legacy). Computes tier-ranked lists and
preserves every source URL for downstream display.

Run: python3 aggregate_v3.py
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
OUT_JSON = HERE / "docs" / "scrooge_latest_v3.json"
PROFILES_DIR = HERE / "docs" / "profiles"


def load_v3_records() -> list[dict]:
    records = []
    for fp in sorted(DATA_DIR.glob("*.v3.json")):
        try:
            with fp.open() as f:
                rec = json.load(f)
            rec["_source_file"] = fp.name
            records.append(rec)
        except Exception as e:
            print(f"  skip {fp.name}: {e}", file=sys.stderr)
    return records


def extract_summary(rec: dict) -> dict:
    """Pull the fields the front-end displays into a flat row."""
    p = rec.get("person", {})
    nw = rec.get("net_worth", {})
    rollup = rec.get("rollup", {})
    vehicles = rec.get("detected_vehicles", {})
    red_flags = [rf["flag"] if isinstance(rf, dict) else rf for rf in rec.get("red_flags", [])]

    # Observable numbers — different schemas have evolved; handle both.
    observable_usd = rollup.get("observable_giving_usd") or rollup.get("observable_usd") or 0
    expected_usd = (
        rollup.get("expected_giving_usd_10pct_liquid_weighted_by_tenure")
        or rollup.get("expected_giving_usd_10pct_liquid_strict")
        or rollup.get("expected_giving_usd")
        or 0
    )
    hidden_upper = (rollup.get("hidden_upper_usd") or {}).get("total_usd") or 0
    # Agents have produced slightly varying key names. Try canonical first,
    # then known alternates, then compute from observable/expected.
    ratio_to_expected = (
        rollup.get("observable_ratio_to_expected")
        or rollup.get("observable_ratio_to_expected_strict")
        or rollup.get("observable_ratio_to_expected_formal_tenure")
        or rollup.get("observable_ratio_to_expected_at_10pct_pledge")
    )
    if ratio_to_expected is None and expected_usd and observable_usd is not None:
        try:
            ratio_to_expected = round(observable_usd / expected_usd, 4)
        except ZeroDivisionError:
            ratio_to_expected = None
    ratio_to_nw = rollup.get("observable_ratio_to_current_nw")

    # Tier — normalize various forms the agents produced
    tier_raw = rollup.get("tier", "unknown")
    tier_norm = normalize_tier(tier_raw)

    return {
        "id": p.get("name_display", "unknown").lower().replace(" ", "_"),
        "name_display": p.get("name_display"),
        "name_legal": p.get("name_legal"),
        "country": p.get("country_primary"),
        "wealth_source": p.get("wealth_source"),
        "years_as_billionaire_approx": p.get("years_as_billionaire_approx"),

        "net_worth_best_usd_b": nw.get("best_estimate_usd_billions"),
        "net_worth_range_usd_b": nw.get("range_usd_billions"),
        "net_worth_as_of": nw.get("as_of"),
        "liquidity_estimate_pct": nw.get("liquidity_estimate_pct"),

        "observable_usd": observable_usd,
        "expected_usd": expected_usd,
        "hidden_upper_usd": hidden_upper,
        "ratio_observable_to_expected": ratio_to_expected,
        "ratio_observable_to_nw": ratio_to_nw,

        "tier": tier_norm,
        "tier_raw": tier_raw,
        "tier_reasoning": rollup.get("tier_reasoning") or rollup.get("tier_published_caveat"),

        "pledge_signed": any(
            p.get("event_role") == "pledge" and ("giving_pledge" in (p.get("source_url") or "").lower() or "giving_pledge" in (p.get("event_id") or "").lower())
            for p in rec.get("pledges_and_announcements", [])
        ),
        "red_flags": red_flags,

        "detected_vehicles": {
            "foundations_active_count": len(vehicles.get("foundations_active", []) or []),
            "foundations_active_names": [
                f.get("name") for f in vehicles.get("foundations_active", []) or []
            ],
            "llcs_philanthropic_count": len(vehicles.get("llcs_philanthropic", []) or []),
            "for_profit_hybrids_count": len(vehicles.get("for_profit_hybrid_vehicles", []) or []),
            "offshore_count": len(vehicles.get("offshore_entities", []) or []),
            "dafs_detected": len(vehicles.get("dafs_detected", []) or []) > 0,
        },

        "sources_count": len(rec.get("sources_all", []) or []),
        "event_count": len(rec.get("cited_events", []) or []) + len(rec.get("pledges_and_announcements", []) or []),

        "right_of_reply_status": (rec.get("right_of_reply", {}) or {}).get("status", "not_yet_requested"),
        "_source_file": rec.get("_source_file"),
    }


def normalize_tier(raw: str) -> str:
    """Map agent-produced tier strings to canonical set:
    A_VERIFIED_LOW / B_PROBABLY_LOW / C_OPAQUE / ON_TRACK.

    Explicit `(Tier X)` markers authoritative; `Tier A+` means on-track (creative writing).
    On-track markers bind only if there is no explicit (Tier B/C) bracket saying otherwise.
    """
    import re
    if not raw:
        return "UNKNOWN"
    r = str(raw).lower()

    # Explicit Tier X bracket has priority
    m = re.search(r"\(tier\s*([abc]\+?)\b", r)
    tier_bracket = m.group(1) if m else None

    on_track_kw = any(k in r for k in (
        "on_track", "on track", "model_pledger", "doing_it", "doing it",
        "ceiling", "high giving", "probably high", "ceiling_reference", "a+"
    ))

    if tier_bracket == "a+":
        return "ON_TRACK"
    if tier_bracket == "a":
        # explicit Tier A from agent — only returns Scrooge-A if no on-track hedge
        return "ON_TRACK" if on_track_kw else "A_VERIFIED_LOW"
    if tier_bracket == "b":
        return "B_PROBABLY_LOW"
    if tier_bracket == "c":
        return "ON_TRACK" if on_track_kw else "C_OPAQUE"

    # No explicit bracket: keyword fallbacks
    if on_track_kw:
        return "ON_TRACK"
    if any(k in r for k in ("probably_low", "probably low", "probably_moderate",
                            "probably moderate", "probably_generous")):
        return "B_PROBABLY_LOW"
    if "opaque" in r:
        return "C_OPAQUE"
    if "verified_low" in r or "verified low" in r:
        return "A_VERIFIED_LOW"
    if "moderate" in r:
        return "MODERATE"
    return "UNKNOWN"


TIER_ORDER = {
    "A_VERIFIED_LOW": 0,
    "B_PROBABLY_LOW": 1,
    "C_OPAQUE": 2,
    "MODERATE": 3,
    "ON_TRACK": 4,
    "UNKNOWN": 5,
}


def rank_within_tier(rows: list[dict]) -> list[dict]:
    """Within each tier, sort by observable-ratio-to-expected ascending (lowest = most Scrooge).
    For Tier A, ordinal rank is published. For other tiers, alphabetical."""
    by_tier: dict[str, list[dict]] = {}
    for r in rows:
        by_tier.setdefault(r["tier"], []).append(r)

    out = []
    for tier, members in by_tier.items():
        if tier == "A_VERIFIED_LOW":
            members.sort(
                key=lambda x: (x.get("ratio_observable_to_expected") or 1.0, -(x.get("net_worth_best_usd_b") or 0))
            )
        else:
            members.sort(key=lambda x: (x.get("name_display") or "").lower())
        for i, m in enumerate(members, start=1):
            m["tier_rank"] = i if tier == "A_VERIFIED_LOW" else None
        out.extend(members)
    out.sort(key=lambda x: (TIER_ORDER.get(x["tier"], 99), x.get("tier_rank") or 999, (x.get("name_display") or "").lower()))
    return out


def copy_profiles(records: list[dict]):
    """Copy each v3 record into docs/profiles/<id>.json so the static site can fetch them.
    Necessary because GitHub Pages serves docs/ as the site root — relative ../data paths don't resolve."""
    PROFILES_DIR.mkdir(exist_ok=True, parents=True)
    # wipe stale files first
    for old in PROFILES_DIR.glob("*.json"):
        old.unlink()
    for rec in records:
        p = rec.get("person", {})
        pid = p.get("name_display", "unknown").lower().replace(" ", "_")
        out = PROFILES_DIR / f"{pid}.json"
        with out.open("w") as f:
            json.dump(rec, f, indent=2, default=str)


def main():
    records = load_v3_records()
    print(f"loaded {len(records)} v3 records from {DATA_DIR}")

    copy_profiles(records)
    print(f"copied {len(records)} profile JSONs to {PROFILES_DIR}")

    rows = [extract_summary(r) for r in records]
    ranked = rank_within_tier(rows)

    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "generator": "aggregate_v3.py",
        "cohort": "US Tier A launch cohort",
        "schema_note": "Published tiers: A_VERIFIED_LOW (ordinal ranked), B_PROBABLY_LOW, C_OPAQUE, MODERATE, ON_TRACK. See docs/methodology.html.",
        "legal_disclaimer": "Every figure is an estimate of OBSERVABLE giving from the cited sources. Does not measure total giving. Subjects have been offered a right-of-reply; responses are published on individual profiles. Corrections welcome — see methodology page.",
        "tier_counts": {t: sum(1 for r in ranked if r["tier"] == t) for t in TIER_ORDER},
        "count": len(ranked),
        "billionaires": ranked,
    }

    OUT_JSON.parent.mkdir(exist_ok=True)
    with OUT_JSON.open("w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"wrote {OUT_JSON}")
    print("\nTier counts:")
    for t, n in out["tier_counts"].items():
        if n:
            print(f"  {t}: {n}")
    print("\nTier A Verified Low (ordinal):")
    for r in ranked:
        if r["tier"] == "A_VERIFIED_LOW":
            print(f"  #{r['tier_rank']} {r['name_display']:<24} NW ${r['net_worth_best_usd_b']}B  obs ${(r['observable_usd'] or 0)/1e6:.0f}M  ratio {r.get('ratio_observable_to_expected')}")


if __name__ == "__main__":
    main()
