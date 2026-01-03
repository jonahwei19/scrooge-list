"""
POLITICAL GIVING Category

Confidence: HIGH - FEC filings are mandatory

Data Sources:
1. FEC API - Individual contributions
2. OpenSecrets API - Aggregated data

This is tracked as CONTEXT, not charitable giving.
Research shows $1 political → $0.33 less charitable (NBER 26616).
"""

import requests
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

# FEC API key (public, rate-limited)
FEC_API_KEY = "DEMO_KEY"  # Replace with real key for production


@dataclass
class PoliticalContribution:
    """A political contribution from FEC records."""
    recipient: str
    recipient_type: str  # CANDIDATE, PAC, PARTY, SUPER_PAC
    amount: float
    date: str
    election_cycle: int
    source_url: str


def search_fec_contributions(
    name: str,
    min_amount: int = 1000,
    cycles: List[int] = None
) -> List[PoliticalContribution]:
    """
    Search FEC for individual contributions.

    Args:
        name: Contributor name
        min_amount: Minimum contribution to include
        cycles: Election cycles to search (default: last 3)
    """
    if cycles is None:
        cycles = [2024, 2022, 2020]

    contributions = []

    try:
        # FEC API endpoint for individual contributions
        url = "https://api.open.fec.gov/v1/schedules/schedule_a/"

        for cycle in cycles:
            params = {
                "api_key": FEC_API_KEY,
                "contributor_name": name,
                "two_year_transaction_period": cycle,
                "min_amount": min_amount,
                "per_page": 100,
                "sort": "-contribution_receipt_amount",
            }

            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                continue

            data = resp.json()
            results = data.get("results", [])

            for r in results:
                # Determine recipient type
                committee_type = r.get("committee", {}).get("committee_type", "")
                if committee_type in ["P", "S", "H"]:
                    recipient_type = "CANDIDATE"
                elif committee_type in ["N", "Q"]:
                    recipient_type = "PAC"
                elif committee_type in ["X", "Y", "Z"]:
                    recipient_type = "PARTY"
                elif committee_type == "O":
                    recipient_type = "SUPER_PAC"
                else:
                    recipient_type = "OTHER"

                contributions.append(PoliticalContribution(
                    recipient=r.get("committee", {}).get("name", "Unknown"),
                    recipient_type=recipient_type,
                    amount=float(r.get("contribution_receipt_amount", 0)),
                    date=r.get("contribution_receipt_date", ""),
                    election_cycle=cycle,
                    source_url=f"https://www.fec.gov/data/receipts/individual-contributions/?contributor_name={name.replace(' ', '+')}&two_year_transaction_period={cycle}",
                ))

            time.sleep(0.5)  # Rate limit

    except Exception as e:
        print(f"    FEC API error: {e}")

    return contributions


def estimate_political_giving(name: str) -> Dict:
    """
    Estimate political giving for a billionaire.

    Returns:
        Dict with political giving data (for context, not charity)
    """
    print(f"  Researching political giving for {name}...")

    contributions = search_fec_contributions(name)

    # Aggregate by type
    by_type = {}
    for c in contributions:
        if c.recipient_type not in by_type:
            by_type[c.recipient_type] = 0
        by_type[c.recipient_type] += c.amount

    total = sum(c.amount for c in contributions)

    # Determine political lean if enough data
    lean = None
    if contributions:
        # This would require party affiliation lookup
        # For now, just note total
        pass

    print(f"    Found {len(contributions)} contributions totaling ${total:,.0f}")

    return {
        "category": "POLITICAL",
        "billionaire": name,
        "contributions": [asdict(c) for c in contributions],
        "total": total,
        "contribution_count": len(contributions),
        "by_type": by_type,
        "confidence": "HIGH" if contributions else "ZERO",
        "note": "Political giving is NOT charitable - tracked for context only",
        "source_urls": list(set(c.source_url for c in contributions)),
    }


if __name__ == "__main__":
    test_names = ["Elon Musk", "George Soros", "Charles Koch"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = estimate_political_giving(name)
        print(f"\nSummary for {name}:")
        print(f"  Total contributions: ${result['total']:,.0f}")
        print(f"  Contribution count: {result['contribution_count']}")
        if result['by_type']:
            print(f"  By type: {result['by_type']}")
