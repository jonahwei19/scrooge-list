"""Run recipient_verify on existing v3 records without a full cohort re-merge.

Codex round 5 found that recipient_verify code was wired into cli.py, but
the pipeline hadn't been re-run end-to-end since the wire-up — so the
`recipient_verified` / `recipient_filing_url` fields appear in zero data
records. This tool annotates the existing records in place, much faster
than the 5+hr full cohort.

Usage:
    python3 -m regen_v3.annotate_existing --all
    python3 -m regen_v3.annotate_existing --subject henry_kravis
    python3 -m regen_v3.annotate_existing --all --dry-run
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

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from regen_v3 import recipient_verify as rv  # noqa: E402


def annotate_one(fp: Path, *, dry_run: bool, refresh: bool) -> tuple[int, int, int]:
    """Returns (annotated, verified, unverifiable) counts for the subject."""
    rec = json.loads(fp.read_text())
    rv.annotate_record(rec, refresh=refresh)

    annotated = 0
    verified = 0
    unverifiable = 0
    for fld in ("cited_events", "pledges_and_announcements"):
        for ev in rec.get(fld) or []:
            if not isinstance(ev, dict):
                continue
            v = ev.get("recipient_verified")
            if v is not None:
                annotated += 1
                if v == "true":
                    verified += 1
                elif v == "unverifiable":
                    unverifiable += 1

    if not dry_run and annotated > 0:
        tmp = fp.with_suffix(fp.suffix + ".tmp")
        tmp.write_text(json.dumps(rec, indent=2))
        os.replace(tmp, fp)

    return (annotated, verified, unverifiable)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--subject")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true",
                    help="Bypass recipient_verify cache (re-fetch all 990s)")
    args = ap.parse_args(argv)

    files = sorted(DATA_DIR.glob("*.v3.json")) if args.all else [DATA_DIR / f"{args.subject}.v3.json"]
    g_annotated = g_verified = g_unver = 0
    for fp in files:
        sid = fp.name.replace(".v3.json", "")
        try:
            a, v, u = annotate_one(fp, dry_run=args.dry_run, refresh=args.refresh)
        except Exception as e:
            print(f"  [{sid}-skip] {type(e).__name__}: {str(e)[:80]}")
            continue
        if a == 0:
            continue
        g_annotated += a
        g_verified += v
        g_unver += u
        print(f"  {sid}: {a} annotated ({v} verified, {u} unverifiable, {a-v-u} false)")

    print(f"\nCohort: {g_annotated} events annotated, {g_verified} verified, {g_unver} unverifiable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
