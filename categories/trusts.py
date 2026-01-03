"""
SPLIT_INTEREST_TRUSTS Category Estimator

Confidence: LOW - Form 5227 is not searchable

Types:
- CLAT (Charitable Lead Annuity Trust): Charity gets income, heirs get remainder
- CRAT (Charitable Remainder Annuity Trust): Donor gets income, charity gets remainder
- CRT (Charitable Remainder Trust): Similar to CRAT
- CLUT (Charitable Lead Unitrust): Variable payment version of CLAT

Famous examples:
- Walton family CLATs (estimated $20B+ transferred tax-free)
- Buffett CRATs

Data Sources:
1. Form 5227 - Filed annually but NOT publicly searchable
2. News/court filings - For famous cases
3. Estate planning articles - Mentions of structures used
"""

import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


# Known split-interest trust structures by billionaire
# Sources: News articles, court filings, estate planning publications
KNOWN_TRUSTS = {
    "jim walton": {
        "trusts": [
            {
                "type": "CLAT",
                "name": "Walton Family CLAT",
                "estimated_value": 5_000_000_000,
                "source": "https://www.bloomberg.com/news/features/2021-09-23/how-the-waltons-billionaires-behind-walmart-spend-their-fortune",
                "note": "Waltons used CLATs to transfer billions tax-free",
            }
        ],
    },
    "rob walton": {
        "trusts": [
            {
                "type": "CLAT",
                "name": "Walton Family CLAT",
                "estimated_value": 5_000_000_000,
                "source": "https://www.bloomberg.com/news/features/2021-09-23/how-the-waltons-billionaires-behind-walmart-spend-their-fortune",
            }
        ],
    },
    "alice walton": {
        "trusts": [
            {
                "type": "CLAT",
                "name": "Walton Family CLAT",
                "estimated_value": 5_000_000_000,
                "source": "https://www.bloomberg.com/news/features/2021-09-23/how-the-waltons-billionaires-behind-walmart-spend-their-fortune",
            }
        ],
    },
    "warren buffett": {
        "trusts": [
            {
                "type": "CRT",
                "name": "Buffett charitable remainder trusts",
                "estimated_value": 1_000_000_000,
                "source": "https://www.forbes.com/sites/danalexander/2023/07/04/warren-buffett-charitable-giving/",
                "note": "Used CRTs for estate planning",
            }
        ],
    },
    # Many tech billionaires likely have CLATs but they're not public
}


@dataclass
class SplitInterestTrust:
    """A split-interest trust."""
    trust_type: str  # CLAT, CRAT, CRT, CLUT
    name: str
    estimated_value: float
    annual_payout: float  # Estimated annual charitable distribution
    source_url: str
    note: str


def estimate_annual_payout(trust_type: str, value: float) -> float:
    """
    Estimate annual charitable payout based on trust type.

    CLATs: Typically 5-8% annual payout to charity
    CRATs: Variable, depends on structure
    """
    if trust_type == "CLAT":
        return value * 0.06  # 6% typical annuity rate
    elif trust_type in ["CRAT", "CRT"]:
        return value * 0.05  # 5% typical
    elif trust_type == "CLUT":
        return value * 0.05
    else:
        return 0


def estimate_split_interest_trusts(name: str) -> Dict:
    """
    Estimate split-interest trust giving for a billionaire.

    Note: Most trusts are NOT observable. We can only track:
    1. Known structures from news/court filings
    2. Estimates based on estate planning norms

    Args:
        name: Billionaire name

    Returns:
        Dict with trust data
    """
    print(f"  Researching split-interest trusts for {name}...")

    name_lower = name.lower()
    known = KNOWN_TRUSTS.get(name_lower, {})

    trusts = []

    if known:
        for t in known.get("trusts", []):
            value = t.get("estimated_value", 0)
            trust_type = t.get("type", "Unknown")

            trusts.append(SplitInterestTrust(
                trust_type=trust_type,
                name=t.get("name", "Unknown"),
                estimated_value=value,
                annual_payout=estimate_annual_payout(trust_type, value),
                source_url=t.get("source", ""),
                note=t.get("note", ""),
            ))

    total_value = sum(t.estimated_value for t in trusts)
    annual_payout = sum(t.annual_payout for t in trusts)

    if trusts:
        confidence = "LOW"  # We have data but it's estimates
    else:
        confidence = "ZERO"  # Can't observe

    print(f"    Found {len(trusts)} known trust structures")
    print(f"    Estimated annual payout: ${annual_payout/1e6:.1f}M")

    return {
        "category": "SPLIT_INTEREST_TRUSTS",
        "billionaire": name,
        "trusts": [asdict(t) for t in trusts],
        "total_value": total_value,
        "annual_payout": annual_payout,
        "trust_count": len(trusts),
        "confidence": confidence,
        "note": "Form 5227 is not publicly searchable - only known cases tracked",
        "source_urls": [t.source_url for t in trusts if t.source_url],
    }


if __name__ == "__main__":
    test_names = ["Jim Walton", "Warren Buffett", "Elon Musk"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = estimate_split_interest_trusts(name)
        print(f"\nSummary for {name}:")
        print(f"  Trust count: {result['trust_count']}")
        print(f"  Total value: ${result['total_value']/1e9:.1f}B")
        print(f"  Annual payout: ${result['annual_payout']/1e6:.1f}M")
        print(f"  Confidence: {result['confidence']}")
