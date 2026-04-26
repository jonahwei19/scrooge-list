"""LLM-generated additional search queries for regen_v3.

Layered enrichment on top of the deterministic template baseline in
``queries.py``. Reads the FULL v3 record and asks Claude Haiku 4.5 to emit
~10-15 highly specific queries grounded in the subject's known vehicles,
geography, controversies, and industry.

Design contract (mirrors regen_v3/extract.py + propublica.py):

    * Same record -> identical output. ``temperature=0`` plus structured
      tool use (forced ``emit_queries`` invocation) plus an on-disk cache
      keyed by ``sha256(json.dumps(record, sort_keys=True, separators=...))``.

    * ADDITIVE only. Output is a list of dicts the caller concatenates with
      ``queries.build_query_plan(record)`` and dedupes by (role, query).

    * Strict role enum. Each emitted query MUST carry one of
      ``CANONICAL_EVENT_ROLES``; the schema enum forces compliance, and
      we drop anything that slips through.

    * Cost discipline. ``claude-haiku-4-5``, ``max_tokens=1500``, system
      prompt marked cacheable. Cap: one API call per subject per run
      (cache enforces this; ``refresh=True`` overrides).

    * Graceful skip. If ``ANTHROPIC_API_KEY`` is unset and there is no
      cache hit, return ``[]`` after logging a one-line skip note. Never
      raise from this module's top-level entrypoint.

See regen_v3/SPEC.md for the cohort-level reproducibility contract.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from anthropic import Anthropic

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "queries_llm"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Source-of-truth import. Mirrors how queries.py duplicates these inline.
from queries import CANONICAL_EVENT_ROLES  # noqa: E402

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1500
TEMPERATURE = 0.0

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a forensic philanthropy researcher generating additional Google search queries for a billionaire whose giving record we are auditing.

You will be given the FULL JSON v3 record of a single subject. Your job is to emit 10-15 ADDITIONAL search queries that the deterministic template baseline does NOT already cover.

THE TEMPLATE BASELINE ALREADY COVERS (do NOT duplicate these):
  * '"NAME" "giving pledge"' / '"NAME" "did not sign" "giving pledge"'
  * '"NAME" donates million' / '"NAME" gift OR donation million'
  * '"NAME" pledges OR commits OR announces'
  * '"NAME" foundation 990-PF' or '"FOUNDATION_NAME" 990-PF' / 'grants'
  * '"EIN" 990-PF'
  * '"NAME" FEC OR PAC contribution'
  * '"NAME" "TOP_POLITICAL_RECIPIENT"'
  * '"NAME" "impact investment" OR "mission-related investment"'
  * '"NAME" site:forbes.com profile'
  * '"NAME" site:propublica.org OR site:icij.org OR site:occrp.org OR site:reuters.com/investigates OR site:theintercept.com'
  * '"NAME" investigation OR exposé OR revealed OR leaked "donor-advised fund" OR "tax shelter"'
  * '"NAME" 2018 OR 2019 OR 2020 gift OR donation revealed OR uncovered'
  * Generic foreign-language templates per country: e.g. Hebrew ('"NAME" תורם OR מתחייב מיליון'), French, German, Spanish, etc.

YOUR JOB IS TO FILL THE GAPS. Generate queries that target SUBJECT-SPECIFIC dark, opaque, or under-reported channels. Use the record context aggressively:

  * Cite SPECIFIC vehicles by name (LLCs, DAFs, holding cos, family-branch foundations) the templates don't generically reach.
  * Cite SPECIFIC geographies, ethnic communities, or religious institutions the subject is tied to.
  * Cite SPECIFIC controversies, lawsuits, or transactions named in the record (e.g. a 2018 estate transfer that surfaces later in IRS filings).
  * Use site-restrictors for INVESTIGATIVE outlets the baseline didn't list: Mother Jones, The Guardian US, Bloomberg Investigation, NYT DealBook, Axios, the Center for Public Integrity, Tax Notes, Citizens for Responsibility and Ethics in Washington (CREW).
  * Use site-restrictors for INDUSTRY trade press relevant to the subject (Inside Philanthropy, Chronicle of Philanthropy, Variety, Hollywood Reporter, Bloomberg Tax, Real Estate Forum).
  * Use FOREIGN-LANGUAGE queries when the subject has non-English geography or ethnic community ties — but make them subject-specific (e.g. for an Israeli, query Hebrew-language Globes/TheMarker by name + the SPECIFIC Israeli NGO they are publicly associated with, not just generic templates).
  * Prefer TIME-SHIFTED retrospective queries — "X 2017 transfer revealed 2024", "X estate plan filed 2023".
  * Target dark channels: dynasty trusts, LLC pass-throughs, 501(c)(4) advocacy shells, religious giving (church, synagogue, mosque, Chabad, etc.), family-office shell entities, offshore holdings, board-seat philanthropy, charity gala underwriting, university capital campaigns where the gift is named-but-unattributed in 990s.

EVERY query must carry an event_role from this enum:
  grant_out, direct_gift, transfer_in, pledge, no_pledge,
  announcement, political, private_investment, corporate_gift, reference_only

EVERY query must carry a one-sentence rationale explaining what specific signal the query is hunting (this is for human reviewers — be concrete, name the channel/outlet/document type).

Output rules:
  * Emit 10-15 queries. Quality > quantity.
  * No duplicates of the baseline list above.
  * Sort your output: roles in canonical order, then queries lexicographically within each role. (The schema doesn't enforce this — it's a soft determinism aid.)
  * Use Google search syntax: quoted phrases, OR, site:, intitle:, filetype:.
  * Keep each query under 200 chars."""


def _tool_schema() -> dict[str, Any]:
    """Tool input schema. The enum on event_role enforces canonical roles."""
    query_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": sorted(CANONICAL_EVENT_ROLES),
                "description": "Canonical event_role this query is hunting for.",
            },
            "query": {
                "type": "string",
                "description": (
                    "Google-search-syntax query string. Quoted phrases, OR, "
                    "site:, intitle:, filetype: all welcome. <= 200 chars."
                ),
            },
            "rationale": {
                "type": "string",
                "description": (
                    "ONE sentence (<= 30 words) explaining what specific "
                    "signal/channel/outlet this query is hunting. Concrete."
                ),
            },
        },
        "required": ["role", "query", "rationale"],
    }
    return {
        "name": "emit_queries",
        "description": (
            "Emit 10-15 additional Google search queries that target "
            "subject-specific philanthropic signals the deterministic "
            "template baseline does NOT already cover. Each query carries "
            "a canonical event_role and a concrete one-sentence rationale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "minItems": 8,
                    "maxItems": 20,
                    "items": query_schema,
                }
            },
            "required": ["queries"],
        },
    }


def _canonical_record_key(record: dict) -> str:
    """Cache key. Same record -> same hex digest -> same cache file."""
    blob = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str) -> list[dict] | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    queries = payload.get("queries")
    if not isinstance(queries, list):
        return None
    return queries


def _write_cache(key: str, queries: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    payload = {
        "input_key": key,
        "model": MODEL,
        "queries": queries,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _build_user_prompt(record: dict) -> str:
    """Embed the full v3 record verbatim. Claude reads it; we don't pre-summarize."""
    name = (record.get("person") or {}).get("name_display") or "(unknown)"
    record_json = json.dumps(record, indent=2, sort_keys=True)
    return (
        f"SUBJECT: {name}\n\n"
        f"FULL V3 RECORD (read all of it — vehicles, geography, controversies, "
        f"news_summary, red_flags, sources_all):\n\n{record_json}\n\n"
        "Generate 10-15 ADDITIONAL queries per the system prompt. Skip anything "
        "the deterministic template baseline already covers. Cite specific vehicles, "
        "geographies, and controversies from this record. Invoke the emit_queries tool."
    )


def _validate_query(item: Any) -> dict | None:
    """Coerce a model-emitted item into the canonical {role, query, rationale}.

    Drops anything missing required fields, with a non-canonical role, with
    an empty query string, or where the query is implausibly long.
    """
    if not isinstance(item, dict):
        return None
    role = item.get("role")
    query = item.get("query")
    rationale = item.get("rationale", "")
    if role not in CANONICAL_EVENT_ROLES:
        logger.warning("queries_llm: dropping item with non-canonical role=%r", role)
        return None
    if not isinstance(query, str) or not query.strip():
        logger.warning("queries_llm: dropping item with empty query")
        return None
    if len(query) > 400:
        logger.warning("queries_llm: dropping over-long query (len=%d)", len(query))
        return None
    if not isinstance(rationale, str):
        rationale = str(rationale)
    return {"role": role, "query": query.strip(), "rationale": rationale.strip()}


def _call_anthropic(record: dict) -> list[dict]:
    """One forced-tool-use call to Claude. Returns validated query dicts."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=api_key)
    tool = _tool_schema()
    user_prompt = _build_user_prompt(record)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                # Cache the system prompt across cohort subjects -> cheap repeat hits.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[tool],
        tool_choice={"type": "tool", "name": "emit_queries"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw: list[dict] = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_queries":
            data = block.input or {}
            items = data.get("queries", [])
            if isinstance(items, list):
                raw = items
            else:
                logger.warning("queries_llm: tool returned non-list queries: %r", items)
            break
    else:
        logger.warning("queries_llm: model did not invoke emit_queries tool")
        return []

    validated: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for item in raw:
        ok = _validate_query(item)
        if ok is None:
            continue
        key = (ok["role"], ok["query"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        validated.append(ok)

    # Deterministic ordering for byte-identical re-runs.
    role_order = sorted(CANONICAL_EVENT_ROLES)
    role_index = {r: i for i, r in enumerate(role_order)}
    validated.sort(key=lambda d: (role_index[d["role"]], d["query"]))

    # Log usage for cost tracking.
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "queries_llm: subject=%r in_tok=%s cache_read=%s cache_create=%s out_tok=%s n=%d",
            (record.get("person") or {}).get("name_display"),
            getattr(usage, "input_tokens", None),
            getattr(usage, "cache_read_input_tokens", None),
            getattr(usage, "cache_creation_input_tokens", None),
            getattr(usage, "output_tokens", None),
            len(validated),
        )

    return validated


def build_llm_query_plan(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return additional query specs for a subject, generated by Claude.

    Each spec: ``{"role": <CANONICAL_EVENT_ROLE>, "query": <str>, "rationale": <str>}``.

    Cached at ``regen_v3/cache/queries_llm/<sha256(canonical_record)>.json``.
    Same record -> byte-identical output across runs.

    Returns ``[]`` (with a one-line skip log) if ``ANTHROPIC_API_KEY`` is
    unset and no cache entry exists. This is intentional — the caller layers
    this on top of the deterministic baseline, which is always available.
    """
    key = _canonical_record_key(record)

    if not refresh:
        cached = _read_cache(key)
        if cached is not None:
            return cached

    try:
        queries = _call_anthropic(record)
    except RuntimeError as exc:
        # Most common: missing API key. Try cache one more time, then skip.
        cached = _read_cache(key)
        if cached is not None:
            return cached
        logger.info("queries_llm: skipping (%s); returning [] for subject", exc)
        return []
    except Exception as exc:  # network / API error
        cached = _read_cache(key)
        if cached is not None:
            return cached
        logger.warning("queries_llm: API call failed (%s); returning []", exc)
        return []

    _write_cache(key, queries)
    return queries


# --- self-test -----------------------------------------------------------


def _format_plan(record: dict, plan: list[dict]) -> str:
    name = (record.get("person") or {}).get("name_display") or "(unknown)"
    lines = [f"=== LLM query plan: {name} ({len(plan)} queries) ==="]
    for item in plan:
        lines.append(f"  [{item['role']:<18}] {item['query']}")
        lines.append(f"    rationale: {item.get('rationale', '')}")
    return "\n".join(lines)


def _main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--subject",
        required=True,
        help="Subject id (e.g. miriam_adelson). Loads data/<subject>.v3.json.",
    )
    ap.add_argument("--refresh", action="store_true", help="Bypass cache.")
    args = ap.parse_args()

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    if not rec_path.exists():
        print(f"[error] no record at {rec_path}", file=sys.stderr)
        sys.exit(2)

    record = json.loads(rec_path.read_text())
    plan = build_llm_query_plan(record, refresh=args.refresh)
    print(_format_plan(record, plan))


if __name__ == "__main__":
    _main()
