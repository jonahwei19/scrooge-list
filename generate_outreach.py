#!/usr/bin/env python3
"""
Generate pre-publication right-of-reply emails for every Tier A and Tier B
subject. One email per subject, saved to outreach/ as plain-text .txt files.

Each email:
- Identifies the source of the claim (this list, with methodology URL)
- Cites the specific numbers we plan to publish
- Documents our data chain per number
- Lists red flags with evidence
- Gives a one-week response window
- Notes that responses are published verbatim (or "no response" is published)

Run: python3 generate_outreach.py [--deadline-days 7]
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from datetime import date, timedelta

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
OUT_DIR = HERE / "outreach"
AGG_JSON = HERE / "docs" / "scrooge_latest_v3.json"

SCROOGE_URL = "https://jonahwei19.github.io/scrooge-list/"
METHODOLOGY_URL = SCROOGE_URL + "methodology.html"


def fmt_usd(usd):
    if usd is None:
        return "—"
    b = usd / 1e9
    if abs(b) >= 1:
        return f"${b:,.2f}B" if b < 10 else f"${b:,.1f}B"
    return f"${usd/1e6:,.0f}M"


def fmt_nw(b):
    if b is None:
        return "—"
    return f"${b:,.0f}B" if b >= 100 else f"${b:,.1f}B"


def fmt_ratio(r):
    if r is None:
        return "—"
    if r >= 1:
        return f"{r:,.2f}× the benchmark"
    return f"{r*100:,.1f}% of the benchmark"


def load_v3_records() -> list[dict]:
    recs = []
    for fp in sorted(DATA_DIR.glob("*.v3.json")):
        with fp.open() as f:
            recs.append(json.load(f))
    return recs


def subject_slug(rec: dict) -> str:
    p = rec.get("person", {})
    return p.get("name_display", "unknown").lower().replace(" ", "_")


# Press / foundation contacts discovered by the press-contact agent.
# Loaded once at module init. Subjects with no entry fall back to placeholder.
_CONTACTS_FILE = HERE / "outreach" / "contacts.json"
_CONTACTS: dict = {}
if _CONTACTS_FILE.exists():
    try:
        _CONTACTS = json.loads(_CONTACTS_FILE.read_text())
    except Exception:
        _CONTACTS = {}


def contact_for(sid: str, name: str) -> tuple[str, str]:
    """Return (To-line, contact-note) for a subject. Falls back to placeholder
    if no entry in contacts.json."""
    c = _CONTACTS.get(sid) or {}
    primary = c.get("primary_contact")
    conf = c.get("confidence", "unknown")
    role = c.get("primary_role", "")
    if not primary:
        return (
            f"To: [press/foundation contact for {name} — UNKNOWN, see contacts.json]",
            "Contact: not yet discovered. Confidence: unknown.",
        )
    if primary.startswith("http"):
        # It's a contact form, not an email.
        return (
            f"To: [submit via {primary}]",
            f"Contact: {role or 'web form'} (confidence: {conf}).",
        )
    return (
        f"To: {primary}",
        f"Contact: {role or 'press inbox'} (confidence: {conf}).",
    )


def tier_of(rec: dict) -> str:
    """Mirror of normalize_tier in aggregate_v3.py — keep in sync."""
    import re
    raw = (rec.get("rollup", {}) or {}).get("tier", "")
    r = str(raw).lower()
    m = re.search(r"\(tier\s*([abc]\+?)\b", r)
    bracket = m.group(1) if m else None
    on_track_kw = any(k in r for k in (
        "on_track", "on track", "model_pledger", "doing_it", "doing it",
        "ceiling", "high giving", "probably high", "ceiling_reference", "a+",
    ))
    if bracket == "a+":
        return "ON_TRACK"
    if bracket == "a":
        return "ON_TRACK" if on_track_kw else "A_VERIFIED_LOW"
    if bracket == "b":
        return "B_PROBABLY_LOW"
    if bracket == "c":
        return "ON_TRACK" if on_track_kw else "C_OPAQUE"
    # no explicit bracket — keyword fallbacks
    if on_track_kw:
        return "ON_TRACK"
    if any(k in r for k in ("probably_low", "probably low", "probably_moderate",
                             "probably moderate", "probably_generous")):
        return "B_PROBABLY_LOW"
    if "opaque" in r:
        return "C_OPAQUE"
    if "verified_low" in r or "verified low" in r:
        return "A_VERIFIED_LOW"
    return "UNKNOWN"


def build_email(rec: dict, deadline: date) -> str:
    p = rec.get("person", {})
    nw = rec.get("net_worth", {})
    rollup = rec.get("rollup", {})
    vehicles = rec.get("detected_vehicles", {})
    flags = rec.get("red_flags", [])
    pol = rec.get("political_giving", {})

    name = p.get("name_display", "[Subject]")
    tier = tier_of(rec)
    sid = subject_slug(rec)
    to_line, contact_note = contact_for(sid, name)

    # body composition
    lines = []
    lines.append(f"Subject: Pre-publication inquiry — your inclusion in The Scrooge List")
    lines.append("")
    lines.append(to_line)
    lines.append(f"From: [editor]")
    lines.append(f"Date: {date.today().isoformat()}")
    lines.append(f"Response deadline: {deadline.isoformat()}")
    lines.append(f"# {contact_note}")
    lines.append("")
    lines.append("=" * 78)
    lines.append("")
    lines.append(f"Dear team at [entity representing {name}],")
    lines.append("")
    lines.append(textwrap.fill(
        f"I am writing in advance of publishing an estimate of {name}'s observable charitable giving on The Scrooge List, a research project at {SCROOGE_URL}. Our methodology is documented at {METHODOLOGY_URL}.",
        width=78))
    lines.append("")
    lines.append("We want to be fair and accurate. Before we publish, we are sending this note to every named subject in Tier A and Tier B so you can review the specific numbers we intend to use, and — if appropriate — respond.")
    lines.append("")
    lines.append("--- WHAT WE INTEND TO PUBLISH ---")
    lines.append("")
    lines.append(f"  Subject:            {name}")
    lines.append(f"  Tier:               {tier}")
    lines.append(f"  Net worth:          {fmt_nw(nw.get('best_estimate_usd_billions'))}  "
                 f"(range {nw.get('range_usd_billions','—')}; as of {nw.get('as_of','—')})")
    lines.append(f"  Observable giving:  {fmt_usd(rollup.get('observable_giving_usd'))}")
    lines.append(f"  Capacity benchmark: {fmt_usd(rollup.get('expected_giving_usd_10pct_liquid_weighted_by_tenure') or rollup.get('expected_giving_usd'))}")
    lines.append(f"  Observable ÷ Cap:   {fmt_ratio(rollup.get('observable_ratio_to_expected'))}")
    lines.append("")

    # Observable components
    lines.append("--- OUR DATA CHAIN FOR THE OBSERVABLE FIGURE ---")
    lines.append("")
    events = rec.get("cited_events", [])
    if events:
        for ev in events:
            role = ev.get("event_role", "")
            if role not in ("grant_out", "direct_gift"):
                continue
            when = ev.get("date") or ev.get("year") or ""
            amt = fmt_usd(ev.get("amount_usd"))
            donor = ev.get("donor_entity", "")
            recip = ev.get("recipient", "") or "—"
            src = ev.get("source_url", "—")
            lines.append(textwrap.fill(
                f"  • {when} · {amt} · {donor} → {recip}", width=78,
                subsequent_indent="    "))
            lines.append(f"    source: {src}")
        lines.append("")
    else:
        lines.append("  (No cited observable events — please advise if we have overlooked any.)")
        lines.append("")

    # Pledges
    pledges = rec.get("pledges_and_announcements", [])
    if pledges:
        lines.append("--- PLEDGES AND ANNOUNCEMENTS (NOT COUNTED AS OBSERVABLE UNTIL DISBURSED) ---")
        lines.append("")
        for pl in pledges:
            role = pl.get("event_role", "")
            when = pl.get("date") or pl.get("year") or ""
            amt = fmt_usd(pl.get("pledged_amount_usd") or pl.get("pledged_amount_usd_at_signing_estimate"))
            recip = pl.get("recipient", "") or ""
            status = pl.get("status") or pl.get("classification") or ""
            src = pl.get("source_url", "—")
            lines.append(f"  • {when} · {amt} · {role}{' · '+recip if recip else ''}{' · '+status if status else ''}")
            lines.append(f"    source: {src}")
        lines.append("")

    # Detected vehicles
    lines.append("--- DETECTED GIVING VEHICLES ---")
    lines.append("")
    had_any = False
    for f in vehicles.get("foundations_active", []) or []:
        had_any = True
        lines.append(f"  • Foundation (active): {f.get('name','?')}"
                     f"{' · EIN '+f.get('ein') if f.get('ein') else ''}")
    for f in vehicles.get("foundations_terminated", []) or []:
        had_any = True
        lines.append(f"  • Foundation (closed): {f.get('name','?')}"
                     f" · terminated {f.get('terminated_year','?')}")
    for l in vehicles.get("llcs_philanthropic", []) or []:
        had_any = True
        lines.append(f"  • LLC (no 990 disclosure): {l.get('name','?')}")
    for fph in vehicles.get("for_profit_hybrid_vehicles", []) or []:
        had_any = True
        lines.append(f"  • For-profit hybrid: {fph.get('name','?')} — NOT counted as charity under our methodology")
    for t in vehicles.get("trusts_disclosed_existence_structure_unknown", []) or []:
        had_any = True
        lines.append(f"  • Trust (structure undisclosed): {t.get('type','?')}")
    if not had_any:
        lines.append("  (None detected.)")
    lines.append("")

    # Political
    if pol.get("observed_total_2021_2025_usd"):
        lines.append("--- POLITICAL GIVING (TRACKED SEPARATELY; NOT COUNTED AS CHARITY) ---")
        lines.append("")
        lines.append(f"  • 2021–2025 floor: {fmt_usd(pol['observed_total_2021_2025_usd'])}")
        lines.append(f"    sources: {', '.join(s.get('url','') for s in pol.get('sources',[])[:3])}")
        lines.append("")

    # Red flags
    if flags:
        lines.append("--- FLAGS WE INTEND TO SURFACE (EACH WITH CITATION) ---")
        lines.append("")
        for f in flags:
            code = f.get("flag") if isinstance(f, dict) else f
            ev = f.get("evidence") if isinstance(f, dict) else ""
            src = f.get("source_url") if isinstance(f, dict) else ""
            lines.append(f"  • {code}")
            if ev:
                lines.append(textwrap.fill(f"    {ev}", width=78, subsequent_indent="    "))
            if src:
                lines.append(f"    source: {src}")
        lines.append("")

    # Tier reasoning
    reasoning = rollup.get("tier_reasoning") or rollup.get("tier_published_caveat")
    if reasoning:
        lines.append("--- OUR REASONING FOR THIS TIER ---")
        lines.append("")
        lines.append(textwrap.fill(reasoning, width=78))
        lines.append("")

    # Ask
    lines.append("=" * 78)
    lines.append("")
    lines.append("WHAT WE ARE ASKING")
    lines.append("")
    lines.append(textwrap.fill(
        "If any of the above is materially incorrect — a number, an attribution, a vehicle we have misclassified — please tell us specifically what is wrong and point to a source we can link. We will update the record and note the correction in a public changelog.",
        width=78))
    lines.append("")
    lines.append(textwrap.fill(
        "If there is documented giving we have missed — with a source we can verify (990 line-item, recipient-side announcement, SEC filing, pledge letter, foundation annual report) — please send it. We will add it.",
        width=78))
    lines.append("")
    lines.append(textwrap.fill(
        f"If you wish to publish a response, it will appear verbatim on the subject's profile page. If we receive no response by {deadline.isoformat()}, we will publish \"no response by [date]\" — which is standard practice.",
        width=78))
    lines.append("")
    lines.append("We are not reporters on deadline. We are building a data project and we would rather be right than first.")
    lines.append("")
    lines.append("Thank you for your time.")
    lines.append("")
    lines.append("[editor]")
    lines.append(f"{SCROOGE_URL}")
    lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline-days", type=int, default=7, help="Response window in days (default 7)")
    ap.add_argument("--tiers", nargs="+", default=["A_VERIFIED_LOW", "B_PROBABLY_LOW"],
                    help="Which tiers to generate outreach for")
    args = ap.parse_args()

    deadline = date.today() + timedelta(days=args.deadline_days)
    OUT_DIR.mkdir(exist_ok=True)
    recs = load_v3_records()

    written = 0
    skipped = 0
    for rec in recs:
        tier = tier_of(rec)
        if tier not in args.tiers:
            skipped += 1
            continue
        slug = subject_slug(rec)
        body = build_email(rec, deadline)
        out = OUT_DIR / f"{slug}.txt"
        with out.open("w") as f:
            f.write(body)
        written += 1
        print(f"  wrote outreach for {rec.get('person',{}).get('name_display')} → {out}")

    print(f"\nGenerated {written} outreach emails. Skipped {skipped} (not in tiers {args.tiers}).")
    print(f"Deadline: {deadline.isoformat()}")
    print(f"Directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
