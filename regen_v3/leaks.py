"""ICIJ Offshore Leaks source for regen_v3 — bulk-CSV edition.

No API keys. Loads ICIJ's freely-published Offshore Leaks Database
(Panama, Paradise, Pandora, Bahamas, Offshore Leaks combined) from the
official bulk CSV download, indexes it locally, and matches each
subject's name(s) against the officer roster. Hits flow into
`sources_all` as `event_role: "reference_only"` candidates — presence
of an offshore vehicle is a *signal of dark-giving capacity*, not
proof of any specific dollar amount.

Why bulk CSV instead of OpenSanctions / Aleph / icij.org search:
- ICIJ's own site is gated by AWS WAF (JS interstitial → no scripted access).
- OCCRP Aleph anonymous queries return 0 results (PRO-tier-only now).
- OpenSanctions republishes the same data but requires a paid API key.
- The bulk CSVs at offshoreleaks-data.icij.org are CC BY-SA, no key, no
  rate limit, ~70 MB compressed / ~626 MB extracted, refreshed weekly.

Download
--------
On first use, downloads `full-oldb.LATEST.zip` from
`https://offshoreleaks-data.icij.org/offshoreleaks/csv/` and unpacks
to `regen_v3/data/icij/`. Pass `refresh=True` (or `--refresh`) to
re-download. Otherwise the local copy is the cache — never re-fetched.

Cache layout
------------
- `regen_v3/data/icij/`              — extracted CSVs (gitignored)
- `regen_v3/cache/leaks/<sha>.json`  — per-subject match results

Output candidate shape (one per matched offshore entity)
-------------------------------------------------------
{
  "event_role": "reference_only",
  "year": None,
  "donor_entity": <subject's display name>,
  "recipient": <ICIJ entity name>,
  "amount_usd": None,
  "source_type": "icij_offshore_leaks",
  "source_url": "https://offshoreleaks.icij.org/nodes/<entity_node_id>",
  "confidence": "low",
  "note": "ICIJ <leak source> — <entity> in <jurisdiction>; officer role: <role>.",
  "regen_source": "leaks",
}
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

try:
    import requests  # already a project dep via search/extract
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache" / "leaks"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ICIJ_DIR = HERE / "data" / "icij"
ICIJ_DIR.mkdir(parents=True, exist_ok=True)

try:
    from regen_v3._atomic import atomic_write_json  # type: ignore
except Exception:  # pragma: no cover - in-package fallback
    from _atomic import atomic_write_json  # type: ignore

DOWNLOAD_URL = "https://offshoreleaks-data.icij.org/offshoreleaks/csv/full-oldb.LATEST.zip"
ZIP_PATH = ICIJ_DIR / "full-oldb.zip"
OFFICERS_CSV = ICIJ_DIR / "nodes-officers.csv"
ENTITIES_CSV = ICIJ_DIR / "nodes-entities.csv"
INTERMEDIARIES_CSV = ICIJ_DIR / "nodes-intermediaries.csv"
RELATIONSHIPS_CSV = ICIJ_DIR / "relationships.csv"

REQUIRED_FILES = (OFFICERS_CSV, ENTITIES_CSV, RELATIONSHIPS_CSV)

# Allow CSVs with very long fields (some `note` columns are huge).
csv.field_size_limit(sys.maxsize)

# Cap hits per name so a wildly-collidant name doesn't blow up sources_all.
MAX_HITS_PER_NAME = 25
# Drop tokens this short from the matching key — almost always initials.
MIN_TOKEN_LEN = 2

_HONORIFICS = {
    "sir", "dame", "lord", "lady", "mr", "mrs", "ms", "miss", "dr",
    "prof", "professor", "rev", "hon", "honourable", "honorable",
    "jr", "sr", "ii", "iii", "iv", "v", "esq",
    "the",
}
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


# ---------------------------------------------------------------------------
# Bootstrap: download + extract the ICIJ bulk CSVs on first use.
# ---------------------------------------------------------------------------

def _download_and_extract(*, refresh: bool = False) -> bool:
    """Ensure the four CSVs are present locally. One download attempt.
    Returns True on success, False on failure (with clear instructions
    printed)."""
    if all(p.exists() for p in REQUIRED_FILES) and not refresh:
        return True
    if requests is None:
        print("    [leaks-skip] `requests` not installed — pip install requests")
        return False
    print(f"    [leaks] downloading ICIJ bulk CSVs from {DOWNLOAD_URL}")
    print("    [leaks] (~70 MB compressed, ~626 MB extracted; one-time)")
    try:
        with requests.get(DOWNLOAD_URL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(ZIP_PATH, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        fh.write(chunk)
    except Exception as e:
        print(f"    [leaks-skip] download failed: {type(e).__name__}: {e}")
        print(f"    [leaks-skip] manual fix: curl -L -o {ZIP_PATH} {DOWNLOAD_URL}")
        print(f"    [leaks-skip] then: unzip -o {ZIP_PATH} -d {ICIJ_DIR}")
        return False
    try:
        with zipfile.ZipFile(ZIP_PATH) as zf:
            zf.extractall(ICIJ_DIR)
    except Exception as e:
        print(f"    [leaks-skip] zip extract failed: {type(e).__name__}: {e}")
        return False
    missing = [p.name for p in REQUIRED_FILES if not p.exists()]
    if missing:
        print(f"    [leaks-skip] zip extracted but missing files: {missing}")
        return False
    return True


# ---------------------------------------------------------------------------
# Name normalization — order-invariant, punctuation-invariant.
# ---------------------------------------------------------------------------

def _tokens(name: str) -> frozenset[str]:
    """Lowercase, strip punctuation, drop honorifics + initials, return
    frozenset of remaining tokens. Order-invariant.

    "KRAVIS, HENRY R."   -> {"henry", "kravis"}
    "Henry Roberts Kravis" -> {"henry", "kravis", "roberts"}
    "Sir Leonard Valentinovich Blavatnik" -> {"blavatnik", "leonard", "valentinovich"}
    "Lauder - Ronald S"  -> {"lauder", "ronald"}
    """
    if not name:
        return frozenset()
    cleaned = _PUNCT_RE.sub(" ", name.lower())
    raw = [t for t in cleaned.split() if t]
    out = []
    for t in raw:
        if len(t) < MIN_TOKEN_LEN:
            continue           # drop initials like "r" or "s"
        if t in _HONORIFICS:
            continue
        out.append(t)
    return frozenset(out)


# ---------------------------------------------------------------------------
# Lazy-loaded indices.
# ---------------------------------------------------------------------------

# Token-set -> list[node_id] for officers AND intermediaries.
# Token-set is the "canonical" key (frozenset of normalized tokens).
_NAME_INDEX: dict[frozenset[str], list[str]] | None = None
# node_id -> raw row dict for officers + intermediaries (for the role label
# / leak source / country) -- both are people-shaped nodes that link via
# `officer_of` / `intermediary_of` to entities.
_PEOPLE: dict[str, dict] | None = None
# entity node_id -> raw row dict (for caption / jurisdiction / source).
_ENTITIES: dict[str, dict] | None = None
# person node_id -> list[(entity_node_id, link_label, sourceID)]
_REL_OUT: dict[str, list[tuple[str, str, str]]] | None = None


def _ensure_indices_loaded() -> bool:
    """One-shot lazy load. Returns True on success."""
    global _NAME_INDEX, _PEOPLE, _ENTITIES, _REL_OUT
    if _NAME_INDEX is not None:
        return True
    if not _download_and_extract():
        return False

    name_index: dict[frozenset[str], list[str]] = {}
    people: dict[str, dict] = {}
    entities: dict[str, dict] = {}
    rel_out: dict[str, list[tuple[str, str, str]]] = {}

    # --- people (officers + intermediaries) ---
    for csv_path in (OFFICERS_CSV, INTERMEDIARIES_CSV):
        if not csv_path.exists():
            continue
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                nid = row.get("node_id")
                name = (row.get("name") or "").strip()
                if not nid or not name:
                    continue
                people[nid] = row
                key = _tokens(name)
                # Single-token keys (e.g. "Acme") are too noisy — skip.
                if len(key) < 2:
                    continue
                name_index.setdefault(key, []).append(nid)

    # --- entities ---
    if ENTITIES_CSV.exists():
        with open(ENTITIES_CSV, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                nid = row.get("node_id")
                if not nid:
                    continue
                entities[nid] = row

    # --- relationships: only person -> entity links we care about ---
    if RELATIONSHIPS_CSV.exists():
        with open(RELATIONSHIPS_CSV, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rel_type = row.get("rel_type") or ""
                if rel_type not in ("officer_of", "intermediary_of"):
                    continue
                start = row.get("node_id_start")
                end = row.get("node_id_end")
                if not start or not end:
                    continue
                rel_out.setdefault(start, []).append((
                    end,
                    (row.get("link") or rel_type).strip(),
                    (row.get("sourceID") or "").strip(),
                ))

    _NAME_INDEX = name_index
    _PEOPLE = people
    _ENTITIES = entities
    _REL_OUT = rel_out
    return True


# ---------------------------------------------------------------------------
# Lookup.
# ---------------------------------------------------------------------------

def _surname_token(name: str) -> str | None:
    """Heuristic surname extraction: last 2+-char non-honorific token of
    the name. Western convention. Used as an anchor that must appear in
    both subject and leak token sets when subset-matching, to avoid
    false positives like (`George Bruce Kaiser` ↔ `GEORGE BRUCE`)."""
    if not name:
        return None
    cleaned = _PUNCT_RE.sub(" ", name.lower())
    # Walk tokens right-to-left until we find a "real" surname token.
    for t in reversed(cleaned.split()):
        if len(t) < MIN_TOKEN_LEN:
            continue
        if t in _HONORIFICS:
            continue
        return t
    return None


def _lookup_by_name(query_name: str, surname_anchor: str | None = None) -> list[str]:
    """Return list of person node_ids whose name tokens are subset-
    compatible with the subject's tokens after normalization.

    Match rule: equality OR one side is a subset of the other AND the
    smaller side has >=2 tokens AND `surname_anchor` (if provided) is
    present in both token sets. The surname anchor prevents
    constellations of common given names from matching unrelated people:

      subject "George Bruce Kaiser" {george, bruce, kaiser}, anchor=kaiser
        vs leak "GEORGE BRUCE" {george, bruce} -> NO match (no `kaiser`)
        == leak "George Kaiser Family Foundation"
                {george, kaiser, family, foundation} ... actually a
                superset case: subject ⊂ leak; anchor `kaiser` present
                in both -> match
      subject "Henry Kravis" {henry, kravis}, anchor=kravis
        ⊂ leak "KRAVIS, HENRY ROGER" {kravis, henry, roger} -> match
      subject "Sir Leonard Valentinovich Blavatnik"
              {leonard, valentinovich, blavatnik}, anchor=blavatnik
        ⊃ leak "Blavatnik - Leonard" {leonard, blavatnik} -> match

    The >=2-tokens floor (enforced both at index-build time and on the
    query side) keeps single-name rows from matching everyone.
    """
    if not _ensure_indices_loaded():
        return []
    assert _NAME_INDEX is not None
    qkey = _tokens(query_name)
    if len(qkey) < 2:
        return []
    if surname_anchor and surname_anchor not in qkey:
        # Caller passed an anchor that isn't in the normalized token set
        # (e.g. punctuation/honorific weirdness) -- fall back to no anchor.
        surname_anchor = None
    out: list[str] = []
    seen: set[str] = set()
    for ikey, ids in _NAME_INDEX.items():
        if len(ikey) < 2:
            continue
        if ikey == qkey:
            ok = True
        elif ikey.issubset(qkey) or qkey.issubset(ikey):
            ok = (surname_anchor is None) or (surname_anchor in ikey)
        else:
            ok = False
        if not ok:
            continue
        for nid in ids:
            if nid not in seen:
                seen.add(nid)
                out.append(nid)
    return out


def _names_to_search(record: dict) -> list[str]:
    """name_display + name_legal + aliases (when distinct).

    Mirrors fec.py / propublica.py shape. Aliases supported even though
    the v3 schema doesn't formally define them yet — future-friendly."""
    person = record.get("person") or {}
    out: list[str] = []
    seen: set[frozenset[str]] = set()
    candidates: list[str] = []
    for fld in ("name_display", "name_legal"):
        v = person.get(fld)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())
    aliases = person.get("aliases") or []
    if isinstance(aliases, list):
        for a in aliases:
            if isinstance(a, str) and a.strip():
                candidates.append(a.strip())
    for n in candidates:
        key = _tokens(n)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def _cache_key(name: str) -> str:
    return hashlib.sha256(name.strip().lower().encode()).hexdigest()


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{_cache_key(name)}.json"


def _load_cache(name: str) -> list[dict] | None:
    p = _cache_path(name)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("matches")
    except Exception:
        return None


def _save_cache(name: str, matches: list[dict]) -> None:
    # Atomic write: parent/child or husband/wife pairs hashing to the
    # same surname-anchored key can race on this cache.
    atomic_write_json(
        _cache_path(name),
        {"name": name, "matches": matches},
    )


def _matches_for_name(name: str, surname_anchor: str | None = None) -> list[dict]:
    """Return raw match dicts (one per (person, entity) pair) for a name.
    Each dict: {person_id, person_name, entity_id, entity_name, role,
    leak_source, jurisdiction, person_country}."""
    assert _PEOPLE is not None and _ENTITIES is not None and _REL_OUT is not None
    out: list[dict] = []
    for pid in _lookup_by_name(name, surname_anchor):
        prow = _PEOPLE.get(pid) or {}
        for eid, role, src in _REL_OUT.get(pid, []):
            erow = _ENTITIES.get(eid) or {}
            out.append({
                "person_id": pid,
                "person_name": (prow.get("name") or "").strip(),
                "person_country": (prow.get("countries") or "").strip(),
                "entity_id": eid,
                "entity_name": (erow.get("name") or "(unnamed entity)").strip(),
                "role": role,
                "leak_source": src or (prow.get("sourceID") or "").strip(),
                "jurisdiction": (
                    erow.get("jurisdiction_description")
                    or erow.get("jurisdiction")
                    or erow.get("countries")
                    or ""
                ).strip(),
            })
    return out


def _to_candidate(subject_name: str, m: dict) -> dict:
    """Raw match -> regen_v3 candidate."""
    leak = m.get("leak_source") or "ICIJ leak"
    juris = m.get("jurisdiction") or "unknown jurisdiction"
    role = m.get("role") or "officer of"
    entity_name = m.get("entity_name") or "(unnamed entity)"
    person_country = m.get("person_country") or ""
    person_country_clause = f" (officer listed in {person_country})" if person_country else ""
    note = (
        f"ICIJ {leak} — {entity_name} in {juris}; "
        f"officer role: {role}{person_country_clause}. "
        f"Matched on subject name; presence of an offshore vehicle is a "
        f"capacity signal, not proof of giving."
    )
    return {
        "event_role": "reference_only",
        "year": None,
        "donor_entity": subject_name,
        "recipient": entity_name,
        "amount_usd": None,
        "source_type": "icij_offshore_leaks",
        "source_url": f"https://offshoreleaks.icij.org/nodes/{m['entity_id']}",
        "confidence": "low",
        "note": note,
        "regen_source": "leaks",
    }


def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Top-level entry point — same shape as fec/sec/propublica.

    `refresh=True` forces a re-download of the ICIJ bulk CSVs (the per-
    subject JSON cache is also re-computed). Otherwise the on-disk CSVs
    are treated as the cache and never re-downloaded.
    """
    if requests is None and not all(p.exists() for p in REQUIRED_FILES):
        print("    [leaks-skip] `requests` not installed and no local CSVs — skipping")
        return []
    if refresh:
        # Wipe per-name JSON cache so we re-match against the new CSVs.
        for p in CACHE_DIR.glob("*.json"):
            try:
                p.unlink()
            except Exception:
                pass
    if not _ensure_indices_loaded() and not refresh:
        # Bootstrap failed AND we don't have local CSVs.
        return []
    if refresh and not _download_and_extract(refresh=True):
        return []
    if refresh:
        # Force index rebuild after the fresh download.
        global _NAME_INDEX, _PEOPLE, _ENTITIES, _REL_OUT
        _NAME_INDEX = _PEOPLE = _ENTITIES = _REL_OUT = None
        if not _ensure_indices_loaded():
            return []

    subject_display = (record.get("person") or {}).get("name_display") or ""
    names = _names_to_search(record)
    if not names:
        return []
    # Anchor surname: most reliable from name_display ("George Kaiser" ->
    # "kaiser"); fall back to per-name last-token if no display.
    anchor = _surname_token(subject_display) if subject_display else None

    candidates: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for name in names:
        per_anchor = anchor or _surname_token(name)
        cached = _load_cache(name)
        if cached is None:
            raw = _matches_for_name(name, per_anchor)
            _save_cache(name, raw)
        else:
            raw = cached
        kept = 0
        for m in raw:
            if kept >= MAX_HITS_PER_NAME:
                break
            cand = _to_candidate(subject_display or name, m)
            dedupe = (cand["recipient"].lower(), cand["source_url"])
            if dedupe in seen_keys:
                continue
            seen_keys.add(dedupe)
            candidates.append(cand)
            kept += 1
    return candidates


# Tiny CLI for ad-hoc probing: `python3 -m regen_v3.leaks <subject>`
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("subject", help="Subject id (e.g. henry_kravis)")
    ap.add_argument("--refresh", action="store_true",
                    help="Force re-download of ICIJ bulk CSVs.")
    args = ap.parse_args()

    rec_path = HERE.parent / "data" / f"{args.subject}.v3.json"
    if not rec_path.exists():
        print(f"no record at {rec_path}")
        sys.exit(2)
    rec = json.loads(rec_path.read_text())
    cands = collect_candidates(rec, refresh=args.refresh)
    print(f"{args.subject}: {len(cands)} candidates")
    for c in cands:
        print(f"  {c['recipient']}  -- {c['source_url']}")
        print(f"      {c['note']}")
