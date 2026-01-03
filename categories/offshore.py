"""
OFFSHORE STRUCTURES Detection

Tracks billionaire connections to offshore entities via:
1. ICIJ Offshore Leaks Database (Panama, Paradise, Pandora Papers)
2. Known offshore foundation jurisdictions
3. Tax haven charity registrations

This is for detecting:
- Offshore foundations (Cayman, BVI, etc.)
- Swiss/Luxembourg philanthropic structures
- Hidden giving channels
"""

import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


# ICIJ Offshore Leaks API
ICIJ_SEARCH_URL = "https://offshoreleaks.icij.org/search"


@dataclass
class OffshoreEntity:
    """An offshore entity linked to a billionaire."""
    name: str
    jurisdiction: str
    entity_type: str  # Foundation, Trust, Company
    source_leak: str  # Panama, Paradise, Pandora
    linked_to: str  # Billionaire name
    source_url: str


# Known offshore philanthropic structures
KNOWN_OFFSHORE_STRUCTURES = {
    "george soros": [
        {
            "name": "Open Society Foundation - London",
            "jurisdiction": "UK",
            "entity_type": "Foundation",
            "source_leak": "Public registration",
            "source_url": "https://register-of-charities.charitycommission.gov.uk/",
        }
    ],
    "mark zuckerberg": [
        {
            "name": "Chan Zuckerberg Initiative UK",
            "jurisdiction": "UK",
            "entity_type": "Ltd Company",
            "source_leak": "Companies House",
            "source_url": "https://find-and-update.company-information.service.gov.uk/",
        }
    ],
    "bill gates": [
        {
            "name": "Bill & Melinda Gates Foundation UK",
            "jurisdiction": "UK",
            "entity_type": "Foundation",
            "source_leak": "Charity Commission",
            "source_url": "https://register-of-charities.charitycommission.gov.uk/",
        }
    ],
}


# Tax haven jurisdictions with philanthropic structures
PHILANTHROPIC_TAX_HAVENS = {
    "Liechtenstein": {
        "structure": "Stiftung (Foundation)",
        "disclosure": "LOW",
        "used_for": "Private foundations, minimal reporting",
    },
    "Switzerland": {
        "structure": "Stiftung",
        "disclosure": "MEDIUM",
        "used_for": "Art foundations, family foundations",
    },
    "Luxembourg": {
        "structure": "Fondation",
        "disclosure": "MEDIUM",
        "used_for": "European philanthropic operations",
    },
    "Netherlands": {
        "structure": "Stichting",
        "disclosure": "MEDIUM",
        "used_for": "Conduit for international giving",
    },
    "Cayman Islands": {
        "structure": "Exempt Trust/Foundation",
        "disclosure": "LOW",
        "used_for": "Asset protection, delayed giving",
    },
    "Singapore": {
        "structure": "Company Limited by Guarantee",
        "disclosure": "MEDIUM",
        "used_for": "Asia-Pacific philanthropy",
    },
}


def search_icij_leaks(name: str) -> List[Dict]:
    """
    Search ICIJ Offshore Leaks database for billionaire connections.

    The database includes:
    - Panama Papers (2016)
    - Paradise Papers (2017)
    - Pandora Papers (2021)

    Note: Many legitimate uses exist (estate planning, etc.)
    """
    results = []

    try:
        # ICIJ provides a public search interface
        # API access requires journalistic partnership
        # Here we document what's available

        # Would scrape: https://offshoreleaks.icij.org/search?q={name}
        pass

    except Exception as e:
        print(f"    ICIJ search error: {e}")

    return results


def check_uk_charity_commission(name: str) -> List[Dict]:
    """
    Search UK Charity Commission for international operations.

    Many US billionaires have UK registered charities for:
    - European grantmaking
    - UK-specific projects
    - Tax efficiency
    """
    results = []

    try:
        # UK Charity Commission API is free
        url = "https://api.charitycommission.gov.uk/register/api/SearchCharities"
        params = {"searchText": name}

        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for charity in data.get("charities", []):
                results.append({
                    "name": charity.get("charity_name"),
                    "number": charity.get("charity_number"),
                    "status": charity.get("status"),
                    "url": f"https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/{charity.get('charity_number')}",
                })
    except Exception as e:
        print(f"    UK Charity Commission error: {e}")

    return results


def estimate_offshore_giving(name: str) -> Dict:
    """
    Estimate offshore philanthropic activity for a billionaire.

    Returns:
        Dict with offshore entity data
    """
    print(f"  Researching offshore structures for {name}...")

    entities = []
    name_lower = name.lower()

    # Check known structures
    known = KNOWN_OFFSHORE_STRUCTURES.get(name_lower, [])
    for k in known:
        entities.append(OffshoreEntity(
            name=k["name"],
            jurisdiction=k["jurisdiction"],
            entity_type=k["entity_type"],
            source_leak=k["source_leak"],
            linked_to=name,
            source_url=k["source_url"],
        ))

    # Search ICIJ (placeholder)
    icij_results = search_icij_leaks(name)
    for r in icij_results:
        entities.append(OffshoreEntity(
            name=r.get("name", ""),
            jurisdiction=r.get("jurisdiction", ""),
            entity_type=r.get("entity_type", ""),
            source_leak=r.get("source", ""),
            linked_to=name,
            source_url=r.get("url", ""),
        ))

    # Search UK Charity Commission
    uk_charities = check_uk_charity_commission(name)
    for c in uk_charities:
        entities.append(OffshoreEntity(
            name=c["name"],
            jurisdiction="UK",
            entity_type="UK Charity",
            source_leak="Charity Commission",
            linked_to=name,
            source_url=c["url"],
        ))

    print(f"    Found {len(entities)} offshore/international structures")

    return {
        "category": "OFFSHORE",
        "billionaire": name,
        "entities": [asdict(e) for e in entities],
        "entity_count": len(entities),
        "jurisdictions": list(set(e.jurisdiction for e in entities)),
        "confidence": "MEDIUM" if entities else "ZERO",
        "note": "Offshore structures may be legitimate, requires context",
        "source_urls": [e.source_url for e in entities if e.source_url],
    }


if __name__ == "__main__":
    test_names = ["Bill Gates", "George Soros", "Mark Zuckerberg"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = estimate_offshore_giving(name)
        print(f"\nSummary for {name}:")
        print(f"  Entities found: {result['entity_count']}")
        print(f"  Jurisdictions: {result['jurisdictions']}")
