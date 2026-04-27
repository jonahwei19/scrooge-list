"""Two-sided 990 cross-check for regen_v3.

A donor-side citation is one observation; the recipient's 990 is the
independent second observation. For each verifiable event we look up the
recipient's 990 for the matching fiscal year and check that contributions
received are consistent with the gift amount, then stamp:

    recipient_verified           "true" | "false" | "unverifiable"
    recipient_filing_url         URL to the recipient's 990 on ProPublica
    recipient_verification_note  1-line explanation

Caches:
    cache/recipient_verify/name_<sha256(name)>.json   EIN lookup
    cache/recipient_verify/<ein9>_<year>.json         filing snapshot
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import requests

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "recipient_verify"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from categories.foundations import (  # noqa: E402
    name_similarity, normalize_ein, search_propublica,
)

_GIFT_ROLES = {"direct_gift", "corporate_gift"}
_FOUNDATION_TRANSFER_ROLES = {"grant_out"}
_VERIFIABLE_ROLES = _GIFT_ROLES | _FOUNDATION_TRANSFER_ROLES

# Recipient strings that are intrinsically un-lookupable.
_NONSPECIFIC = ("various", "unspecified", "undisclosed", "anonymous",
                "multiple", "(990-pf aggregate", "to disburse",
                "of her choice", "of his choice")

_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")
_TRAILING_DESC_RE = re.compile(r"\s*[—–\-]\s*.*$")
_LEADING_MULTI_RE = re.compile(r"^\s*(?:multiple|various|including)\s*[:—\-]\s*", re.I)


def _ein_digits(ein: str) -> str:
    return normalize_ein(str(ein)).replace("-", "")


def _normalize_recipient(name: str) -> str:
    if not name:
        return ""
    n = _LEADING_MULTI_RE.sub("", name)
    n = _PAREN_RE.sub(" ", n)
    n = _TRAILING_DESC_RE.sub("", n)
    n = re.sub(r"\s+", " ", n).strip().strip(",")
    return n if len(n) >= 4 else ""


def _is_nonspecific(name: str) -> bool:
    low = (name or "").lower()
    return any(tok in low for tok in _NONSPECIFIC)


def _load(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save(p: Path, data) -> None:
    p.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# EIN resolution
# ---------------------------------------------------------------------------

def _ein_cache_path(name: str) -> Path:
    h = hashlib.sha256(name.strip().lower().encode()).hexdigest()[:32]
    return CACHE_DIR / f"name_{h}.json"


def _resolve_ein(recipient_name: str, *, refresh: bool = False) -> dict:
    """Return {ein, name, status, note}. status ∈ {resolved, ambiguous, not_found, skip}."""
    cache_p = _ein_cache_path(recipient_name)
    if not refresh:
        cached = _load(cache_p)
        if cached is not None:
            return cached

    cleaned = _normalize_recipient(recipient_name)
    if not cleaned or _is_nonspecific(recipient_name):
        out = {"ein": "", "name": "", "status": "skip",
               "note": "nonspecific or aggregate recipient"}
        _save(cache_p, out)
        return out

    try:
        orgs = search_propublica(cleaned) or []
    except Exception as e:
        return {"ein": "", "name": "", "status": "not_found",
                "note": f"propublica search error: {type(e).__name__}"}

    matches = [(name_similarity(cleaned, o.get("name") or ""), o) for o in orgs]
    matches = [m for m in matches if m[0] > 0.7]

    if not matches:
        out = {"ein": "", "name": cleaned, "status": "not_found",
               "note": f"no IRS filing found for recipient {cleaned!r}"}
    elif len(matches) == 1:
        sim, o = matches[0]
        out = {"ein": _ein_digits(o.get("ein", "")),
               "name": o.get("name") or cleaned, "status": "resolved",
               "note": f"single ProPublica match (sim={sim:.2f})"}
    else:
        # Disambiguate by org-level revenue (search response has none).
        best, best_rev = None, -1.0
        for sim, o in matches:
            ein9 = _ein_digits(o.get("ein", ""))
            rev = (_filing_snapshot(ein9, year=None) or {}).get("org_revenue", 0.0)
            if rev > best_rev:
                best, best_rev = (sim, o), rev
        if best and best_rev > 0:
            sim, o = best
            out = {"ein": _ein_digits(o.get("ein", "")),
                   "name": o.get("name") or cleaned, "status": "resolved",
                   "note": (f"chose largest of {len(matches)} matches by revenue "
                            f"(${best_rev/1e6:.1f}M, sim={sim:.2f})")}
        else:
            out = {"ein": "", "name": cleaned, "status": "ambiguous",
                   "note": f"{len(matches)} candidates, none with revenue data"}

    _save(cache_p, out)
    return out


# ---------------------------------------------------------------------------
# 990 fetch
# ---------------------------------------------------------------------------

def _filing_cache_path(ein9: str, year) -> Path:
    suffix = "all" if year is None else str(int(year))
    return CACHE_DIR / f"{ein9}_{suffix}.json"


def _filing_snapshot(ein9: str, *, year=None, refresh: bool = False) -> dict:
    """Return a snapshot of the recipient's filings. With `year`, returns
    the matching filing (±1 yr tolerance); otherwise an org summary."""
    cache_p = _filing_cache_path(ein9, year)
    if not refresh:
        cached = _load(cache_p)
        if cached is not None:
            return cached

    try:
        url = f"https://projects.propublica.org/nonprofits/api/v2/organizations/{ein9}.json"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            out = {"ok": False, "error": f"http_{resp.status_code}"}
            _save(cache_p, out)
            return out
        data = resp.json()
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        _save(cache_p, out)
        return out

    org = data.get("organization") or {}
    filings = data.get("filings_with_data") or []
    out: dict = {
        "ok": True, "ein9": ein9,
        "org_name": org.get("name") or "",
        "org_revenue": float(org.get("revenue_amount") or 0),
        "filing_url": f"https://projects.propublica.org/nonprofits/organizations/{ein9}",
    }
    if year is None:
        _save(cache_p, out)
        return out

    target = int(year)
    chosen = None
    for f in filings:
        fy = int(f.get("tax_prd_yr") or 0)
        if fy and abs(fy - target) <= 1:
            if chosen is None or abs(fy - target) < abs(int(chosen.get("tax_prd_yr") or 0) - target):
                chosen = f
    if chosen is None:
        out["filing_found"] = False
        _save(cache_p, out)
        return out

    # 990 → totcntrbgfts; 990-PF → grscontrgifts; 990-EZ → totcntrbs.
    contrib = (chosen.get("totcntrbgfts") or chosen.get("grscontrgifts")
               or chosen.get("totcntrbs") or chosen.get("contriamtrptd") or 0)
    out.update({
        "filing_found": True,
        "fiscal_year": int(chosen.get("tax_prd_yr") or 0),
        "formtype": chosen.get("formtype"),
        "contributions_received": float(contrib or 0),
        "total_revenue": float(chosen.get("totrevenue") or 0),
    })
    _save(cache_p, out)
    return out


# ---------------------------------------------------------------------------
# Per-event verification
# ---------------------------------------------------------------------------

def _verify_event(event: dict, *, refresh: bool = False) -> dict:
    """Return {verified, filing_url, note} for one event, or {} if not applicable."""
    role = event.get("event_role") or ""
    if role not in _VERIFIABLE_ROLES:
        return {}

    recipient = event.get("recipient") or ""
    year = event.get("year")
    if not recipient or not year:
        return {"verified": "unverifiable", "filing_url": "",
                "note": "missing recipient name or year"}
    if _is_nonspecific(recipient):
        return {"verified": "unverifiable", "filing_url": "",
                "note": f"recipient placeholder ({recipient[:40]!r}) — no entity to look up"}

    res = _resolve_ein(recipient, refresh=refresh)
    if res["status"] != "resolved":
        return {"verified": "unverifiable", "filing_url": "",
                "note": res.get("note") or "EIN unresolved"}

    ein9 = res["ein"]
    snap = _filing_snapshot(ein9, year=int(year), refresh=refresh)
    if not snap.get("ok"):
        return {"verified": "unverifiable",
                "filing_url": f"https://projects.propublica.org/nonprofits/organizations/{ein9}",
                "note": f"recipient EIN {ein9}: {snap.get('error')}"}
    if not snap.get("filing_found"):
        return {"verified": "unverifiable", "filing_url": snap.get("filing_url", ""),
                "note": (f"no 990 on file for {snap.get('org_name','')} (EIN {ein9}) "
                         f"within ±1 yr of {year}")}

    filing_url = snap.get("filing_url", "")
    pool = max(snap.get("contributions_received") or 0, snap.get("total_revenue") or 0)
    amount = float(event.get("amount_usd") or 0)
    fy = snap.get("fiscal_year")
    org_name = snap.get("org_name", "")

    if amount <= 0:
        return {"verified": "true", "filing_url": filing_url,
                "note": (f"recipient {org_name} (EIN {ein9}) filed FY{fy} 990; "
                         f"amount not provided in event so no dollar match attempted")}
    if pool >= amount:
        confidence = "verified" if role in _FOUNDATION_TRANSFER_ROLES else "circumstantial"
        return {"verified": "true", "filing_url": filing_url,
                "note": (f"recipient {org_name} (EIN {ein9}) FY{fy} 990 reports "
                         f"${pool/1e6:.1f}M in contributions/revenue ≥ event "
                         f"${amount/1e6:.1f}M ({confidence})")}
    return {"verified": "false", "filing_url": filing_url,
            "note": (f"recipient {org_name} (EIN {ein9}) FY{fy} 990 reports only "
                     f"${pool/1e6:.1f}M in contributions/revenue; event claims "
                     f"${amount/1e6:.1f}M (gap ${(amount-pool)/1e6:.1f}M)")}


# ---------------------------------------------------------------------------
# Public contract — mirrors regen_v3.dafs shape
# ---------------------------------------------------------------------------

def annotate_record(record: dict, *, refresh: bool = False) -> dict:
    """Mutate `record` in place: stamp recipient_verified / recipient_filing_url
    / recipient_verification_note onto every verifiable event."""
    for fld in ("cited_events", "pledges_and_announcements"):
        for ev in (record.get(fld) or []):
            if not isinstance(ev, dict):
                continue
            if (ev.get("event_role") or "") not in _VERIFIABLE_ROLES:
                continue
            result = _verify_event(ev, refresh=refresh)
            if not result:
                continue
            ev["recipient_verified"] = result["verified"]
            ev["recipient_filing_url"] = result["filing_url"]
            ev["recipient_verification_note"] = result["note"]
    return record


if __name__ == "__main__":
    import argparse
    from collections import Counter

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_path.read_text())
    annotate_record(record, refresh=args.refresh)

    counts = Counter()
    examples: dict[str, list] = {"true": [], "false": [], "unverifiable": []}
    for fld in ("cited_events", "pledges_and_announcements"):
        for ev in (record.get(fld) or []):
            v = ev.get("recipient_verified")
            if v:
                counts[v] += 1
                if len(examples.get(v, [])) < 3:
                    examples[v].append(ev)

    print(f"\n{args.subject}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    for status, exs in examples.items():
        if not exs:
            continue
        print(f"\n--- {status} ---")
        for e in exs:
            amt = e.get("amount_usd")
            amt_s = f"${amt/1e6:.1f}M" if isinstance(amt, (int, float)) and amt else "—"
            print(f"  {e.get('year')} {amt_s:>9}  {(e.get('recipient') or '')[:60]!r}")
            print(f"       {e.get('recipient_verification_note')}")
