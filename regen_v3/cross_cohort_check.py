"""Cross-cohort sanity check for v3 records.

Finds events likely misattributed across subjects. Read-only on data/*.v3.json.

Checks:
  1. same_event_multiple_subjects — same (year, recipient_norm, amount_bucket)
     under 2+ subjects.
  2. foundation_in_other_subject — subject A's foundation appears as a
     `recipient` in subject B's cited_events.
  3. shared_url_conflict — same source_url under 2+ subjects with different
     amounts or recipients.

Usage:
    python3 -m regen_v3.cross_cohort_check [--json] [--severity {low,medium,high}]

Exits non-zero if any high-severity collision found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from regen_v3.merge import _amount_bucket, _normalize_recipient  # noqa: E402

# Family co-attribution is sometimes legitimate (Walton sibs, Koch bros,
# Mars sibs, Lauder bros, Brin/Page co-foundation, Kravis spouse). When a
# match is between two subjects in the same group, severity drops to 'low'.
FAMILY_GROUPS: list[set[str]] = [
    {"alice_walton", "jim_walton", "rob_walton", "lukas_walton"},
    {"charles_koch", "julia_koch"},
    {"jacqueline_mars", "john_mars"},
    {"larry_page", "sergey_brin"},
    {"leonard_lauder", "ronald_lauder"},
]

OBSERVABLE_ROLES = {
    "grant_out", "direct_gift", "transfer_in",
    "political", "private_investment", "corporate_gift",
}

# Recipient strings that are too generic to imply a single shared gift.
# DAF sponsors are common co-recipients across many subjects — flagging
# their co-occurrence is noise, not signal.
_GENERIC_RECIPIENT_RE = re.compile(
    r"\b(various|unspecified|multiple|unknown|n/a)\b"
    r"|donor[\s-]?advised"
    r"|fidelity (investments )?charitable"
    r"|schwab charitable"
    r"|vanguard charitable"
    r"|national philanthropic trust"
    r"|silicon valley community foundation"
    r"|jewish communal fund",
    re.IGNORECASE,
)


def _is_family_pair(a: str, b: str) -> bool:
    return any(a in g and b in g for g in FAMILY_GROUPS)


def _is_generic_recipient(name: str | None) -> bool:
    if not isinstance(name, str) or not name.strip():
        return True
    return bool(_GENERIC_RECIPIENT_RE.search(name))


def _load_records() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for p in sorted(DATA_DIR.glob("*.v3.json")):
        try:
            out.append((p.name.replace(".v3.json", ""), json.loads(p.read_text())))
        except json.JSONDecodeError:
            continue
    return out


def _iter_observable_events(record: dict):
    for ev in record.get("cited_events") or []:
        if isinstance(ev, dict) and ev.get("event_role") in OBSERVABLE_ROLES:
            yield ev


def _foundation_names(record: dict) -> list[str]:
    dv = record.get("detected_vehicles")
    if not isinstance(dv, dict):
        return []
    fa = dv.get("foundations_active") or []
    return [f["name"] for f in fa
            if isinstance(f, dict) and isinstance(f.get("name"), str)]


def _foundation_recipient_match(foundation: str, recipient: str) -> bool:
    """True if recipient contains every distinctive foundation token."""
    f_norm = _normalize_recipient(foundation)
    r_norm = _normalize_recipient(recipient)
    if not f_norm or not r_norm:
        return False
    return set(f_norm.split()).issubset(set(r_norm.split()))


def _ev_ref(subject: str, ev: dict) -> dict:
    return {
        "subject": subject,
        "event_id": ev.get("event_id"),
        "year": ev.get("year"),
        "recipient": ev.get("recipient"),
        "amount_usd": ev.get("amount_usd"),
        "source_url": ev.get("source_url"),
        "event_role": ev.get("event_role"),
    }


def _check_same_event(records: list[tuple[str, dict]]) -> list[dict]:
    bucket: dict[tuple[int, str, int], list[tuple[str, dict]]] = {}
    for subj, rec in records:
        for ev in _iter_observable_events(rec):
            year, amt = ev.get("year"), _amount_bucket(ev.get("amount_usd"))
            recip = ev.get("recipient")
            if not isinstance(year, int) or amt is None:
                continue
            if _is_generic_recipient(recip):
                continue
            r_norm = _normalize_recipient(recip)
            if not r_norm:
                continue
            bucket.setdefault((year, r_norm, amt), []).append((subj, ev))

    out: list[dict] = []
    for (year, r_norm, amt), hits in bucket.items():
        subjects = sorted({s for s, _ in hits})
        if len(subjects) < 2:
            continue
        sev = "low" if len(subjects) == 2 and _is_family_pair(*subjects) else "high"
        out.append({
            "type": "same_event_multiple_subjects",
            "severity": sev, "year": year,
            "recipient": hits[0][1].get("recipient"),
            "recipient_norm": r_norm, "amount_bucket_musd": amt,
            "subjects": subjects,
            "events": [_ev_ref(s, e) for s, e in hits],
        })
    return out


def _check_foundation_in_other(records: list[tuple[str, dict]]) -> list[dict]:
    foundations: list[tuple[str, str]] = []
    for subj, rec in records:
        for fname in _foundation_names(rec):
            if _is_generic_recipient(fname):
                continue
            if _normalize_recipient(fname):
                foundations.append((subj, fname))

    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for subj_b, rec in records:
        for ev in _iter_observable_events(rec):
            recip = ev.get("recipient")
            if not isinstance(recip, str) or _is_generic_recipient(recip):
                continue
            for subj_a, fname in foundations:
                if subj_a == subj_b:
                    continue
                if _foundation_recipient_match(fname, recip):
                    grouped.setdefault((subj_a, fname, subj_b), []).append(ev)

    out: list[dict] = []
    for (subj_a, fname, subj_b), evs in grouped.items():
        sev = "low" if _is_family_pair(subj_a, subj_b) else "high"
        out.append({
            "type": "foundation_in_other_subject",
            "severity": sev, "foundation": fname,
            "foundation_owner": subj_a,
            "subjects": sorted([subj_a, subj_b]),
            "events": [_ev_ref(subj_b, e) for e in evs],
        })
    return out


def _check_shared_url(records: list[tuple[str, dict]]) -> list[dict]:
    by_url: dict[str, list[tuple[str, dict]]] = {}
    for subj, rec in records:
        for ev in _iter_observable_events(rec):
            url = ev.get("source_url")
            if isinstance(url, str) and url.strip():
                by_url.setdefault(url, []).append((subj, ev))

    out: list[dict] = []
    for url, hits in by_url.items():
        subjects = sorted({s for s, _ in hits})
        if len(subjects) < 2:
            continue
        amts = {_amount_bucket(e.get("amount_usd")) for _, e in hits} - {None}
        recs = {_normalize_recipient(e.get("recipient")) for _, e in hits} - {None}
        if len(amts) <= 1 and len(recs) <= 1:
            continue  # consistent — likely a legit co-cited article
        sev = "low" if len(subjects) == 2 and _is_family_pair(*subjects) else "high"
        out.append({
            "type": "shared_url_conflict",
            "severity": sev, "source_url": url, "subjects": subjects,
            "distinct_amount_buckets": sorted(amts),
            "distinct_recipients": sorted(recs),
            "events": [_ev_ref(s, e) for s, e in hits],
        })
    return out


def detect_cross_cohort_collisions(records: list[dict]) -> list[dict]:
    """Public API: list of v3 record dicts -> flagged collisions."""
    indexed: list[tuple[str, dict]] = []
    for rec in records:
        name = (rec.get("person") or {}).get("name_display") or "unknown"
        indexed.append((name.lower().replace(" ", "_"), rec))
    return (_check_same_event(indexed)
            + _check_foundation_in_other(indexed)
            + _check_shared_url(indexed))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_SEV_RANK = {"high": 2, "medium": 1, "low": 0}


def _format_line(c: dict) -> str:
    t = c.get("type", "?")
    if t == "same_event_multiple_subjects":
        detail = f"{c.get('year')} {c.get('recipient')!r} ~${c.get('amount_bucket_musd')}M"
    elif t == "foundation_in_other_subject":
        detail = (f"{c.get('foundation_owner')}'s {c.get('foundation')!r} "
                  "appears in another subject's recipient")
    elif t == "shared_url_conflict":
        detail = (f"{c.get('source_url')} "
                  f"amounts={c.get('distinct_amount_buckets')} "
                  f"recipients={len(c.get('distinct_recipients') or [])}")
    else:
        detail = "?"
    subjs = c.get("subjects") or []
    return f"[{c.get('severity','?')}] {t}: {detail} ({len(subjs)} subjects: {','.join(subjs)})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="regen_v3.cross_cohort_check")
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    ap.add_argument("--severity", choices=["low", "medium", "high"],
                    help="minimum severity to report")
    args = ap.parse_args(argv)

    collisions = detect_cross_cohort_collisions([r for _, r in _load_records()])
    min_rank = _SEV_RANK.get(args.severity, 0) if args.severity else 0
    filtered = [c for c in collisions
                if _SEV_RANK.get(c.get("severity"), 0) >= min_rank]
    filtered.sort(key=lambda c: (
        -_SEV_RANK.get(c.get("severity"), 0),
        c.get("type", ""),
        ",".join(c.get("subjects") or []),
    ))

    if args.json:
        json.dump(filtered, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        by_type: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for c in filtered:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
            by_sev[c["severity"]] = by_sev.get(c["severity"], 0) + 1
            print(_format_line(c))
        print(f"\n# total collisions: {len(filtered)}  "
              f"by_type={by_type}  by_severity={by_sev}")

    return 1 if any(c.get("severity") == "high" for c in filtered) else 0


if __name__ == "__main__":
    raise SystemExit(main())
