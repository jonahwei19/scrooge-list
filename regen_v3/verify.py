"""URL liveness pre-filter for regen_v3.

Uses check_urls.check_one (browser UA, HEAD-with-GET-fallback) to filter the
search-result URL stream before extraction. Dead URLs are not extracted from;
they get annotated with a `dead_link_<reason>` status string for downstream
provenance.

Reason mapping mirrors DEAD_URLS.md vocabulary:
  404                -> dead_link_rotted
  410                -> dead_link_rotted
  TIMEOUT/CONN/SSL   -> dead_link_unreachable
  401/403/406/429    -> alive (bot-blocked or paywalled — URL exists)
  any 2xx/3xx        -> alive

Wayback fallback: any URL that fails the live check is queried against
the Wayback Machine `available` API. If a snapshot exists, the URL is
promoted to alive with `wayback_url` set; the snapshot URL becomes the
canonical citation downstream. Lookups are cached at
`regen_v3/cache/wayback/<sha256(url)>.json` so the same URL is queried
once and never again unless `refresh=True`.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

import requests

# Reuse the canonical liveness checker from check_urls.py at the repo root.
HERE = Path(__file__).parent
ROOT = HERE.parent
WAYBACK_CACHE = HERE / "cache" / "wayback"
WAYBACK_CACHE.mkdir(parents=True, exist_ok=True)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from check_urls import check_one  # noqa: E402


_ALIVE_NONOK_CODES = frozenset({401, 403, 406, 429})  # bot/paywall, URL real
_WAYBACK_ENDPOINT = "https://archive.org/wayback/available"
_WAYBACK_TIMEOUT = 8  # seconds


def classify(status: int | str) -> tuple[bool, str | None]:
    """Map a check_one() result to (alive, dead_link_reason).

    `alive=True` means downstream layers may extract from this URL. The
    `dead_link_reason` is None when alive, or one of the canonical
    `dead_link_*` strings when not.
    """
    if isinstance(status, int):
        if 200 <= status < 400:
            return True, None
        if status in _ALIVE_NONOK_CODES:
            return True, None
        if status in (404, 410):
            return False, "dead_link_rotted"
        return False, f"dead_link_http_{status}"
    if status in {"TIMEOUT", "CONN", "SSL"}:
        return False, "dead_link_unreachable"
    return False, f"dead_link_{str(status).lower()}"


def _wayback_cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return WAYBACK_CACHE / f"{h}.json"


def lookup_wayback(url: str, *, refresh: bool = False) -> str | None:
    """Return a Wayback Machine snapshot URL for `url`, or None.

    Caches result indefinitely — Wayback snapshots don't disappear once
    written, so a "found" or "missing" answer is stable. Network failures
    are NOT cached so they can be retried on next run.
    """
    cache_path = _wayback_cache_path(url)
    if not refresh and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            return cached.get("wayback_url")
        except Exception:
            pass

    try:
        resp = requests.get(
            _WAYBACK_ENDPOINT,
            params={"url": url},
            timeout=_WAYBACK_TIMEOUT,
            headers={"User-Agent": "scrooge-regen-v3 (research)"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        snap = (data.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available") and snap.get("url"):
            wb_url = snap["url"]
            # Normalize Wayback URLs to https; their default mix of http/https
            # is annoying for downstream exact-match dedupe.
            if wb_url.startswith("http://web.archive.org/"):
                wb_url = "https" + wb_url[4:]
            cache_path.write_text(json.dumps({"src": url, "wayback_url": wb_url}))
            return wb_url
        # Snapshot doesn't exist — cache the negative answer too.
        cache_path.write_text(json.dumps({"src": url, "wayback_url": None}))
        return None
    except Exception:
        # Don't cache transient network failures.
        return None


def _check_with_wayback(url: str, timeout: int, refresh_wayback: bool) -> dict:
    status, _note = check_one(url, timeout)
    alive, reason = classify(status)
    out: dict = {"alive": alive, "status": status, "dead_link_reason": reason, "wayback_url": None}
    if not alive:
        wb = lookup_wayback(url, refresh=refresh_wayback)
        if wb:
            out["wayback_url"] = wb
            out["alive"] = True  # promote: a snapshot exists, the citation is recoverable
            out["dead_link_reason"] = "alive_via_wayback"
    return out


def verify_urls(
    urls: Iterable[str],
    *,
    timeout: int = 8,
    workers: int = 8,
    use_wayback: bool = True,
    refresh_wayback: bool = False,
) -> dict[str, dict]:
    """Return {url: {"alive", "status", "dead_link_reason", "wayback_url"}}.

    Dedupes input. Concurrent. Same URL checked once even if passed twice.
    When `use_wayback=True` (default), URLs that fail the live check are
    looked up against archive.org/wayback; if a snapshot exists, the URL is
    promoted to alive and `wayback_url` is set.
    """
    unique = sorted(set(u for u in urls if u))
    out: dict[str, dict] = {}
    if not unique:
        return out

    def _do(url: str) -> dict:
        if use_wayback:
            return _check_with_wayback(url, timeout, refresh_wayback)
        status, _note = check_one(url, timeout)
        alive, reason = classify(status)
        return {"alive": alive, "status": status, "dead_link_reason": reason, "wayback_url": None}

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        fut_to_url = {ex.submit(_do, url): url for url in unique}
        for fut in cf.as_completed(fut_to_url):
            url = fut_to_url[fut]
            out[url] = fut.result()
    return out


if __name__ == "__main__":
    sample = [
        "https://www.givingpledge.org/",
        "https://www.givingpledge.org/pledger/haim-saban/",  # confirmed 404
        "https://www.forbes.com/profile/henry-kravis/",
    ]
    result = verify_urls(sample)
    for u, info in result.items():
        wb = info.get("wayback_url") or "-"
        print(
            f"  {info['status']:>7}  alive={info['alive']!s:<5}  "
            f"reason={info['dead_link_reason']}  wayback={wb[:60]}  {u}"
        )
