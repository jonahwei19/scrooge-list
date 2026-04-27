"""Merge regen_v3 candidate events into an existing v3 record.

Contract:
  merge_candidates(record, candidates, *, run_id, extractor_model)
      -> (new_record, diff_report)

Routing:
  event_role in {grant_out, direct_gift, transfer_in, political,
                 private_investment, corporate_gift}        -> cited_events
  event_role in {pledge, no_pledge, announcement}           -> pledges_and_announcements
  event_role == reference_only                              -> sources_all only
  unknown role                                              -> dropped, counted

Preservation:
  Manual / unprovenanced events are sacred. Only entries already stamped
  provenance == "regen_v3" can be displaced by a higher-confidence candidate.

Dedupe key:
  (year, canonical_role(event_role), amount_bucket)
  amount_bucket = round(amount_usd / 1e6) if amount_usd else None
  Tolerance: within +/- 5% of the existing amount counts as a collision even
  if the bucket integer differs.

Fabricated URLs:
  Hard-load the DEAD_URLS.md "likely fabricated" set. Any candidate with
  a source_url in that set is refused and logged to skipped_fabricated.
  URLs flagged as rotted (live-but-dead-link or never_existed_not_signer)
  pass through but the entry gets a source_verification_status stamp.

No file I/O for production code. The CLI is responsible for writing.
See SPEC.md for the broader pipeline design.
"""

from __future__ import annotations

import copy
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Make the parent scrooge/ importable when this module is run with
# `python3 -m regen_v3.merge` from the project root.
_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from aggregate_v3 import OBSERVABLE_ROLES, canonical_role  # noqa: E402

# ---------------------------------------------------------------------------
# Routing tables
# ---------------------------------------------------------------------------

CITED_EVENT_ROLES: frozenset[str] = frozenset({
    "grant_out",
    "direct_gift",
    "transfer_in",
    "political",
    "private_investment",
    "corporate_gift",
})

PLEDGE_ANNOUNCEMENT_ROLES: frozenset[str] = frozenset({
    "pledge",
    "no_pledge",
    "announcement",
})

REFERENCE_ONLY_ROLES: frozenset[str] = frozenset({"reference_only"})

# Confidence ordering for candidate-vs-candidate ties.
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


# Fabricated URL set: re-exported from `_fabricated`, the single
# source of truth shared with `search.py`. To add or remove a fabrication,
# edit DEAD_URLS.md (the loader picks it up at next interpreter start).
from regen_v3._fabricated import LIKELY_FABRICATED  # noqa: E402, F401

# URLs known to 404 because the subject never signed the Giving Pledge.
# Allowed through (the absence is the citation) but stamped accordingly.
DEAD_LINK_NEVER_SIGNER: frozenset[str] = frozenset({
    "https://www.givingpledge.org/pledger/haim-saban/",
    "https://www.givingpledge.org/pledger/henry-kravis/",
})

# URLs that are rotted but were once real. Allow through with a warning stamp.
DEAD_LINK_ROTTED: frozenset[str] = frozenset({
    "https://blogs.und.edu/uletter/2012/09/und-announces-14-million-in-private-public-partnership-funding-and-the-naming-of-the-harold-hamm-school-of-geology-and-geological-engineering-at-the-college-of-engineering-and-mines/",
    "https://philanthropy.com/article/melinda-french-gates-announces-where-1-billion-in_new-funds-will-go-to-help-women-and-girls",
    "https://opb.org/article/2025/12/16/oregon-phil-penny-knight-donation-ohsu-tops-charitable-list/",
    "https://strivetogether.org/news/ballmer-group-pledges-60-million-strivetogether/",
    # CNBC missing-extension pair — kept as rotted (re-add .html in a follow-up).
    "https://cnbc.com/2020/01/09/billionaire-barry-diller-us-should-get-rid-of-paid-political-ads",
    "https://cnbc.com/2022/10/24/how-googles-former-ceo-eric-schmidt-helped-write-ai-laws-in-washington-without-publicly-disclosing-investments-in-a-i-start-ups.html",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _amount_bucket(amount_usd: Any) -> int | None:
    if not isinstance(amount_usd, (int, float)) or amount_usd <= 0:
        return None
    return round(float(amount_usd) / 1e6)


def _within_tolerance(a: float | None, b: float | None, pct: float = 0.05) -> bool:
    """True if a and b are within +/- pct of each other (or both None/zero)."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if a == 0 or b == 0:
        return a == b
    diff = abs(a - b)
    return diff <= max(abs(a), abs(b)) * pct


_RECIPIENT_NOISE_RE = re.compile(r"\b(the|inc|inc\.|llc|foundation|fund|trust|charitable|family|center|university|college|school|institute|hospital)\b", re.IGNORECASE)


def _normalize_recipient(name: str | None) -> str | None:
    """Return a token-bag string for fuzzy recipient matching in dedupe.

    Keeps the meaningful tokens (drops articles, common org-suffix noise),
    lowercases, and sorts so word-order doesn't matter. Empty / generic
    placeholders ("various", "unspecified", "multiple") return None so they
    don't false-positive collide.
    """
    if not isinstance(name, str):
        return None
    s = name.strip().lower()
    if not s:
        return None
    # Generic placeholders — don't dedupe by these.
    if s in {"various", "unspecified", "multiple", "n/a", "unknown"}:
        return None
    # Strip common noise tokens, keep distinctive ones.
    s = _RECIPIENT_NOISE_RE.sub(" ", s)
    tokens = [t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= 3]
    if not tokens:
        return None
    return " ".join(sorted(set(tokens)))


def _dedupe_key(entry: dict) -> tuple[int | None, str | None, int | None, str | None]:
    """Return (year, role, amount_bucket, recipient_norm) for dedupe.

    Adding recipient_norm catches two extracts of the same gift that
    landed in different roles (e.g., a Bezos $10B Earth Fund event
    extracted once as `direct_gift` and once as `grant_out`). When
    recipient is generic / missing, falls back to the prior 3-tuple
    behavior so we don't over-collide unrelated events.
    """
    year = entry.get("year") if isinstance(entry.get("year"), int) else None
    role = canonical_role(entry.get("event_role"))
    bucket = _amount_bucket(entry.get("amount_usd"))
    recipient = _normalize_recipient(entry.get("recipient"))
    return (year, role, bucket, recipient)


def _has_regen_provenance(entry: dict) -> bool:
    return entry.get("provenance") == "regen_v3"


def _is_protected(entry: dict) -> bool:
    """Manual or unprovenanced entries are sacred and never get touched."""
    if not isinstance(entry, dict):
        return True
    prov = entry.get("provenance")
    if prov is None:
        return True
    if prov == "manual":
        return True
    return False


def _confidence_rank(entry: dict) -> int:
    return _CONFIDENCE_RANK.get(entry.get("confidence"), 0)


def _subject_id(record: dict) -> str:
    person = record.get("person") or {}
    name = person.get("name_display") or "unknown"
    return name.lower().replace(" ", "_")


def _retrieved_at_from_run_id(run_id: str) -> str | None:
    """Derive a deterministic `retrieved_at` from the run_id.

    * If `run_id` has a parseable ISO date prefix (`YYYY-MM-DD…`), use it.
    * Otherwise — including the content-addressed `sha256-…` form — return
      None so the caller omits the field entirely. We deliberately do NOT
      fall back to `datetime.now()`: that would make merged output
      wall-clock dependent, defeating reproducibility.
    """
    if isinstance(run_id, str) and len(run_id) >= 10:
        head = run_id[:10]
        try:
            datetime.strptime(head, "%Y-%m-%d")
            return head
        except ValueError:
            pass
    return None


def _publisher_for(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.removeprefix("www.")
    except Exception:
        return ""


def _stamp_provenance(entry: dict, *, run_id: str, extractor_model: str) -> dict:
    """Add the regen_v3 provenance fields to a fresh candidate dict."""
    entry["provenance"] = "regen_v3"
    entry["regen_run_id"] = run_id
    entry["regen_query"] = entry.get("regen_query", "")
    entry["regen_extractor_model"] = extractor_model
    return entry


def _classify_url(url: str) -> str | None:
    """Return source_verification_status for known dead URLs, else None."""
    if not isinstance(url, str):
        return None
    if url in DEAD_LINK_NEVER_SIGNER:
        return "dead_link_never_existed_not_signer"
    if url in DEAD_LINK_ROTTED:
        return "dead_link_rotted"
    return None


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _route_for(role: str | None) -> str | None:
    """Return one of {'cited_events', 'pledges_and_announcements',
    'sources_all', None} based on the canonical role."""
    if role is None:
        return None
    if role in CITED_EVENT_ROLES:
        return "cited_events"
    if role in PLEDGE_ANNOUNCEMENT_ROLES:
        return "pledges_and_announcements"
    if role in REFERENCE_ONLY_ROLES:
        return "sources_all"
    return None


# ---------------------------------------------------------------------------
# Core merge
# ---------------------------------------------------------------------------


def merge_candidates(
    record: dict,
    candidates: list[dict],
    *,
    run_id: str,
    extractor_model: str,
) -> tuple[dict, dict]:
    """Merge a list of regen_v3 candidate events into an existing v3 record.

    See module docstring for routing, preservation, dedupe, and fabricated-URL
    rules. Returns (new_record, diff_report). Does NOT write to disk.
    """
    new_record = copy.deepcopy(record)
    new_record.setdefault("cited_events", [])
    new_record.setdefault("pledges_and_announcements", [])
    new_record.setdefault("sources_all", [])

    diff_report: dict[str, Any] = {
        "added_cited_events": 0,
        "added_pledges_and_announcements": 0,
        "added_sources_all": 0,
        "skipped_duplicate": [],
        "skipped_fabricated": [],
        "skipped_unknown_role": [],
    }

    # Index existing events by dedupe key for fast collision checks.
    # Each value is a list of (bucket_index_in_list, entry_dict, list_name).
    existing_index: dict[tuple[int | None, str | None, int | None], list[tuple[int, dict, str]]] = {}
    for list_name in ("cited_events", "pledges_and_announcements"):
        for idx, entry in enumerate(new_record[list_name]):
            if not isinstance(entry, dict):
                continue
            key = _dedupe_key(entry)
            existing_index.setdefault(key, []).append((idx, entry, list_name))

    # Track per-(year, role) regen-add counters for event_id generation.
    subject_id = _subject_id(new_record)
    regen_counter: dict[tuple[int | None, str], int] = {}
    for list_name in ("cited_events", "pledges_and_announcements"):
        for entry in new_record[list_name]:
            if not isinstance(entry, dict):
                continue
            if entry.get("provenance") != "regen_v3":
                continue
            year = entry.get("year") if isinstance(entry.get("year"), int) else None
            role = canonical_role(entry.get("event_role")) or "unknown"
            regen_counter[(year, role)] = regen_counter.get((year, role), 0) + 1

    # Track candidates we already accepted in this run, keyed by dedupe key,
    # so candidate-vs-candidate collisions can pick the higher-confidence one.
    accepted_by_key: dict[tuple[int | None, str | None, int | None], tuple[int, dict, str]] = {}

    # ---- Phase 1: candidate routing + dedupe + add ------------------------
    for cand in candidates:
        if not isinstance(cand, dict):
            diff_report["skipped_unknown_role"].append({
                "why": "candidate is not a dict",
                "candidate": cand,
            })
            continue

        url = cand.get("source_url")

        # Fabricated URL refusal — applies regardless of role.
        if isinstance(url, str) and url in LIKELY_FABRICATED:
            diff_report["skipped_fabricated"].append({
                "why": f"source_url in LIKELY_FABRICATED: {url}",
                "candidate": cand,
            })
            continue

        raw_role = cand.get("event_role")
        role = canonical_role(raw_role)
        route = _route_for(role)

        if route is None:
            diff_report["skipped_unknown_role"].append({
                "why": f"unknown or unrouteable event_role: {raw_role!r} -> {role!r}",
                "candidate": cand,
            })
            continue

        # reference_only never becomes an event; handled in phase 2 below
        # via the sources_all loop. Don't drop yet — we still want its URL.
        if route == "sources_all":
            continue

        # Collision check vs existing entries.
        key = _dedupe_key(cand)
        cand_amt = cand.get("amount_usd")

        collision = None
        # Strict-key collisions (same year, same role, same bucket).
        for idx, existing_entry, list_name in existing_index.get(key, []):
            collision = (idx, existing_entry, list_name)
            break
        # Tolerance-based collisions: same year + same role, amount within +/- 5%.
        if collision is None and cand_amt is not None:
            for ek, items in existing_index.items():
                ek_year, ek_role, _ek_bucket, _ek_recipient = ek
                if ek_year != key[0] or ek_role != key[1]:
                    continue
                for idx, existing_entry, list_name in items:
                    if _within_tolerance(existing_entry.get("amount_usd"), cand_amt):
                        collision = (idx, existing_entry, list_name)
                        break
                if collision is not None:
                    break

        # Cross-role collision: same (year, recipient_normalized, amount-bucket)
        # but different roles — catches the case Codex flagged where the same
        # gift gets extracted under both `direct_gift` and `grant_out`.
        if collision is None and key[3] is not None and key[2] is not None:
            for ek, items in existing_index.items():
                if ek[0] != key[0] or ek[3] != key[3]:
                    continue
                if cand_amt is None:
                    if ek[2] == key[2]:  # exact bucket match
                        for idx, existing_entry, list_name in items:
                            collision = (idx, existing_entry, list_name)
                            break
                else:
                    for idx, existing_entry, list_name in items:
                        if _within_tolerance(existing_entry.get("amount_usd"), cand_amt):
                            collision = (idx, existing_entry, list_name)
                            break
                if collision is not None:
                    break

        if collision is not None:
            idx, existing_entry, list_name = collision
            if _is_protected(existing_entry):
                diff_report["skipped_duplicate"].append({
                    "why": f"manual/unprovenanced entry wins on key {key}",
                    "candidate": cand,
                })
                continue
            # Existing entry is regen_v3: replace only if candidate is strictly
            # higher confidence. Otherwise skip.
            if _confidence_rank(cand) > _confidence_rank(existing_entry):
                replacement = _build_event_from_candidate(
                    cand,
                    role=role,
                    subject_id=subject_id,
                    regen_counter=regen_counter,
                    run_id=run_id,
                    extractor_model=extractor_model,
                )
                new_record[list_name][idx] = replacement
                # Refresh index entry for this key with the new dict.
                existing_index[key] = [(idx, replacement, list_name)]
                # Don't increment add counters — this is a swap, not an add.
                continue
            diff_report["skipped_duplicate"].append({
                "why": (
                    f"regen_v3 entry already at key {key} with confidence "
                    f"{existing_entry.get('confidence')!r}; candidate not stronger"
                ),
                "candidate": cand,
            })
            continue

        # Candidate-vs-candidate collision in this same run.
        if key in accepted_by_key:
            prior_idx, prior_entry, prior_list = accepted_by_key[key]
            cand_rank = _confidence_rank(cand)
            prior_rank = _confidence_rank(prior_entry)
            if cand_rank > prior_rank or (
                cand_rank == prior_rank
                and (cand.get("source_url") or "") < (prior_entry.get("source_url") or "")
            ):
                replacement = _build_event_from_candidate(
                    cand,
                    role=role,
                    subject_id=subject_id,
                    regen_counter=regen_counter,
                    run_id=run_id,
                    extractor_model=extractor_model,
                    # Reuse the already-issued event_id so the regen counter
                    # doesn't drift when we swap a same-run candidate.
                    reuse_event_id=prior_entry.get("event_id"),
                )
                new_record[prior_list][prior_idx] = replacement
                accepted_by_key[key] = (prior_idx, replacement, prior_list)
                existing_index[key] = [(prior_idx, replacement, prior_list)]
            else:
                diff_report["skipped_duplicate"].append({
                    "why": f"another candidate already accepted at key {key}",
                    "candidate": cand,
                })
            continue

        # Fresh add.
        event = _build_event_from_candidate(
            cand,
            role=role,
            subject_id=subject_id,
            regen_counter=regen_counter,
            run_id=run_id,
            extractor_model=extractor_model,
        )
        target_list_name = route  # cited_events or pledges_and_announcements
        new_record[target_list_name].append(event)
        new_idx = len(new_record[target_list_name]) - 1
        existing_index.setdefault(key, []).append((new_idx, event, target_list_name))
        accepted_by_key[key] = (new_idx, event, target_list_name)
        if target_list_name == "cited_events":
            diff_report["added_cited_events"] += 1
        else:
            diff_report["added_pledges_and_announcements"] += 1

    # ---- Phase 2: bibliography (sources_all) ------------------------------
    retrieved_at = _retrieved_at_from_run_id(run_id)
    existing_urls = set()
    for src in new_record["sources_all"]:
        if isinstance(src, dict) and isinstance(src.get("url"), str):
            existing_urls.add(src["url"])

    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        url = cand.get("source_url")
        if not isinstance(url, str) or not url:
            continue
        if url in LIKELY_FABRICATED:
            # already counted in skipped_fabricated; never let it into bib
            continue
        if url in existing_urls:
            continue
        bib_entry: dict[str, Any] = {
            "publisher": _publisher_for(url),
            "url": url,
            "provenance": "regen_v3",
            "regen_run_id": run_id,
        }
        if retrieved_at is not None:
            bib_entry["retrieved_at"] = retrieved_at
        status = _classify_url(url)
        if status:
            bib_entry["source_verification_status"] = status
        new_record["sources_all"].append(bib_entry)
        existing_urls.add(url)
        diff_report["added_sources_all"] += 1

    # ---- Phase 3: top-level provenance / generated-by --------------------
    # `generated_at` mirrors the ISO date prefix of run_id when it is one,
    # otherwise we leave whatever the prior record carried in place — the
    # run_id itself is the canonical provenance handle.
    if retrieved_at is not None:
        new_record["generated_at"] = retrieved_at

    existing_gb = new_record.get("generated_by") or ""
    suffix = f" + regen_v3@{run_id}"
    if isinstance(existing_gb, str) and existing_gb.startswith("scrooge v3 manual"):
        if suffix not in existing_gb:
            new_record["generated_by"] = existing_gb + suffix
    elif isinstance(existing_gb, str) and existing_gb:
        if "regen_v3@" not in existing_gb:
            new_record["generated_by"] = existing_gb + suffix
    else:
        new_record["generated_by"] = f"regen_v3@{run_id}"

    return new_record, diff_report


def _build_event_from_candidate(
    cand: dict,
    *,
    role: str,
    subject_id: str,
    regen_counter: dict[tuple[int | None, str], int],
    run_id: str,
    extractor_model: str,
    reuse_event_id: str | None = None,
) -> dict:
    """Assemble a fresh event dict from a candidate, with provenance + id."""
    event: dict[str, Any] = copy.deepcopy(cand)

    # Normalize the canonical event_role (preserve original if already canonical).
    event["event_role"] = role

    year = event.get("year") if isinstance(event.get("year"), int) else None

    if reuse_event_id:
        event["event_id"] = reuse_event_id
    else:
        bucket_key = (year, role)
        regen_counter[bucket_key] = regen_counter.get(bucket_key, 0) + 1
        n = regen_counter[bucket_key]
        year_part = year if year is not None else "x"
        event["event_id"] = f"{subject_id}_{role}_{year_part}_regen{n}"

    _stamp_provenance(event, run_id=run_id, extractor_model=extractor_model)

    # Stamp dead-link statuses where applicable, but never overwrite an
    # existing status the candidate brought in (extractor-supplied wins).
    url = event.get("source_url")
    if isinstance(url, str):
        if "source_verification_status" not in event:
            status = _classify_url(url)
            if status:
                event["source_verification_status"] = status

    return event


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _selftest() -> int:
    import json

    here = Path(__file__).resolve().parent.parent
    data_path = here / "data" / "henry_kravis.v3.json"
    with data_path.open() as f:
        record = json.load(f)

    original_first_event = copy.deepcopy(record["cited_events"][0])

    run_id = "2026-04-25T17:00:00Z"
    extractor_model = "claude-haiku-4-5"

    # Build synthetic candidates:
    candidates = [
        # 1) New grant_out, no collision (year 2016 has NO 990-PF event in record).
        {
            "event_role": "grant_out",
            "year": 2016,
            "donor_entity": "The Marie-Josee and Henry R. Kravis Foundation",
            "amount_usd": 35_000_000,
            "source_url": "https://projects.propublica.org/nonprofits/organizations/133341521/201712809349100307/full",
            "source_type": "990-PF",
            "confidence": "high",
            "regen_query": '"Marie-Josee and Henry R. Kravis Foundation" 990-PF 2016',
            "extraction_note": "FY2016 grants per 990-PF summary",
        },
        # 2) Collision with existing manual event (kravis_mjhkf_2024 = $45.4M).
        # Same year + same canonical role + amount within 5%. Should SKIP.
        {
            "event_role": "grant_out",
            "year": 2024,
            "donor_entity": "MJHKF",
            "amount_usd": 45_500_000,
            "source_url": "https://example.com/duplicate-2024",
            "source_type": "990-PF",
            "confidence": "high",
            "regen_query": "test collision",
        },
        # 3) Fabricated URL — should SKIP.
        {
            "event_role": "direct_gift",
            "year": 2012,
            "donor_entity": "MJHKF",
            "amount_usd": 75_000_000,
            "source_url": "https://www.cmc.edu/news/kravis-foundation-75-million-gift-announced/9266",
            "source_type": "announcement",
            "confidence": "medium",
            "regen_query": '"Henry Kravis" CMC',
        },
        # 4) Fresh announcement — no existing announcement events on record.
        {
            "event_role": "announcement",
            "year": 2025,
            "donor_entity": "Henry R. Kravis",
            "amount_usd": None,
            "source_url": "https://example.com/kravis-2025-announcement",
            "source_type": "news_article",
            "confidence": "medium",
            "regen_query": '"Henry Kravis" announces 2025',
            "extraction_note": "Hypothetical announcement for test",
        },
        # 5) reference_only — should land in sources_all only.
        {
            "event_role": "reference_only",
            "year": 2026,
            "source_url": "https://www.forbes.com/profile/henry-kravis/",
            "source_type": "news_article",
            "confidence": "high",
            "regen_query": "forbes profile",
        },
        # 6) Unknown role — should be dropped.
        {
            "event_role": "totally_made_up_role",
            "year": 2025,
            "amount_usd": 1_000_000,
            "source_url": "https://example.com/junk",
            "confidence": "low",
        },
    ]

    new_record, diff = merge_candidates(
        record,
        candidates,
        run_id=run_id,
        extractor_model=extractor_model,
    )

    print("=== diff_report ===")
    for k in (
        "added_cited_events",
        "added_pledges_and_announcements",
        "added_sources_all",
    ):
        print(f"  {k}: {diff[k]}")
    for k in ("skipped_duplicate", "skipped_fabricated", "skipped_unknown_role"):
        print(f"  {k}: {len(diff[k])}")
        for item in diff[k]:
            print(f"     - {item['why']}")

    # ----- Assertions -----
    assert diff["added_cited_events"] == 1, (
        f"expected 1 cited_event added, got {diff['added_cited_events']}"
    )
    assert diff["added_pledges_and_announcements"] == 1, (
        f"expected 1 announcement added, got {diff['added_pledges_and_announcements']}"
    )
    assert len(diff["skipped_duplicate"]) == 1, (
        f"expected 1 skipped_duplicate, got {len(diff['skipped_duplicate'])}"
    )
    assert len(diff["skipped_fabricated"]) == 1, (
        f"expected 1 skipped_fabricated, got {len(diff['skipped_fabricated'])}"
    )
    assert len(diff["skipped_unknown_role"]) == 1, (
        f"expected 1 skipped_unknown_role, got {len(diff['skipped_unknown_role'])}"
    )

    # The first cited event in the original was a manual entry — confirm
    # nothing about it changed.
    assert new_record["cited_events"][0] == original_first_event, (
        "manual cited_events[0] was mutated"
    )

    # generated_at + generated_by stamping
    assert new_record["generated_at"] == run_id[:10], "generated_at not bumped"
    assert "regen_v3@" in (new_record.get("generated_by") or ""), "generated_by missing regen marker"
    assert "manual" in (new_record.get("generated_by") or ""), "manual marker lost"

    # Run validate_v3.check on the merged record AND on the original record;
    # gate is "merge introduced no new errors", since the kravis manual record
    # already carries pre-existing fabricated-URL errors (which is why
    # DEAD_URLS.md exists).
    from validate_v3 import check  # noqa: WPS433
    pre_errors, _ = check(record, data_path)
    post_errors, post_warnings = check(new_record, data_path)
    new_errors = [e for e in post_errors if e not in pre_errors]
    print("\n=== validate_v3.check (post-merge) ===")
    print(f"  errors total:       {len(post_errors)}")
    print(f"  errors pre-existing:{len(pre_errors)}")
    print(f"  errors NEW from merge: {len(new_errors)}")
    for e in new_errors:
        print(f"    NEW ERROR  {e}")
    print(f"  warnings: {len(post_warnings)}")

    if new_errors:
        print("\nFAIL — merge.py introduced new validator errors")
        return 1
    print("\nOK — merge.py self-test passed (no new validator errors introduced)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
