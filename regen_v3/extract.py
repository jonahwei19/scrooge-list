"""Snippet -> structured philanthropic-event extractor.

Calls Claude Haiku 4.5 with a forced tool-use schema. Same input -> same output
(temperature=0 + on-disk cache keyed by sha256(url|snippet|role_hint|subject)).
Caller passes a snippet; nothing here fetches the web.

See regen_v3/SPEC.md for the contract.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from aggregate_v3 import CANONICAL_EVENT_ROLES

HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache" / "extract"

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2048
TEMPERATURE = 0.0

# Per-process cost cap. Counts only LIVE LLM calls (cache hits free).
# Default 10,000 = ~$45 at $0.0045/call (claude-haiku-4-5 with our snippet
# size). Override via env. Once exceeded, extract_events() returns [] for
# all uncached URLs and prints a one-line skip notice.
_MAX_EXTRACT_CALLS = int(os.environ.get("MAX_EXTRACT_CALLS", "10000"))
_live_call_count = 0
_cap_warned = False

# Shared cross-worker counter when running under multiprocessing. The pool
# initializer (in batch_runner.py) calls install_shared_counter() with an
# mp.Value, and workers atomically increment THAT instead of the local global.
# Falls through to the local global when workers=1 / non-parallel runs.
_shared_counter = None  # type: ignore  # set via install_shared_counter
_shared_lock = None     # type: ignore


def install_shared_counter(counter, lock) -> None:
    """Called by the parent process via multiprocessing.Pool initializer
    to give each worker a handle on the shared mp.Value counter + Lock.
    After install, _do_extract() increments the SHARED counter."""
    global _shared_counter, _shared_lock
    _shared_counter = counter
    _shared_lock = lock

ALLOWED_SOURCE_TYPES = {
    "press_release",
    "news_article",
    "990-PF",
    "sec_filing",
    "university_press",
    "blog",
    "wikipedia",
    "other",
}
ALLOWED_DATE_PRECISION = {"day", "month", "year", None}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

AMOUNT_HALLUCINATION_LIMIT = 1_000_000_000_000  # $1T

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You extract one or more philanthropic-giving events from a news snippet. "
    "Be conservative: only emit an event if the snippet states a concrete giving "
    "action by the named subject. Use the canonical event_role enum.\n\n"
    "GROUNDING RULE — most important: every event you emit MUST be supported by a "
    "verbatim substring in the snippet+title. Copy that substring EXACTLY into "
    "extraction_evidence (no paraphrasing, no extra words). The substring must "
    "contain the recipient name AND, if you set amount_usd, the dollar amount in "
    "some surface form ('$25M', '$25 million', '25,000,000'). If you cannot find "
    "such a substring, do not emit the event — return events: [] for that input.\n\n"
    "If amount is missing from the snippet, set amount_usd=null (don't guess). "
    "Never invent or estimate numbers. Never extract from your training-data "
    "knowledge of the subject; ground every claim in the snippet text only."
)


def _cache_key(url: str, snippet: str, role_hint: str, subject_name: str) -> str:
    raw = f"{url}|{snippet}|{role_hint}|{subject_name}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _tool_schema() -> dict[str, Any]:
    """Tool input schema describing the events array."""
    event_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "event_role": {
                "type": "string",
                "enum": sorted(CANONICAL_EVENT_ROLES),
                "description": "Canonical event role.",
            },
            "year": {
                "type": ["integer", "null"],
                "description": "4-digit year if stated, else null.",
            },
            "date": {
                "type": ["string", "null"],
                "description": "ISO-8601 date if stated, else null.",
            },
            "date_precision": {
                "type": ["string", "null"],
                "enum": ["day", "month", "year", None],
            },
            "donor_entity": {
                "type": "string",
                "description": "Person or foundation named as donor.",
            },
            "recipient": {
                "type": "string",
                "description": "Recipient named, or 'unspecified'.",
            },
            "amount_usd": {
                "type": ["integer", "null"],
                "description": "Dollar amount as integer USD, null if not stated.",
            },
            "source_type": {
                "type": "string",
                "enum": sorted(ALLOWED_SOURCE_TYPES),
            },
            "source_url": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "extraction_note": {
                "type": "string",
                "description": "<= 1 sentence on what the snippet said.",
            },
            "extraction_evidence": {
                "type": "string",
                "description": "Verbatim substring from snippet, <= 30 words.",
            },
        },
        "required": [
            "event_role",
            "year",
            "date",
            "date_precision",
            "donor_entity",
            "recipient",
            "amount_usd",
            "source_type",
            "source_url",
            "confidence",
            "extraction_note",
            "extraction_evidence",
        ],
    }
    return {
        "name": "record_events",
        "description": (
            "Record 0..N philanthropic-giving events extracted from the snippet. "
            "Pass an empty list when the snippet does not describe a concrete "
            "giving action by the named subject."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": event_schema,
                }
            },
            "required": ["events"],
        },
    }


def _build_user_prompt(
    *, subject_name: str, role_hint: str, url: str, title: str, snippet: str
) -> str:
    return (
        f"SUBJECT: {subject_name}\n"
        f"ROLE_HINT (likely event_role from query plan): {role_hint}\n"
        f"URL: {url}\n"
        f"TITLE: {title}\n"
        f"SNIPPET:\n{snippet}\n\n"
        "Extract any concrete giving events the SUBJECT made that the snippet "
        "describes. Use the role_hint as a prior, but override it if the snippet "
        "clearly indicates a different canonical role. Echo the URL into "
        "source_url verbatim.\n\n"
        "YEAR IS REQUIRED. Infer it aggressively from any of: "
        "(a) explicit dates in the snippet/title, (b) the URL slug "
        "(e.g. '2023-01-15-...' or '/2024/03/...'), (c) phrasing like "
        "'last year' or 'in 2022' or 'this past June'. Only return year=null "
        "if NO temporal signal exists anywhere in title+url+snippet. A wrong "
        "year is worse than null, but null without trying is worse than both.\n\n"
        "AMOUNT: only emit a number if the snippet explicitly states one for "
        "this single transaction. NEVER emit cumulative / lifetime / 'total since "
        "X' figures as a single event. NEVER multiply or aggregate amounts.\n\n"
        "Return events: [] if the snippet does not describe a concrete giving "
        "action by the subject."
    )


# Pattern guards: catch role mis-labels the LLM commonly produces.
# Each pattern is checked against the event's `extraction_evidence` (verbatim
# snippet) + `extraction_note` (LLM 1-liner) + recipient + note. If the LLM
# emitted role X but the text matches pattern Y, re-label to Y's canonical role.
import re as _re_guards
_PLEDGE_PHRASES = _re_guards.compile(
    r"\b(pledge|pledged|pledges|will\s+(give|donate|commit)|commits?\s+to\s+give|"
    r"plans?\s+to\s+(donate|give)|promises?\s+to\s+(donate|give)|"
    r"announc(es|ed)?\s+(a|the)?\s*\$?[\d,.]+\s*(million|billion|m|b)?\s+(pledge|commitment))\b",
    _re_guards.IGNORECASE,
)
_POLITICAL_PHRASES = _re_guards.compile(
    r"\b(super\s*PAC|PAC\b|political\s+action\s+committee|campaign\s+committee|"
    r"FEC|federal\s+election|Trump\s+campaign|Biden\s+campaign|Harris\s+campaign|"
    r"Republican\s+(National|party|candidates?)|Democratic\s+(National|party|candidates?)|"
    r"presidential\s+(campaign|inauguration)|2024\s+(election|race)|midterm)\b",
    _re_guards.IGNORECASE,
)
_TRANSFER_TO_OWN_PHRASES = _re_guards.compile(
    r"\b(contributed?\s+to\s+(his|her|their|the)\s+(own|family)?\s*foundation|"
    r"funded\s+(his|her|their|the)\s+foundation|moved\s+\$?[\d,.]+\s*\w*\s+into\s+"
    r"(his|her|their|the)\s+foundation)\b",
    _re_guards.IGNORECASE,
)

# Cardinality red flags: extraction claims a single-recipient gift but the
# evidence text says "across N", "split among N", "to N nonprofits", etc.
# Pattern: number followed by a plural-recipient noun phrase.
_MULTI_RECIPIENT_PHRASES = _re_guards.compile(
    r"\b(across|split\s+among|distributed\s+to|spread\s+across|to|among)\s+"
    r"(\d+|two|three|four|five|six|seven|eight|nine|ten|several|multiple|various|many)\s+"
    r"(universities|colleges|schools|nonprofits|charities|organizations|institutions|"
    r"recipients|groups|causes|hospitals|grantees|partners|projects)\b",
    _re_guards.IGNORECASE,
)

# Cumulative-not-transactional language. The Warren Buffett "$43B cumulative
# giving" article was extracted as a single 2024 event; same risk for any
# "total since X", "lifetime giving", "to date" framing.
_CUMULATIVE_PHRASES = _re_guards.compile(
    # Drops "to date" alone (false-positives on "largest gift to date").
    # Only matches phrases unambiguously denoting a cumulative figure.
    r"\b(cumulative\s+(giving|donations|contributions|total)|"
    r"lifetime\s+(giving|donations|contributions|total)|"
    r"(?:given|donated|contributed)\s+(?:so\s+far|over\s+his\s+lifetime)|"
    r"bringing\s+(?:his|her|their|the)\s+total\s+(?:giving|donations|contributions)|"
    r"since\s+\d{4}\s+(?:has|have)\s+(?:given|donated|contributed)|"
    r"over\s+the\s+(?:past|last)\s+\d+\s+years\s+(?:has|have)\s+(?:given|donated)|"
    r"running\s+total|all-?time\s+(?:giving|donations|contributions)|"
    r"total\s+(?:giving|donations|contributions)\s+(?:since|of\s+\$?\d)|"
    # New patterns from Buffett 2024 audit:
    r"as\s+of\s+\w+\s+\d{4},?\s+(?:he|she|they)\s+(?:had|has)\s+(?:given|donated|contributed)|"
    r"between\s+\d{4}\s+and\s+\d{4}|"
    r"from\s+\d{4}\s+(?:to|through)\s+\d{4}|"
    r"received\s+more\s+than\s+\$[\d.]+\s*(?:billion|million)|"
    r"has\s+(?:received|been\s+given|been\s+gifted)\s+(?:roughly\s+)?\$[\d.]+\s*(?:billion|million)\s+(?:from|by)|"
    # MacKenzie Scott 2025 audit additions:
    r"having\s+(?:given|donated|contributed|distributed)\s+\$?[\d.]+\s*(?:billion|million)|"
    r"in\s+total,?\s+(?:he|she|they)\s+(?:has|have|had)\s+(?:given|donated|contributed)|"
    r"(?:total|all)\s+(?:she|he|they|her|his|their)\s+(?:has|have|had)\s+(?:given|donated|contributed))\b",
    _re_guards.IGNORECASE,
)


def _maybe_relabel(event: dict[str, Any]) -> dict[str, Any]:
    """Apply pattern guards to re-label role if the LLM mis-categorized.
    Mutates event in place (sets `_role_relabeled_from` for audit)."""
    role = event.get("event_role")
    text_blobs = " | ".join(
        str(event.get(k) or "") for k in ("extraction_evidence", "extraction_note", "note")
    )
    new_role = role
    reason = None

    # 1. PAC / FEC language → political (catches: $200M America PAC labeled corporate_gift)
    if role in {"direct_gift", "grant_out", "corporate_gift", "private_investment"}:
        if _POLITICAL_PHRASES.search(text_blobs) or _POLITICAL_PHRASES.search(
            str(event.get("recipient") or "")
        ):
            new_role = "political"
            reason = "matched political_phrases"

    # 2. Pledge / will-give language → pledge (catches: $10B Earth Fund stored as grant_out)
    if role == "grant_out" or role == "direct_gift":
        if _PLEDGE_PHRASES.search(text_blobs):
            new_role = "pledge"
            reason = "matched pledge_phrases"

    # 3. Transfer-to-own-foundation → transfer_in (catches: 1.5M-share gift to own
    #    foundation labeled as direct_gift instead of transfer_in)
    if role == "direct_gift":
        if _TRANSFER_TO_OWN_PHRASES.search(text_blobs):
            new_role = "transfer_in"
            reason = "matched transfer_to_own_phrases"

    if new_role != role:
        event["_role_relabeled_from"] = role
        event["_role_relabel_reason"] = reason
        event["event_role"] = new_role

    # 4. Cardinality guard: claims single-recipient gift but evidence says many.
    #    Don't drop — downgrade confidence and flag so reviewer can split.
    if _MULTI_RECIPIENT_PHRASES.search(text_blobs):
        event["_cardinality_flag"] = "multi_recipient_phrase_detected"
        if event.get("confidence") in ("high", None):
            event["confidence"] = "medium"

    # 5. Cumulative-not-transactional guard: drop the event entirely if the
    #    snippet is reporting a lifetime or cumulative figure rather than a
    #    single discrete gift. Cumulative figures double-count when summed
    #    with the underlying transactions.
    if _CUMULATIVE_PHRASES.search(text_blobs):
        event["_cumulative_flag"] = "cumulative_or_lifetime_phrase_detected"
        # Demote to reference_only so it doesn't add to dollar totals,
        # but preserve the URL as a citation.
        if event.get("event_role") not in {"pledge", "no_pledge", "reference_only"}:
            event["_role_relabeled_from"] = event.get("event_role")
            event["_role_relabel_reason"] = "cumulative_phrase"
            event["event_role"] = "reference_only"

    return event


_HTML_TAG_RE = _re_guards.compile(r"<[^>]+>")
_HTML_ENTITY_RE = _re_guards.compile(r"&(?:quot|amp|lt|gt|nbsp|apos|#\d+|#x[\da-fA-F]+);")


def _normalize_text(s: str) -> str:
    """Lowercase, strip HTML tags + entities, collapse whitespace. Used for
    the `extraction_evidence` substring check — Brave search descriptions
    arrive with raw `<strong>` tags and `&quot;` entities, while the LLM
    usually emits clean text in extraction_evidence. Without normalization,
    a tag inserted between two words breaks the 4-word window check."""
    if not isinstance(s, str):
        return ""
    s = _HTML_TAG_RE.sub(" ", s)
    s = _HTML_ENTITY_RE.sub(" ", s)
    s = s.lower()
    # Collapse whitespace (including newlines).
    s = _re_guards.sub(r"\s+", " ", s).strip()
    return s


def _amount_variants(amount_int: int) -> list[str]:
    """Surface forms an LLM might find an amount in: $25M, $25 million, 25,000,000,
    25 million, etc. The check passes if ANY variant appears in the evidence/snippet."""
    out: list[str] = []
    if amount_int <= 0:
        return out
    # Plain integer with commas + bare integer.
    out.append(f"{amount_int:,}")
    out.append(str(amount_int))
    if amount_int >= 1_000_000_000:
        b = amount_int / 1_000_000_000
        # 1.5b, $1.5b, 1.5 billion, $1.5 billion (also handle whole-number 10b)
        whole = abs(b - round(b)) < 0.05
        if whole:
            out += [f"{round(b)} billion", f"${round(b)} billion",
                    f"{round(b)}b", f"${round(b)}b",
                    f"{round(b)}bn", f"${round(b)}bn"]
        out += [f"{b:.1f} billion", f"${b:.1f} billion",
                f"{b:.1f}b", f"${b:.1f}b",
                f"{b:.2f} billion", f"${b:.2f} billion"]
    if amount_int >= 1_000_000:
        m = amount_int / 1_000_000
        whole = abs(m - round(m)) < 0.05
        if whole:
            out += [f"{round(m)} million", f"${round(m)} million",
                    f"{round(m)}m", f"${round(m)}m",
                    f"{round(m)} mil", f"${round(m)} mil"]
        out += [f"{m:.1f} million", f"${m:.1f} million",
                f"{m:.1f}m", f"${m:.1f}m"]
    if amount_int >= 1_000:
        k = amount_int / 1_000
        whole = abs(k - round(k)) < 0.05
        if whole:
            out += [f"{round(k)},000", f"${round(k)},000",
                    f"{round(k)}k", f"${round(k)}k"]
    # Lowercase everything so the haystack-matching is case-insensitive.
    return [v.lower() for v in out]


def _evidence_anchored(evidence: str, haystack: str, *, min_match_words: int = 4) -> bool:
    """Whether `evidence` appears in `haystack`, allowing for minor LLM tweaks.

    Strategy: split evidence into 4-word windows; require at least one window
    to appear in haystack. This is loose enough to tolerate paraphrasing of
    the boundaries but strict enough to catch fabrication (an evidence string
    invented from whole cloth has no 4-word run that appears verbatim in the
    snippet)."""
    e = _normalize_text(evidence)
    h = _normalize_text(haystack)
    if not e or not h:
        return False
    # Quick win: full evidence is a substring.
    if e in h:
        return True
    words = e.split()
    if len(words) < min_match_words:
        # Evidence too short to do a window check — just require literal substring.
        return False
    # Try longest run that's still meaningfully specific.
    span = max(min_match_words, min(8, len(words)))
    for i in range(len(words) - span + 1):
        window = " ".join(words[i:i + span])
        if window in h:
            return True
    return False


def _validate_event(
    event: dict[str, Any],
    expected_url: str,
    *,
    snippet: str | None = None,
    title: str | None = None,
) -> dict[str, Any] | None:
    """Return the event if valid; else None.

    When `snippet` and `title` are passed, also runs *grounded-evidence*
    checks that drop events whose `extraction_evidence` doesn't appear in
    the snippet+title (i.e. the LLM fabricated the supporting text) or
    whose stated `amount_usd` doesn't appear in any common surface form
    (e.g. "$25M", "25 million", "25,000,000"). These are deterministic,
    no-LLM-cost checks intended to catch the most common extraction
    hallucination mode: the LLM emits a clean structured event whose
    numbers / recipient bear no relation to what the snippet actually said.
    """
    # Pattern-based role re-labeling BEFORE canonical-role check, since the
    # guards may convert e.g. "corporate_gift" -> "political".
    _maybe_relabel(event)
    role = event.get("event_role")
    if role not in CANONICAL_EVENT_ROLES:
        logger.warning("dropping event with non-canonical event_role=%r", role)
        return None

    src_url = event.get("source_url")
    if src_url != expected_url:
        logger.warning(
            "dropping event with source_url=%r != input url=%r", src_url, expected_url
        )
        return None

    amount = event.get("amount_usd")
    if amount is not None:
        try:
            amount_int = int(amount)
        except (TypeError, ValueError):
            logger.warning("dropping event with non-integer amount_usd=%r", amount)
            return None
        if amount_int > AMOUNT_HALLUCINATION_LIMIT:
            logger.warning(
                "dropping event with amount_usd=%r > $1T (likely hallucinated)",
                amount_int,
            )
            return None
        event["amount_usd"] = amount_int

    if event.get("source_type") not in ALLOWED_SOURCE_TYPES:
        logger.warning(
            "coercing unknown source_type=%r to 'other'", event.get("source_type")
        )
        event["source_type"] = "other"

    if event.get("confidence") not in ALLOWED_CONFIDENCE:
        event["confidence"] = "low"

    if event.get("date_precision") not in ALLOWED_DATE_PRECISION:
        event["date_precision"] = None

    # ---- Grounded-evidence checks (only when caller passed snippet/title) ----
    if snippet is not None or title is not None:
        # The LLM prompt feeds url + title + snippet, and URL slugs are a
        # legitimate source of facts (e.g., '/2024/marcus-foundation-awards-
        # 38-million-...'). Include the URL in the haystack so we don't
        # false-drop events whose evidence comes from the slug.
        url_text = (expected_url or "").replace("/", " ").replace("-", " ").replace("_", " ")
        haystack = " ".join(s for s in (title or "", snippet or "", url_text) if s)
        evidence = event.get("extraction_evidence") or ""

        # 1. Evidence must be anchored in the snippet.
        if evidence and not _evidence_anchored(evidence, haystack):
            event["_grounded_check"] = "evidence_not_in_snippet"
            event["confidence"] = "low"
            # If the LLM also asserted a non-trivial dollar amount, drop the
            # event entirely — no anchored evidence + a fabricated amount is
            # the exact pattern deep QA caught (Henry Samueli $30M-vs-$200M,
            # John Doerr $255M, John Mars Smithsonian $5M, Bernard Marcus
            # Autism Speaks $25M).
            if isinstance(event.get("amount_usd"), int) and event["amount_usd"] >= 1_000_000:
                logger.warning(
                    "dropping event: evidence not anchored in snippet and amount=$%s",
                    f"{event['amount_usd']:,}",
                )
                return None

        # 2. Stated amount must appear in some surface form in evidence + snippet.
        amt = event.get("amount_usd")
        if isinstance(amt, int) and amt >= 1_000_000:
            haystack_lower = haystack.lower()
            evidence_lower = (evidence or "").lower()
            variants = _amount_variants(amt)
            found = any(v in haystack_lower or v in evidence_lower for v in variants)
            if not found:
                logger.warning(
                    "dropping event: amount $%s not found in any surface form in snippet",
                    f"{amt:,}",
                )
                return None

    return event


def _call_anthropic(
    *, subject_name: str, role_hint: str, url: str, title: str, snippet: str
) -> list[dict[str, Any]]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=api_key)
    tool = _tool_schema()
    user_prompt = _build_user_prompt(
        subject_name=subject_name,
        role_hint=role_hint,
        url=url,
        title=title,
        snippet=snippet,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_events"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_events":
            data = block.input or {}
            events = data.get("events", [])
            if not isinstance(events, list):
                logger.warning("tool returned non-list events: %r", events)
                return []
            return events

    logger.warning("model did not invoke record_events tool")
    return []


def extract_events(
    *,
    url: str,
    title: str,
    snippet: str,
    role_hint: str,
    subject_name: str,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Extract 0..N candidate events from a snippet via Claude Haiku 4.5.

    Cached at ``regen_v3/cache/extract/<sha>.json`` keyed by
    ``sha256(url|snippet|role_hint|subject_name)``. Re-runs are free.
    Raises ``RuntimeError`` if ``ANTHROPIC_API_KEY`` is missing AND no cache hit.
    """
    key = _cache_key(url, snippet, role_hint, subject_name)

    if not refresh:
        cached = _read_cache(key)
        if cached is not None:
            return cached.get("events", [])

    # Cost cap: bail before making the LLM call if the per-process budget
    # is exhausted. Counts only LIVE calls; cache hits are free above.
    global _live_call_count, _cap_warned
    # Use shared mp.Value counter when running under multiprocessing.Pool;
    # falls through to the local global when workers=1 / non-parallel.
    if _shared_counter is not None and _shared_lock is not None:
        with _shared_lock:
            cur = _shared_counter.value
            if cur >= _MAX_EXTRACT_CALLS:
                if not _cap_warned:
                    logger.warning(
                        "MAX_EXTRACT_CALLS=%d reached (shared across workers); "
                        "remaining LLM extracts will be skipped.",
                        _MAX_EXTRACT_CALLS,
                    )
                    _cap_warned = True
                return []
            _shared_counter.value = cur + 1
    else:
        if _live_call_count >= _MAX_EXTRACT_CALLS:
            if not _cap_warned:
                logger.warning(
                    "MAX_EXTRACT_CALLS=%d reached; remaining LLM extracts will be "
                    "skipped (returns []). Override via env var.",
                    _MAX_EXTRACT_CALLS,
                )
                _cap_warned = True
            return []
        _live_call_count += 1

    try:
        raw_events = _call_anthropic(
            subject_name=subject_name,
            role_hint=role_hint,
            url=url,
            title=title,
            snippet=snippet,
        )
    except RuntimeError:
        # No key. If we got here with refresh=True, fall back to cache anyway.
        cached = _read_cache(key)
        if cached is not None:
            return cached.get("events", [])
        raise

    validated: list[dict[str, Any]] = []
    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        ok = _validate_event(ev, expected_url=url, snippet=snippet, title=title)
        if ok is not None:
            validated.append(ok)

    # Cache files are content-addressed by input hash; omit wall-clock
    # `cached_at` so two extractor runs against the same input produce
    # byte-identical caches. File mtime preserves fetch-time provenance.
    payload = {
        "input_key": key,
        "events": validated,
        "model": MODEL,
    }
    _write_cache(key, payload)
    return validated


# -- tests ------------------------------------------------------------------


def _test_cache_roundtrip() -> None:
    """Write a synthetic cache entry, read it back, confirm shape."""
    url = "https://example.com/test"
    snippet = "Synthetic snippet for cache test."
    role_hint = "pledge"
    subject_name = "Test Subject"
    key = _cache_key(url, snippet, role_hint, subject_name)

    fake_event = {
        "event_role": "pledge",
        "year": 2020,
        "date": None,
        "date_precision": None,
        "donor_entity": "Test Subject",
        "recipient": "unspecified",
        "amount_usd": None,
        "source_type": "other",
        "source_url": url,
        "confidence": "low",
        "extraction_note": "synthetic",
        "extraction_evidence": "Synthetic snippet for cache test.",
    }
    _write_cache(
        key,
        {
            "input_key": key,
            "events": [fake_event],
            "model": MODEL,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    out = extract_events(
        url=url,
        title="Test",
        snippet=snippet,
        role_hint=role_hint,
        subject_name=subject_name,
    )
    assert len(out) == 1, f"expected 1 cached event, got {len(out)}"
    assert out[0]["event_role"] == "pledge"
    assert out[0]["source_url"] == url
    print("[ok] cache roundtrip: cached event read back correctly")

    # Cleanup synthetic cache file so future live runs aren't poisoned.
    _cache_path(key).unlink(missing_ok=True)


def _test_live_bezos() -> None:
    url = (
        "https://www.cnbc.com/2020/02/17/jeff-bezos-pledges-10-billion-to-fight-"
        "climate-change-via-bezos-earth-fund.html"
    )
    title = "Jeff Bezos pledges $10 billion..."
    snippet = (
        "Amazon CEO Jeff Bezos announced Monday a $10 billion commitment to "
        "fight climate change through a new Bezos Earth Fund."
    )
    role_hint = "pledge"
    subject_name = "Jeff Bezos"

    # Ensure clean state for this exact key so we measure a real API call first.
    key = _cache_key(url, snippet, role_hint, subject_name)
    _cache_path(key).unlink(missing_ok=True)

    t0 = time.time()
    events = extract_events(
        url=url,
        title=title,
        snippet=snippet,
        role_hint=role_hint,
        subject_name=subject_name,
    )
    dt_first = time.time() - t0
    print(f"[ok] live call returned {len(events)} event(s) in {dt_first:.2f}s")
    assert len(events) >= 1, "expected at least one event"

    # Find an event with the expected ~$10B amount and a plausible role.
    plausible = [
        e
        for e in events
        if (e.get("amount_usd") is not None and 9e9 <= e["amount_usd"] <= 1.1e10)
        and e.get("event_role") in {"pledge", "announcement"}
    ]
    assert plausible, f"no plausible Bezos pledge event found in: {events}"
    print(
        f"[ok] plausible event: role={plausible[0]['event_role']} "
        f"amount=${plausible[0]['amount_usd']:,}"
    )

    # Now verify cache hit: second call should be much faster and identical.
    t0 = time.time()
    events2 = extract_events(
        url=url,
        title=title,
        snippet=snippet,
        role_hint=role_hint,
        subject_name=subject_name,
    )
    dt_second = time.time() - t0
    assert events2 == events, "cached result differs from first call"
    assert dt_second < 0.5, (
        f"second call took {dt_second:.2f}s — cache appears to have missed"
    )
    print(f"[ok] cache hit: second call in {dt_second:.3f}s (no API)")


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[skip] ANTHROPIC_API_KEY not set; running cache-roundtrip test only")
        _test_cache_roundtrip()
        return

    print("[run] ANTHROPIC_API_KEY present; running cache-roundtrip + live tests")
    _test_cache_roundtrip()
    _test_live_bezos()
    print("[done] all tests passed")


if __name__ == "__main__":
    _main()
