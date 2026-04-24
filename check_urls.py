#!/usr/bin/env python3
"""
URL liveness check for every source_url in every data/*.v3.json record.

Slow (network-bound; HEAD per URL with a small delay). Keep out of the fast
validation loop; run before publishing or on a cadence. Exits non-zero when
a configurable fraction of URLs are unreachable (default 5%).

Run: python3 check_urls.py             # check all records, default timeout 8s
     python3 check_urls.py --timeout 4 # tighter timeout
     python3 check_urls.py --subject elon_musk  # only one subject
     python3 check_urls.py --fail-pct 0  # fail on first dead URL
"""

from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"


# Bloomberg, OpenSecrets, Reuters, etc. aggressively reject non-browser UAs with 403/401.
# Use a common Safari UA so the liveness check reflects whether a human browser could
# reach the URL, not whether a bot can. This is a liveness check, not a scrape — we
# don't download the content, we just confirm the endpoint exists.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def collect_urls(rec: dict) -> list[tuple[str, str]]:
    """Return list of (field_path, url) for every cited URL in a record."""
    out = []
    for i, s in enumerate(rec.get("sources_all") or []):
        if isinstance(s, dict) and s.get("url"):
            out.append((f"sources_all[{i}]", s["url"]))
    for fld in ("cited_events", "pledges_and_announcements"):
        for i, ev in enumerate(rec.get(fld) or []):
            if isinstance(ev, dict) and ev.get("source_url"):
                out.append((f"{fld}[{i}]", ev["source_url"]))
    # net_worth.sources
    for i, s in enumerate((rec.get("net_worth") or {}).get("sources") or []):
        if isinstance(s, dict) and s.get("url"):
            out.append((f"net_worth.sources[{i}]", s["url"]))
    return out


def check_one(url: str, timeout: int) -> tuple[int | str, str]:
    """HEAD first; if the site refuses HEAD, fall back to a lightweight GET.
    Returns (status, note). `status` is an int HTTP code, or a string for transport errors.
    """
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=timeout)
        if r.status_code == 405 or r.status_code >= 400:
            # Some hosts 405 HEAD; retry with GET range to avoid downloading.
            r = requests.get(url, headers={**HEADERS, "Range": "bytes=0-0"}, allow_redirects=True, timeout=timeout, stream=True)
            r.close()
        return r.status_code, ""
    except requests.exceptions.SSLError as e:
        return "SSL", str(e)[:80]
    except requests.exceptions.ConnectionError as e:
        return "CONN", str(e)[:80]
    except requests.exceptions.Timeout:
        return "TIMEOUT", ""
    except Exception as e:
        return "ERR", str(e)[:80]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=8, help="Per-URL timeout in seconds")
    ap.add_argument("--subject", help="Restrict to one subject id (e.g. elon_musk)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fail-pct", type=float, default=5.0, help="Exit non-zero if >X%% URLs are dead")
    args = ap.parse_args()

    files = sorted(DATA_DIR.glob("*.v3.json"))
    if args.subject:
        files = [f for f in files if args.subject in f.name]
        if not files:
            print(f"no records matching {args.subject!r}")
            return 2

    all_urls: list[tuple[str, str, str]] = []  # (subject, field, url)
    for fp in files:
        rec = json.loads(fp.read_text())
        subject = rec.get("person", {}).get("name_display", fp.stem)
        for field, url in collect_urls(rec):
            all_urls.append((subject, field, url))

    # Dedupe by URL so we don't hammer the same endpoint many times.
    by_url: dict[str, list[tuple[str, str]]] = {}
    for subject, field, url in all_urls:
        by_url.setdefault(url, []).append((subject, field))

    total = len(by_url)
    print(f"checking {total} unique URLs across {len(files)} subjects (timeout={args.timeout}s, workers={args.workers})")

    dead: list[tuple[int | str, str, list[tuple[str, str]]]] = []
    ok_count = 0

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut_to_url = {ex.submit(check_one, url, args.timeout): url for url in by_url}
        for i, fut in enumerate(cf.as_completed(fut_to_url), start=1):
            url = fut_to_url[fut]
            status, note = fut.result()
            callers = by_url[url]
            if isinstance(status, int) and 200 <= status < 400:
                ok_count += 1
            else:
                dead.append((status, url, callers))
                print(f"  [{status}] {url}  ← {callers[0][0]} {callers[0][1]}" + (f"  ({note})" if note else ""))
            if i % 25 == 0:
                print(f"  … {i}/{total} ({ok_count} ok)")

    dead_pct = (len(dead) / total * 100) if total else 0
    print(f"\nSummary: {ok_count}/{total} live · {len(dead)} dead ({dead_pct:.1f}%)")

    if dead_pct > args.fail_pct:
        print(f"FAIL — {dead_pct:.1f}% dead exceeds --fail-pct {args.fail_pct}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
