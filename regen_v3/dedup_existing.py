"""Retroactively dedupe existing v3 records using the improved key.

Catches cross-role duplicates that slipped through earlier merges (when
the dedupe key only used (year, role, amount_bucket) but not recipient).
Codex flagged these:
  * Bezos $10B Earth Fund counted twice (direct_gift + grant_out)
  * Buffett 1.5M-share counted twice (transfer_in + direct_gift)
  * Melinda $1B counted three times across roles

Algorithm: for each subject, walk cited_events + pledges_and_announcements,
group by (year, recipient_normalized, amount_bucket). If a group has
multiple entries, keep the one with highest confidence (then prefer
manual provenance over regen_v3, then prefer earlier index).

Manual entries are still NEVER displaced — only regen_v3 entries.
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

from regen_v3.merge import _amount_bucket, _normalize_recipient, _is_protected, _confidence_rank  # noqa: E402


def _crosskey(entry: dict) -> tuple | None:
    """Cross-role dedupe key: (year, recipient_norm, amount_bucket).
    Returns None if entry is too generic to dedupe by."""
    year = entry.get("year") if isinstance(entry.get("year"), int) else None
    if year is None:
        return None
    recipient = _normalize_recipient(entry.get("recipient"))
    if recipient is None:
        return None
    bucket = _amount_bucket(entry.get("amount_usd"))
    if bucket is None:
        return None
    return (year, recipient, bucket)


def _generic_crosskey(entry: dict) -> tuple | None:
    """Looser cross-role key for events with generic/empty recipient.
    Same gift extracted twice with `unspecified` recipient under different
    roles (e.g. Lukas Walton's $3B Builders Vision total) — collide them.
    Requires year + amount; ignores recipient.
    """
    year = entry.get("year") if isinstance(entry.get("year"), int) else None
    if year is None:
        return None
    recipient = _normalize_recipient(entry.get("recipient"))
    if recipient is not None:
        return None  # only fires when recipient is generic
    bucket = _amount_bucket(entry.get("amount_usd"))
    if bucket is None:
        return None
    return ("__generic__", year, bucket)


def dedupe_record(rec: dict) -> tuple[int, list[str]]:
    """Mutate rec in place. Returns (n_removed, removed_descriptions)."""
    removed_total = 0
    removed_log: list[str] = []

    for fld in ("cited_events", "pledges_and_announcements"):
        entries = rec.get(fld) or []
        # Group by both keys: strict cross-role (with recipient) AND generic
        # cross-role (when recipient is generic/missing).
        groups: dict[tuple, list[int]] = {}
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                continue
            k = _crosskey(e)
            if k is not None:
                groups.setdefault(k, []).append(i)
            gk = _generic_crosskey(e)
            if gk is not None:
                groups.setdefault(gk, []).append(i)

        # Generic-recipient TOLERANCE pass: catch the case where two events
        # have the same year, generic recipient, and amounts within ±5%
        # (e.g. Scott 2025 $7.0B + $7.1B were the same gift quoted with
        # different rounding across two articles). The strict bucket check
        # above misses these because round(7e9/1e6)=7000 vs round(7.1e9/1e6)=7100.
        for i, ei in enumerate(entries):
            if not isinstance(ei, dict):
                continue
            if _normalize_recipient(ei.get("recipient")) is not None:
                continue  # only fire for generic recipients
            yi = ei.get("year") if isinstance(ei.get("year"), int) else None
            ai = ei.get("amount_usd")
            if yi is None or not isinstance(ai, (int, float)) or ai <= 0:
                continue
            for j in range(i + 1, len(entries)):
                ej = entries[j]
                if not isinstance(ej, dict):
                    continue
                if _normalize_recipient(ej.get("recipient")) is not None:
                    continue
                yj = ej.get("year") if isinstance(ej.get("year"), int) else None
                aj = ej.get("amount_usd")
                if yi != yj or not isinstance(aj, (int, float)) or aj <= 0:
                    continue
                if abs(ai - aj) <= 0.05 * max(ai, aj):
                    # Treat as collision via shared synthetic key
                    key = ("__tol__", yi, round(min(ai, aj) / 1e8))
                    groups.setdefault(key, []).extend([i, j])

        # Find groups with collisions
        to_remove: set[int] = set()
        for k, idxs in groups.items():
            if len(idxs) <= 1:
                continue
            # Pick winner: manual first, then highest confidence, then earliest
            def rank(i: int) -> tuple:
                e = entries[i]
                is_manual = _is_protected(e)
                conf = _confidence_rank(e)
                return (-int(is_manual), -conf, i)
            idxs_sorted = sorted(idxs, key=rank)
            winner = idxs_sorted[0]
            losers = idxs_sorted[1:]
            for li in losers:
                # Refuse to drop a manual entry (defense in depth)
                if _is_protected(entries[li]):
                    continue
                to_remove.add(li)
                e = entries[li]
                removed_log.append(
                    f'{fld}[{li}] {e.get("event_role","?")} ${(e.get("amount_usd") or 0)/1e6:.0f}M '
                    f'{e.get("year")} {e.get("recipient","")[:40]} -> kept [{winner}]'
                )

        if to_remove:
            rec[fld] = [e for i, e in enumerate(entries) if i not in to_remove]
            removed_total += len(to_remove)

    return (removed_total, removed_log)


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
        n, log = dedupe_record(rec)
        if n == 0:
            continue
        if not args.dry_run:
            tmp = fp.with_suffix(fp.suffix + ".tmp")
            tmp.write_text(json.dumps(rec, indent=2))
            os.replace(tmp, fp)
        touched.append(f"{sid}: -{n}")
        grand += n
        if args.dry_run or args.subject:
            for line in log[:5]:
                print(f"  {line}")

    print(f"\nTotal cross-role duplicates removed: {grand}")
    for line in touched:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
