"""Fabricated-source replacement report.

Reads existing data/<subject>.v3.json records, identifies entries flagged
`source_verification_status: dead_link_likely_fabricated`, and surfaces
candidate replacement URLs from regen_v3/cache/search/.

Output: regen_v3/REPLACEMENT_CANDIDATES.md — one section per affected
subject with the broken URL, the original event/source it cited, and
ranked candidate replacements pulled from the search cache.

Usage:
    python3 -m regen_v3.report
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
SEARCH_CACHE = HERE / "cache" / "search"
OUT_PATH = HERE / "REPLACEMENT_CANDIDATES.md"

# Domains whose URLs we trust most for sourcing dollar-bearing events.
HIGH_SIGNAL = (
    "philanthropy.com",
    "philanthropynewsdigest.org",
    "forbes.com",
    "bloomberg.com",
    "reuters.com",
    "nytimes.com",
    "wsj.com",
    "washingtonpost.com",
    "theguardian.com",
    "apnews.com",
    "cnbc.com",
    "businessinsider.com",
    "cbsnews.com",
    "foxnews.com",
    "foxbusiness.com",
    "rockefeller.edu",
    "mskcc.org",
    "loomischaffee.org",
    "stanford.edu",
    "harvard.edu",
    "mit.edu",
    "columbia.edu",
    "magazine.columbia.edu",
    "stern.nyu.edu",
    "yale.edu",
    "princeton.edu",
    "uchicago.edu",
    "duke.edu",
    "northwestern.edu",
)


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _domain_score(url: str) -> int:
    d = _domain(url)
    if any(d == h or d.endswith("." + h) for h in HIGH_SIGNAL):
        return 2
    if d.endswith(".edu") or d.endswith(".gov"):
        return 2
    if d.endswith(".org"):
        return 1
    return 0


_AMOUNT_RE = re.compile(
    r"\$[\d.,]+\s*(million|billion|m|b)\b",
    re.IGNORECASE,
)


def _amount_score(snippet: str) -> int:
    return 1 if _AMOUNT_RE.search(snippet or "") else 0


def _year_score(snippet: str, target_year: int | None) -> int:
    if target_year is None:
        return 0
    return 1 if str(target_year) in (snippet or "") else 0


def _fabricated_entries(rec: dict) -> list[dict]:
    """Return the list of entries (events / pledges / sources) flagged as
    likely-fabricated, with provenance info attached for the report."""
    out: list[dict] = []
    for fld in ("cited_events", "pledges_and_announcements"):
        for i, ev in enumerate(rec.get(fld) or []):
            if isinstance(ev, dict) and (ev.get("source_verification_status") or "").startswith(
                "dead_link_likely_fabricated"
            ):
                out.append({"_field": fld, "_index": i, **ev})
    for i, s in enumerate(rec.get("sources_all") or []):
        if isinstance(s, dict) and (s.get("source_verification_status") or "").startswith(
            "dead_link_likely_fabricated"
        ):
            out.append({"_field": "sources_all", "_index": i, **s})
    return out


def _load_subject_caches(subject_id: str) -> list[dict]:
    """Load all search-cache entries whose query mentions the subject's tokens.
    Cheap heuristic: just load every cache file; we'll match by query text."""
    out = []
    for fp in SEARCH_CACHE.glob("*.json"):
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        out.append(d)
    return out


def _candidate_urls(rec: dict, caches: list[dict], target_amount: int | None,
                    target_year: int | None) -> list[tuple[int, str, str, str]]:
    """Return [(score, url, query, snippet)] sorted desc by score, deduped by url."""
    name = rec.get("person", {}).get("name_display") or ""
    name_legal = rec.get("person", {}).get("name_legal") or ""
    tokens = {t.lower() for t in (name + " " + name_legal).split() if len(t) > 2}

    seen: set[str] = set()
    rows: list[tuple[int, str, str, str]] = []
    for cache in caches:
        q = cache.get("query") or ""
        # Crude relevance: at least one of the subject's name tokens in the query.
        ql = q.lower()
        if not any(t in ql for t in tokens):
            continue
        for r in cache.get("results") or []:
            url = r.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            snippet = (r.get("description") or "").replace("<strong>", "").replace("</strong>", "")
            score = (
                _domain_score(url)
                + _amount_score(snippet)
                + _year_score(snippet, target_year)
            )
            # boost if snippet mentions the rough dollar amount we're trying to
            # corroborate (e.g., "100 million" when target_amount=100_000_000)
            if target_amount and snippet:
                amt_str_m = f"{int(round(target_amount/1e6))} million"
                amt_str_b = f"{round(target_amount/1e9, 1)} billion"
                if amt_str_m.lower() in snippet.lower() or amt_str_b.lower() in snippet.lower():
                    score += 2
            if score > 0:
                rows.append((score, url, q, snippet[:220]))
    rows.sort(key=lambda r: (-r[0], r[1]))
    return rows


def _section_for_subject(rec_path: Path) -> str | None:
    rec = json.loads(rec_path.read_text())
    fab = _fabricated_entries(rec)
    if not fab:
        return None

    subject_id = rec_path.name.replace(".v3.json", "")
    name = rec.get("person", {}).get("name_display") or subject_id
    caches = _load_subject_caches(subject_id)

    lines = [f"## {name}  ({subject_id})", ""]
    for entry in fab:
        url = entry.get("source_url") or entry.get("url") or "(no url)"
        amount = entry.get("amount_usd")
        year = entry.get("year")
        recipient = entry.get("recipient") or entry.get("publisher") or ""
        role = entry.get("event_role") or "(bibliography)"
        amount_s = f"${amount/1e6:.0f}M" if amount else "—"
        lines.append(f"### `{entry['_field']}[{entry['_index']}]` — {role} · {amount_s} · {year or '?'}")
        if recipient:
            lines.append(f"- **Recipient:** {recipient}")
        lines.append(f"- **Broken URL:** `{url}`")
        lines.append("")
        cands = _candidate_urls(rec, caches, amount, year)[:6]
        if cands:
            lines.append("**Candidate replacements (ranked):**")
            for score, c_url, q, snippet in cands:
                lines.append(f"- score {score} · [{c_url}]({c_url})")
                lines.append(f"  - via query: `{q}`")
                lines.append(f"  - snippet: {snippet}")
        else:
            lines.append("_No candidate replacements found in search cache. Try `--refresh`._")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    sections: list[str] = []
    for fp in sorted(DATA_DIR.glob("*.v3.json")):
        s = _section_for_subject(fp)
        if s:
            sections.append(s)

    header = (
        "# Fabricated-URL Replacement Candidates\n\n"
        f"Generated by `regen_v3.report` from {SEARCH_CACHE.relative_to(ROOT)}.\n\n"
        "For each event/source flagged `dead_link_likely_fabricated`, this lists\n"
        "high-signal replacement candidates pulled from the regen_v3 search cache.\n"
        "Score = domain reputation (0-2) + dollar-amount-mentioned (0-1) + year-match (0-1)\n"
        "+ amount-figure-match (+2 if the exact rough $-figure appears in the snippet).\n\n"
        "Pick a candidate, copy its URL into the corresponding event's `source_url`,\n"
        "remove the `source_verification_status` annotation, and re-run `validate_v3.py`.\n\n"
    )
    OUT_PATH.write_text(header + "\n---\n\n".join(sections) + "\n")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)} ({len(sections)} subjects with fabricated URLs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
