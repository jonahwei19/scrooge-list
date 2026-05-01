"""LLM-driven tier_reasoning generator.

Each subject's `rollup.tier_reasoning` is a 2-3 sentence narrative explaining
why they sit in their tier (terse, journalistic, acknowledges nuance — not
boilerplate). The 51 hand-curated v3 records have these (some live under the
legacy field name `tier_published_caveat`); the ~935 stub records produced by
`regen_v3.seed` will not. This module fills that gap.

Reproducibility: cached by sha256 of the LLM input bundle. temperature=0.

Cost: ~$0.02/subject with claude-haiku-4-5 (~1500 input + 200 output tokens).

Usage (programmatic):
    from regen_v3.llm_tier_reasoning import generate_tier_reasoning
    para = generate_tier_reasoning(record)

Usage (CLI):
    python3 -m regen_v3.llm_tier_reasoning --subject daniel_loeb
    python3 -m regen_v3.llm_tier_reasoning --subject daniel_loeb --refresh
    python3 -m regen_v3.llm_tier_reasoning --subject daniel_loeb --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = HERE / "cache" / "llm_tier_reasoning"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 512

_SYSTEM_PROMPT = """You write the `tier_reasoning` paragraph for a billionaire-giving research record.

Voice: terse, direct, journalistic. 2-3 sentences. ONE paragraph. No headers, no bullets.
Acknowledge nuance — say "DAF-heavy but committed" or "low payout but structural reasons"
when warranted. Don't moralize; describe. Don't restate raw numbers the reader already sees;
explain what they mean. Treat the reader as someone who landed on the profile expecting one
thing and might be surprised.

Reference voice — match this register:

  Reed Hastings (ON_TRACK): "Hastings is the canonical 'DAF-heavy Giving Pledger' —
  publicly committed, structurally liquid, and has moved large dollar amounts out of
  his personal balance sheet into a charitable vehicle. Readers who reach this profile
  expecting low giving will see otherwise."

  Larry Ellison (Tier B / Probably Low): "Readers should see Ellison as the canonical
  example of 'signed the Giving Pledge, hasn't followed through yet.' Observable giving
  is ~0.2% of current net worth and 8% of the formal norm. The trust could still make
  good; as of today it has not."

  Mark Zuckerberg (Tier C / Opaque): "The canonical LLC_OPACITY case. 990-PF grants alone
  would place him mid-tier; the 99% Meta shares pledge, if delivered to 501(c)(3)s, would
  make him one of the largest philanthropists in history. As of today only ~2.3% of that
  notional has reached the 501(c)(3) arm — the rest sits in a for-profit LLC whose
  grantees we cannot independently verify."

Tier semantics:
- Tier A / Verified Low: observable + plausible hidden upper << expected. Strong claim.
- Tier B / Probably Low: low observable, but structural reason to expect more later
  (signed pledge, disclosed trust, recent liquidity event).
- Tier C / Opaque: meaningful giving structure exists (LLC, DAF) but the pipeline
  cannot verify what reaches end charities. Methodology-dependent.
- ON_TRACK: observable + reasonable hidden estimate is close to or above the 5%-of-
  liquid-by-tenure norm.
- Buffett-like / CEILING_REFERENCE: observable far exceeds norm; reference standard.
- UNKNOWN / pending: pipeline hasn't filled enough to judge.

What to anchor on (in roughly this order):
1. The size of the gap (or excess) between observable and the 5%-of-liquid-by-tenure norm.
2. The structure of giving vehicles: foundation, DAF, philanthropic LLC, trust.
3. Giving Pledge status — signed but undelivered is the load-bearing fact for many.
4. Notable controversies only if they matter for the tier judgment.

Constraints:
- 2-3 sentences. Hard ceiling.
- Don't write "this person." Use the surname.
- Don't hedge with "appears to" / "seems" — if the data says it, say it.
- Don't recap their wealth source unless it bears on liquidity (e.g., real estate -> illiquid).
- Don't fabricate numbers. Only use figures that appear in the input bundle.
"""


def _tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "tier_reasoning": {"type": "string"},
        },
        "required": ["tier_reasoning"],
    }


def _have_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _existing_reasoning(record: dict) -> str | None:
    rollup = record.get("rollup") or {}
    val = rollup.get("tier_reasoning")
    if isinstance(val, str) and val.strip():
        return val
    # legacy field on hand-curated records
    val = rollup.get("tier_published_caveat")
    if isinstance(val, str) and val.strip():
        return val
    return None


def _summarize_inputs(record: dict) -> dict:
    """Distill a record down to the fields the LLM actually needs."""
    p = record.get("person") or {}
    nw = record.get("net_worth") or {}
    rollup = record.get("rollup") or {}
    vehicles = record.get("detected_vehicles") or {}
    pledge = record.get("giving_pledge_status") or {}

    foundations = [
        {"name": f.get("name"), "ein": f.get("ein")}
        for f in (vehicles.get("foundations_active") or [])
        if f.get("name")
    ]
    llcs = [l.get("name") for l in (vehicles.get("llcs_philanthropic") or []) if l.get("name")]

    return {
        "name": p.get("name_display"),
        "wealth_source": p.get("wealth_source"),
        "years_as_billionaire_approx": p.get("years_as_billionaire_approx"),
        "net_worth_best_usd_b": nw.get("best_estimate_usd_billions"),
        "net_worth_range_usd_b": nw.get("range_usd_billions"),
        "liquidity_estimate_pct": nw.get("liquidity_estimate_pct"),
        "observable_giving_usd": rollup.get("observable_giving_usd"),
        "expected_5pct_tenure_usd": rollup.get("expected_5pct_tenure_usd"),
        "ratio_observable_to_5pct_tenure": rollup.get("ratio_observable_to_5pct_tenure")
            or rollup.get("observable_ratio_to_expected"),
        "shortfall_5pct_usd": rollup.get("shortfall_5pct_usd"),
        "tier": rollup.get("tier"),
        "tier_raw": rollup.get("tier_raw"),
        "foundations_active": foundations,
        "llcs_philanthropic": llcs,
        "giving_pledge_signed": bool(pledge.get("signed")),
        "giving_pledge_year_signed": pledge.get("year_signed"),
        "notable_controversies": record.get("notable_controversies") or [],
    }


def _cache_key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def generate_tier_reasoning(record: dict, *, refresh: bool = False) -> str:
    """Generate a 2-3 sentence tier_reasoning paragraph for a subject.

    Skips (returns existing) if record.rollup.tier_reasoning (or the legacy
    tier_published_caveat) is already set.
    Cached at regen_v3/cache/llm_tier_reasoning/<sha256(record)>.json.
    Returns empty string on failure (no key, API error).
    """
    if not refresh:
        existing = _existing_reasoning(record)
        if existing:
            return existing

    payload = _summarize_inputs(record)
    cache_path = CACHE_DIR / f"{_cache_key(payload)}.json"
    if not refresh and cache_path.exists():
        try:
            return json.loads(cache_path.read_text()).get("tier_reasoning", "")
        except Exception:
            pass

    if not _have_key() or anthropic is None:
        print("  [tier_reasoning] ANTHROPIC_API_KEY not set — [skip]")
        return ""

    client = anthropic.Anthropic()
    user_prompt = (
        "Subject record (only these fields — do not invent others):\n\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n\nWrite the tier_reasoning paragraph."
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=_SYSTEM_PROMPT,
            tools=[{
                "name": "record_tier_reasoning",
                "description": "Emit the tier_reasoning paragraph.",
                "input_schema": _tool_schema(),
            }],
            tool_choice={"type": "tool", "name": "record_tier_reasoning"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        print(f"  [tier_reasoning] Anthropic call failed: {type(e).__name__}: {e}")
        return ""

    block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
    if block is None:
        print("  [tier_reasoning] no tool_use block in response")
        return ""
    out = (dict(block.input).get("tier_reasoning") or "").strip()
    if not out:
        return ""
    cache_path.write_text(json.dumps({"tier_reasoning": out}, indent=2))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True, help="subject id (e.g. daniel_loeb)")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore cached reasoning and regenerate")
    ap.add_argument("--write", action="store_true",
                    help="write the reasoning into rollup.tier_reasoning of the record")
    args = ap.parse_args(argv)

    fp = DATA_DIR / f"{args.subject}.v3.json"
    if not fp.exists():
        ap.error(f"no record at {fp}")
    record = json.loads(fp.read_text())

    para = generate_tier_reasoning(record, refresh=args.refresh)
    if not para:
        print("[tier_reasoning] (empty — skipped or failed)")
        return 1

    print(para)

    if args.write:
        rollup = record.setdefault("rollup", {})
        rollup["tier_reasoning"] = para
        tmp = fp.with_suffix(fp.suffix + ".tmp")
        tmp.write_text(json.dumps(record, indent=2))
        os.replace(tmp, fp)
        print(f"[tier_reasoning] wrote → {fp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
