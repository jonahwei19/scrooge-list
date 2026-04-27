"""regen_v3 CLI — wire queries → search → verify → extract → merge.

Reproducible: same subject + same caches ⇒ identical output.

Usage:
    python3 -m regen_v3 --subject henry_kravis
    python3 -m regen_v3 --subject henry_kravis --dry-run
    python3 -m regen_v3 --subject henry_kravis --candidates-only
    python3 -m regen_v3 --all
    python3 -m regen_v3 --refresh
    python3 -m regen_v3 --replace-fabricated
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
CANDIDATES_DIR = HERE / "cache" / "candidates"
CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from regen_v3 import queries as queries_mod
from regen_v3 import queries_llm as queries_llm_mod
from regen_v3 import search as search_mod
from regen_v3 import verify as verify_mod
from regen_v3 import extract as extract_mod
from regen_v3 import merge as merge_mod
from regen_v3 import propublica as propublica_mod
from regen_v3 import sec as sec_mod
from regen_v3 import fec as fec_mod
from regen_v3 import leaks as leaks_mod
from regen_v3 import dafs as dafs_mod
from regen_v3 import llcs as llcs_mod
from regen_v3 import state_charities as state_charities_mod
from regen_v3 import recipient_verify as recipient_verify_mod
from validate_v3 import check as validate_check  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _content_run_id(record: dict) -> str:
    """Derive a deterministic, content-addressed run identifier so two runs
    of the same input produce byte-identical outputs. Hashes the canonical
    JSON form of the record with sort_keys."""
    blob = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    return "sha256-" + hashlib.sha256(blob).hexdigest()[:16]


def subject_id_of(path: Path) -> str:
    return path.name.replace(".v3.json", "")


def load_record(subject_id: str) -> tuple[Path, dict]:
    fp = DATA_DIR / f"{subject_id}.v3.json"
    if not fp.exists():
        raise FileNotFoundError(f"No data record for {subject_id!r} at {fp}")
    return fp, json.loads(fp.read_text())


def list_all_subjects() -> list[str]:
    return sorted(subject_id_of(p) for p in DATA_DIR.glob("*.v3.json"))


def list_fabricated_subjects() -> list[str]:
    """Subjects whose existing records cite a likely_fabricated URL."""
    out: list[str] = []
    for fp in sorted(DATA_DIR.glob("*.v3.json")):
        try:
            rec = json.loads(fp.read_text())
        except Exception:
            continue
        if _record_has_fabricated_source(rec):
            out.append(subject_id_of(fp))
    return out


def _record_has_fabricated_source(rec: dict) -> bool:
    for fld in ("cited_events", "pledges_and_announcements"):
        for ev in (rec.get(fld) or []):
            if isinstance(ev, dict):
                status = ev.get("source_verification_status") or ""
                if status.startswith("dead_link_likely_fabricated"):
                    return True
    for s in rec.get("sources_all") or []:
        if isinstance(s, dict):
            status = s.get("source_verification_status") or ""
            if status.startswith("dead_link_likely_fabricated"):
                return True
    return False


def _short(url: str, n: int = 70) -> str:
    return url if len(url) <= n else url[: n - 1] + "…"


def run_one(
    subject_id: str,
    *,
    refresh: bool,
    candidates_only: bool,
    dry_run: bool,
    verbose: bool,
    use_timestamp_run_id: bool = False,
) -> dict:
    """Run the full pipeline for one subject. Returns a summary dict."""
    fp, record = load_record(subject_id)
    subject_name = record.get("person", {}).get("name_display", subject_id)
    # Default: content-addressed run_id so same input ⇒ identical output.
    # Opt-in timestamp via --with-timestamp for forensic provenance runs.
    run_id = _now_iso() if use_timestamp_run_id else _content_run_id(record)

    print(f"\n=== {subject_name}  [{subject_id}] ===")

    # 0. Structured-API sources (ProPublica 990-PF, SEC Form 4, FEC).
    #    These run BEFORE the search/extract path because they are cheap,
    #    rate-limited, and authoritative. Their candidates feed into the
    #    same merge layer as the LLM-extracted candidates.
    structured_candidates: list[dict] = []
    structured_breakdown: dict[str, int] = {}
    for src_name, src_mod in (
        ("propublica", propublica_mod),
        ("dafs", dafs_mod),
        ("sec", sec_mod),
        ("fec", fec_mod),
        ("leaks", leaks_mod),
        ("llcs", llcs_mod),
        ("state_charities", state_charities_mod),
    ):
        try:
            cands = src_mod.collect_candidates(record, refresh=refresh)
        except Exception as e:
            print(f"    [{src_name}-skip] {type(e).__name__}: {e}")
            cands = []
        structured_breakdown[src_name] = len(cands)
        structured_candidates.extend(cands)
    print(
        "  structured: "
        + ", ".join(f"{k}={v}" for k, v in structured_breakdown.items())
        + f" (total {len(structured_candidates)})"
    )

    # 1. Plan queries — deterministic template baseline + LLM-generated
    #    enrichment, deduped by (role, query). Baseline wins on ties.
    plan_baseline = queries_mod.build_query_plan(record)
    try:
        plan_llm = queries_llm_mod.build_llm_query_plan(record, refresh=refresh)
    except Exception as e:
        print(f"    [queries_llm-skip] {type(e).__name__}: {e}")
        plan_llm = []
    seen = {(q["role"], q["query"]) for q in plan_baseline}
    plan = list(plan_baseline) + [q for q in plan_llm if (q["role"], q["query"]) not in seen]
    print(f"  queries: {len(plan)}  ({len(plan_baseline)} baseline + {len(plan)-len(plan_baseline)} LLM)")

    # 2. Search (cached)
    seen_urls: dict[str, dict] = {}  # url -> {role, query, title, snippet}
    cache_hits = 0
    live_calls = 0
    for spec in plan:
        q = spec["query"]
        cache_key_path = (
            search_mod.CACHE_DIR
            / f"{search_mod.hashlib.sha256(q.strip().lower().encode()).hexdigest()}.json"
        )
        was_cached = cache_key_path.exists() and not refresh
        try:
            sr = search_mod.search(q, count=10, refresh=refresh)
        except (RuntimeError, Exception) as e:
            # Includes Brave RuntimeErrors and any unexpected requests errors
            # from the live path. Skip the query, keep the subject going.
            print(f"    [skip] {q!r}: {type(e).__name__}: {e}")
            continue
        if was_cached:
            cache_hits += 1
        else:
            live_calls += 1
        kept, dropped = search_mod.filter_results(sr.get("results") or [])
        if verbose:
            print(f"    [{spec['role']:<18}] {q[:60]:<60}  kept={len(kept)} dropped={len(dropped)}")
        for r in kept:
            url = r.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls[url] = {
                "role_hint": spec["role"],
                "query": q,
                "title": r.get("title", ""),
                "snippet": r.get("description", ""),
            }
    print(f"  search: {cache_hits} cache-hits, {live_calls} live; {len(seen_urls)} unique URLs after filter")

    # 3. Verify URL liveness
    liveness = verify_mod.verify_urls(list(seen_urls.keys()))
    alive = {u for u, info in liveness.items() if info["alive"]}
    dead = {u for u in seen_urls if u not in alive}
    print(f"  verify: {len(alive)} alive, {len(dead)} dead")

    # 4. Extract candidate events from live URLs
    #    Seed with the structured-API candidates so they flow through the
    #    same dump + merge + validate pipeline as the LLM-extracted ones.
    candidates: list[dict] = list(structured_candidates)
    extract_errors = 0
    for url in sorted(alive):
        meta = seen_urls[url]
        try:
            events = extract_mod.extract_events(
                url=url,
                title=meta["title"],
                snippet=meta["snippet"],
                role_hint=meta["role_hint"],
                subject_name=subject_name,
                refresh=refresh,
            )
        except RuntimeError as e:
            extract_errors += 1
            if verbose:
                print(f"    [extract-skip] {_short(url)}: {e}")
            continue
        for ev in events:
            ev["regen_query"] = meta["query"]
            candidates.append(ev)
    extracted_count = len(candidates) - len(structured_candidates)
    print(
        f"  extract: {extracted_count} LLM events + {len(structured_candidates)} structured "
        f"= {len(candidates)} total ({extract_errors} skipped)"
    )

    candidates_path = CANDIDATES_DIR / f"{subject_id}.json"
    candidates_path.write_text(
        json.dumps(
            {
                "subject_id": subject_id,
                "subject_name": subject_name,
                "run_id": run_id,
                "candidates": candidates,
                "dead_urls": sorted(dead),
                "queries_used": [s["query"] for s in plan],
                "structured_breakdown": structured_breakdown,
            },
            indent=2,
            sort_keys=False,
        )
    )

    if candidates_only:
        print(f"  → candidates dumped to {candidates_path.relative_to(ROOT)}")
        return {
            "subject_id": subject_id,
            "queries": len(plan),
            "urls_found": len(seen_urls),
            "alive": len(alive),
            "candidates": len(candidates),
            "merged": False,
        }

    # 5. Merge
    new_record, diff = merge_mod.merge_candidates(
        record,
        candidates,
        run_id=run_id,
        extractor_model="claude-haiku-4-5",
    )
    print(
        f"  merge: +{diff['added_cited_events']} events, "
        f"+{diff['added_pledges_and_announcements']} pledges, "
        f"+{diff['added_sources_all']} sources, "
        f"skipped: {len(diff['skipped_duplicate'])} dup / "
        f"{len(diff['skipped_fabricated'])} fab / "
        f"{len(diff['skipped_unknown_role'])} unknown"
    )

    # 5b. Two-sided recipient cross-check: stamp recipient_verified /
    #     _filing_url / _verification_note onto every direct_gift /
    #     corporate_gift / grant_out event whose recipient + year are
    #     populated. Mutates in place. Doesn't affect validation; informational.
    try:
        recipient_verify_mod.annotate_record(new_record, refresh=refresh)
    except Exception as e:
        print(f"    [recipient_verify-skip] {type(e).__name__}: {e}")

    # 6. Validate
    errs, warns = validate_check(new_record, fp)
    print(f"  validate: {len(errs)} errors, {len(warns)} warnings")
    if errs:
        for e in errs[:5]:
            print(f"    ERROR  {e}")
        if len(errs) > 5:
            print(f"    ... +{len(errs)-5} more")

    if dry_run:
        print(f"  [dry-run] not writing {fp.relative_to(ROOT)}")
    elif errs:
        print(f"  [refusing] validate_v3 errors — {fp.relative_to(ROOT)} unchanged")
    else:
        fp.write_text(json.dumps(new_record, indent=2))
        print(f"  → wrote {fp.relative_to(ROOT)}")

    return {
        "subject_id": subject_id,
        "queries": len(plan),
        "urls_found": len(seen_urls),
        "alive": len(alive),
        "candidates": len(candidates),
        "added_events": diff["added_cited_events"] + diff["added_pledges_and_announcements"],
        "added_sources": diff["added_sources_all"],
        "validate_errors": len(errs),
        "validate_warnings": len(warns),
        "merged": not dry_run and not errs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--subject", help="Subject id (e.g. henry_kravis)")
    g.add_argument("--all", action="store_true", help="Run all 51 subjects")
    g.add_argument("--replace-fabricated", action="store_true",
                   help="Run only on subjects whose record cites a likely_fabricated URL")
    ap.add_argument("--dry-run", action="store_true", help="Don't write output")
    ap.add_argument("--candidates-only", action="store_true",
                    help="Stop after extract.py; dump candidates JSON only")
    ap.add_argument("--refresh", action="store_true",
                    help="Bypass search & extract caches (live calls)")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--with-timestamp", action="store_true",
                    help="Use a wall-clock run_id instead of a content hash. "
                         "Breaks reproducibility; opt-in for forensic runs.")
    args = ap.parse_args(argv)

    if args.all:
        subjects = list_all_subjects()
    elif args.replace_fabricated:
        subjects = list_fabricated_subjects()
        print(f"replace-fabricated: {len(subjects)} subjects with fabricated sources")
    else:
        subjects = [args.subject]

    summaries: list[dict] = []
    t0 = time.time()
    for sid in subjects:
        try:
            s = run_one(
                sid,
                refresh=args.refresh,
                candidates_only=args.candidates_only,
                dry_run=args.dry_run,
                verbose=args.verbose,
                use_timestamp_run_id=args.with_timestamp,
            )
            summaries.append(s)
        except FileNotFoundError as e:
            print(f"  [error] {e}")
        except Exception as e:
            print(f"  [error] {sid}: {type(e).__name__}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

    elapsed = time.time() - t0
    print(f"\n=== Cohort summary ({len(summaries)} subjects, {elapsed:.1f}s) ===")
    print(f"  {'subject':<28} {'plan':>4} {'urls':>5} {'alive':>5} {'cands':>5} {'errs':>4}  status")
    for s in summaries:
        status = "merged" if s.get("merged") else (
            "candidates-only" if s.get("candidates", 0) and "added_events" not in s
            else "skipped"
        )
        print(
            f"  {s['subject_id']:<28} "
            f"{s.get('queries', 0):>4} "
            f"{s.get('urls_found', 0):>5} "
            f"{s.get('alive', 0):>5} "
            f"{s.get('candidates', 0):>5} "
            f"{s.get('validate_errors', 0):>4}  {status}"
        )
    any_errors = any(s.get("validate_errors", 0) for s in summaries)
    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())
