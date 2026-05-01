"""LLM-driven stub-record generator for new subjects.

Given just (name, net_worth_usd_b, country), produce a valid v3.json stub
that the rest of the pipeline can fill in. The single Claude call
populates the fields that require qualitative knowledge:

  * person.wealth_source              (1-2 sentence narrative)
  * person.dob_year                   (int)
  * person.years_as_billionaire_approx (int — Claude estimates)
  * net_worth.liquidity_estimate_pct  (0-1, heuristic from wealth source)
  * net_worth.liquidity_notes         (one line)
  * detected_vehicles.foundations_active[]  (known foundations + EINs)
  * detected_vehicles.llcs_philanthropic[]  (known CZI-pattern vehicles)
  * detected_vehicles.foundations_note      (one line)
  * giving_pledge_status                    ({signed, year_signed})
  * notable_controversies                   (1-3 sentences if relevant)

Empty arrays for cited_events, pledges_and_announcements, sources_all —
those get filled by regen_v3 (propublica, sec, fec, leaks, llcs, brave+extract).

Reproducibility: cached by sha256(name|nw|country). temperature=0. Same
seed input always produces the same stub.

Cost: ~$0.05/subject with claude-haiku-4-5 (3K input + 2K output tokens).

Usage:
    python3 -m regen_v3.seed --name "Jane Smith" --nw 5.2 --country "United States"
    python3 -m regen_v3.seed --from-forbes --limit 25  # bulk seed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = HERE / "cache" / "seed"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2048

_SYSTEM_PROMPT = """You are a research assistant building a stub research record for a billionaire.

Given just a name, net worth (in USD billions), and country, output a JSON record
with what you know about them from public sources. Be honest about what you don't
know — return null/empty fields rather than fabricating. The pipeline will fill in
the actual giving events from primary-source APIs (IRS 990-PF, SEC, FEC, etc.).

Specifically populate:

1. `wealth_source`: 1-2 sentence narrative. Source of fortune (company, role, year founded,
   key liquidity events). Example: "Larry Ellison co-founded Oracle in 1977; net worth is
   concentrated in Oracle stock plus large real estate (Lanai)."

2. `dob_year`: Integer year of birth, or null if uncertain.

3. `years_as_billionaire_approx`: Integer estimate. If Forbes / press has been calling them
   a billionaire for ~N years, return N. If recent (<5y), use 5 minimum. If you don't know,
   estimate based on company-IPO date or major liquidity event.

4. `liquidity_estimate_pct`: 0.0-1.0 (decimal, not percent). Rough share of net worth that
   is reasonably liquid (cash, public stock, marketable securities). Heuristic by wealth source:
     * Tech founder still holding pre-IPO equity: 0.20-0.40
     * Tech founder post-IPO with diversified holdings: 0.40-0.60
     * Hedge fund GP carry / liquid markets: 0.55-0.75
     * Public-company CEO / heir holding public stock: 0.40-0.60
     * Private real estate / family business: 0.10-0.25
     * Diverse / unknown: 0.30 (default)

5. `liquidity_notes`: One sentence explaining the estimate.

6. `foundations_active`: Array of any known active charitable foundations operated by
   this person OR jointly with a spouse. For each: {name, ein, established_year (if known),
   status: "active"}. Set ein to a 9-digit string with hyphen ("XX-XXXXXXX") if you know
   it; null if not. Be conservative — only include foundations you're sure exist.

7. `llcs_philanthropic`: Array of any known philanthropic LLCs they operate (Chan Zuckerberg
   Initiative LLC, Ballmer Group LLC, Emerson Collective, Lost Horse LLC, etc.). For each:
   {name, status: "active"}.

8. `foundations_note`: One line explaining the philanthropic vehicle landscape, especially
   if there's no foundation or if giving routes through DAFs.

9. `giving_pledge_status`: {signed: bool, year_signed: int|null}. Only mark signed=true if
   you're confident — the official Giving Pledge website lists ~256 signers. Default false.

10. `notable_controversies`: Array of 0-3 short strings if there are public concerns
    (political mega-donor, low-payout foundation, family-foundation attribution disputes,
    etc.). Empty if none. NOT defamatory speculation — only well-documented public concerns.

When unsure, prefer null over guess. You will be cross-checked against ProPublica /
SEC / FEC primary sources — making things up gets caught.
"""


def _tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "wealth_source": {"type": "string"},
            "dob_year": {"type": ["integer", "null"]},
            "years_as_billionaire_approx": {"type": ["integer", "null"]},
            "liquidity_estimate_pct": {"type": ["number", "null"]},
            "liquidity_notes": {"type": "string"},
            "foundations_active": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "ein": {"type": ["string", "null"]},
                        "established_year": {"type": ["integer", "null"]},
                        "status": {"type": "string"},
                    },
                    "required": ["name", "status"],
                },
            },
            "llcs_philanthropic": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "foundations_note": {"type": "string"},
            "giving_pledge_status": {
                "type": "object",
                "properties": {
                    "signed": {"type": "boolean"},
                    "year_signed": {"type": ["integer", "null"]},
                },
                "required": ["signed"],
            },
            "notable_controversies": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "wealth_source", "years_as_billionaire_approx",
            "liquidity_estimate_pct", "foundations_active",
            "llcs_philanthropic", "giving_pledge_status",
        ],
    }


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "").replace(".", "").replace(",", "")


def _cache_key(name: str, nw_b: float, country: str) -> str:
    raw = f"{name.strip().lower()}|{round(nw_b, 2)}|{country.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(name: str, nw_b: float, country: str) -> Path:
    return CACHE_DIR / f"{_cache_key(name, nw_b, country)}.json"


def _have_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def call_llm_seed(
    name: str, nw_b: float, country: str, *, refresh: bool = False
) -> dict | None:
    """Return the LLM-extracted seed dict, or None on failure."""
    cache_path = _cache_path(name, nw_b, country)
    if not refresh and cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass

    if not _have_key() or anthropic is None:
        print("  [seed] ANTHROPIC_API_KEY not set — cannot LLM-seed.")
        return None

    client = anthropic.Anthropic()
    user_prompt = (
        f"NAME: {name}\n"
        f"NET WORTH: ${nw_b:.1f}B\n"
        f"COUNTRY: {country}\n\n"
        "Populate the structured record. Return null/empty rather than guessing."
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=_SYSTEM_PROMPT,
            tools=[{
                "name": "record_seed",
                "description": "Emit the seed record.",
                "input_schema": _tool_schema(),
            }],
            tool_choice={"type": "tool", "name": "record_seed"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        print(f"  [seed] Anthropic call failed: {type(e).__name__}: {e}")
        return None

    block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
    if block is None:
        print("  [seed] no tool_use block in response")
        return None
    seed = dict(block.input)
    cache_path.write_text(json.dumps(seed, indent=2))
    return seed


def build_stub_record(
    name: str, nw_b: float, country: str, *, forbes_id: str | None = None,
    refresh: bool = False,
) -> dict:
    """Assemble a v3.json record from the LLM seed + minimal scaffolding."""
    seed = call_llm_seed(name, nw_b, country, refresh=refresh) or {}

    rec: dict[str, Any] = {
        "schema_version": "v3.0.0-draft",
        "schema_notes": "LLM-seeded stub; populated by regen_v3 from primary-source APIs.",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_by": f"regen_v3.seed (model={MODEL})",
        "person": {
            "name_display": name,
            "name_legal": None,
            "dob_year": seed.get("dob_year"),
            "country_primary": country,
            "wealth_source": seed.get("wealth_source", ""),
            "years_as_billionaire_approx": seed.get("years_as_billionaire_approx"),
        },
        "net_worth": {
            "best_estimate_usd_billions": float(nw_b),
            "range_usd_billions": [round(nw_b * 0.85, 1), round(nw_b * 1.15, 1)],
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m"),
            "range_note": "Forbes RTB seed; range is ±15% to acknowledge stock-price volatility.",
            "sources": [{"publisher": "forbes.com",
                         "url": f"https://www.forbes.com/billionaires/list/" if not forbes_id
                                else f"https://www.forbes.com/profile/{forbes_id}/",
                         "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d")}],
            "liquidity_estimate_pct": seed.get("liquidity_estimate_pct"),
            "liquidity_notes": seed.get("liquidity_notes", ""),
        },
        "cited_events": [],
        "pledges_and_announcements": [],
        "political_giving": {"sources": [], "summary": ""},
        "detected_vehicles": {
            "foundations_active": seed.get("foundations_active", []),
            "foundations_terminated": [],
            "foundations_note": seed.get("foundations_note", ""),
            "dafs_detected": [],
            "dafs_note": "Not yet checked.",
            "llcs_philanthropic": seed.get("llcs_philanthropic", []),
            "llcs_note": "",
        },
        "giving_pledge_status": seed.get("giving_pledge_status", {"signed": False, "year_signed": None}),
        "notable_controversies": seed.get("notable_controversies", []),
        "right_of_reply": {
            "status": "not_yet_requested",
            "scheduled_outreach_date": None,
            "response_deadline": None,
            "response_text": None,
        },
        "sources_all": [],
        "rollup": {
            "tier": "UNKNOWN",
            "tier_raw": "Unknown — pending pipeline run",
            "observable_giving_usd": None,
        },
    }
    return rec


def write_subject(name: str, nw_b: float, country: str = "United States",
                  *, forbes_id: str | None = None,
                  refresh: bool = False, dry_run: bool = False) -> Path | None:
    """Write the stub record to data/<slug>.v3.json. Returns the path or None
    if a record already exists (won't overwrite)."""
    sid = _slug(name)
    fp = DATA_DIR / f"{sid}.v3.json"
    if fp.exists() and not refresh:
        print(f"  [seed] {sid}: already exists, skipping")
        return None
    rec = build_stub_record(name, nw_b, country, forbes_id=forbes_id, refresh=refresh)
    if dry_run:
        print(f"  [seed] {sid}: would write {fp.relative_to(ROOT)} ({len(json.dumps(rec))} bytes)")
        return fp
    tmp = fp.with_suffix(fp.suffix + ".tmp")
    tmp.write_text(json.dumps(rec, indent=2))
    os.replace(tmp, fp)
    print(f"  [seed] {sid}: wrote {fp.relative_to(ROOT)}")
    return fp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--name")
    g.add_argument("--from-forbes", action="store_true")
    ap.add_argument("--nw", type=float, help="Net worth in USD billions")
    ap.add_argument("--country", default="United States")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.name:
        if args.nw is None:
            ap.error("--nw is required when using --name")
        write_subject(args.name, args.nw, args.country,
                      refresh=args.refresh, dry_run=args.dry_run)
        return 0

    # --from-forbes: pull current US billionaires, seed up to --limit not yet present
    from stages.stage1_forbes import fetch_forbes_billionaires
    bs = fetch_forbes_billionaires()
    us_only = [b for b in bs
               if (b.get("country") or "").lower() in ("united states", "usa", "us")]
    us_only.sort(key=lambda x: -(x.get("net_worth_billions") or 0))
    print(f"[seed] {len(us_only)} US billionaires from Forbes RTB")

    seeded = 0
    for b in us_only:
        if seeded >= args.limit:
            break
        name = b.get("name")
        nw = b.get("net_worth_billions")
        if not name or not nw:
            continue
        sid = _slug(name)
        if (DATA_DIR / f"{sid}.v3.json").exists() and not args.refresh:
            continue
        write_subject(name, nw, "United States",
                      refresh=args.refresh, dry_run=args.dry_run)
        seeded += 1
    print(f"[seed] seeded {seeded} new subjects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
