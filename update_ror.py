#!/usr/bin/env python3
"""
Update the right_of_reply section of a per-subject v3 JSON when a response
comes in (or after the 1-week deadline passes with no response).

Usage:
    # Record a response
    python3 update_ror.py elon_musk --response "Our client has no comment on the ranking." \
                                    --received 2026-05-02

    # Record "no response" after deadline
    python3 update_ror.py larry_page --no-response --received 2026-05-01

    # Mark outreach as sent but awaiting response
    python3 update_ror.py thomas_peterffy --sent --scheduled 2026-05-01

After updating, re-run aggregate_v3.py so docs/profiles/<id>.json reflects
the new state.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from datetime import date

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subject_id", help="slug of subject (e.g., 'elon_musk')")
    ap.add_argument("--response", help="Subject's verbatim response text")
    ap.add_argument("--no-response", action="store_true", help="Mark as no response received")
    ap.add_argument("--sent", action="store_true", help="Mark outreach as sent")
    ap.add_argument("--scheduled", help="ISO date outreach was/will be sent")
    ap.add_argument("--received", help="ISO date response (or no-response deadline)")
    args = ap.parse_args()

    fp = DATA_DIR / f"{args.subject_id}.v3.json"
    if not fp.exists():
        print(f"ERROR: {fp} not found", file=sys.stderr)
        sys.exit(1)

    with fp.open() as f:
        rec = json.load(f)

    ror = rec.setdefault("right_of_reply", {})

    if args.response:
        ror["status"] = "response_received"
        ror["response_text"] = args.response
        ror["response_received_date"] = args.received or date.today().isoformat()
    elif args.no_response:
        ror["status"] = "no_response_by_deadline"
        ror["response_deadline"] = args.received or date.today().isoformat()
    elif args.sent:
        ror["status"] = "outreach_sent_awaiting_response"
        ror["scheduled_outreach_date"] = args.scheduled or date.today().isoformat()
    else:
        print("ERROR: specify --response, --no-response, or --sent", file=sys.stderr)
        sys.exit(1)

    with fp.open("w") as f:
        json.dump(rec, f, indent=2, default=str)

    print(f"Updated {fp}")
    print(f"  status: {ror['status']}")
    if ror.get('response_text'):
        print(f"  response: {ror['response_text'][:80]}{'…' if len(ror['response_text'])>80 else ''}")
    print("\nNext: run `python3 aggregate_v3.py` to refresh docs/profiles/")


if __name__ == "__main__":
    main()
