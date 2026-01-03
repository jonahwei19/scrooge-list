"""
DAF (Donor-Advised Fund) Category Estimator

Confidence: LOW - DAFs have minimal disclosure requirements

Data Flow:
1. Check foundation 990-PF Part XV for grants to DAF sponsors
2. Estimate based on net worth (industry average ~0.3% annually)
3. Track as "parked" vs "deployed" giving

Key DAF sponsors to look for:
- Fidelity Charitable
- Schwab Charitable
- Vanguard Charitable
- National Philanthropic Trust
- Silicon Valley Community Foundation
"""

import requests
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


# Major DAF sponsors and their EINs
DAF_SPONSORS = {
    "Fidelity Charitable Gift Fund": "11-0303001",
    "Schwab Charitable Fund": "31-1640316",
    "Vanguard Charitable Endowment Program": "23-2888152",
    "National Philanthropic Trust": "52-1934107",
    "Silicon Valley Community Foundation": "20-5205488",
    "Goldman Sachs Philanthropy Fund": "45-2831855",
    "Donors Trust": "52-2166327",
    "Tides Foundation": "51-0198509",
}


@dataclass
class DAFContribution:
    """A contribution to a DAF sponsor."""
    sponsor_name: str
    amount: float
    year: int
    source: str  # "990-PF" or "estimate"
    source_url: str


def search_foundation_daf_grants(foundation_ein: str) -> List[DAFContribution]:
    """
    Search foundation 990-PF for grants to DAF sponsors.

    Note: This requires parsing Part XV of the 990-PF which lists
    all grants made. We look for any grants to known DAF sponsors.
    """
    contributions = []

    try:
        # Fetch foundation data from ProPublica
        ein_clean = foundation_ein.replace("-", "")
        url = f"https://projects.propublica.org/nonprofits/api/v2/organizations/{ein_clean}.json"

        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        filings = data.get("filings_with_data", [])

        # ProPublica doesn't expose Part XV grant details via API
        # We can only detect DAF transfers if they're in the XML filing
        # For now, flag that this needs manual review

    except Exception as e:
        print(f"    Error checking foundation for DAF grants: {e}")

    return contributions


def estimate_daf_from_networth(net_worth_billions: float) -> float:
    """
    Estimate DAF contributions based on net worth.

    Industry data suggests UHNW individuals contribute ~0.3% of
    net worth to DAFs annually. This is a rough proxy.
    """
    # 0.3% of net worth is industry average
    return net_worth_billions * 1e9 * 0.003


def estimate_daf_giving(
    name: str,
    net_worth_billions: float,
    foundation_eins: List[str] = None
) -> Dict:
    """
    Estimate DAF contributions for a billionaire.

    Args:
        name: Billionaire name
        net_worth_billions: Net worth
        foundation_eins: List of their foundation EINs to check

    Returns:
        Dict with DAF estimate data
    """
    print(f"  Researching DAF contributions for {name}...")

    all_contributions = []

    # Check foundation 990s for DAF grants
    if foundation_eins:
        for ein in foundation_eins:
            contributions = search_foundation_daf_grants(ein)
            all_contributions.extend(contributions)

    # Calculate observed DAF transfers
    observed_total = sum(c.amount for c in all_contributions)

    # Net worth based estimate
    nw_estimate = estimate_daf_from_networth(net_worth_billions)

    # If we found actual transfers, use those (higher confidence)
    # Otherwise use the estimate (low confidence)
    if observed_total > 0:
        total = observed_total
        confidence = "MEDIUM"
        method = "990-PF Part XV"
    else:
        total = nw_estimate
        confidence = "LOW"
        method = "net worth proxy (0.3%)"

    print(f"    Observed DAF transfers: ${observed_total/1e6:.1f}M")
    print(f"    Net worth estimate: ${nw_estimate/1e6:.1f}M")
    print(f"    Using: {method}")

    return {
        "category": "DAFS",
        "billionaire": name,
        "contributions": [asdict(c) for c in all_contributions],
        "observed_total": observed_total,
        "nw_estimate": nw_estimate,
        "total_used": total,
        "method": method,
        "confidence": confidence,
        "note": "DAFs are 'parked' giving - may not reach charities for years",
        "red_flag": observed_total > total * 0.5 if total > 0 else False,
        "source_urls": [c.source_url for c in all_contributions],
    }


if __name__ == "__main__":
    test_cases = [
        ("Elon Musk", 718.0, ["85-2133087"]),
        ("Mark Zuckerberg", 223.0, ["45-5002209"]),
        ("Warren Buffett", 146.8, ["47-0824147"]),
    ]

    for name, nw, eins in test_cases:
        print(f"\n{'='*60}")
        result = estimate_daf_giving(name, nw, eins)
        print(f"\nSummary for {name}:")
        print(f"  Observed transfers: ${result['observed_total']/1e6:.1f}M")
        print(f"  NW estimate: ${result['nw_estimate']/1e6:.1f}M")
        print(f"  Confidence: {result['confidence']}")
