"""Philanthropic-LLC source for regen_v3.

Philanthropic LLCs (Chan Zuckerberg Initiative LLC, Ballmer Group LLC,
Emerson Collective, etc.) are 501-exempt and have NO 990 filing
requirement. They are total opacity downstream — we cannot see the
disbursement, only the donor's public commitment to fund the vehicle.

The framing for this module is deliberately conservative: **bounds, not
voids.** A widely-reported, dated, on-the-record commitment from the
donor (or the LLC's own self-disclosure) establishes a floor on
philanthropic capacity. We emit those as `pledge` candidates with
`amount_usd` set when a hard public number exists, or `None` when the
commitment is fuzzy ("99% of stake during our lifetimes") and we want to
record the bound without faking a number.

Catalog
-------
`KNOWN_PHILANTHROPIC_LLCS` is a hand-curated dict keyed by lowercased
`name_display`. Each value lists one or more `LLCCommitment` records.
Every dollar figure points to a real news article (the URL is in the
commitment dict). Sources verified April 2026 via web research; if a
figure is updated upstream the commitment year + source_url should be
updated together.

Match logic
-----------
1. Look up `record.person.name_display` (case-insensitive) in
   `KNOWN_PHILANTHROPIC_LLCS`.
2. Also walk `record.detected_vehicles.llcs_philanthropic` — records may
   declare additional LLCs the catalog hasn't caught yet. For declared
   vehicles WITHOUT a curated commitment, we still emit one
   `reference_only` candidate per vehicle so the LLC's existence shows
   up in `sources_all` (capacity signal).

Cache
-----
`regen_v3/cache/llcs/<subject_id>.json` — purely the assembled candidate
list. The catalog is hardcoded so there's no live network call to cache,
but persisting per-subject keeps the cli.py cache-hit accounting
consistent with the other structured modules.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

HERE = Path(__file__).parent
ROOT = HERE.parent
CACHE_DIR = HERE / "cache" / "llcs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLCCommitment:
    """One publicly-reported commitment to a philanthropic LLC.

    `amount_usd=None` means the commitment is fuzzy by design ("99% of
    stake during our lifetimes") and we deliberately refuse to fake a
    number. The `note` should describe the bound precisely.
    """
    llc_name: str
    year: int
    amount_usd: Optional[float]
    source_url: str
    note: str
    event_role: str = "pledge"  # or "transfer_in" when money has demonstrably moved
    confidence: str = "medium"
    secondary_source_url: Optional[str] = None


# Each list is one or more public commitments to that subject's
# philanthropic-LLC structure(s). Multiple entries per subject capture
# either (a) successive top-up pledges or (b) distinct LLC vehicles.
KNOWN_PHILANTHROPIC_LLCS: dict[str, list[LLCCommitment]] = {
    "mark zuckerberg": [
        LLCCommitment(
            llc_name="Chan Zuckerberg Initiative LLC",
            year=2015,
            amount_usd=None,  # 99% of Facebook stake "during our lifetimes" — no dated dollar floor
            source_url="https://money.cnn.com/2015/12/01/technology/zuckerberg-facebook-stock-daughter/",
            secondary_source_url="https://www.bloomberg.com/news/articles/2015-12-01/zuckerberg-to-give-99-of-facebook-stock-away-during-lifetime",
            note=(
                "CZI LLC 2015 lifetime commitment: 99% of Mark Zuckerberg's Facebook/Meta "
                "shares (≈$45B at announcement; appreciated since) over the donors' "
                "lifetimes. SEC filing capped at $1B/year for the first three years. "
                "LLC is opaque downstream — bound only, not a deployment figure."
            ),
        ),
    ],
    "steve ballmer": [
        LLCCommitment(
            llc_name="Ballmer Group LLC",
            year=2024,
            amount_usd=4_000_000_000.0,  # cumulative as of 2024 reporting
            source_url="https://en.wikipedia.org/wiki/Ballmer_Group",
            secondary_source_url="https://ballmergroup.org/",
            note=(
                "Ballmer Group LLC self-reported cumulative giving of ≈$4B since 2015 "
                "founding (≈$767M in 2024 alone per its own annual update). 501(c)(4) "
                "+ DAF blend; LLC structure opaque — figure is donor self-disclosure, "
                "not a 990 audit number."
            ),
            event_role="transfer_in",
        ),
    ],
    "laurene powell jobs": [
        LLCCommitment(
            llc_name="Emerson Collective LLC",
            year=2004,
            amount_usd=None,
            source_url="https://en.wikipedia.org/wiki/Emerson_Collective",
            note=(
                "Emerson Collective LLC, founded 2004 as Laurene Powell Jobs's primary "
                "vehicle. CJR and Inside Philanthropy both note Emerson is 'notoriously "
                "lacking in transparency on hard giving figures'; reported assets ≈$1.8B. "
                "LLC is opaque — capacity signal only."
            ),
        ),
        LLCCommitment(
            llc_name="Waverley Street Foundation",
            year=2021,
            amount_usd=3_500_000_000.0,
            source_url="https://philanthropynewsdigest.org/news/powell-jobs-to-invest-3.5-billion-in-climate-action-over-ten-years",
            secondary_source_url="https://www.philanthropy.com/news/the-head-of-laurene-powell-jobss-climate-foundation-has-more-than-3-billion-to-spend-and-a-deadline/",
            note=(
                "Waverley Street Foundation (operating arm of Emerson Collective for "
                "climate): 2021 dated commitment of $3.5B over 10 years for climate "
                "action. Spend-down by 2035. ≈$500M deployed 2021-2023 per foundation. "
                "Note: classified as 'foundation' but functions as an LLC-adjacent spend-"
                "down vehicle inside the Emerson Collective umbrella."
            ),
        ),
    ],
    "dustin moskovitz": [
        LLCCommitment(
            llc_name="Coefficient Giving LLC (formerly Open Philanthropy LLC)",
            year=2025,
            amount_usd=4_000_000_000.0,  # cumulative as of June 2025
            source_url="https://coefficientgiving.org/research/our-progress-in-2024-and-plans-for-2025/",
            secondary_source_url="https://en.wikipedia.org/wiki/Coefficient_Giving",
            note=(
                "Coefficient Giving (rebranded from Open Philanthropy LLC, Nov 2025) "
                "self-reported cumulative directed grants ≈$4B as of June 2025; ≈$1B "
                "directed in 2025 alone (largest year on record). Funded primarily by "
                "Good Ventures (Moskovitz & Tuna). Among the most transparent "
                "philanthropic LLCs — publishes full grants database with recipient, "
                "amount, date, cause area."
            ),
            confidence="high",
            event_role="transfer_in",
        ),
    ],
    "cari tuna": [
        # Same commitment surface as Moskovitz — joint donors via Good Ventures.
        LLCCommitment(
            llc_name="Coefficient Giving LLC (formerly Open Philanthropy LLC)",
            year=2025,
            amount_usd=4_000_000_000.0,
            source_url="https://coefficientgiving.org/research/our-progress-in-2024-and-plans-for-2025/",
            note=(
                "Cari Tuna chairs Coefficient Giving's board of managers; joint donor "
                "with Moskovitz via Good Ventures. Cumulative ≈$4B directed as of "
                "June 2025."
            ),
            confidence="high",
            event_role="transfer_in",
        ),
    ],
    "eric schmidt": [
        LLCCommitment(
            llc_name="Schmidt Futures (now Schmidt Sciences)",
            year=2019,
            amount_usd=1_000_000_000.0,
            source_url="https://schmidtocean.org/one-billion-dollar-philanthropic-commitment-talent/",
            secondary_source_url="https://www.prnewswire.com/news-releases/eric-and-wendy-schmidt-announce-new-1-billion-philanthropic-commitment-to-identify-develop-and-support-global-talent-working-in-service-of-others-300957008.html",
            note=(
                "Eric & Wendy Schmidt Nov-2019 commitment: $1B 'philanthropic "
                "commitment to identify, develop, and support global talent.' Operated "
                "via Schmidt Futures, rebranded Schmidt Sciences in 2024. Inside "
                "Philanthropy notes the Schmidts have given >$1B cumulatively across "
                "all vehicles to date."
            ),
        ),
    ],
    "wendy schmidt": [
        LLCCommitment(
            llc_name="Schmidt Futures (now Schmidt Sciences)",
            year=2019,
            amount_usd=1_000_000_000.0,
            source_url="https://schmidtocean.org/one-billion-dollar-philanthropic-commitment-talent/",
            note="Joint commitment with Eric Schmidt — see Eric Schmidt entry.",
        ),
    ],
    "reid hoffman": [
        LLCCommitment(
            llc_name="Aphorism Foundation (private grantmaker; LLC-adjacent giving via DAFs)",
            year=2014,
            amount_usd=None,
            source_url="https://www.insidephilanthropy.com/home/reid-hoffman-and-the-complexity-of-the-modern-megadonor",
            secondary_source_url="https://www.influencewatch.org/non-profit/aphorism-foundation/",
            note=(
                "Reid Hoffman is a Giving Pledge signatory who has stated he intends "
                "to spend his fortune (Forbes ≈$2.5B) during his lifetime. Primary "
                "vehicle is the ≈$1B Aphorism Foundation (2014). Hoffman publishes a "
                "list of seven-figure-plus DAF grants but no website; Inside "
                "Philanthropy describes the structure as deliberately low-publicity. "
                "LLC layer is opaque — bound is the pledged spend-down."
            ),
        ),
    ],
    "marc benioff": [
        LLCCommitment(
            llc_name="Benioff personal philanthropy + TIME / TIME Ventures climate fund",
            year=2024,
            amount_usd=1_000_000_000.0,
            source_url="https://www.salesforce.com/news/stories/marc-benioff-philanthropy/",
            secondary_source_url="https://www.salesforce.com/news/press-releases/2021/10/28/marc-and-lynne-benioff-and-salesforce-announce-investment-to-accelerate-ecosystem-restoration-and-climate-justice/",
            note=(
                "Marc & Lynne Benioff personal giving cumulative >$1B per Salesforce/"
                "TIME-cited reporting; includes $600M to healthcare in Hawaii and SF. "
                "Climate/restoration arm flows partly through TIME (acquired 2018, "
                "$190M) — Benioff TIME Tree Fund $100M + TIME Ventures $100M (2021). "
                "Mixed LLC + foundation + corporate-philanthropy structure."
            ),
            event_role="transfer_in",
        ),
    ],
    "jeff bezos": [
        LLCCommitment(
            llc_name="Bezos Earth Fund (operating LLC: Fellowship Ventures LLC)",
            year=2020,
            amount_usd=10_000_000_000.0,
            source_url="https://www.bezosearthfund.org/our-journey",
            secondary_source_url="https://www.npr.org/2020/02/17/806720144/jeff-bezos-pledges-10-billion-to-fight-climate-change-planets-biggest-threat",
            note=(
                "Bezos Earth Fund: Feb-2020 dated commitment of $10B for climate, "
                "to be fully disbursed by 2030. Operating LLC is Fellowship Ventures "
                "LLC. ≈$2B disbursed as of 2026 (Fortune/Axios). LLC structure means "
                "no 990; figures are donor + fund self-disclosure."
            ),
        ),
    ],
    "melinda french gates": [
        LLCCommitment(
            llc_name="Pivotal Ventures LLC",
            year=2019,
            amount_usd=1_000_000_000.0,
            source_url="https://www.pivotal.com/articles/melinda-french-gates-announces-1billlion-commitment-to-advance-women-globally",
            note=(
                "Pivotal Ventures LLC: 2019 commitment of $1B over 10 years for "
                "gender-equality work in the U.S. LLC blends VC-style investing with "
                "philanthropy and advocacy — disclosure is partial."
            ),
        ),
        LLCCommitment(
            llc_name="Pivotal Ventures LLC",
            year=2024,
            amount_usd=1_000_000_000.0,
            source_url="https://variety.com/2024/biz/news/melinda-french-gates-1-billion-women-pivotal-ventures-1236017610/",
            secondary_source_url="https://philanthropynewsdigest.org/news/melinda-french-gates-commits-1-billion-to-women-s-causes",
            note=(
                "Pivotal: May-2024 additional $1B commitment over 2 years for "
                "reproductive rights and women's causes globally. Brings cumulative "
                "Pivotal commitments to ≈$2B."
            ),
        ),
    ],
    "mackenzie scott": [
        LLCCommitment(
            llc_name="Lost Horse LLC",
            year=2025,
            amount_usd=26_000_000_000.0,  # cumulative announced gifts as of 2025
            source_url="https://www.ceotodaymagazine.com/2025/02/mackenzie-scotts-monumental-donations-a-legacy-of-philanthropy/",
            secondary_source_url="https://www.insidephilanthropy.com/home/2022-12-15-mackenzie-scotts-website-and-grants-database-has-arrived-heres-what-we-learned",
            note=(
                "Lost Horse LLC (Seattle, est. late 2019) is MacKenzie Scott's family-"
                "office vehicle that orchestrates her giving (paid out via DAFs and "
                "direct grants). Cumulative announced giving ≈$26B as of 2025 "
                "(including $7.2B in 2025 alone). Unusual — Lost Horse is opaque but "
                "Scott self-publishes a recipient database (yieldgiving.com)."
            ),
            confidence="high",
            event_role="transfer_in",
        ),
    ],
    "ken griffin": [
        LLCCommitment(
            llc_name="Griffin Catalyst",
            year=2023,
            amount_usd=2_500_000_000.0,
            source_url="https://www.griffincatalyst.org/about/",
            secondary_source_url="https://en.wikipedia.org/wiki/Kenneth_C._Griffin",
            note=(
                "Griffin Catalyst (est. Sep 2023) is the umbrella label for Ken "
                "Griffin's philanthropic and civic activity; described as a 'civic "
                "engagement initiative,' not a formal grantmaker. Self-reported "
                "lifetime giving >$2.5B. Structure ambiguous — sits over multiple "
                "underlying vehicles."
            ),
            confidence="medium",
            event_role="transfer_in",
        ),
    ],
    "lukas walton": [
        LLCCommitment(
            llc_name="Builders Vision LLC",
            year=2025,
            amount_usd=15_000_000_000.0,
            source_url="https://lifestylesmagazine.com/latest-news/15-billion-self-funded-initiative-by-38-year-old-lukas-walton-will-accelerate-investment-and-innovation-in-environmental-solutions/",
            secondary_source_url="https://www.buildersvision.com/who-we-are/",
            note=(
                "Builders Vision LLC: June-2025 first-ever public disclosure — Lukas "
                "Walton has committed $15B of personal wealth across the platform "
                "(food/agriculture, energy, oceans). ≈$700M philanthropic capital "
                "disbursed to date. LLC blends impact investing + grants — capacity "
                "is large but disbursement opaque."
            ),
            event_role="transfer_in",
        ),
    ],
    "john arnold": [
        LLCCommitment(
            llc_name="Arnold Ventures LLC",
            year=2024,
            amount_usd=2_000_000_000.0,
            source_url="https://fortune.com/2025/10/25/billionaire-success-couple-donated-half-their-wealth-the-giving-pledge-bill-gates-philiantrophy-john-laura-arnold-arnold-ventures/",
            secondary_source_url="https://en.wikipedia.org/wiki/Arnold_Ventures",
            note=(
                "Arnold Ventures LLC (formerly Laura and John Arnold Foundation, "
                "restructured to LLC): cumulative giving ≈$2B since 2010 Giving "
                "Pledge signing. IPS 2025 'Giving Pledge at 15' report names the "
                "Arnolds as the only signatories technically in compliance with "
                "the pledge."
            ),
            confidence="high",
            event_role="transfer_in",
        ),
    ],
    "laura arnold": [
        LLCCommitment(
            llc_name="Arnold Ventures LLC",
            year=2024,
            amount_usd=2_000_000_000.0,
            source_url="https://fortune.com/2025/10/25/billionaire-success-couple-donated-half-their-wealth-the-giving-pledge-bill-gates-philiantrophy-john-laura-arnold-arnold-ventures/",
            note="Joint commitment with John Arnold — see John Arnold entry.",
            confidence="high",
            event_role="transfer_in",
        ),
    ],
    "pierre omidyar": [
        LLCCommitment(
            llc_name="Omidyar Network LLC",
            year=2025,
            amount_usd=4_000_000_000.0,
            source_url="https://time.com/collections/time100-philanthropy-2025/7286018/pierre-omidyar-pam-omidyar/",
            secondary_source_url="https://en.wikipedia.org/wiki/Omidyar_Network",
            note=(
                "Omidyar Network (LLC + 501(c)(3) hybrid, est. 2004) cumulative "
                "directed >$1.94B across ≈700 organizations as of 2025. Pierre and "
                "Pam Omidyar combined philanthropic giving across all vehicles >$4B "
                "per TIME100 Philanthropy 2025 (includes Omidyar Network, Humanity "
                "United, Democracy Fund, Luminate)."
            ),
            confidence="high",
            event_role="transfer_in",
        ),
    ],
    "yvon chouinard": [
        LLCCommitment(
            llc_name="Holdfast Collective (501(c)(4) — LLC-equivalent opacity)",
            year=2022,
            amount_usd=3_000_000_000.0,
            source_url="https://www.patagonia.com/ownership/",
            secondary_source_url="https://www.cbsnews.com/news/patagonia-gives-away-company-to-climate-change-nonprofit/",
            note=(
                "Sep-2022 transfer of 98% of Patagonia equity (≈$3B) to Holdfast "
                "Collective, a 501(c)(4) social-welfare org. Future Patagonia profits "
                "(~$100M/yr) flow to Holdfast for climate advocacy. 501(c)(4) "
                "structure has LLC-equivalent opacity — no donor disclosure required."
            ),
            confidence="high",
            event_role="transfer_in",
        ),
    ],
    "jack dorsey": [
        LLCCommitment(
            llc_name="Start Small LLC",
            year=2020,
            amount_usd=1_000_000_000.0,
            source_url="https://x.com/jack/status/1247616214769086465",
            secondary_source_url="https://startsmall.llc/",
            note=(
                "April-2020 transfer of $1B Square equity (≈28% of his net worth) "
                "to Start Small LLC — initially for COVID-19 relief, later girls' "
                "health/education + UBI + Bitcoin. As of Jan-2026 self-tracker "
                "shows ≈$1.64B notional (after appreciation), ≈$795M distributed, "
                "≈$844M remaining. Most transparent LLC in catalog — public "
                "Google sheet of every grant."
            ),
            confidence="high",
            event_role="transfer_in",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_path(subject_id: str) -> Path:
    return CACHE_DIR / f"{subject_id}.json"


def _load_cache(subject_id: str) -> list[dict] | None:
    p = _cache_path(subject_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_cache(subject_id: str, candidates: list[dict]) -> None:
    _cache_path(subject_id).write_text(json.dumps(candidates, indent=2))


def _subject_id(record: dict) -> str:
    name = (record.get("person") or {}).get("name_display") or "unknown"
    return name.lower().replace(" ", "_")


# ---------------------------------------------------------------------------
# Candidate assembly
# ---------------------------------------------------------------------------


def _commitment_to_candidate(c: LLCCommitment, subject_name: str) -> dict:
    return {
        "event_role": c.event_role,
        "year": c.year,
        "date_precision": "year",
        "donor_entity": subject_name,
        "recipient": c.llc_name,
        "amount_usd": c.amount_usd,
        "source_type": "philanthropic_llc_commitment",
        "source_url": c.source_url,
        "confidence": c.confidence,
        "note": c.note,
        "regen_source": "llcs",
    }


def _declared_vehicles_to_reference(record: dict, covered_llc_names: set[str]) -> list[dict]:
    """Emit reference_only candidates for record-declared LLC vehicles
    that the curated catalog hasn't covered. These flow into sources_all
    as a capacity signal — 'this LLC exists, look here for further work.'
    """
    out: list[dict] = []
    vehicles = record.get("detected_vehicles") or {}
    declared = vehicles.get("llcs_philanthropic") or []
    subject_name = (record.get("person") or {}).get("name_display") or ""

    seen_urls: set[str] = set()
    for v in declared:
        if not isinstance(v, dict):
            continue
        name = (v.get("name") or "").strip()
        if not name:
            continue
        # Skip vehicles flagged in their own name as non-philanthropic.
        lname = name.lower()
        if "not philanthropic" in lname or "family office" in lname:
            continue
        # Skip if catalog already produced commitments for this LLC.
        if any(
            covered.lower() in lname or lname in covered.lower()
            for covered in covered_llc_names
        ):
            continue
        url = v.get("source_url")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        out.append({
            "event_role": "reference_only",
            "year": v.get("established_year") or v.get("year_established") or v.get("year_launched"),
            "donor_entity": subject_name,
            "recipient": name,
            "amount_usd": None,
            "source_type": "philanthropic_llc_declared",
            "source_url": url,
            "confidence": "low",
            "note": (
                f"Record-declared philanthropic LLC '{name}' for {subject_name}; "
                f"no curated commitment in KNOWN_PHILANTHROPIC_LLCS. Capacity signal "
                f"only — opaque downstream."
            ),
            "regen_source": "llcs",
        })
    return out


def collect_candidates(record: dict, *, refresh: bool = False) -> list[dict]:
    """Return regen_v3 candidate events for philanthropic LLC commitments.

    Mirrors `regen_v3/propublica.py`. Cached per subject so the cohort run
    has predictable cache-hit behavior. The catalog is hardcoded, so
    `refresh=True` mostly serves to re-pick-up edits to this file.
    """
    subject_name = (record.get("person") or {}).get("name_display") or ""
    if not subject_name:
        return []
    sid = _subject_id(record)

    if not refresh:
        cached = _load_cache(sid)
        if cached is not None:
            return cached

    candidates: list[dict] = []
    name_key = subject_name.lower()

    catalog_hits = KNOWN_PHILANTHROPIC_LLCS.get(name_key) or []
    covered_llcs: set[str] = set()
    for c in catalog_hits:
        candidates.append(_commitment_to_candidate(c, subject_name))
        covered_llcs.add(c.llc_name)

    candidates.extend(_declared_vehicles_to_reference(record, covered_llcs))

    candidates.sort(key=lambda c: (c.get("year") or 0, c.get("recipient") or ""))
    _save_cache(sid, candidates)
    return candidates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True, help="Subject id (e.g. mark_zuckerberg)")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    rec_path = ROOT / "data" / f"{args.subject}.v3.json"
    record = json.loads(rec_path.read_text())
    cands = collect_candidates(record, refresh=args.refresh)
    print(f"{args.subject}: {len(cands)} candidates")
    for c in cands:
        amt = c.get("amount_usd")
        amt_s = f"${amt/1e9:.2f}B" if amt else "  bound  "
        print(
            f"  {c['year']!s:<6} {c['event_role']:<14} "
            f"{amt_s:<10} {c.get('recipient')}"
        )
