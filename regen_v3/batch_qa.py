"""regen_v3 batch_qa — post-batch quality auditor.

BS-checks newly-merged subject records before they go live. For each subject,
emits a per-issue list and a 0-100 composite score. CI-style gate: exits
non-zero if any subject scores < 50.

Read-only on data/*.v3.json. Deep mode (`--deep`) opts in to a per-event
hallucination spot-check via WebFetch + a Claude call (~$0.05/subject).

Usage:
    python3 -m regen_v3.batch_qa --subjects daniel_loeb robert_kraft
    python3 -m regen_v3.batch_qa --batch <batch_id>
    python3 -m regen_v3.batch_qa --all
    python3 -m regen_v3.batch_qa --subjects daniel_loeb --deep

Hard cap: 10 subjects per invocation (matches batch_runner). Scaling up beyond
that without thinking is what the user explicitly told us not to do.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
QA_CACHE_DIR = HERE / "cache" / "batch_qa"
QA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
BATCH_STATE_DIR = HERE / "cache" / "batch_state"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validate_v3 import check as validate_check  # noqa: E402
from regen_v3.search import BLOCKLIST_DOMAINS  # noqa: E402

HARD_CAP = 10

# Severity → score penalty (composite score starts at 100).
PENALTY_FAIL = 25
PENALTY_WARN = 5

DEEP_SAMPLE_PER_SUBJECT = 3  # number of LLM-extracted events to spot-check


# --------------------------------------------------------------------------- #
# Issue helpers
# --------------------------------------------------------------------------- #

def _issue(severity: str, category: str, msg: str) -> dict:
    return {"severity": severity, "category": category, "msg": msg}


def _domain_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------- #
# Static checks (cheap, always run)
# --------------------------------------------------------------------------- #

def _check_required_fields(rec: dict) -> list[dict]:
    out: list[dict] = []
    person = rec.get("person") or {}
    nw = rec.get("net_worth") or {}

    if not (person.get("wealth_source") or "").strip():
        out.append(_issue("fail", "required_fields", "person.wealth_source missing"))
    if nw.get("best_estimate_usd_billions") in (None, 0):
        out.append(_issue("fail", "required_fields", "net_worth.best_estimate_usd_billions missing"))
    liq = nw.get("liquidity_estimate_pct")
    if liq is None:
        out.append(_issue("fail", "required_fields", "net_worth.liquidity_estimate_pct missing"))
    elif not (0 <= liq <= 1):
        out.append(_issue("fail", "required_fields",
                          f"liquidity_estimate_pct out of range: {liq}"))
    if not person.get("years_as_billionaire_approx"):
        out.append(_issue("fail", "required_fields", "person.years_as_billionaire_approx missing"))
    return out


def _check_validator(rec: dict, fp: Path) -> list[dict]:
    errs, _ = validate_check(rec, fp)
    return [_issue("fail", "validator", e) for e in errs]


def _check_sanity_flags(rec: dict) -> list[dict]:
    rollup = rec.get("rollup") or {}
    out: list[dict] = []
    for key in ("sanity_flag_observable_exceeds_networth",
                "sanity_flag_yearly_giving_exceeds_20pct_nw",
                "sanity_flag_tier_inconsistent"):
        msg = rollup.get(key)
        if msg:
            out.append(_issue("warn", "sanity_flag", f"{key}: {msg}"))
    return out


def _check_blocklist_sources(rec: dict) -> list[dict]:
    """Flag blocklisted domains. Aggregate per-domain so a record citing the
    same bad domain 6 times produces one issue, not six. Blocklisted-source
    references are `warn`, not `fail`: they're signal that a manual replace
    is needed, but not a release blocker on their own."""
    out: list[dict] = []
    seen: dict[str, list[str]] = {}
    for fld in ("cited_events", "pledges_and_announcements", "sources_all"):
        for i, item in enumerate(rec.get(fld, []) or []):
            if not isinstance(item, dict):
                continue
            url = item.get("source_url") or item.get("url")
            if not url:
                continue
            host = _domain_of(url)
            parts = host.split(".")
            for j in range(len(parts) - 1):
                root = ".".join(parts[j:])
                if root in BLOCKLIST_DOMAINS:
                    seen.setdefault(root, []).append(f"{fld}[{i}]")
                    break
    for root, locs in sorted(seen.items()):
        out.append(_issue("warn", "blocklist_source",
                          f"cites blocklisted domain {root} ({len(locs)} ref(s): {', '.join(locs[:3])}{'...' if len(locs) > 3 else ''})"))
    return out


def _check_extract_quality(rec: dict) -> list[dict]:
    out: list[dict] = []
    events = rec.get("cited_events") or []
    foundations = (rec.get("detected_vehicles") or {}).get("foundations_active") or []
    if not events and not foundations:
        out.append(_issue("warn", "empty_extracts",
                          "no cited_events and no foundations detected — no giving evidence"))
    if events:
        all_none = all(ev.get("amount_usd") in (None, 0) for ev in events if isinstance(ev, dict))
        if all_none:
            out.append(_issue("warn", "empty_extracts",
                              "all cited_events have null/zero amount_usd — no dollar figures"))
    return out


def _check_aggregate_sanity(rec: dict) -> list[dict]:
    out: list[dict] = []
    rollup = rec.get("rollup") or {}
    obs_ev = rollup.get("observable_from_events_usd")
    if obs_ev and obs_ev > 10e9:
        # Any structured-source event present?
        structured_sources = {"propublica", "sec", "dafs"}
        has_structured = any(
            isinstance(ev, dict) and ev.get("regen_source") in structured_sources
            for ev in (rec.get("cited_events") or [])
        )
        if not has_structured:
            out.append(_issue("warn", "aggregate_sanity",
                              f"observable_from_events_usd ${obs_ev/1e9:.1f}B > $10B "
                              "but no SEC/990-PF/DAF source events — likely all from press"))
    hidden = rollup.get("hidden_upper_usd")
    if hidden is None or (isinstance(hidden, dict) and hidden.get("total_usd") is None):
        out.append(_issue("warn", "aggregate_sanity",
                          "hidden_upper_usd.total_usd not generated"))
    return out


# --------------------------------------------------------------------------- #
# Deep check — LLM hallucination spot-check (opt-in)
# --------------------------------------------------------------------------- #

def _llm_extracted_events(rec: dict) -> list[dict]:
    """Events from the LLM-from-search path (provenance regen_v3, regen_source
    NOT in any structured source). Structured sources have deterministic
    search URLs that don't render data via plain WebFetch (FEC and ICIJ both
    require JS); checking them produces false-positive hallucination flags."""
    structured = {"propublica", "sec", "dafs", "llcs", "fec", "leaks",
                  "state_charities", "candid"}
    out: list[dict] = []
    for ev in (rec.get("cited_events") or []):
        if not isinstance(ev, dict):
            continue
        if ev.get("provenance") != "regen_v3":
            continue
        if ev.get("regen_source") in structured:
            continue
        if not ev.get("source_url"):
            continue
        out.append(ev)
    return out


def _verify_event_with_llm(ev: dict, page_text: str, client: Any, model: str) -> dict:
    """Ask Claude whether `page_text` supports the claim in `ev`. Returns
    {"supported": bool, "reason": str}."""
    payload = {
        "recipient": ev.get("recipient"),
        "amount_usd": ev.get("amount_usd"),
        "year": ev.get("year"),
        "event_role": ev.get("event_role"),
        "donor_entity": ev.get("donor_entity"),
    }
    sys_prompt = (
        "You are a fact-checker. Decide whether the provided web page text supports "
        "the claim. Be strict: if recipient, amount, or year is not corroborated, mark "
        "it unsupported. Never speculate."
    )
    user = (
        f"Claim: {json.dumps(payload, default=str)}\n\n"
        f"Source URL: {ev.get('source_url')}\n\n"
        f"Page text (truncated to 6000 chars):\n{(page_text or '')[:6000]}\n\n"
        "Reply in JSON only: {\"supported\": bool, \"reason\": \"<<=200 chars\"}."
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=300,
            system=sys_prompt,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        # Strip code fences if present.
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        parsed = json.loads(text)
        return {"supported": bool(parsed.get("supported")), "reason": str(parsed.get("reason", ""))[:200]}
    except Exception as e:
        return {"supported": True, "reason": f"verification_error: {type(e).__name__}: {e}"}


def _check_hallucinations_deep(rec: dict, *, fetcher, client, model: str) -> list[dict]:
    """Sample LLM-extracted events, fetch their cited URL, ask Claude if the
    page supports the claim. `fetcher(url) -> str | None` is injected so this
    module stays testable without a live network."""
    out: list[dict] = []
    candidates = _llm_extracted_events(rec)
    if not candidates:
        return out
    sample = random.sample(candidates, k=min(DEEP_SAMPLE_PER_SUBJECT, len(candidates)))
    for ev in sample:
        url = ev.get("source_url")
        page_text = fetcher(url)
        if page_text is None:
            out.append(_issue("fail", "hallucination",
                              f"event source URL dead/unfetchable: {url}"))
            continue
        verdict = _verify_event_with_llm(ev, page_text, client, model)
        if not verdict["supported"]:
            recip = ev.get("recipient")
            amt = ev.get("amount_usd")
            amt_str = f"${amt/1e6:.0f}M" if isinstance(amt, (int, float)) and amt else "no-amount"
            out.append(_issue("fail", "hallucination",
                              f"page does not support claim ({recip}, {amt_str}, "
                              f"{ev.get('year')}): {verdict['reason']} — {url}"))
    return out


# --------------------------------------------------------------------------- #
# Per-subject audit
# --------------------------------------------------------------------------- #

def audit_subject(subject_id: str, *, deep: bool = False,
                  fetcher=None, client=None, model: str = "claude-haiku-4-5") -> dict:
    """Return a QA report for a single subject record.

    Output:
        { "subject_id", "status": "ok|warn|fail", "score": 0-100, "issues": [...] }
    Each issue: { "severity": "warn|fail", "category": str, "msg": str }.
    """
    fp = DATA_DIR / f"{subject_id}.v3.json"
    if not fp.exists():
        return {
            "subject_id": subject_id,
            "status": "fail",
            "score": 0,
            "issues": [_issue("fail", "io", f"record not found: {fp}")],
        }
    rec = json.loads(fp.read_text())

    issues: list[dict] = []
    issues += _check_required_fields(rec)
    issues += _check_validator(rec, fp)
    issues += _check_sanity_flags(rec)
    issues += _check_blocklist_sources(rec)
    issues += _check_extract_quality(rec)
    issues += _check_aggregate_sanity(rec)
    if deep and fetcher is not None and client is not None:
        issues += _check_hallucinations_deep(rec, fetcher=fetcher, client=client, model=model)

    fails = sum(1 for i in issues if i["severity"] == "fail")
    warns = sum(1 for i in issues if i["severity"] == "warn")
    score = max(0, 100 - PENALTY_FAIL * fails - PENALTY_WARN * warns)
    if fails > 0:
        status = "fail"
    elif warns > 0:
        status = "warn"
    else:
        status = "ok"
    return {"subject_id": subject_id, "status": status, "score": score, "issues": issues}


# --------------------------------------------------------------------------- #
# Subject resolution + CLI
# --------------------------------------------------------------------------- #

def _resolve_batch(batch_id: str) -> list[str]:
    fp = BATCH_STATE_DIR / f"{batch_id}.json"
    if not fp.exists():
        raise SystemExit(f"[batch_qa] no batch state at {fp}")
    state = json.loads(fp.read_text())
    return sorted(s for s, v in (state.get("subjects") or {}).items()
                  if v.get("status") == "merged" or v.get("status") == "pending")


def _resolve_all() -> list[str]:
    return sorted(p.name.replace(".v3.json", "") for p in DATA_DIR.glob("*.v3.json"))


def _make_deep_helpers():
    """Lazy-construct the WebFetch fetcher + Anthropic client for deep mode."""
    import anthropic  # noqa: F401 — only needed in deep mode
    import urllib.request

    client = anthropic.Anthropic()

    def fetcher(url: str) -> str | None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "scrooge-qa/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read(200_000).decode("utf-8", errors="ignore")
            # Strip tags crudely — we only need page text for support-checking.
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.S | re.I)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
        except Exception:
            return None

    return fetcher, client


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--subjects", nargs="+", help="Explicit subject ids")
    g.add_argument("--batch", metavar="BATCH_ID", help="Audit subjects from a batch_runner checkpoint")
    g.add_argument("--all", action="store_true", help="All subjects in data/")
    ap.add_argument("--deep", action="store_true",
                    help="Run hallucination spot-check via WebFetch + Claude (~$0.05/subject)")
    ap.add_argument("--unsafe-allow-large", action="store_true",
                    help=f"Bypass {HARD_CAP}-subject hard cap")
    ap.add_argument("--seed", type=int, default=None, help="Deterministic deep-mode sampling")
    args = ap.parse_args(argv)

    if args.subjects:
        subjects = list(args.subjects)
        batch_id = "ad_hoc_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    elif args.batch:
        subjects = _resolve_batch(args.batch)
        batch_id = args.batch
    else:
        subjects = _resolve_all()
        batch_id = "all_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if not subjects:
        print("[batch_qa] nothing to audit")
        return 0
    if len(subjects) > HARD_CAP and not args.unsafe_allow_large:
        print(f"[batch_qa] refusing: {len(subjects)} subjects > hard cap {HARD_CAP}. "
              "Pass --unsafe-allow-large to override.", file=sys.stderr)
        return 2

    if args.seed is not None:
        random.seed(args.seed)

    fetcher, client = (None, None)
    if args.deep:
        try:
            fetcher, client = _make_deep_helpers()
        except Exception as e:
            print(f"[batch_qa] --deep unavailable ({e}); falling back to static checks", file=sys.stderr)
            args.deep = False

    reports = []
    worst_score = 100
    for sid in subjects:
        rep = audit_subject(sid, deep=args.deep, fetcher=fetcher, client=client)
        reports.append(rep)
        worst_score = min(worst_score, rep["score"])
        n_issues = len(rep["issues"])
        print(f"[{rep['score']:3}] {sid:<32} {rep['status']:<5} ({n_issues} issues)")

    out_path = QA_CACHE_DIR / f"{batch_id}.json"
    out_path.write_text(json.dumps({
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deep": bool(args.deep),
        "reports": reports,
    }, indent=2, sort_keys=True))
    print(f"\n[batch_qa] report: {out_path}")

    fail_threshold = 50
    failing = [r for r in reports if r["score"] < fail_threshold]
    if failing:
        print(f"[batch_qa] FAIL — {len(failing)} subjects scored < {fail_threshold}", file=sys.stderr)
        for r in failing:
            print(f"  {r['subject_id']} ({r['score']})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
