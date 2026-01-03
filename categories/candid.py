"""
CANDID (Foundation Directory) Integration

Candid (formerly Foundation Center + GuideStar) is the most comprehensive
database of US nonprofits and foundation grants.

Data Sources:
1. Candid API - Requires subscription for full access
2. 990 Finder - Free search for 990 forms
3. Foundation Directory Online - Grant records

This provides HIGHER QUALITY data than ProPublica alone:
- Includes grant recipient details
- Has historical data going back decades
- Tracks foundation officer compensation
"""

import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


# Candid API endpoints (require API key for full access)
CANDID_990_SEARCH = "https://api.candid.org/premier/v3/essentials"
CANDID_GRANTS = "https://api.candid.org/grants/v1/grants"


@dataclass
class CandidGrant:
    """A grant from Candid's database."""
    funder_name: str
    funder_ein: str
    recipient_name: str
    recipient_ein: str
    amount: float
    year: int
    purpose: str
    source_url: str


def search_candid_990(ein: str, api_key: str = None) -> Dict:
    """
    Search Candid for 990 filing data.

    Note: Full API requires subscription (~$1000/year).
    Free tier provides basic organization info only.
    """
    if not api_key:
        # Return placeholder - would need real API key
        return {"error": "API key required for Candid access"}

    try:
        headers = {"Subscription-Key": api_key}
        url = f"{CANDID_990_SEARCH}/{ein}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"    Candid API error: {e}")

    return {}


def search_candid_grants(funder_ein: str, api_key: str = None) -> List[CandidGrant]:
    """
    Search Candid for grants made by a foundation.

    This is the gold standard for grant tracking - includes:
    - All 990-PF Schedule grants
    - Multi-year grant data
    - Grant purpose descriptions
    """
    grants = []

    if not api_key:
        return grants

    try:
        headers = {"Subscription-Key": api_key}
        params = {"funder_ein": funder_ein, "limit": 100}
        resp = requests.get(CANDID_GRANTS, headers=headers, params=params, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            for g in data.get("grants", []):
                grants.append(CandidGrant(
                    funder_name=g.get("funder_name", ""),
                    funder_ein=funder_ein,
                    recipient_name=g.get("recipient_name", ""),
                    recipient_ein=g.get("recipient_ein", ""),
                    amount=float(g.get("amount", 0)),
                    year=int(g.get("year", 2024)),
                    purpose=g.get("purpose", ""),
                    source_url=f"https://candid.org/grants/{g.get('grant_id', '')}",
                ))
    except Exception as e:
        print(f"    Candid grants error: {e}")

    return grants


# ============================================================
# ALTERNATIVE FREE SOURCES (no API key required)
# ============================================================

def search_guidestar_free(name: str) -> List[Dict]:
    """
    Search GuideStar's free public profiles.

    Limited info but useful for:
    - Organization overview
    - Latest 990 availability
    - Mission statements
    """
    results = []
    try:
        # GuideStar search (redirects to Candid now)
        url = f"https://www.guidestar.org/search?q={name}"
        # Would need to parse HTML - placeholder
        pass
    except:
        pass
    return results


def get_990_from_irs(ein: str) -> Dict:
    """
    Get 990 directly from IRS e-file database.

    IRS makes 990 XMLs available at:
    https://www.irs.gov/charities-non-profits/form-990-series-downloads

    This is the RAW SOURCE - same data ProPublica uses.
    """
    try:
        # IRS bulk downloads by year
        # Format: https://apps.irs.gov/pub/epostcard/990/xml/{year}/{ein}.xml
        # Note: Only available for e-filed returns
        pass
    except:
        pass
    return {}


# ============================================================
# STATE CHARITY DATABASES
# ============================================================

STATE_CHARITY_DATABASES = {
    "CA": {
        "name": "California Registry of Charitable Trusts",
        "url": "https://rct.doj.ca.gov/Verification/Web/Search.aspx",
        "note": "Includes private foundations, searches by name/EIN",
    },
    "NY": {
        "name": "New York Charities Bureau",
        "url": "https://www.charitiesnys.com/RegistrySearch/search_charities.jsp",
        "note": "Extensive database, includes unregistered warnings",
    },
    "MA": {
        "name": "Massachusetts Attorney General",
        "url": "https://www.mass.gov/service-details/search-the-list-of-charities",
        "note": "Searchable charity database",
    },
    "FL": {
        "name": "Florida Division of Consumer Services",
        "url": "https://csapp.fdacs.gov/cspublicapp/Solicitation/Search.aspx",
        "note": "Charitable organization search",
    },
}


def search_state_charity_db(state: str, name: str) -> Dict:
    """
    Search state-level charity databases.

    States require registration and provide additional oversight data:
    - Registration status
    - Compliance history
    - Officer information
    - Financial summaries
    """
    if state not in STATE_CHARITY_DATABASES:
        return {}

    db = STATE_CHARITY_DATABASES[state]
    # Would need to implement per-state scraping
    return {
        "database": db["name"],
        "url": db["url"],
        "note": "Manual search required",
    }


# ============================================================
# UNIVERSITY ENDOWMENT DATABASES
# ============================================================

# Major university gift announcements
UNIVERSITY_GIFT_SOURCES = [
    {
        "name": "Chronicle of Philanthropy",
        "url": "https://www.philanthropy.com/",
        "note": "Tracks all $1M+ gifts",
    },
    {
        "name": "Inside Philanthropy",
        "url": "https://www.insidephilanthropy.com/",
        "note": "In-depth donor profiles",
    },
    {
        "name": "CASE (Council for Advancement)",
        "url": "https://www.case.org/",
        "note": "University fundraising data",
    },
]


def estimate_from_candid_sources(name: str, ein_list: List[str]) -> Dict:
    """
    Aggregate data from Candid ecosystem sources.

    Even without API access, we can document:
    1. What sources exist
    2. What data they contain
    3. Confidence levels
    """
    return {
        "sources_available": [
            {
                "name": "Candid API (subscription)",
                "data_type": "Complete 990 data, grant records",
                "confidence": "HIGH",
                "access": "Requires API key",
            },
            {
                "name": "IRS 990 e-files",
                "data_type": "Raw 990 XML files",
                "confidence": "HIGH",
                "access": "Free bulk download",
            },
            {
                "name": "State charity databases",
                "data_type": "Registration, compliance",
                "confidence": "MEDIUM",
                "access": "Free, manual search",
            },
            {
                "name": "University gift announcements",
                "data_type": "Named gifts $1M+",
                "confidence": "MEDIUM",
                "access": "Free, web search",
            },
        ],
        "recommendation": "For production, obtain Candid API subscription for comprehensive data",
    }
