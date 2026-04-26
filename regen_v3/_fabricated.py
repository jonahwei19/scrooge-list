"""Single source of truth for the `likely_fabricated` URL set.

Before this module existed, `search.py` and `merge.py` each maintained
their own copy of the fabricated-URL list — one parsed from DEAD_URLS.md,
one hardcoded as a frozenset. They drifted. Adding a fresh fabrication to
one but not the other caused silent acceptance.

Now both consumers import `LIKELY_FABRICATED` from here. The list is
parsed lazily from `DEAD_URLS.md` at import time. If the file is missing
or the markdown shape changes, we fail closed (empty set) rather than
crash — domain-level allow/blocklists still bite.

Sections recognized:
  * `### Likely fabricated by research agents (high-concern)`
    URLs appear in backticks (`` `https://...` ``) — pulled directly.
  * `### InsidePhilanthropy — 7 URLs, all 404`
    URLs appear as numbered list items lacking the `https://` scheme:
    `` `insidephilanthropy.com/...-html` ``. We prepend `https://` when
    re-emitting these so consumer code can do exact-string matching.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
DEAD_URLS_PATH = ROOT / "DEAD_URLS.md"


# Section header prefixes (markdown ###) that we treat as fabrication-list
# entry points. Order matters only for self-test reporting.
_FABRICATED_SECTION_HEADERS = (
    "### Likely fabricated",
    "### InsidePhilanthropy",
)


def _iter_backticked(line: str):
    """Yield each backtick-wrapped substring on a line."""
    i = 0
    while i < len(line):
        lo = line.find("`", i)
        if lo < 0:
            return
        hi = line.find("`", lo + 1)
        if hi < 0:
            return
        yield line[lo + 1:hi].strip()
        i = hi + 1


def _normalize(token: str) -> str | None:
    """Return a canonical https:// URL if `token` looks like one. The
    InsidePhilanthropy section omits the scheme; we prepend `https://`
    so downstream comparisons can be exact-string."""
    t = token.strip()
    if t.startswith("http://") or t.startswith("https://"):
        return t
    if t.startswith("insidephilanthropy.com/"):
        return "https://" + t
    return None


def _load() -> frozenset[str]:
    if not DEAD_URLS_PATH.exists():
        return frozenset()

    urls: set[str] = set()
    in_section = False
    try:
        text = DEAD_URLS_PATH.read_text(encoding="utf-8")
    except OSError:
        return frozenset()

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("### "):
            in_section = any(
                stripped.startswith(h) for h in _FABRICATED_SECTION_HEADERS
            )
            continue
        if not in_section:
            continue
        for token in _iter_backticked(stripped):
            url = _normalize(token)
            if url:
                urls.add(url)
    return frozenset(urls)


LIKELY_FABRICATED: frozenset[str] = _load()


if __name__ == "__main__":
    print(f"loaded {len(LIKELY_FABRICATED)} fabricated URL(s):")
    for u in sorted(LIKELY_FABRICATED):
        print(f"  {u}")
