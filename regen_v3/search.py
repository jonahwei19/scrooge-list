"""Brave Search REST wrapper with disk-cache.

Stage 2 of the regen_v3 pipeline (see SPEC.md). Deterministic by design:
sha256(normalized query) keys the cache; same input -> identical JSON.

No CLI here. The host (`regen_v3.cli`) owns argument parsing and
orchestration. This module exposes two callables:

    search(query, *, count=10, refresh=False) -> dict
    filter_results(results) -> tuple[list, list]
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache" / "search"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
PROVIDER = "brave-search-api-v1"
RATE_LIMIT_SECONDS = 1.05  # Brave free tier: 1 req/sec; pad slightly.

# Reuse Safari UA pattern from check_urls.py so anti-bot defenses don't
# distort what Brave returns to us. Brave itself only needs the auth header,
# but matching the rest of the codebase keeps requests uniform.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

ALLOWLIST_DOMAINS: frozenset[str] = frozenset({
    "forbes.com",
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "philanthropy.com",
    "wsj.com",
    "nytimes.com",
    "washingtonpost.com",
    "opb.org",
    "npr.org",
    "propublica.org",
    "candid.org",
    "foundationcenter.org",
    "fec.gov",
    "sec.gov",
    "irs.gov",
    "givingpledge.org",
    "givinginstitute.org",
    "ap.org",
    "apnews.com",
    "theguardian.com",
    # Investigative-journalism outlets (added: surface late-revealed gifts,
    # leaked filings, dark-giving exposés that announcement-style queries miss).
    "icij.org",
    "occrp.org",
    "themarkup.org",
    "revealnews.org",
    "theintercept.com",
    "motherjones.com",
    # Foreign / international investigative desks.
    "bbc.com",
    "bbc.co.uk",
    "sueddeutsche.de",
    "lemonde.fr",
    "haaretz.com",
    "ft.com",
})

BLOCKLIST_DOMAINS: frozenset[str] = frozenset({
    "insidephilanthropy.com",
    "nationaltoday.com",
    "heartlandforward.org",
    # Audit-flagged 2026-04-26: aggregator / wiki-clone / unverified-news / typosquat
    "caproasia.com",         # rewrites of other outlets, no editorial verification
    "grokipedia.com",        # AI-generated wiki clone
    "dnyuz.com",             # NYT republisher / aggregator
    "newstral.com",          # German news aggregator scraping other outlets
    "technewsjunkies.com",   # low-editorial tech aggregator
    "elonmskgrantdonations.org",  # TYPOSQUAT (missing 'u' in 'musk') — fake domain
    "techstory.in",          # low-editorial Indian tech aggregator
})

# Re-exported from `_fabricated` so search.py and merge.py share one
# canonical refusal list. To add or remove a fabrication, edit DEAD_URLS.md
# (the loader picks it up at next interpreter start).
from regen_v3._fabricated import LIKELY_FABRICATED as FABRICATED_URLS  # noqa: E402


def _domain_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _registrable_root(host: str) -> str:
    """Return the last two labels of a host (best-effort eTLD+1).

    For our allowlist we only care about exact second-level matches like
    `forbes.com` or `nytimes.com`. This is intentionally simple: hosts under
    `news.forbes.com` should still match `forbes.com`. Falls back to the host
    itself when fewer than two labels are present.
    """
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _cache_key(query: str) -> str:
    normalized = query.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _api_key() -> str | None:
    """Accept either BRAVE_SEARCH_API_KEY (canonical) or BRAVE_API_KEY (the
    name used by Jonah's brave-search MCP config). First non-empty wins."""
    for k in ("BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"):
        v = os.environ.get(k)
        if v:
            return v
    return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # sort_keys for byte-identical re-runs on cache-hit re-serialization callers.
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


# Process-local timestamp of the last live (non-cached) Brave call. Used to
# enforce the 1 req/sec rate limit only when we actually hit the network.
_last_live_call_ts: float = 0.0

# Shared cross-worker rate-limit state when running under multiprocessing.
# batch_runner.py installs an mp.Value (timestamp) + mp.Lock via the pool
# initializer so all workers share a single Brave 1-req/sec budget. Falls
# through to the local global when workers=1.
_shared_ts = None  # type: ignore
_shared_lock = None  # type: ignore


def install_shared_rate_limiter(ts_value, lock) -> None:
    """Called by parent via Pool initializer. Workers atomically read+update
    the shared mp.Value timestamp instead of the local global."""
    global _shared_ts, _shared_lock
    _shared_ts = ts_value
    _shared_lock = lock


def _rate_limit() -> None:
    global _last_live_call_ts
    if _shared_ts is not None and _shared_lock is not None:
        # Cross-worker: lock + read shared ts + sleep + update.
        with _shared_lock:
            now = time.monotonic()
            elapsed = now - _shared_ts.value
            if _shared_ts.value > 0 and elapsed < RATE_LIMIT_SECONDS:
                time.sleep(RATE_LIMIT_SECONDS - elapsed)
            _shared_ts.value = time.monotonic()
        return
    now = time.monotonic()
    elapsed = now - _last_live_call_ts
    if _last_live_call_ts > 0 and elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    _last_live_call_ts = time.monotonic()


def _call_brave(query: str, count: int, api_key: str) -> list[dict[str, Any]]:
    _rate_limit()
    headers = {
        **BASE_HEADERS,
        "X-Subscription-Token": api_key,
    }
    # Brave's `count` caps at 20 and we only ever want 10 by default.
    params = {"q": query, "count": max(1, min(count, 20))}
    # Two attempts: one fast (15s), one with a longer ceiling (30s). Brave
    # occasionally returns slow on cold cache; this keeps the cohort
    # progressing without hammering the API.
    last_exc: Exception | None = None
    for attempt_timeout in (15, 30):
        try:
            resp = requests.get(
                BRAVE_ENDPOINT, headers=headers, params=params, timeout=attempt_timeout
            )
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(1.0)
    else:
        raise RuntimeError(f"Brave Search failed after retries: {last_exc}") from last_exc
    body = resp.json()
    raw_results = (body.get("web") or {}).get("results") or []
    cleaned: list[dict[str, Any]] = []
    for r in raw_results:
        cleaned.append({
            "url": r.get("url") or "",
            "title": r.get("title") or "",
            "description": r.get("description") or "",
            "age": r.get("age") or "",
        })
    return cleaned


def search(query: str, *, count: int = 10, refresh: bool = False) -> dict[str, Any]:
    """Cached Brave Search lookup. See module docstring for cache shape."""
    key = _cache_key(query)
    path = _cache_path(key)

    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    api_key = _api_key()
    if not api_key:
        # Permitted fallback: if a refresh was requested but we have no key,
        # serve the cached copy if one exists.
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise RuntimeError(
            f"BRAVE_SEARCH_API_KEY (or BRAVE_API_KEY) not set and no cache for query: {query!r}"
        )

    results = _call_brave(query, count=count, api_key=api_key)
    # Cache files are content-addressed by query hash; we deliberately
    # omit `retrieved_at` from the payload so two cohort runs produce
    # byte-identical caches when the upstream returns the same results.
    # If you need fetch-time provenance, the file's mtime carries it.
    payload = {
        "query": query,
        "results": results,
        "_cache_key": key,
        "_provider": PROVIDER,
    }
    _atomic_write_json(path, payload)
    return payload


def filter_results(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split results into (kept, dropped) per SPEC allow/block rules.

    Drop precedence (highest first): exact fabricated-URL match, blocklisted
    domain. Allowlisted domains get a free pass and an `_allowlisted` marker.
    Everything else passes through unchanged.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for r in results:
        url = r.get("url") or ""
        if url in FABRICATED_URLS:
            d = dict(r)
            d["_dropped_reason"] = "likely_fabricated_url"
            dropped.append(d)
            continue

        host = _domain_of(url)
        root = _registrable_root(host)

        if root in BLOCKLIST_DOMAINS or host in BLOCKLIST_DOMAINS:
            d = dict(r)
            d["_dropped_reason"] = f"blocklisted_domain:{root or host}"
            dropped.append(d)
            continue

        if root in ALLOWLIST_DOMAINS or host in ALLOWLIST_DOMAINS or host.endswith(".edu"):
            k = dict(r)
            k["_allowlisted"] = True
            kept.append(k)
            continue

        kept.append(dict(r))
    return kept, dropped


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
def _run_filter_test() -> None:
    sample_fab = next(iter(FABRICATED_URLS), None)
    synthetic = [
        {
            "url": "https://www.forbes.com/profile/henry-kravis/",
            "title": "Henry Kravis - Forbes",
            "description": "Profile page.",
            "age": "",
        },
        {
            "url": "https://insidephilanthropy.com/find-a-grant/major-donors/barry-diller-html",
            "title": "Inside Philanthropy article",
            "description": "Should be dropped.",
            "age": "",
        },
        {
            "url": "https://example.com/some/article",
            "title": "Pass-through",
            "description": "Random domain not on either list.",
            "age": "",
        },
    ]
    if sample_fab:
        synthetic.append({
            "url": sample_fab,
            "title": "Known fabricated URL",
            "description": "Should hit FABRICATED_URLS exact match.",
            "age": "",
        })

    kept, dropped = filter_results(synthetic)

    forbes = next(r for r in kept if "forbes.com" in r["url"])
    assert forbes.get("_allowlisted") is True, "forbes.com should be allowlisted"

    pass_through = next(r for r in kept if "example.com" in r["url"])
    assert "_allowlisted" not in pass_through, "example.com should pass through"

    blocklisted = next(r for r in dropped if "insidephilanthropy.com" in r["url"])
    assert blocklisted["_dropped_reason"].startswith("blocklisted_domain"), \
        "InsidePhilanthropy should be dropped as blocklisted"

    if sample_fab:
        fab_drop = next(r for r in dropped if r["url"] == sample_fab)
        assert fab_drop["_dropped_reason"] == "likely_fabricated_url", \
            "fabricated URL should be dropped with likely_fabricated_url reason"

    print(f"[ok] filter_results: {len(kept)} kept, {len(dropped)} dropped "
          f"(fabricated-URLs loaded: {len(FABRICATED_URLS)})")


def _run_live_tests() -> None:
    q = "Henry Kravis foundation 990-PF"
    key = _cache_key(q)
    path = _cache_path(key)
    pre_existed = path.exists()

    t0 = time.monotonic()
    result1 = search(q)
    t1 = time.monotonic()
    assert isinstance(result1, dict), "search must return a dict"
    assert isinstance(result1.get("results"), list), "results must be a list"
    assert result1.get("_cache_key") == key, "cache key must round-trip"
    assert result1.get("_provider") == PROVIDER
    print(f"[ok] search miss-or-hit took {t1 - t0:.2f}s, "
          f"{len(result1['results'])} results, cache_pre_existed={pre_existed}")

    t2 = time.monotonic()
    result2 = search(q)
    t3 = time.monotonic()
    elapsed2 = t3 - t2
    assert result2 == result1, "second call must return identical cached payload"
    assert elapsed2 < 0.2, f"cache hit should be <0.2s, got {elapsed2:.3f}s"
    print(f"[ok] cache-hit returned in {elapsed2 * 1000:.1f}ms (no HTTP call)")


if __name__ == "__main__":
    _run_filter_test()

    if not _api_key():
        # Per the contract: degrade gracefully when key is absent.
        any_cached = any(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else False
        print("[skip] BRAVE_SEARCH_API_KEY/BRAVE_API_KEY not set — skipping live search tests. "
              f"(cache files present: {any_cached})")
    else:
        _run_live_tests()
