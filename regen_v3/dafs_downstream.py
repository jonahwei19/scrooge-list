"""DAF downstream attribution for regen_v3.

Companion to `dafs.py`: the latter spots foundation→DAF transfers
(visible). This one parses the SPONSOR's Schedule I (Form 990, not
990-PF) to recover the eventual end-charity for each transfer.

Two attribution modes:
  1. Donor-advisor match (confidence='medium'). Match if the sponsor
     discloses a donor-advisor string and it contains a subject-name
     token. Empirically (April 2026) NONE of Fidelity / Vanguard /
     Schwab / NPT / SVCF render this on ProPublica — the matcher
     is plumbed in so it activates if any sponsor starts disclosing.
  2. Statistical amount match (confidence='low'). For each transfer
     T (donor→sponsor, year Y, amount A), accept a downstream grant
     iff EXACTLY ONE grant line in sponsor FY Y or Y+1 has
     |grant−A|/A ≤ 0.10 (sponsors' FYs often close mid-CY). Multiple
     hits → ambiguous → skipped.

Cache: regen_v3/cache/dafs_downstream/<sponsor_ein>_<fy>.json. Sch I
files are 1-280MB; cache is mandatory for a re-run to be cheap.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "dafs_downstream"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from regen_v3.dafs import (  # noqa: E402
    DAF_SPONSORS,
    _discover_filings,
    _ein_digits,
    _http_get,
    _match_daf_sponsor,
)

# Override the broken NPT EIN in dafs.py (232017646 → 237825575). Map by
# canonical sponsor name so we always resolve to a working EIN regardless
# of what `dafs.py` records.
_SPONSOR_NAME_OVERRIDES: dict[str, str] = {
    "National Philanthropic Trust": "237825575",
}
_SPONSOR_BY_NAME: dict[str, str] = {s.name: s.ein for s in DAF_SPONSORS}
_SPONSOR_BY_NAME.update(_SPONSOR_NAME_OVERRIDES)

_AMOUNT_TOL = 0.10  # ±10% statistical-match tolerance per spec
_FY_OFFSETS = (0, 1)  # sponsor FY may close mid-CY; widen to Y..Y+1


# --- Schedule I parser --------------------------------------------------

# Single-pass tokenizer over the rendered HTML. One regex captures
# (row_idx, field_name, value) for every interesting span; we bucket
# per row in one O(N) sweep. The naive per-row re.search approach is
# O(N*M) and was unusable on Fidelity Sch I (280MB, 72k rows).
_SPAN_RE = re.compile(
    r'IRS990ScheduleI\[1\]/RecipientTable\[(\d+)\]/'
    r'(?:RecipientBusinessName\[1\]/)?'
    r'(BusinessNameLine1Txt|CashGrantAmt|RecipientEIN|PurposeOfGrantTxt'
    r'|DonorAdvisorTxt|GrantorAdvisorTxt|RecipientRelationshipTxt)'
    r'\[1\]"[^>]*>([^<]*)</span>'
)
_FIELD_KEY = {
    "BusinessNameLine1Txt": "recipient",
    "CashGrantAmt": "_cash_raw",
    "RecipientEIN": "recipient_ein",
    "PurposeOfGrantTxt": "purpose",
    "DonorAdvisorTxt": "donor_advisor",
    "GrantorAdvisorTxt": "donor_advisor",
    "RecipientRelationshipTxt": "donor_advisor",
}


def _parse_amount(s: str) -> float:
    return float(s.replace(",", "").strip() or 0)


def _parse_schedule_i(html: str) -> list[dict]:
    """One dict per RecipientTable[idx] with a positive cash grant."""
    by_idx: dict[int, dict] = {}
    for m in _SPAN_RE.finditer(html):
        value = (m.group(3) or "").strip()
        if not value:
            continue
        key = _FIELD_KEY.get(m.group(2))
        if not key:
            continue
        by_idx.setdefault(int(m.group(1)), {}).setdefault(key, value)

    rows: list[dict] = []
    for idx in sorted(by_idx):
        row = by_idx[idx]
        amount = _parse_amount(row.get("_cash_raw") or "0")
        if amount <= 0 or not row.get("recipient"):
            continue
        rows.append({
            "recipient": row["recipient"],
            "recipient_ein": row.get("recipient_ein", ""),
            "amount_usd": amount,
            "purpose": row.get("purpose", ""),
            "donor_advisor": row.get("donor_advisor", ""),
        })
    return rows


def _fetch_sponsor_schedule_i(
    sponsor_ein: str, fiscal_year: int, *, refresh: bool = False
) -> list[dict]:
    cache_p = CACHE_DIR / f"{_ein_digits(sponsor_ein)}_{fiscal_year}.json"
    if not refresh and cache_p.exists():
        try:
            return json.loads(cache_p.read_text())
        except Exception:
            pass
    filings = _discover_filings(sponsor_ein, refresh=refresh)
    match = next(
        (f for f in filings if int(f["fiscal_year"]) == fiscal_year), None
    )
    if match is None:
        cache_p.write_text("[]")
        return []
    url = (
        f"https://projects.propublica.org/nonprofits/full_text/"
        f"{match['object_id']}/IRS990ScheduleI"
    )
    try:
        html = _http_get(url)
    except requests.RequestException:
        cache_p.write_text("[]")
        return []
    rows = _parse_schedule_i(html)
    cache_p.write_text(json.dumps(rows, indent=2))
    return rows


# --- Subject discovery + matching --------------------------------------

def _subject_daf_transfers(record: dict) -> list[dict]:
    """Pull all `dafs`-sourced foundation→sponsor transfers from a
    subject's v3 record. Returns dicts with the sponsor EIN attached."""
    out: list[dict] = []
    for fld in ("cited_events", "pledges_and_announcements"):
        for ev in record.get(fld) or []:
            if not isinstance(ev, dict):
                continue
            if ev.get("regen_source") != "dafs":
                continue
            sponsor_name = (ev.get("recipient") or "").strip()
            sponsor_ein = _SPONSOR_BY_NAME.get(sponsor_name)
            if not sponsor_ein:
                # Fall back to substring match against canonical patterns.
                hit = _match_daf_sponsor(sponsor_name)
                if hit is None:
                    continue
                sponsor_ein = _SPONSOR_NAME_OVERRIDES.get(hit.name, hit.ein)
                sponsor_name = hit.name
            year = ev.get("year")
            amount = ev.get("amount_usd") or 0
            if not year or amount <= 0:
                continue
            out.append({
                "year": int(year),
                "amount_usd": float(amount),
                "donor_entity": ev.get("donor_entity") or "",
                "donor_ein": ev.get("donor_ein") or "",
                "sponsor_name": sponsor_name,
                "sponsor_ein": sponsor_ein,
                "source_url": ev.get("source_url") or "",
            })
    return out


def _name_tokens(*names: str) -> set[str]:
    """Lowercased token set for advisor-string matching. Only tokens
    ≥4 chars (so 'the', 'foundation', 'inc' don't false-match)."""
    out: set[str] = set()
    for n in names:
        for tok in re.split(r"[^a-z0-9]+", (n or "").lower()):
            if len(tok) >= 4 and tok not in {"foundation", "trust", "fund"}:
                out.add(tok)
    return out


def _attempt_attribution(
    transfer: dict,
    grants: list[dict],
    person_name: str,
) -> tuple[list[dict], str]:
    """Return (matched_grants, kind) where kind ∈ {'verified','statistical',''}.
    `verified` ⇒ donor-advisor field carries one of the subject's name
    tokens. `statistical` ⇒ exactly one grant within ±10% of the
    transfer amount. Empty list + '' ⇒ no defensible attribution."""
    tokens = _name_tokens(person_name, transfer["donor_entity"])
    verified = [
        g for g in grants
        if g.get("donor_advisor")
        and any(t in g["donor_advisor"].lower() for t in tokens)
    ]
    if verified:
        return verified, "verified"

    target = transfer["amount_usd"]
    band_lo, band_hi = target * (1 - _AMOUNT_TOL), target * (1 + _AMOUNT_TOL)
    statistical = [g for g in grants if band_lo <= g["amount_usd"] <= band_hi]
    if len(statistical) == 1:
        return statistical, "statistical"
    return [], ""


# --- Public contract ----------------------------------------------------

def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return regen_v3 candidate events for DAF downstream grants
    attributable to this subject's foundation→DAF transfers."""
    person_name = (record.get("person") or {}).get("name_display") or ""
    transfers = _subject_daf_transfers(record)
    if not transfers:
        return []

    # Cache parsed Sch I per (sponsor_ein, fy) within this call.
    grant_cache: dict[tuple[str, int], list[dict]] = {}

    candidates: list[dict] = []
    for t in transfers:
        for offset in _FY_OFFSETS:
            fy = t["year"] + offset
            key = (t["sponsor_ein"], fy)
            if key not in grant_cache:
                grant_cache[key] = _fetch_sponsor_schedule_i(
                    t["sponsor_ein"], fy, refresh=refresh
                )
            grants = grant_cache[key]
            matched, kind = _attempt_attribution(t, grants, person_name)
            if not matched:
                continue
            for g in matched:
                conf = "medium" if kind == "verified" else "low"
                ein_dig = _ein_digits(t["sponsor_ein"])
                candidates.append({
                    "event_role": "grant_out",
                    "year": fy,
                    "date_precision": "year",
                    "donor_entity": t["donor_entity"],
                    "donor_ein": t["donor_ein"],
                    "recipient": g["recipient"],
                    "amount_usd": float(g["amount_usd"]),
                    "source_type": "990",
                    "source_url": (
                        f"https://projects.propublica.org/nonprofits/"
                        f"organizations/{ein_dig}"
                    ),
                    "confidence": conf,
                    "note": (
                        f"DAF downstream — {t['sponsor_name']} grant "
                        f"attributable to "
                        + (
                            f"donor advisor '{matched[0]['donor_advisor']}'"
                            if kind == "verified"
                            else f"statistical match (±10%) of "
                                 f"{t['donor_entity']} → {t['sponsor_name']} "
                                 f"${t['amount_usd']/1e6:.2f}M in {t['year']}"
                        )
                        + f". Sponsor FY{fy}; recipient EIN "
                        f"{g.get('recipient_ein') or 'n/a'}; "
                        f"purpose: {g.get('purpose') or 'n/a'}."
                    ),
                    "regen_source": "dafs_downstream",
                })
            break  # don't double-count a transfer across offset years

    candidates.sort(
        key=lambda c: (c["donor_ein"], c["year"], -c["amount_usd"])
    )
    return candidates


# --- CLI ----------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_path.read_text())
    cands = collect_candidates(record, refresh=args.refresh)
    print(f"{args.subject}: {len(cands)} downstream candidates")
    for c in cands:
        kind = "VER" if c["confidence"] == "medium" else "stat"
        print(
            f"  [{kind}] {c['year']}  ${c['amount_usd']/1e6:>7.2f}M  "
            f"{c['donor_entity'][:30]:<30} → {c['recipient'][:50]}"
        )
