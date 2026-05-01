"""LLM-driven generator for `rollup.hidden_upper_usd` component breakdown.

The 51 hand-curated v3 records carry a `rollup.hidden_upper_usd` blob with
per-channel uplift estimates (DAF, LLC, offshore, anonymous-cohort, religious,
trust-outcome) plus method notes. Newly seeded subjects (~935) won't have this.

This module asks Claude to generate the SAME shape using only the subject's
vehicles + wealth profile (no full event list — too long).

Pattern mirrors regen_v3/seed.py: structured tool use, claude-haiku-4-5,
temperature=0, sha256-keyed cache. ~$0.03/subject.

Usage:
    from regen_v3.llm_hidden_upper import generate_hidden_upper
    generate_hidden_upper(record)  # mutates in place; cached
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "llm_hidden_upper"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1500


_SYSTEM_PROMPT = """You estimate the upper-bound "hidden giving" for a billionaire across
six opaque channels. The output is consumed by the Scrooge List tier classifier — it
shows the maximum plausible giving the subject *could* be doing through channels we
can't directly observe.

You will be given the subject's vehicles + wealth profile (no event list). Reason
from those signals alone. The conventions below mirror existing hand-curated entries
(Ellison, Bezos, Musk, Zuckerberg, Gates) — match their reasoning style and ranges.

CHANNELS (all in absolute USD, integers):

1. daf_uplift_usd — Donor-advised fund balance/disbursement upper bound.
   * If detected_vehicles.dafs_detected is non-empty: use known DAF balance as upper.
   * If foundation→DAF transfers exist: those dollars could have been re-disbursed.
   * If NO DAF evidence at all: 0. Note: "No DAF evidence. Zero uplift."

2. llc_uplift_usd — Philanthropic LLC opacity uplift.
   * If detected_vehicles.llcs_philanthropic is non-empty: apply ~0.2% of liquid wealth
     as an upper bound (LLC wrappers can hide grants). Round to a clean number.
     liquid_wealth = best_estimate_usd_billions × 1e9 × liquidity_estimate_pct.
   * If NO philanthropic LLC: 0. Note: "No philanthropic LLC. Zero uplift."

3. offshore_uplift_usd — ICIJ leaks / offshore-trust uplift.
   * Default 0 with note "Not yet checked (Phase 2). Zero until checked."
   * Only set non-zero if clear offshore evidence in the record.

4. anonymous_cohort_uplift_usd — BofA/Lilly cohort uplift.
   * BofA/Lilly 2024: 69% of older HNW donors give anonymously at least sometimes.
   * Default heuristic: 0.1-0.2% of liquid wealth as upper. Reduce if subject is
     known as publicly-branded giver (Bezos: low). Increase if subject has
     documented anonymous-giving pattern (Musk's mystery Form 4 gifts; Ellison's
     stated privacy preference).
   * For seeded subjects with limited info: 0.1% × liquid_wealth, round to a clean
     number. Note should cite "BofA/Lilly 2024" explicitly.

5. religious_cohort_uplift_usd — Tithing-norm uplift.
   * If wealth_source / controversies suggest a religious affiliation with tithing
     norms (LDS: 10%; Evangelical: 2-5%; Orthodox Jewish: 10%): apply norm × annual
     income proxy (assume income ~ 5% of net worth × tithing rate).
   * Default 0 with note "No publicly disclosed religious affiliation with tithing norms. Zero."

6. trust_outcome_uncertainty_usd — Pledged charitable trust uncertainty.
   * If giving_pledge_status.signed AND no visible disbursement vehicle commensurate
     with pledge: set an uncertainty envelope reflecting what a 10-year disbursement
     of the pledged charitable portion might deploy. Typical: $1B–$10B for $50B+
     pledgers. Note: this is an UNCERTAINTY envelope, not a credit.
   * If NOT signed AND no disclosed charitable trust: 0. Note: "No disclosed
     charitable trust. No trust uplift."
   * If signed but observable_giving already large relative to net worth: scale down.

7. total_usd = sum of the six channel uplifts.

8. total_method = one-line formula like "anonymous + trust (others zero)" or
   "daf + llc + anonymous (offshore/religious/trust zero)".

STYLE NOTES:
* Notes should be 1-3 sentences. Reference specific signals from the input
  (e.g. "no philanthropic LLC detected", "Forbes net worth = $X.XB", pledge status).
* Use round numbers. $200M, $500M, $1B — not $217.4M.
* Be CONSERVATIVE with anonymous + LLC uplifts when no signal exists. Default low.
* Be CONSERVATIVE with trust uncertainty. Don't credit pledges that have no
  disclosed vehicle.
* If observable_giving_usd is small AND net worth is small (<$5B), all uplifts
  should be small or zero. Don't apply the same dollar bounds as a $200B subject.

OUTPUT: emit_hidden_upper tool call. Integers only for *_usd fields.
"""


def _tool_schema() -> dict[str, Any]:
    str_field = {"type": "string"}
    int_field = {"type": "integer"}
    return {
        "type": "object",
        "properties": {
            "daf_uplift_usd": int_field,
            "daf_uplift_note": str_field,
            "llc_uplift_usd": int_field,
            "llc_uplift_note": str_field,
            "offshore_uplift_usd": int_field,
            "offshore_uplift_note": str_field,
            "anonymous_cohort_uplift_usd": int_field,
            "anonymous_cohort_method": str_field,
            "religious_cohort_uplift_usd": int_field,
            "religious_note": str_field,
            "trust_outcome_uncertainty_usd": int_field,
            "trust_outcome_method": str_field,
            "total_usd": int_field,
            "total_method": str_field,
        },
        "required": [
            "daf_uplift_usd", "daf_uplift_note",
            "llc_uplift_usd", "llc_uplift_note",
            "offshore_uplift_usd", "offshore_uplift_note",
            "anonymous_cohort_uplift_usd", "anonymous_cohort_method",
            "religious_cohort_uplift_usd", "religious_note",
            "trust_outcome_uncertainty_usd", "trust_outcome_method",
            "total_usd", "total_method",
        ],
    }


def _have_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _build_user_prompt(record: dict) -> str:
    person = record.get("person", {}) or {}
    nw = record.get("net_worth", {}) or {}
    vehicles = record.get("detected_vehicles", {}) or {}
    rollup = record.get("rollup", {}) or {}
    pledge = record.get("giving_pledge_status", {}) or {}

    payload = {
        "name": person.get("name_display"),
        "wealth_source": person.get("wealth_source"),
        "country": person.get("country_primary"),
        "years_as_billionaire_approx": person.get("years_as_billionaire_approx"),
        "net_worth_usd_billions": nw.get("best_estimate_usd_billions"),
        "liquidity_estimate_pct": nw.get("liquidity_estimate_pct"),
        "liquidity_notes": nw.get("liquidity_notes"),
        "foundations_active": vehicles.get("foundations_active", []),
        "llcs_philanthropic": vehicles.get("llcs_philanthropic", []),
        "dafs_detected": vehicles.get("dafs_detected", []),
        "foundations_note": vehicles.get("foundations_note", ""),
        "dafs_note": vehicles.get("dafs_note", ""),
        "observable_giving_usd": rollup.get("observable_giving_usd"),
        "giving_pledge_status": pledge,
        "notable_controversies": record.get("notable_controversies", []),
    }
    return (
        "Subject profile:\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n\nEmit the hidden_upper_usd component breakdown via the tool call."
    )


def _canonical_input_json(record: dict) -> str:
    """Stable JSON of just the inputs the LLM sees — used for the cache key."""
    person = record.get("person", {}) or {}
    nw = record.get("net_worth", {}) or {}
    vehicles = record.get("detected_vehicles", {}) or {}
    rollup = record.get("rollup", {}) or {}
    payload = {
        "name": person.get("name_display"),
        "wealth_source": person.get("wealth_source"),
        "nw_b": nw.get("best_estimate_usd_billions"),
        "liq_pct": nw.get("liquidity_estimate_pct"),
        "foundations": [f.get("name") for f in vehicles.get("foundations_active", []) or []],
        "llcs": [l.get("name") for l in vehicles.get("llcs_philanthropic", []) or []],
        "dafs": [d.get("name") for d in vehicles.get("dafs_detected", []) or []],
        "observable_usd": rollup.get("observable_giving_usd"),
        "pledge_signed": (record.get("giving_pledge_status", {}) or {}).get("signed"),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _cache_path(record: dict) -> Path:
    h = hashlib.sha256(_canonical_input_json(record).encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


def _existing_total(record: dict) -> int:
    rollup = record.get("rollup") or {}
    hu = rollup.get("hidden_upper_usd") or {}
    if not isinstance(hu, dict):
        return 0
    try:
        return int(hu.get("total_usd") or 0)
    except (TypeError, ValueError):
        return 0


def generate_hidden_upper(record: dict, *, refresh: bool = False) -> dict | None:
    """Mutate record in place: if rollup.hidden_upper_usd is missing/empty, call
    Claude to generate it. Returns the new component dict (or the existing one
    if preserved). Returns None on failure.
    """
    # Preserve any hand-curated hidden_upper_usd dict, even when its total_usd
    # is 0 — Moskovitz is the canonical case (rich per-channel curation,
    # total nets to 0). Running the LLM would overwrite the carefully-written
    # notes. Refresh=True still forces a regeneration.
    rollup = record.get("rollup") or {}
    existing = rollup.get("hidden_upper_usd")
    if not refresh and isinstance(existing, dict) and len(existing) > 0:
        return existing

    cache_path = _cache_path(record)
    if not refresh and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            record.setdefault("rollup", {})["hidden_upper_usd"] = cached
            return cached
        except Exception:
            pass

    if not _have_key() or anthropic is None:
        name = (record.get("person") or {}).get("name_display", "?")
        print(f"  [hidden_upper-skip] {name}: ANTHROPIC_API_KEY not set")
        return None

    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=_SYSTEM_PROMPT,
            tools=[{
                "name": "emit_hidden_upper",
                "description": "Emit hidden_upper_usd component breakdown.",
                "input_schema": _tool_schema(),
            }],
            tool_choice={"type": "tool", "name": "emit_hidden_upper"},
            messages=[{"role": "user", "content": _build_user_prompt(record)}],
        )
    except Exception as e:
        print(f"  [hidden_upper] Anthropic call failed: {type(e).__name__}: {e}")
        return None

    block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
    if block is None:
        print("  [hidden_upper] no tool_use block in response")
        return None
    components = dict(block.input)

    # Recompute total_usd defensively from channel sums.
    channel_keys = [
        "daf_uplift_usd", "llc_uplift_usd", "offshore_uplift_usd",
        "anonymous_cohort_uplift_usd", "religious_cohort_uplift_usd",
        "trust_outcome_uncertainty_usd",
    ]
    components["total_usd"] = int(sum(int(components.get(k) or 0) for k in channel_keys))

    cache_path.write_text(json.dumps(components, indent=2))
    record.setdefault("rollup", {})["hidden_upper_usd"] = components
    # Best-effort token logging (helps cost tuning).
    usage = getattr(resp, "usage", None)
    if usage is not None:
        name = (record.get("person") or {}).get("name_display", "?")
        print(
            f"  [hidden_upper] {name}: in={usage.input_tokens} out={usage.output_tokens} "
            f"total=${components['total_usd']:,}"
        )
    return components


# ---- CLI for ad-hoc testing -------------------------------------------------

def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", help="Path to a v3.json record")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--write", action="store_true",
                    help="Write the mutated record back to disk")
    args = ap.parse_args()

    fp = Path(args.path)
    record = json.loads(fp.read_text())
    before_total = _existing_total(record)
    out = generate_hidden_upper(record, refresh=args.refresh)
    after_total = _existing_total(record)

    print(f"  before total_usd = {before_total:,}")
    print(f"  after  total_usd = {after_total:,}")
    if out:
        print(json.dumps(out, indent=2))
    if args.write and out:
        fp.write_text(json.dumps(record, indent=2))
        print(f"  wrote {fp}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
