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
"""
from __future__ import annotations

import concurrent.futures as cf
import sys
from pathlib import Path
from typing import Iterable

# Reuse the canonical liveness checker from check_urls.py at the repo root.
HERE = Path(__file__).parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from check_urls import check_one  # noqa: E402


_ALIVE_NONOK_CODES = frozenset({401, 403, 406, 429})  # bot/paywall, URL real


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


def verify_urls(
    urls: Iterable[str],
    *,
    timeout: int = 8,
    workers: int = 8,
) -> dict[str, dict]:
    """Return {url: {"alive": bool, "status": int|str, "dead_link_reason": str|None}}.

    Dedupes input. Concurrent. Same URL checked once even if passed twice.
    """
    unique = sorted(set(u for u in urls if u))
    out: dict[str, dict] = {}
    if not unique:
        return out

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        fut_to_url = {ex.submit(check_one, url, timeout): url for url in unique}
        for fut in cf.as_completed(fut_to_url):
            url = fut_to_url[fut]
            status, _note = fut.result()
            alive, reason = classify(status)
            out[url] = {"alive": alive, "status": status, "dead_link_reason": reason}
    return out


if __name__ == "__main__":
    sample = [
        "https://www.givingpledge.org/",
        "https://www.givingpledge.org/pledger/haim-saban/",  # confirmed 404
        "https://www.forbes.com/profile/henry-kravis/",
    ]
    result = verify_urls(sample)
    for u, info in result.items():
        print(f"  {info['status']:>7}  alive={info['alive']!s:<5}  reason={info['dead_link_reason']}  {u}")
