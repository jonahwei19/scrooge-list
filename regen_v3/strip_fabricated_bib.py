"""Strip fabricated-URL bibliography entries from v3 records.

Mechanical fix for `sources_all` entries flagged
`dead_link_likely_fabricated*`. These are bibliography pointers, not
dollar-bearing events — removing them is non-destructive for the giving
arithmetic. Per-event fabricated URLs (in `cited_events` /
`pledges_and_announcements`) require manual replacement and are NOT
touched by this tool.

Usage:
    python3 -m regen_v3.strip_fabricated_bib --all          # cohort
    python3 -m regen_v3.strip_fabricated_bib --subject foo  # one
    python3 -m regen_v3.strip_fabricated_bib --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"


def _is_fab(s: dict) -> bool:
    if not isinstance(s, dict):
        return False
    status = s.get("source_verification_status") or ""
    return status.startswith("dead_link_likely_fabricated")


def strip_one(fp: Path, *, dry_run: bool) -> tuple[int, int]:
    """Returns (n_stripped_bib, n_remaining_event_fab)."""
    rec = json.loads(fp.read_text())

    # Fab entries in sources_all → strip.
    src_before = rec.get("sources_all") or []
    src_after = [s for s in src_before if not _is_fab(s)]
    n_stripped = len(src_before) - len(src_after)

    # Fab entries in cited_events / pledges_and_announcements → leave;
    # report so the human can replace.
    n_event_fab = 0
    for fld in ("cited_events", "pledges_and_announcements"):
        for ev in rec.get(fld) or []:
            if _is_fab(ev):
                n_event_fab += 1

    if n_stripped == 0:
        return (0, n_event_fab)

    if dry_run:
        return (n_stripped, n_event_fab)

    rec["sources_all"] = src_after
    tmp = fp.with_suffix(fp.suffix + ".tmp")
    tmp.write_text(json.dumps(rec, indent=2))
    os.replace(tmp, fp)
    return (n_stripped, n_event_fab)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--subject")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.all:
        files = sorted(DATA_DIR.glob("*.v3.json"))
    else:
        files = [DATA_DIR / f"{args.subject}.v3.json"]

    grand_stripped = 0
    grand_event_fab = 0
    touched: list[str] = []
    blocked: list[str] = []

    for fp in files:
        sid = fp.name.replace(".v3.json", "")
        n_strip, n_event = strip_one(fp, dry_run=args.dry_run)
        if n_strip:
            touched.append(f"{sid}: -{n_strip} bib")
            grand_stripped += n_strip
        if n_event:
            blocked.append(f"{sid}: {n_event} dollar-event still flagged (manual replace)")
            grand_event_fab += n_event

    print(f"Bibliography fab entries stripped: {grand_stripped}")
    for line in touched:
        print(f"  {line}")
    if blocked:
        print(f"\nManual replacement still needed for {grand_event_fab} dollar-bearing events:")
        for line in blocked:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
