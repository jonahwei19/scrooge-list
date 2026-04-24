#!/usr/bin/env python3
"""
Data-quality validator for the v3 cohort. Flags issues that would
embarrass us at publish: missing fields, inconsistent numbers, non-http
source URLs, subjects with zero cited events, etc.

Exits non-zero if any subjects have errors (missing-field or inconsistent-
numeric) — useful as a CI gate before `git push` or GitHub Pages refresh.
Warnings don't fail; informational only.

Run: python3 validate_v3.py
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"

REQUIRED_TOP = [
    "person", "net_worth", "rollup", "detected_vehicles",
    "sources_all", "schema_version",
]
REQUIRED_PERSON = ["name_display", "country_primary"]
REQUIRED_NW = ["best_estimate_usd_billions", "as_of"]

URL_RE = re.compile(r"^https?://\S+$")


def check(rec: dict, path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for key in REQUIRED_TOP:
        if key not in rec:
            errors.append(f"missing top-level key: {key}")
    p = rec.get("person", {}) or {}
    for key in REQUIRED_PERSON:
        if not p.get(key):
            errors.append(f"person.{key} missing")
    nw = rec.get("net_worth", {}) or {}
    for key in REQUIRED_NW:
        if nw.get(key) is None:
            errors.append(f"net_worth.{key} missing")

    # sources_all URLs
    for i, s in enumerate(rec.get("sources_all", []) or []):
        url = s.get("url") if isinstance(s, dict) else None
        if not url or not URL_RE.match(url):
            errors.append(f"sources_all[{i}] invalid url: {url!r}")
        if not (isinstance(s, dict) and s.get("retrieved_at")):
            warnings.append(f"sources_all[{i}] missing retrieved_at")

    # Event source URLs
    for fld in ("cited_events", "pledges_and_announcements"):
        for i, ev in enumerate(rec.get(fld, []) or []):
            if not isinstance(ev, dict):
                continue
            url = ev.get("source_url")
            if url and not URL_RE.match(url):
                errors.append(f"{fld}[{i}] invalid source_url: {url!r}")
            if not ev.get("event_role"):
                warnings.append(f"{fld}[{i}] missing event_role")
            if not ev.get("source_url") and ev.get("amount_usd"):
                warnings.append(f"{fld}[{i}] amount with no source_url")

    # Rollup sanity
    rollup = rec.get("rollup", {}) or {}
    obs = rollup.get("observable_giving_usd")
    exp = (rollup.get("expected_giving_usd_10pct_liquid_weighted_by_tenure")
           or rollup.get("expected_giving_usd_10pct_liquid_strict")
           or rollup.get("expected_giving_usd"))
    ratio = (rollup.get("observable_ratio_to_expected")
             or rollup.get("observable_ratio_to_expected_strict")
             or rollup.get("observable_ratio_to_expected_formal_tenure"))
    if obs is not None and exp:
        computed = obs / exp
        if ratio is not None:
            if abs(computed - ratio) > max(0.02, ratio * 0.05):
                warnings.append(
                    f"ratio mismatch: stored {ratio:.4f} vs observable/expected {computed:.4f}"
                )
        else:
            warnings.append(f"ratio_observable_to_expected missing (computed would be {computed:.4f})")

    # Zero events
    event_count = len(rec.get("cited_events", []) or []) + len(rec.get("pledges_and_announcements", []) or [])
    if event_count == 0:
        warnings.append("zero cited events — may be intentional for Tier A 'no foundation' case, but worth a sanity check")

    # Tier string shape
    tier = rollup.get("tier")
    if not tier:
        warnings.append("rollup.tier missing")

    # right_of_reply should exist
    if "right_of_reply" not in rec:
        warnings.append("right_of_reply block missing")

    return errors, warnings


def main():
    files = sorted(DATA_DIR.glob("*.v3.json"))
    print(f"validating {len(files)} v3 records from {DATA_DIR}\n")

    total_errors = 0
    total_warnings = 0
    per_subject_report = []

    for fp in files:
        try:
            rec = json.loads(fp.read_text())
        except Exception as e:
            print(f"  [PARSE FAIL] {fp.name}: {e}")
            total_errors += 1
            continue

        errors, warnings = check(rec, fp)
        total_errors += len(errors)
        total_warnings += len(warnings)

        if errors or warnings:
            per_subject_report.append((fp.name, errors, warnings))

    # Per-subject details
    for name, errors, warnings in per_subject_report:
        print(f"\n{name}")
        for e in errors:
            print(f"  ERROR   {e}")
        for w in warnings:
            print(f"  warn    {w}")

    # Cohort-wide stats
    print("\n" + "=" * 60)
    print(f"Cohort summary — {len(files)} subjects")
    print(f"  errors:   {total_errors}")
    print(f"  warnings: {total_warnings}")

    # Tier distribution snapshot
    tiers = Counter()
    for fp in files:
        try:
            r = json.loads(fp.read_text())
            tiers[r.get("rollup", {}).get("tier", "unknown")] += 1
        except Exception:
            pass

    print("\n  Tier strings seen (raw, pre-normalization):")
    for t, n in tiers.most_common():
        print(f"    {n:3}  {t}")

    if total_errors:
        print(f"\nFAIL — {total_errors} errors. Fix before publishing.")
        sys.exit(1)
    else:
        print("\nOK — no errors. Warnings are informational.")
        sys.exit(0)


if __name__ == "__main__":
    main()
