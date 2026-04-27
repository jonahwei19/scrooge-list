"""Retroactively re-label mis-categorized events using extract.py guards.

Codex audit (round 4) found:
  * pledge stored as grant_out
  * political (PAC/FEC) stored as direct_gift / corporate_gift
  * direct gifts to own foundation stored as transfer_in / direct_gift inconsistently

Applies the same `_maybe_relabel` rules from regen_v3/extract.py to the
existing data records (which were merged before the guards were added).

Manual entries are NEVER touched. Only regen_v3 events.
Re-labeled events also need to be re-routed: pledge → pledges_and_announcements;
political → cited_events (already there); etc.
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

from regen_v3.extract import _maybe_relabel  # noqa: E402
from regen_v3.merge import _is_protected, _route_for  # noqa: E402


def relabel_record(rec: dict) -> tuple[int, list[str]]:
    """Mutate rec in place. Returns (n_relabeled, log_lines)."""
    log: list[str] = []
    n = 0

    # Walk both lists, re-label, then re-route to correct list if needed.
    new_cited: list = []
    new_pledges: list = []

    src_cited = rec.get("cited_events") or []
    src_pledges = rec.get("pledges_and_announcements") or []

    for fld_name, src in (("cited_events", src_cited), ("pledges_and_announcements", src_pledges)):
        for ev in src:
            if not isinstance(ev, dict):
                (new_cited if fld_name == "cited_events" else new_pledges).append(ev)
                continue
            if _is_protected(ev):
                (new_cited if fld_name == "cited_events" else new_pledges).append(ev)
                continue
            old_role = ev.get("event_role")
            ev_copy = dict(ev)  # _maybe_relabel mutates in place
            _maybe_relabel(ev_copy)
            new_role = ev_copy.get("event_role")
            if new_role != old_role:
                n += 1
                log.append(
                    f"  {ev.get('event_id','?')}: {old_role} -> {new_role} "
                    f"(${(ev.get('amount_usd') or 0)/1e6:.0f}M, {ev.get('year')}, "
                    f"{ev.get('recipient','')[:40]})"
                )
            # Route by new role
            route = _route_for(new_role)
            if route == "pledges_and_announcements":
                new_pledges.append(ev_copy)
            elif route == "sources_all":
                # reference_only events shouldn't have been events in the first place;
                # leave them where they are to avoid losing data
                (new_cited if fld_name == "cited_events" else new_pledges).append(ev_copy)
            else:
                new_cited.append(ev_copy)

    rec["cited_events"] = new_cited
    rec["pledges_and_announcements"] = new_pledges
    return (n, log)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--subject")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    files = sorted(DATA_DIR.glob("*.v3.json")) if args.all else [DATA_DIR / f"{args.subject}.v3.json"]
    grand = 0
    touched: list[str] = []
    for fp in files:
        sid = fp.name.replace(".v3.json", "")
        rec = json.loads(fp.read_text())
        n, log = relabel_record(rec)
        if n == 0:
            continue
        if not args.dry_run:
            tmp = fp.with_suffix(fp.suffix + ".tmp")
            tmp.write_text(json.dumps(rec, indent=2))
            os.replace(tmp, fp)
        touched.append(f"{sid}: {n} relabeled")
        grand += n
        if args.dry_run or args.subject:
            for line in log[:8]:
                print(line)

    print(f"\nTotal events re-labeled: {grand}")
    for line in touched:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
