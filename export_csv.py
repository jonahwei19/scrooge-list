#!/usr/bin/env python3
"""
Export the Tier A cohort to CSV for journalists and researchers.

Reads docs/scrooge_latest_v3.json and writes docs/scrooge_latest_v3.csv
with one row per subject and the key fields flattened.

Run: python3 export_csv.py
"""

from __future__ import annotations
import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
IN_JSON = HERE / "docs" / "scrooge_latest_v3.json"
OUT_CSV = HERE / "docs" / "scrooge_latest_v3.csv"

FIELDS = [
    ("id", "id"),
    ("name_display", "name"),
    ("country", "country"),
    ("wealth_source", "wealth_source"),
    ("years_as_billionaire_approx", "years_as_billionaire"),
    ("net_worth_best_usd_b", "net_worth_best_usd_billions"),
    ("net_worth_as_of", "net_worth_as_of"),
    ("liquidity_estimate_pct", "liquidity_pct"),
    ("tier", "tier"),
    ("tier_rank", "tier_rank"),
    ("observable_usd", "observable_giving_usd"),
    ("expected_usd", "expected_giving_usd"),
    ("hidden_upper_usd", "hidden_upper_usd"),
    ("ratio_observable_to_expected", "obs_vs_capacity_ratio"),
    ("ratio_observable_to_nw", "obs_vs_nw_ratio"),
    ("pledge_signed", "giving_pledge_signed"),
    ("sources_count", "sources_count"),
    ("event_count", "cited_event_count"),
    ("right_of_reply_status", "right_of_reply_status"),
]


def main():
    data = json.load(IN_JSON.open())
    rows = data.get("billionaires", [])

    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        # header
        w.writerow([hdr for _, hdr in FIELDS] + ["red_flags", "foundations_active", "llcs", "profile_url"])
        for row in rows:
            vehicles = row.get("detected_vehicles", {}) or {}
            red_flags = "; ".join(row.get("red_flags", []) or [])
            foundations = "; ".join(vehicles.get("foundations_active_names", []) or [])
            llcs = str(vehicles.get("llcs_philanthropic_count", 0) or 0)
            profile_url = f"profile.html?id={row.get('id')}"
            out = []
            for src_key, _ in FIELDS:
                v = row.get(src_key)
                if isinstance(v, (list, tuple)):
                    v = "; ".join(str(x) for x in v)
                out.append(v if v is not None else "")
            out += [red_flags, foundations, llcs, profile_url]
            w.writerow(out)

    print(f"wrote {OUT_CSV} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
