"""
NONCASH CONTRIBUTIONS (IRS Form 8283)

IRS Form 8283 is required for noncash charitable contributions over $500.
For contributions over $5,000, a qualified appraisal is required.

Common noncash gifts from billionaires:
- Appreciated stock (most common - avoids capital gains)
- Real estate (land, buildings, conservation easements)
- Art and collectibles
- Cryptocurrency
- Business interests (LLC/partnership interests)
- Patents and intellectual property

Note: Form 8283 is filed with individual tax returns and is NOT public.
However, we can infer noncash contributions from:
1. SEC Form 4 (stock gifts)
2. Conservation easement databases
3. Art donation announcements
4. Real estate transfer records
"""

import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class NoncashContribution:
    """A noncash charitable contribution."""
    donor: str
    asset_type: str  # Stock, Real Estate, Art, Crypto, etc.
    recipient: str
    fair_market_value: float
    cost_basis: float  # Original cost (for tax benefit calculation)
    year: int
    description: str
    source_url: str


# Known major noncash contributions
KNOWN_NONCASH_CONTRIBUTIONS = {
    "warren buffett": [
        {
            "asset_type": "Stock",
            "recipient": "Bill & Melinda Gates Foundation",
            "fair_market_value": 4_640_000_000,
            "cost_basis": 0,  # Near zero basis
            "year": 2023,
            "description": "Berkshire Hathaway Class B shares",
            "source_url": "https://www.philanthropy.com/article/buffett-gives-4-6-billion",
        },
        {
            "asset_type": "Stock",
            "recipient": "Susan Thompson Buffett Foundation",
            "fair_market_value": 1_100_000_000,
            "cost_basis": 0,
            "year": 2023,
            "description": "Berkshire Hathaway Class B shares",
            "source_url": "https://www.philanthropy.com/article/buffett-gives-4-6-billion",
        },
    ],
    "elon musk": [
        {
            "asset_type": "Stock",
            "recipient": "Fidelity Charitable (DAF)",
            "fair_market_value": 5_700_000_000,
            "cost_basis": 100_000_000,  # Estimated original options cost
            "year": 2021,
            "description": "Tesla shares",
            "source_url": "https://www.bloomberg.com/news/articles/2022-02-15/musk-gave-5-7-billion-of-tesla-shares-to-charity-last-november",
        },
    ],
    "mark zuckerberg": [
        {
            "asset_type": "Stock",
            "recipient": "Chan Zuckerberg Initiative",
            "fair_market_value": 45_000_000_000,
            "cost_basis": 0,  # Founder shares
            "year": 2015,
            "description": "Meta shares (99% pledge)",
            "source_url": "https://www.facebook.com/notes/mark-zuckerberg/a-letter-to-our-daughter/10153375081581634/",
        },
    ],
    "jeff bezos": [
        {
            "asset_type": "Stock",
            "recipient": "Bezos Earth Fund",
            "fair_market_value": 10_000_000_000,
            "cost_basis": 0,  # Founder shares
            "year": 2020,
            "description": "Amazon shares (pledge)",
            "source_url": "https://www.bezosearthfund.org/",
        },
    ],
    "mackenzie scott": [
        {
            "asset_type": "Stock",
            "recipient": "Various nonprofits (direct)",
            "fair_market_value": 8_500_000_000,
            "cost_basis": 0,  # From divorce settlement
            "year": 2021,
            "description": "Amazon shares distributed to 700+ orgs",
            "source_url": "https://mackenzie-scott.medium.com/",
        },
    ],
    "bill gates": [
        {
            "asset_type": "Stock",
            "recipient": "Gates Foundation",
            "fair_market_value": 20_000_000_000,
            "cost_basis": 100_000_000,
            "year": 2022,
            "description": "Microsoft and other securities",
            "source_url": "https://www.gatesfoundation.org/",
        },
    ],
    "george soros": [
        {
            "asset_type": "Stock",
            "recipient": "Open Society Foundations",
            "fair_market_value": 18_000_000_000,
            "cost_basis": 0,
            "year": 2017,
            "description": "Bulk of personal fortune transferred",
            "source_url": "https://www.wsj.com/articles/george-soros-transfers-18-billion-to-his-foundation-1508252926",
        },
    ],
}


# Conservation easement data (large land donations)
KNOWN_CONSERVATION_EASEMENTS = {
    "ted turner": [
        {
            "asset_type": "Conservation Easement",
            "recipient": "Various land trusts",
            "fair_market_value": 500_000_000,
            "year": 2020,
            "description": "2 million acres across multiple states",
            "source_url": "https://www.tedturner.com/turner-ranches/",
        },
    ],
    "john malone": [
        {
            "asset_type": "Conservation Easement",
            "recipient": "Land trusts",
            "fair_market_value": 300_000_000,
            "year": 2022,
            "description": "Largest private landowner in US - conservation restrictions",
            "source_url": "https://landreport.com/",
        },
    ],
}


# Art donation data (museum gifts)
KNOWN_ART_DONATIONS = {
    "eli broad": [
        {
            "asset_type": "Art",
            "recipient": "The Broad Museum (LA)",
            "fair_market_value": 2_000_000_000,
            "year": 2015,
            "description": "Contemporary art collection",
            "source_url": "https://www.thebroad.org/",
        },
    ],
    "leonard lauder": [
        {
            "asset_type": "Art",
            "recipient": "Metropolitan Museum of Art",
            "fair_market_value": 1_000_000_000,
            "year": 2013,
            "description": "Cubist art collection (78 works)",
            "source_url": "https://www.metmuseum.org/",
        },
    ],
    "david geffen": [
        {
            "asset_type": "Art",
            "recipient": "LACMA / MoMA",
            "fair_market_value": 300_000_000,
            "year": 2020,
            "description": "Various contemporary works",
            "source_url": "https://www.lacma.org/",
        },
    ],
}


def calculate_tax_benefit(fmv: float, cost_basis: float,
                          marginal_rate: float = 0.37,
                          cap_gains_rate: float = 0.238) -> Dict:
    """
    Calculate tax benefit of donating appreciated assets.

    For appreciated stock held > 1 year:
    - Deduct full FMV
    - Avoid capital gains tax

    Tax benefit = FMV * marginal_rate + (FMV - basis) * cap_gains_rate
    """
    deduction_value = fmv * marginal_rate
    avoided_cap_gains = (fmv - cost_basis) * cap_gains_rate
    total_benefit = deduction_value + avoided_cap_gains

    return {
        "fair_market_value": fmv,
        "cost_basis": cost_basis,
        "unrealized_gain": fmv - cost_basis,
        "deduction_value": deduction_value,
        "avoided_cap_gains_tax": avoided_cap_gains,
        "total_tax_benefit": total_benefit,
        "effective_cost": fmv - total_benefit,
        "benefit_rate": total_benefit / fmv if fmv > 0 else 0,
    }


def estimate_noncash_contributions(name: str) -> Dict:
    """
    Estimate noncash charitable contributions for a billionaire.

    Returns:
        Dict with noncash contribution findings
    """
    print(f"  Researching noncash contributions for {name}...")

    name_lower = name.lower()

    all_contributions = []

    # Check securities/stock gifts
    stock_gifts = KNOWN_NONCASH_CONTRIBUTIONS.get(name_lower, [])
    for g in stock_gifts:
        all_contributions.append(NoncashContribution(
            donor=name,
            asset_type=g["asset_type"],
            recipient=g["recipient"],
            fair_market_value=g["fair_market_value"],
            cost_basis=g.get("cost_basis", 0),
            year=g["year"],
            description=g["description"],
            source_url=g["source_url"],
        ))

    # Check conservation easements
    easements = KNOWN_CONSERVATION_EASEMENTS.get(name_lower, [])
    for e in easements:
        all_contributions.append(NoncashContribution(
            donor=name,
            asset_type=e["asset_type"],
            recipient=e["recipient"],
            fair_market_value=e["fair_market_value"],
            cost_basis=0,
            year=e["year"],
            description=e["description"],
            source_url=e["source_url"],
        ))

    # Check art donations
    art_gifts = KNOWN_ART_DONATIONS.get(name_lower, [])
    for a in art_gifts:
        all_contributions.append(NoncashContribution(
            donor=name,
            asset_type=a["asset_type"],
            recipient=a["recipient"],
            fair_market_value=a["fair_market_value"],
            cost_basis=0,
            year=a["year"],
            description=a["description"],
            source_url=a["source_url"],
        ))

    total_fmv = sum(c.fair_market_value for c in all_contributions)
    total_basis = sum(c.cost_basis for c in all_contributions)

    # Calculate aggregate tax benefit
    if all_contributions:
        tax_benefit = calculate_tax_benefit(total_fmv, total_basis)
    else:
        tax_benefit = {}

    asset_types = list(set(c.asset_type for c in all_contributions))

    print(f"    Found {len(all_contributions)} noncash contributions")
    print(f"    Total FMV: ${total_fmv/1e9:.2f}B")
    if tax_benefit:
        print(f"    Tax benefit: ${tax_benefit.get('total_tax_benefit', 0)/1e9:.2f}B")

    return {
        "category": "NONCASH_CONTRIBUTIONS",
        "billionaire": name,
        "contributions": [asdict(c) for c in all_contributions],
        "contribution_count": len(all_contributions),
        "asset_types": asset_types,
        "total_fair_market_value": total_fmv,
        "total_cost_basis": total_basis,
        "total_unrealized_gain": total_fmv - total_basis,
        "tax_benefit_analysis": tax_benefit,
        "confidence": "HIGH" if all_contributions else "ZERO",
        "source_urls": [c.source_url for c in all_contributions],
    }


if __name__ == "__main__":
    test_names = ["Warren Buffett", "Elon Musk", "MacKenzie Scott", "Eli Broad"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = estimate_noncash_contributions(name)
        print(f"\nSummary for {name}:")
        print(f"  Contributions: {result['contribution_count']}")
        print(f"  Total FMV: ${result['total_fair_market_value']/1e9:.2f}B")
        if result['tax_benefit_analysis']:
            print(f"  Effective cost: ${result['tax_benefit_analysis'].get('effective_cost', 0)/1e9:.2f}B")
