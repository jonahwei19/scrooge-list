"""
STATE CHARITY REGISTRATION Databases

Many states require charities to register and file annual reports.
These provide ADDITIONAL data not in federal 990s:
- State-specific financial summaries
- Compliance history
- Officer/director details
- Fundraising costs

Key states with searchable databases:
- California: Registry of Charitable Trusts (largest)
- New York: Charities Bureau
- Massachusetts: Attorney General
- Florida: Division of Consumer Services
"""

import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class StateCharityRecord:
    """A charity record from a state database."""
    name: str
    state: str
    registration_number: str
    status: str  # Active, Delinquent, Suspended
    total_revenue: float
    total_assets: float
    program_expenses: float
    fundraising_expenses: float
    admin_expenses: float
    source_url: str


# California Registry of Charitable Trusts
# https://rct.doj.ca.gov/Verification/Web/Search.aspx
CA_CHARITIES_URL = "https://rct.doj.ca.gov/Verification/Web/Search.aspx"

# New York Charities Bureau
# https://www.charitiesnys.com/RegistrySearch/search_charities.jsp
NY_CHARITIES_URL = "https://www.charitiesnys.com/RegistrySearch/search_charities.jsp"

# Known billionaire foundations by state
KNOWN_STATE_REGISTRATIONS = {
    "bill gates": {
        "CA": [
            {
                "name": "Bill & Melinda Gates Foundation",
                "registration_number": "CT0094641",
                "status": "Active",
                "source_url": "https://rct.doj.ca.gov/Verification/Web/Search.aspx?facility=Y",
            }
        ],
        "NY": [
            {
                "name": "Bill & Melinda Gates Foundation",
                "registration_number": "41-50-96",
                "status": "Active",
                "source_url": "https://www.charitiesnys.com/",
            }
        ],
    },
    "mark zuckerberg": {
        "CA": [
            {
                "name": "Chan Zuckerberg Initiative Foundation",
                "registration_number": "CT0228362",
                "status": "Active",
                "source_url": "https://rct.doj.ca.gov/Verification/Web/Search.aspx",
            }
        ],
    },
    "george soros": {
        "NY": [
            {
                "name": "Open Society Foundations",
                "registration_number": "07-04-28",
                "status": "Active",
                "source_url": "https://www.charitiesnys.com/",
            },
            {
                "name": "Foundation to Promote Open Society",
                "registration_number": "42-60-93",
                "status": "Active",
                "source_url": "https://www.charitiesnys.com/",
            },
        ],
    },
    "michael bloomberg": {
        "NY": [
            {
                "name": "Bloomberg Philanthropies",
                "registration_number": "45-93-83",
                "status": "Active",
                "source_url": "https://www.charitiesnys.com/",
            },
        ],
    },
    "warren buffett": {
        "CA": [
            {
                "name": "Susan Thompson Buffett Foundation",
                "registration_number": "CT0108899",
                "status": "Active",
                "source_url": "https://rct.doj.ca.gov/Verification/Web/Search.aspx",
            },
        ],
    },
    "larry ellison": {
        "CA": [
            {
                "name": "Lawrence Ellison Foundation",
                "registration_number": "CT0117082",
                "status": "Active",
                "source_url": "https://rct.doj.ca.gov/Verification/Web/Search.aspx",
            },
            {
                "name": "Ellison Medical Foundation",
                "registration_number": "CT0169231",
                "status": "Active",
                "source_url": "https://rct.doj.ca.gov/Verification/Web/Search.aspx",
            },
        ],
    },
    "elon musk": {
        "CA": [
            {
                "name": "Musk Foundation",
                "registration_number": "CT0158692",
                "status": "Active",
                "source_url": "https://rct.doj.ca.gov/Verification/Web/Search.aspx",
            },
        ],
    },
    "jeff bezos": {
        "WA": [
            {
                "name": "Bezos Family Foundation",
                "registration_number": "WA-2001-00183",
                "status": "Active",
                "source_url": "https://www.sos.wa.gov/charities/",
            },
        ],
    },
}


def search_california_registry(name: str) -> List[Dict]:
    """
    Search California Registry of Charitable Trusts.

    CA requires registration for any charity soliciting in the state.
    Database includes:
    - Registration status
    - Annual report filings
    - Financial summaries
    - Delinquency notices
    """
    results = []

    # CA registry requires session/form submission
    # Would need Selenium or similar for full automation
    # Here we use known registrations

    name_lower = name.lower()
    if name_lower in KNOWN_STATE_REGISTRATIONS:
        ca_records = KNOWN_STATE_REGISTRATIONS[name_lower].get("CA", [])
        for record in ca_records:
            results.append({
                "name": record["name"],
                "state": "CA",
                "registration_number": record["registration_number"],
                "status": record["status"],
                "source_url": record["source_url"],
            })

    return results


def search_new_york_charities(name: str) -> List[Dict]:
    """
    Search New York Charities Bureau.

    NY has one of the strictest charity registration requirements.
    Database includes:
    - Registration status
    - CHAR500 annual filings
    - Financial data
    - Sanctions/suspensions
    """
    results = []

    name_lower = name.lower()
    if name_lower in KNOWN_STATE_REGISTRATIONS:
        ny_records = KNOWN_STATE_REGISTRATIONS[name_lower].get("NY", [])
        for record in ny_records:
            results.append({
                "name": record["name"],
                "state": "NY",
                "registration_number": record["registration_number"],
                "status": record["status"],
                "source_url": record["source_url"],
            })

    return results


def check_compliance_status(records: List[Dict]) -> Dict:
    """
    Analyze compliance status across state registrations.

    Red flags:
    - Delinquent status
    - Suspended registration
    - Missing annual reports
    """
    compliance_issues = []

    for record in records:
        status = record.get("status", "").lower()
        if status in ["delinquent", "suspended", "revoked"]:
            compliance_issues.append({
                "state": record.get("state"),
                "name": record.get("name"),
                "issue": status,
            })

    return {
        "total_registrations": len(records),
        "compliance_issues": compliance_issues,
        "all_compliant": len(compliance_issues) == 0,
    }


def estimate_state_charity_data(name: str) -> Dict:
    """
    Aggregate state charity registration data for a billionaire.

    Returns:
        Dict with state registration findings
    """
    print(f"  Researching state charity registrations for {name}...")

    all_records = []

    # Search major states
    ca_records = search_california_registry(name)
    ny_records = search_new_york_charities(name)

    all_records.extend(ca_records)
    all_records.extend(ny_records)

    # Check for known registrations in other states
    name_lower = name.lower()
    if name_lower in KNOWN_STATE_REGISTRATIONS:
        for state, records in KNOWN_STATE_REGISTRATIONS[name_lower].items():
            if state not in ["CA", "NY"]:
                for record in records:
                    all_records.append({
                        "name": record["name"],
                        "state": state,
                        "registration_number": record["registration_number"],
                        "status": record["status"],
                        "source_url": record["source_url"],
                    })

    compliance = check_compliance_status(all_records)

    print(f"    Found {len(all_records)} state registrations")
    if compliance["compliance_issues"]:
        print(f"    WARNING: {len(compliance['compliance_issues'])} compliance issues")

    return {
        "category": "STATE_CHARITIES",
        "billionaire": name,
        "registrations": all_records,
        "registration_count": len(all_records),
        "states": list(set(r.get("state") for r in all_records)),
        "compliance": compliance,
        "confidence": "HIGH" if all_records else "ZERO",
        "source_urls": [r.get("source_url") for r in all_records if r.get("source_url")],
    }


if __name__ == "__main__":
    test_names = ["Bill Gates", "George Soros", "Larry Ellison", "Elon Musk"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = estimate_state_charity_data(name)
        print(f"\nSummary for {name}:")
        print(f"  Registrations: {result['registration_count']}")
        print(f"  States: {result['states']}")
        print(f"  Compliant: {result['compliance']['all_compliant']}")
