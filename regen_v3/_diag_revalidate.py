"""Diagnostic: re-run the new _validate_event over cached (url, snippet)
pairs for one subject to count how many already-extracted events would
be dropped by the grounded-evidence rule. No LLM calls; reads from the
search cache to recover original snippets.

Usage:
    python3 -m regen_v3._diag_revalidate --subject bernard_marcus
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
SEARCH_CACHE = HERE / "cache" / "search"
EXTRACT_CACHE = HERE / "cache" / "extract"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from regen_v3.extract import _cache_key, _validate_event  # noqa: E402


def load_search_meta_for_subject(record: dict) -> dict[str, dict]:
    """Build url -> {title, snippet} from every search-cache file.

    The search cache isn't keyed by subject, so we just walk all files.
    Same URL appearing in multiple queries gets the longest snippet wins."""
    meta: dict[str, dict] = {}
    for fp in SEARCH_CACHE.glob("*.json"):
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        for r in d.get("results") or []:
            if not isinstance(r, dict):
                continue
            url = r.get("url")
            if not isinstance(url, str):
                continue
            title = r.get("title") or ""
            snippet = r.get("description") or ""
            if url not in meta or len(snippet) > len(meta[url]["snippet"]):
                meta[url] = {"title": title, "snippet": snippet}
    return meta


def find_extract_cache_for_event(
    *, url: str, snippet: str, role_hint: str, subject_name: str
) -> dict | None:
    """Try to find the extract cache that matches this exact set of inputs.
    role_hint is unknown to us at this point — try a few common ones."""
    # The role_hint is a free string but generally one of the canonical roles.
    # Try a small set; if none hit, return None.
    for rh in ("grant_out", "direct_gift", "announcement", "pledge", "no_pledge",
               "transfer_in", "political", "reference_only", "")  :
        key = _cache_key(url, snippet, rh, subject_name)
        fp = EXTRACT_CACHE / f"{key}.json"
        if fp.exists():
            try:
                return json.loads(fp.read_text())
            except Exception:
                continue
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True)
    args = ap.parse_args(argv)

    rec_fp = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_fp.read_text())
    person = record.get("person") or {}
    subject_name = person.get("name_display") or person.get("name_legal") or ""
    print(f"subject: {subject_name}")

    url_meta = load_search_meta_for_subject(record)
    print(f"loaded {len(url_meta)} url->meta pairs from search cache")

    events = record.get("cited_events") or []
    print(f"cited_events: {len(events)}")

    kept = 0
    dropped = 0
    demoted_no_drop = 0
    no_meta = 0
    for ev in events:
        url = ev.get("source_url")
        meta = url_meta.get(url)
        if not meta:
            no_meta += 1
            continue
        # Run the new validator with the recovered snippet.
        before_conf = ev.get("confidence")
        ev_copy = dict(ev)
        ev_copy.pop("_grounded_check", None)  # clear in case run before
        # source_url must match expected_url for validate to accept.
        ev_copy["source_url"] = url
        result = _validate_event(
            ev_copy,
            expected_url=url,
            snippet=meta["snippet"],
            title=meta["title"],
        )
        if result is None:
            dropped += 1
            amt = ev.get("amount_usd") or 0
            recip = (ev.get("recipient") or "")[:40]
            year = ev.get("year")
            print(f"  DROP: ${amt/1e6:.0f}M  {year}  {recip!r}  {url[:80]}")
        else:
            kept += 1
            if result.get("_grounded_check"):
                demoted_no_drop += 1

    print()
    print(f"  kept:               {kept}")
    print(f"  dropped (new rule): {dropped}")
    print(f"  demoted not dropped: {demoted_no_drop}")
    print(f"  no search-cache meta: {no_meta} (events from structured sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
