#!/usr/bin/env python3
"""
Aggregates all data/*.v3.json files into docs/scrooge_latest_v3.json.

Reads v3 schema records, computes a deterministic capacity benchmark
(5% of liquid wealth per year of billionaire tenure, uncapped) and
the absolute dollar shortfall vs. that benchmark. Tier A is ranked by
shortfall descending — i.e., largest undisbursed capacity first.

Also canonicalizes the 50+ variant event_role strings written by
research agents down to a 10-value canonical set, so downstream
deduplication and display are consistent.

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


# 10 canonical event roles. Everything else normalizes into one of these
# via ROLE_NORMALIZATION, or is flagged as unknown by the validator.
CANONICAL_EVENT_ROLES = {
    "grant_out",              # $ out of a donor's foundation to charity
    "direct_gift",            # $ direct from donor to charity (not via foundation)
    "transfer_in",            # $ in to donor's own vehicle — not giving yet
    "pledge",                 # stated commitment to give
    "no_pledge",              # documented declining / absence of a pledge
    "announcement",           # stated intention without a specific $ / counterparty
    "political",              # political contribution — substitution signal, not charity
    "private_investment",     # not charity (trust restructuring, PE, etc.)
    "corporate_gift",         # company-attributed, not personal
    "reference_only",         # context (asset snapshots, rollups, recognitions)
}

ROLE_NORMALIZATION = {
    # grant_out family
    "grant_out_cumulative":                  "grant_out",
    "grant_out_via_affiliated_foundation":   "grant_out",
    "expense_out":                           "grant_out",
    "charitable_expenditures_total":         "grant_out",
    "program_funding":                       "grant_out",
    # direct_gift family
    "direct_gift_announced":                 "direct_gift",
    "direct_gift_cumulative":                "direct_gift",
    "in_kind_donation_minor":                "direct_gift",
    "conservation_easement":                 "direct_gift",
    # pledge (affirmative) family
    "pledge_status":                         "pledge",
    "pledge_status_check":                   "pledge",
    "pledge_amendment":                      "pledge",
    "pledge_fulfilled":                      "pledge",
    "pledge_informal":                       "pledge",
    "informal_commitment":                   "pledge",
    "pledge_response_to_challenge":          "pledge",
    "pledge_adjacent":                       "pledge",
    "pledge_reaffirmation":                  "pledge",
    # no_pledge family
    "pledge_absent":                         "no_pledge",
    "pledge_absence":                        "no_pledge",
    "pledge_absence_verified":               "no_pledge",
    "pledge_declined":                       "no_pledge",
    "pledge_not_signed":                     "no_pledge",
    "pledge_NOT_SIGNED":                     "no_pledge",
    "pledge_refusal":                        "no_pledge",
    "pledge_nonsignatory":                   "no_pledge",
    "pledge_nonsigner":                      "no_pledge",
    "public_statement_not_pledge":           "no_pledge",
    # announcement family
    "announcement_rollup":                   "announcement",
    "announcement_aggregate":                "announcement",
    "vehicle_announcement":                  "announcement",
    "announcement_vehicle_launch":           "announcement",
    # non-charity
    "transfer_in_political_not_charity":     "political",
    "trust_restructuring_not_charity":       "private_investment",
    "private_investment_not_charity":        "private_investment",
    "corporate_gift_not_personal":           "corporate_gift",
    # ambiguous inflows
    "transfer_in_or_pledge_ambiguous":       "transfer_in",
    # reference-only / informational
    "foundation_assets_snapshot":            "reference_only",
    "recognition":                           "reference_only",
    "mission_statement":                     "reference_only",
    "contextual_total_not_counted":          "reference_only",
    "cumulative_disclosure":                 "reference_only",
    "summary_rollup_external":               "reference_only",
    "self_reported_lifetime":                "reference_only",
    "self_reported_total":                   "reference_only",
    "public_statement":                      "reference_only",
    "reference_only_not_attributable":       "reference_only",
    "aggregate_claim":                       "reference_only",
    "dailymail_claim_verification":          "reference_only",
    "event":                                 "reference_only",
    "direct_gift_rollup_anchor":             "reference_only",
}


def canonical_role(raw):
    if not raw:
        return None
    if raw in CANONICAL_EVENT_ROLES:
        return raw
    return ROLE_NORMALIZATION.get(raw)


# Event roles that COUNT toward observable giving when summing.
# Everything else (transfers in, pledges, announcements, political, private, corporate, reference) is excluded.
OBSERVABLE_ROLES = {"grant_out", "direct_gift"}


def compute_expected_5pct_tenure(rec) -> int | None:
    """Canonical capacity benchmark:
        expected = best_estimate_nw_usd × liquidity_pct × 5% × years_as_billionaire

    Rationale: a stable 5%/year of *liquid* wealth is a defensible
    "should-have-given" floor for any billionaire who has had time to give.
    Uncapped tenure: someone who has been a billionaire for 40 years carries
    eight times the expectation of someone who has been one for 5.

    The absolute dollar value of (expected − observable) is the headline
    number — Musk not giving 5%/yr against $800B+ of liquid Tesla stock is
    worse in absolute terms than Peterffy not giving 5%/yr against $83B,
    even if the ratios look similar.
    """
    nw = rec.get("net_worth", {}) or {}
    p = rec.get("person", {}) or {}
    best_nw_b = nw.get("best_estimate_usd_billions")
    liq = nw.get("liquidity_estimate_pct")
    years = p.get("years_as_billionaire_approx")
    if best_nw_b is None or liq is None or years is None:
        return None
    try:
        return int(float(best_nw_b) * 1e9 * float(liq) * 0.05 * float(years))
    except (TypeError, ValueError):
        return None


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

    # NEW canonical benchmark: 5% × liquidity × net_worth × years_as_billionaire, uncapped.
    # This is the headline number for the v3 ranking.
    expected_5pct_tenure_usd = compute_expected_5pct_tenure(rec)
    if expected_5pct_tenure_usd is not None and observable_usd is not None:
        shortfall_5pct_usd = expected_5pct_tenure_usd - observable_usd
        try:
            ratio_to_5pct = round(observable_usd / expected_5pct_tenure_usd, 4) if expected_5pct_tenure_usd else None
        except ZeroDivisionError:
            ratio_to_5pct = None
    else:
        shortfall_5pct_usd = None
        ratio_to_5pct = None

    # Reconciliation: what does the event list alone support?
    # This is the strict "sum of cited, countable charitable outflows" figure.
    # It will often diverge from rollup.observable_giving_usd (the agent's
    # considered judgment) — we publish both and show the delta on profiles.
    #
    # Year=None events are EXCLUDED from this sum: without a year, dedupe
    # cannot collapse multiple press reports of the same gift, so summing
    # them risks 2-3× double-counting. Their dollar value is tracked
    # separately as `unyear_dollars_excluded_usd` so the gap is visible.
    event_sum = 0.0
    unyear_excluded = 0.0
    for ev in (rec.get("cited_events") or []):
        if not isinstance(ev, dict):
            continue
        if canonical_role(ev.get("event_role")) in OBSERVABLE_ROLES:
            amt = ev.get("amount_usd")
            if isinstance(amt, (int, float)) and amt > 0:
                if ev.get("year") is None:
                    unyear_excluded += amt
                else:
                    event_sum += amt
    observable_from_events_usd = int(event_sum) if event_sum > 0 else 0
    unyear_dollars_excluded_usd = int(unyear_excluded) if unyear_excluded > 0 else 0
    if observable_usd and observable_from_events_usd:
        drift_abs = abs(observable_from_events_usd - observable_usd)
        observable_drift_pct = round(drift_abs / observable_usd, 3)
    else:
        observable_drift_pct = None

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
        # Event-sum reconciliation: sum of canonical grant_out + direct_gift
        # amount_usd. When it diverges materially from observable_usd, the
        # drift is surfaced on the profile page.
        "observable_from_events_usd": observable_from_events_usd,
        "observable_drift_pct": observable_drift_pct,
        "unyear_dollars_excluded_usd": unyear_dollars_excluded_usd,
        # Legacy per-record 10%-of-liquid-weighted-by-tenure expected figure (from agent JSON).
        # Preserved for back-compat and comparison; not used for ranking.
        "expected_usd": expected_usd,
        # NEW canonical benchmark (derived in aggregator, not from JSON):
        "expected_5pct_tenure_usd": expected_5pct_tenure_usd,
        "shortfall_5pct_usd": shortfall_5pct_usd,
        "ratio_observable_to_5pct_tenure": ratio_to_5pct,
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
    """Within Tier A, sort by absolute shortfall_5pct_usd descending — i.e. the
    largest undisbursed-capacity-in-dollars comes first. This reframes the
    list from 'who gave the lowest fraction' (which rewards smaller fortunes)
    to 'who left the most capacity on the table' (which reflects actual scale).

    Tier B and C are also shortfall-sorted for legibility; they do not get a
    published ordinal rank. On Track stays alphabetical.
    """
    by_tier: dict[str, list[dict]] = {}
    for r in rows:
        by_tier.setdefault(r["tier"], []).append(r)

    out = []
    for tier, members in by_tier.items():
        if tier in ("A_VERIFIED_LOW", "B_PROBABLY_LOW", "C_OPAQUE"):
            members.sort(
                key=lambda x: (-(x.get("shortfall_5pct_usd") or 0), (x.get("name_display") or "").lower())
            )
        else:
            members.sort(key=lambda x: (x.get("name_display") or "").lower())
        for i, m in enumerate(members, start=1):
            m["tier_rank"] = i if tier == "A_VERIFIED_LOW" else None
        out.extend(members)
    out.sort(key=lambda x: (TIER_ORDER.get(x["tier"], 99), x.get("tier_rank") or 999, (x.get("name_display") or "").lower()))
    return out


def annotate_with_canonical(rec: dict) -> dict:
    """Return a shallow-copied record with canonical fields added without
    destroying agent-written originals. Adds:
      - event_role_canonical on each cited_event / pledges_and_announcements entry
      - rollup.expected_5pct_tenure_usd / shortfall_5pct_usd / ratio_observable_to_5pct_tenure
    """
    import copy
    rec = copy.deepcopy(rec)
    for bucket in ("cited_events", "pledges_and_announcements"):
        for ev in rec.get(bucket) or []:
            if isinstance(ev, dict):
                raw = ev.get("event_role")
                ev["event_role_canonical"] = canonical_role(raw)

    rollup = rec.setdefault("rollup", {})
    exp = compute_expected_5pct_tenure(rec)
    obs = rollup.get("observable_giving_usd") or rollup.get("observable_usd")
    rollup["expected_5pct_tenure_usd"] = exp
    rollup["expected_5pct_tenure_method"] = "5% × net_worth_best × liquidity_pct × years_as_billionaire (uncapped tenure); computed by aggregate_v3.py"
    if exp and obs is not None:
        rollup["shortfall_5pct_usd"] = exp - obs
        try:
            rollup["ratio_observable_to_5pct_tenure"] = round(obs / exp, 4) if exp else None
        except ZeroDivisionError:
            rollup["ratio_observable_to_5pct_tenure"] = None

    # Reconciliation figures — see extract_summary() for rationale.
    # Year=None events are EXCLUDED (can't be deduped — risk of 2-3× counting).
    event_sum = 0.0
    unyear_excluded = 0.0
    for ev in (rec.get("cited_events") or []):
        if not isinstance(ev, dict):
            continue
        if canonical_role(ev.get("event_role")) in OBSERVABLE_ROLES:
            amt = ev.get("amount_usd")
            if isinstance(amt, (int, float)) and amt > 0:
                if ev.get("year") is None:
                    unyear_excluded += amt
                else:
                    event_sum += amt
    rollup["observable_from_events_usd"] = int(event_sum) if event_sum > 0 else 0
    rollup["unyear_dollars_excluded_usd"] = int(unyear_excluded) if unyear_excluded > 0 else 0

    # Sanity check: if observable_from_events exceeds the subject's net worth,
    # something is double-counted (a real person can't give more than they have).
    # Stamp a flag so it's visible on the public profile and we can audit.
    nw_b = rec.get("person", {}).get("net_worth_best_usd_b")
    if nw_b and event_sum > float(nw_b) * 1e9:
        rollup["sanity_flag_observable_exceeds_networth"] = (
            f"observable_from_events_usd ${event_sum/1e9:.1f}B > "
            f"net_worth ${float(nw_b):.1f}B — possible double-count from "
            f"cumulative-figure events not yet caught by extract.py guards."
        )

    if obs and event_sum > 0:
        rollup["observable_drift_pct"] = round(abs(event_sum - obs) / obs, 3)
        rollup["observable_reconciliation_note"] = (
            "Published `observable_giving_usd` reflects agent judgment about attributable giving. "
            "`observable_from_events_usd` is the strict sum of canonical grant_out + direct_gift event amounts. "
            "A gap can mean self-reported lifetime figures beyond cited events (rollup > sum) "
            "or exclusion of inherited-foundation / family-foundation portions (rollup < sum)."
        )
    return rec


# Internal audit fields stamped by extract.py / merge.py guards. Useful in
# the master records for auditing why an event was relabeled, but they look
# like noise on the public profile JSONs. Stripped here.
_INTERNAL_AUDIT_FIELDS = (
    "_role_relabeled_from",
    "_role_relabel_reason",
    "_cardinality_flag",
    "_cumulative_flag",
)


def _strip_audit(rec: dict) -> dict:
    """Return a deep-copyish view of `rec` with internal _ fields removed
    from each event. Mutates a shallow copy; doesn't touch the master record."""
    import copy as _c
    out = _c.deepcopy(rec)
    for fld in ("cited_events", "pledges_and_announcements", "sources_all"):
        items = out.get(fld) or []
        for ev in items:
            if isinstance(ev, dict):
                for k in _INTERNAL_AUDIT_FIELDS:
                    ev.pop(k, None)
    return out


def copy_profiles(records: list[dict]):
    """Copy each v3 record into docs/profiles/<id>.json so the static site can fetch them.
    Necessary because GitHub Pages serves docs/ as the site root — relative ../data paths don't resolve.

    Adds canonical event_role annotations and the 5%/yr-tenure benchmark so profile pages
    can display the derived numbers without recomputing client-side.

    Strips internal `_role_relabeled_from` / `_cardinality_flag` audit fields
    so the public JSON doesn't carry the audit trail (kept in master records).
    """
    PROFILES_DIR.mkdir(exist_ok=True, parents=True)
    # wipe stale files first
    for old in PROFILES_DIR.glob("*.json"):
        old.unlink()
    for rec in records:
        p = rec.get("person", {})
        pid = p.get("name_display", "unknown").lower().replace(" ", "_")
        annotated = annotate_with_canonical(rec)
        annotated = _strip_audit(annotated)
        out = PROFILES_DIR / f"{pid}.json"
        with out.open("w") as f:
            json.dump(annotated, f, indent=2, default=str)


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
        "schema_note": "Published tiers: A_VERIFIED_LOW (ordinal, ranked by $ shortfall vs. 5%-per-year-of-tenure capacity benchmark, uncapped), B_PROBABLY_LOW, C_OPAQUE, ON_TRACK. See docs/methodology.html.",
        "ranking_basis": "shortfall_5pct_usd = (net_worth_best × liquidity_pct × 0.05 × years_as_billionaire) − observable_giving_usd. Computed in aggregator, not read from source JSON.",
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
    print("\nTier A Verified Low (ranked by $ shortfall vs. 5%/yr-tenure benchmark):")
    for r in ranked:
        if r["tier"] == "A_VERIFIED_LOW":
            sf = r.get("shortfall_5pct_usd")
            exp = r.get("expected_5pct_tenure_usd")
            obs = r.get("observable_usd") or 0
            sf_s = f"${sf/1e9:.1f}B" if sf else "—"
            exp_s = f"${exp/1e9:.1f}B" if exp else "—"
            print(f"  #{r['tier_rank']} {r['name_display']:<22} NW ${r['net_worth_best_usd_b']}B  obs ${obs/1e6:.0f}M  exp {exp_s}  shortfall {sf_s}")


if __name__ == "__main__":
    main()
