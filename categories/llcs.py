"""
PHILANTHROPIC_LLCs Category Estimator

Confidence: MEDIUM for known LLCs, ZERO for unknown

Data Flow:
1. Check known LLC database for billionaire
2. Scrape LLC website for self-reported grants
3. Search news for announced grants
4. Reverse lookup: search 990s of nonprofits for grants FROM the LLC

LLCs don't file 990s, so we rely on:
- Self-disclosure
- News coverage
- Recipient 990 grants_received
"""

import requests
import re
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


# Known philanthropic LLCs and similar structures
# These entities don't file 990s but engage in philanthropic activities
KNOWN_LLCS = {
    "mark zuckerberg": {
        "name": "Chan Zuckerberg Initiative",
        "type": "LLC",
        "website": "https://chanzuckerberg.com",
        "grants_url": "https://chanzuckerberg.com/grants-ventures/grants/",
        "self_reports": True,
        "focus_areas": ["science", "education", "community"],
        "estimated_annual": 1_500_000_000,  # ~$1.5B/year in grants+investments
    },
    "laurene powell jobs": {
        "name": "Emerson Collective",
        "type": "LLC",
        "website": "https://www.emersoncollective.com",
        "self_reports": False,  # Minimal disclosure
        "focus_areas": ["education", "immigration", "environment", "media"],
        "estimated_annual": 500_000_000,  # Rough estimate based on news
    },
    "steve ballmer": {
        "name": "Ballmer Group",
        "type": "LLC",
        "website": "https://www.ballmergroup.org",
        "self_reports": True,
        "focus_areas": ["economic mobility", "children"],
        "estimated_annual": 400_000_000,
    },
    "yvon chouinard": {
        "name": "Holdfast Collective",
        "type": "501(c)(4)",  # Not LLC but similar opacity
        "website": None,
        "self_reports": False,
        "note": "Patagonia profits flow here for climate advocacy",
        "estimated_annual": 100_000_000,
    },
    "pierre omidyar": {
        "name": "Omidyar Network",
        "type": "LLC",
        "website": "https://omidyar.com",
        "self_reports": True,
        "focus_areas": ["tech", "governance", "financial inclusion"],
        "estimated_annual": 300_000_000,
    },
    "reid hoffman": {
        "name": "Greylock Philanthropic",  # + personal giving via LLC
        "type": "LLC",
        "website": None,
        "self_reports": False,
        "focus_areas": ["democracy", "AI safety"],
        "estimated_annual": 50_000_000,
    },
    "jack dorsey": {
        "name": "Start Small LLC",  # Precursor to foundation
        "type": "LLC",
        "website": None,
        "self_reports": True,  # Tweeted all grants
        "note": "Committed $1B via #startsmall, transferred to foundation",
        "estimated_annual": 200_000_000,
    },
    "dustin moskovitz": {
        "name": "Open Philanthropy",  # LLC that advises Good Ventures
        "type": "LLC",
        "website": "https://www.openphilanthropy.org",
        "self_reports": True,  # Publishes all grants
        "focus_areas": ["global health", "animal welfare", "AI safety", "biosecurity"],
        "estimated_annual": 500_000_000,
    },
    "john arnold": {
        "name": "Arnold Ventures",
        "type": "LLC",
        "website": "https://www.arnoldventures.org",
        "self_reports": True,
        "focus_areas": ["criminal justice", "healthcare", "education"],
        "estimated_annual": 400_000_000,
    },
    "chris sacca": {
        "name": "Lowercase Foundation + LLC giving",
        "type": "Mixed",
        "website": None,
        "self_reports": False,
        "estimated_annual": 20_000_000,
    },
}


@dataclass
class LLCGrant:
    """A grant from a philanthropic LLC."""
    llc_name: str
    recipient: str
    amount: float
    year: int
    purpose: str
    source_url: str


def scrape_czi_grants() -> List[LLCGrant]:
    """
    Attempt to get CZI grant data.
    Note: Would need to parse their grants page or use their API if available.
    """
    # CZI publishes grants at chanzuckerberg.com/grants-ventures/grants/
    # This would require a real scraper or use of LLM web research
    # For now, return known aggregate data
    return []


def search_news_for_llc_grants(llc_name: str, billionaire_name: str) -> List[Dict]:
    """
    Search news for LLC grant announcements.
    Returns raw search results for LLM to process.
    """
    # This would use Brave Search API or similar
    # Actual implementation via MCP tool
    return []


def search_recipient_990s(llc_name: str) -> List[LLCGrant]:
    """
    Search nonprofit 990s for grants received FROM the LLC.

    This is a reverse lookup - find charities that received grants
    from the LLC and sum them up.
    """
    grants = []

    try:
        # Search ProPublica for organizations mentioning the LLC
        # Note: ProPublica doesn't index grant sources, so this is limited
        # Would need to use IRS e-file data or Candid
        pass

    except Exception as e:
        print(f"    Error searching recipient 990s: {e}")

    return grants


def estimate_llc_giving(
    name: str,
    net_worth_billions: float = 0,
    known_grants: List[Dict] = None
) -> Dict:
    """
    Estimate philanthropic LLC giving for a billionaire.

    Args:
        name: Billionaire name
        net_worth_billions: Net worth for context
        known_grants: Pre-researched grants from LLM research

    Returns:
        Dict with LLC giving data
    """
    print(f"  Researching philanthropic LLCs for {name}...")

    name_lower = name.lower()
    llc_info = KNOWN_LLCS.get(name_lower)

    all_grants = []

    if llc_info:
        print(f"    Found known LLC: {llc_info['name']}")

        # Check if they self-report
        if llc_info.get("self_reports"):
            print(f"    LLC self-reports - would scrape {llc_info.get('grants_url', 'website')}")

        # Add any pre-researched grants
        if known_grants:
            for grant in known_grants:
                all_grants.append(LLCGrant(
                    llc_name=llc_info["name"],
                    recipient=grant.get("recipient", "Unknown"),
                    amount=grant.get("amount", 0),
                    year=grant.get("year", 2024),
                    purpose=grant.get("purpose", ""),
                    source_url=grant.get("source_url", ""),
                ))
    else:
        print(f"    No known LLC for {name}")

    total = sum(g.amount for g in all_grants)

    # Determine confidence
    if llc_info and llc_info.get("self_reports") and all_grants:
        confidence = "MEDIUM"
    elif llc_info and all_grants:
        confidence = "LOW"
    elif llc_info:
        confidence = "VERY_LOW"  # Known LLC but no grant data
    else:
        confidence = "ZERO"  # Unknown if they even have an LLC

    return {
        "category": "PHILANTHROPIC_LLCS",
        "billionaire": name,
        "llc_name": llc_info["name"] if llc_info else None,
        "llc_website": llc_info.get("website") if llc_info else None,
        "grants": [asdict(g) for g in all_grants],
        "total": total,
        "grant_count": len(all_grants),
        "confidence": confidence,
        "note": "LLCs have no 990 filing requirement - data depends on self-disclosure",
        "source_urls": [g.source_url for g in all_grants if g.source_url],
    }


if __name__ == "__main__":
    # Test with known LLC data (as if from LLM research)
    test_cases = [
        ("Mark Zuckerberg", 223.0, [
            {"recipient": "Various (aggregate)", "amount": 7_220_000_000, "year": 2024,
             "purpose": "CZI cumulative grants", "source_url": "https://chanzuckerberg.com"},
        ]),
        ("Laurene Powell Jobs", 12.0, []),  # Emerson Collective doesn't disclose
        ("Larry Ellison", 245.0, []),  # No known LLC
    ]

    for name, nw, grants in test_cases:
        print(f"\n{'='*60}")
        result = estimate_llc_giving(name, nw, grants)
        print(f"\nSummary for {name}:")
        print(f"  LLC: {result['llc_name'] or 'None known'}")
        print(f"  Total grants: ${result['total']/1e6:.1f}M")
        print(f"  Confidence: {result['confidence']}")
