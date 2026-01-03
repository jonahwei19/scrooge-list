"""
Stage 2: Match Foundations via ProPublica 990-PF

STATUS: ✅ Implemented

For each billionaire, searches ProPublica Nonprofit Explorer for foundations
matching their name. Pulls 990-PF data: assets, grants paid, payout rate.
"""

import requests
import re
import time
from dataclasses import dataclass
from typing import List, Dict, Optional

PROPUBLICA_BASE = "https://projects.propublica.org/nonprofits/api/v2"
RATE_LIMIT_DELAY = 0.5


@dataclass
class Foundation:
    ein: str
    name: str
    total_assets: float
    grants_paid_latest: float
    payout_rate: float
    years_of_data: int
    officer_compensation: float = 0
    daf_grants_pct: float = 0


# Known foundation mappings for top billionaires
KNOWN_FOUNDATIONS = {
    "elon musk": ["musk foundation"],
    "jeff bezos": ["bezos earth fund", "bezos day one fund", "bezos family foundation"],
    "mark zuckerberg": ["chan zuckerberg initiative"],
    "bill gates": ["bill melinda gates foundation", "gates foundation"],
    "warren buffett": ["susan thompson buffett foundation", "howard buffett foundation"],
    "larry ellison": ["ellison medical foundation", "lawrence ellison foundation"],
    "michael bloomberg": ["bloomberg philanthropies", "bloomberg family foundation"],
    "mackenzie scott": ["lost horse llc"],
    "larry page": ["carl victor page memorial foundation"],
    "sergey brin": ["brin wojcicki foundation", "sergey brin family foundation"],
    "steve ballmer": ["ballmer group"],
    "michael dell": ["michael susan dell foundation"],
    "phil knight": ["knight foundation"],
    "charles koch": ["charles koch foundation", "charles koch institute"],
    "ray dalio": ["dalio foundation", "dalio philanthropies"],
    "stephen schwarzman": ["schwarzman foundation", "stephen schwarzman foundation"],
    "ken griffin": ["kenneth griffin foundation", "citadel foundation"],
    "jensen huang": ["jen-hsun lori huang foundation"],
}


def _generate_search_terms(name: str) -> List[str]:
    """Generate likely foundation name variants."""
    clean_name = re.sub(r'\s*&\s*family\s*', ' ', name).strip()
    parts = clean_name.split()
    last_name = parts[-1].lower() if parts else ""
    first_name = parts[0].lower() if parts else ""

    return [
        f"{last_name} foundation",
        f"{last_name} family foundation",
        f"{first_name} {last_name} foundation",
    ]


def _get_search_terms(name: str) -> List[str]:
    """Get search terms, using known mappings when available."""
    key = name.lower()
    if key in KNOWN_FOUNDATIONS:
        return KNOWN_FOUNDATIONS[key]
    return _generate_search_terms(name)


def _search_propublica(query: str) -> List[Dict]:
    """Search ProPublica Nonprofit Explorer."""
    url = f"{PROPUBLICA_BASE}/search.json"
    try:
        resp = requests.get(url, params={"q": query}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("organizations", [])
    except Exception:
        return []


def _get_foundation_details(ein: str) -> Optional[Dict]:
    """Get detailed 990-PF filing data."""
    url = f"{PROPUBLICA_BASE}/organizations/{ein}.json"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _extract_metrics(org_data: Dict) -> Optional[Foundation]:
    """Extract key metrics from 990-PF filings."""
    org = org_data.get("organization", {})
    filings = org_data.get("filings_with_data", [])

    pf_filings = [f for f in filings if f.get("formtype") == 2]
    if not pf_filings:
        return None

    latest = pf_filings[0]
    total_assets = latest.get("totassetsend") or latest.get("fairmrktvalamt") or 0
    grants_paid = latest.get("contrpdpbks") or 0
    payout_rate = (grants_paid / total_assets) if total_assets > 0 else 0
    officer_comp = latest.get("compenstateofadings") or 0

    return Foundation(
        ein=org.get("ein", ""),
        name=org.get("name", ""),
        total_assets=total_assets,
        grants_paid_latest=grants_paid,
        payout_rate=payout_rate,
        years_of_data=len(pf_filings),
        officer_compensation=officer_comp,
    )


def match_foundations(name: str) -> List[Foundation]:
    """
    Find all foundations likely associated with a billionaire.

    Returns list of Foundation objects with assets, grants, payout rate.
    """
    foundations = []
    seen_eins = set()

    search_terms = _get_search_terms(name)

    for term in search_terms:
        results = _search_propublica(term)
        time.sleep(RATE_LIMIT_DELAY)

        for org in results[:5]:
            ein = org.get("ein")
            if ein in seen_eins:
                continue
            seen_eins.add(ein)

            if org.get("subseccd") != 3:
                continue

            details = _get_foundation_details(ein)
            if not details:
                continue

            foundation = _extract_metrics(details)
            if foundation and foundation.total_assets > 1_000_000:
                foundations.append(foundation)

            time.sleep(RATE_LIMIT_DELAY)

    return foundations


if __name__ == "__main__":
    test_names = ["Bill Gates", "Warren Buffett", "Elon Musk"]
    for name in test_names:
        print(f"\n{name}:")
        foundations = match_foundations(name)
        for f in foundations:
            print(f"  {f.name}: ${f.total_assets/1e9:.2f}B assets, {f.payout_rate:.1%} payout")
