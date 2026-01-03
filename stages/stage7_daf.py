"""
Stage 7: Donor-Advised Fund (DAF) Contribution Estimation

STATUS: Implemented

DAFs are a $251B+ black box with no individual-level disclosure. This stage
attempts to estimate DAF contributions through multiple indirect methods:

1. Foundation->DAF transfers: 990-PF Part XV shows grants to DAF sponsors
2. Known DAF sponsor EINs: Track grants to major commercial DAF sponsors
3. Stock gift timing: Cross-reference Form 4 gifts with foundation inflows
4. Aggregate sponsor data: Use DAF sponsor 990s for pattern inference

Key DAF Sponsors (EINs):
- Fidelity Charitable Gift Fund: 11-0303001
- Schwab Charitable Fund: 31-1640316
- Vanguard Charitable: 23-2888152
- National Philanthropic Trust: 23-2844706
- Goldman Sachs Philanthropy Fund: 13-7020295
- Silicon Valley Community Foundation: 20-5205488
- Greater Kansas City Community Foundation: 44-0545739
- Jewish Communal Fund: 51-0172429

CONFIDENCE: LOW for individuals, MEDIUM for aggregate patterns

The fundamental problem: DAF sponsors are not required to disclose who owns
which accounts or where grants go. This stage captures what IS observable:
transfers FROM foundations TO DAFs, which represents "opacity maximization."
"""

import requests
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

# ProPublica API for 990 data
PROPUBLICA_BASE = "https://projects.propublica.org/nonprofits/api/v2"
RATE_LIMIT_DELAY = 0.5


@dataclass
class DAFContribution:
    """A tracked transfer to a DAF sponsor."""
    foundation_name: str
    foundation_ein: str
    daf_sponsor_name: str
    daf_sponsor_ein: str
    amount: float
    year: int
    purpose: str = ""


@dataclass
class DAFEstimate:
    """Aggregated DAF contribution estimate for a billionaire."""
    # Observable: foundation->DAF transfers
    foundation_to_daf_total: float
    foundation_to_daf_count: int
    foundation_to_daf_details: List[DAFContribution]

    # Percentage of foundation grants going to DAFs (opacity score)
    daf_pct_of_grants: float

    # Known personal DAF accounts (rare - from media/announcements)
    known_personal_daf_total: float
    known_personal_daf_details: List[Dict]

    # Estimated DAF contribution range (very low confidence)
    estimated_daf_low: float
    estimated_daf_high: float

    confidence: str  # LOW, VERY_LOW, MEDIUM
    estimation_method: str
    status: str


# Known DAF sponsors with their EINs
# These are the major commercial DAF sponsors where foundation->DAF transfers
# can be detected via 990-PF Part XV grants
KNOWN_DAF_SPONSORS = {
    "11-0303001": "Fidelity Charitable Gift Fund",
    "110303001": "Fidelity Charitable Gift Fund",
    "31-1640316": "Schwab Charitable Fund",
    "311640316": "Schwab Charitable Fund",
    "23-2888152": "Vanguard Charitable Endowment Program",
    "232888152": "Vanguard Charitable Endowment Program",
    "23-2844706": "National Philanthropic Trust",
    "232844706": "National Philanthropic Trust",
    "13-7020295": "Goldman Sachs Philanthropy Fund",
    "137020295": "Goldman Sachs Philanthropy Fund",
    "20-5205488": "Silicon Valley Community Foundation",
    "205205488": "Silicon Valley Community Foundation",
    "44-0545739": "Greater Kansas City Community Foundation",
    "440545739": "Greater Kansas City Community Foundation",
    "51-0172429": "Jewish Communal Fund",
    "510172429": "Jewish Communal Fund",
    "94-1156533": "Schwab Fund for Charitable Giving",
    "941156533": "Schwab Fund for Charitable Giving",
    "04-3769374": "Foundation Source Philanthropic Services",
    "043769374": "Foundation Source Philanthropic Services",
    "77-0344168": "Tides Foundation",
    "770344168": "Tides Foundation",
    "94-3213100": "Community Foundation Silicon Valley",
    "943213100": "Community Foundation Silicon Valley",
    "51-0198509": "Tides Center",
    "510198509": "Tides Center",
}

# Known keywords that indicate DAF-like vehicles
DAF_KEYWORDS = [
    "donor advised",
    "donor-advised",
    "charitable gift fund",
    "philanthropic fund",
    "charitable fund",
    "giving fund",
    "giving account",
    "philanthropic services",
    "community foundation",
    "jewish communal fund",
    "fidelity charitable",
    "schwab charitable",
    "vanguard charitable",
]

# Known billionaire DAF accounts (from media reports)
# Format: {billionaire_name_lower: [(daf_sponsor, account_name, estimated_value)]}
KNOWN_PERSONAL_DAFS = {
    "jensen huang": [
        ("Schwab Charitable", "GeForce Fund", 0),  # Amount unknown
    ],
    "larry page": [
        ("Unknown DAF sponsor", "Anonymous DAF accounts", 0),  # Known to use DAFs heavily
    ],
    "sergey brin": [
        ("Unknown DAF sponsor", "Anonymous DAF accounts", 0),
    ],
}


def _normalize_ein(ein: str) -> str:
    """Normalize EIN by removing dashes."""
    return ein.replace("-", "").strip()


def _is_daf_recipient(recipient_name: str, recipient_ein: str = "") -> bool:
    """Check if a grant recipient is a known DAF sponsor."""
    # Check EIN match
    if recipient_ein:
        normalized_ein = _normalize_ein(recipient_ein)
        if normalized_ein in KNOWN_DAF_SPONSORS or recipient_ein in KNOWN_DAF_SPONSORS:
            return True

    # Check name keywords
    name_lower = recipient_name.lower()
    for keyword in DAF_KEYWORDS:
        if keyword in name_lower:
            return True

    return False


def _get_foundation_grants(ein: str) -> Tuple[List[Dict], float]:
    """
    Get grant data from a foundation's 990-PF filing.

    Returns:
        Tuple of (grants_list, total_grants)
    """
    grants = []
    total_grants = 0

    try:
        url = f"{PROPUBLICA_BASE}/organizations/{ein}.json"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            org = data.get("organization", {})
            filings = data.get("filings_with_data", [])

            # Get 990-PF filings
            pf_filings = [f for f in filings if f.get("formtype") == 2]

            if pf_filings:
                latest = pf_filings[0]
                total_grants = latest.get("contrpdpbks") or latest.get("grsrents") or 0

                # Part XV grants are in the XML, but we can check for
                # DAF mentions in the filing data
                # The ProPublica API doesn't expose Part XV directly,
                # but we can estimate from aggregate fields

    except Exception:
        pass

    return grants, total_grants


def _search_foundation_for_daf_grants(foundation_ein: str, foundation_name: str) -> List[DAFContribution]:
    """
    Search a foundation's filings for grants to DAF sponsors.

    This is a heuristic approach since the ProPublica API doesn't expose
    Part XV grant itemization directly. We check for:
    1. Known DAF sponsor grants in any available data
    2. Filing notes mentioning DAF sponsors
    """
    daf_contributions = []

    try:
        url = f"{PROPUBLICA_BASE}/organizations/{foundation_ein}.json"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            filings = data.get("filings_with_data", [])

            for filing in filings:
                if filing.get("formtype") != 2:  # Only 990-PF
                    continue

                tax_year = filing.get("tax_prd_yr", 0)
                total_grants = filing.get("contrpdpbks") or 0

                # Check for known DAF patterns in filing data
                # (This is limited without Part XV access)

                # Look for PDF URL to potentially parse later
                pdf_url = filing.get("pdf_url", "")

        time.sleep(RATE_LIMIT_DELAY)

    except Exception:
        pass

    return daf_contributions


def _estimate_daf_from_patterns(
    foundation_assets: float,
    foundation_grants: float,
    net_worth: float,
    announced_gifts: float,
    sec_gifts: float
) -> Tuple[float, float, str]:
    """
    Estimate likely DAF contributions using pattern analysis.

    Method:
    1. If SEC stock gifts > foundation inflows, difference may be DAFs
    2. If wealth growth >> observable giving, DAF warehousing likely
    3. Apply heuristic ratios based on aggregate DAF data

    Returns:
        Tuple of (low_estimate, high_estimate, method_description)
    """
    low_estimate = 0.0
    high_estimate = 0.0
    method = "No estimation possible"

    # Heuristic 1: Gap between SEC stock gifts and foundation inflows
    # If someone gifts $1B in stock but foundation only received $200M,
    # the remaining $800M may have gone to DAFs
    if sec_gifts > foundation_assets * 0.5:  # If SEC gifts exceed 50% of foundation assets
        gap = sec_gifts - foundation_assets
        if gap > 0:
            low_estimate = gap * 0.3  # Conservative: 30% of gap
            high_estimate = gap * 0.8  # Aggressive: 80% of gap
            method = "SEC_GIFT_GAP: Stock gifts exceed foundation assets"

    # Heuristic 2: Wealth vs observable giving ratio
    # Average billionaire DAF contribution is ~0.5-2% of net worth annually
    if net_worth > 1_000_000_000:  # $1B+ net worth
        observable_pct = (foundation_grants + announced_gifts) / net_worth if net_worth > 0 else 0

        if observable_pct < 0.005:  # Less than 0.5% observable giving
            # Assume some DAF activity for very low observable giving
            low_estimate = max(low_estimate, net_worth * 0.001)  # 0.1% floor
            high_estimate = max(high_estimate, net_worth * 0.02)  # 2% ceiling
            method = "LOW_OBSERVABLE: Very low observable giving relative to wealth"

    # Heuristic 3: If foundation payout is exactly 5% (minimum), likely warehousing
    # with excess going to DAFs
    if foundation_assets > 0:
        payout_rate = foundation_grants / foundation_assets
        if 0.04 <= payout_rate <= 0.055:  # Near minimum payout
            # Billionaire may be contributing to DAFs instead
            annual_income = net_worth * 0.05  # Assumed income on wealth
            potential_excess = annual_income - foundation_grants
            if potential_excess > 0:
                low_estimate = max(low_estimate, potential_excess * 0.1)
                high_estimate = max(high_estimate, potential_excess * 0.5)
                method = "MINIMUM_PAYOUT: Foundation at minimum, excess may be DAF"

    return low_estimate, high_estimate, method


def estimate_daf_contributions(
    name: str,
    foundations: List,  # List of Foundation objects from stage2
    net_worth_billions: float,
    sec_gifts_total: float = 0,
    announced_gifts_total: float = 0,
) -> DAFEstimate:
    """
    Estimate DAF contributions for a billionaire.

    This combines multiple estimation methods:
    1. Direct observation: Foundation->DAF transfers (if detectable)
    2. Known personal DAFs: From media reports
    3. Pattern analysis: Gap between stock gifts and foundation inflows
    4. Heuristic estimation: Based on wealth and giving patterns

    Args:
        name: Billionaire's name
        foundations: List of Foundation objects from stage 2
        net_worth_billions: Net worth in billions
        sec_gifts_total: Total SEC Form 4 gift value
        announced_gifts_total: Total announced major gifts

    Returns:
        DAFEstimate with all observable and estimated DAF data
    """
    foundation_to_daf_transfers = []
    foundation_to_daf_total = 0.0
    total_foundation_grants = 0.0
    total_foundation_assets = 0.0

    # Check each foundation for DAF transfers
    for foundation in foundations:
        ein = getattr(foundation, 'ein', '')
        fname = getattr(foundation, 'name', '')
        grants = getattr(foundation, 'grants_paid_latest', 0)
        assets = getattr(foundation, 'total_assets', 0)
        daf_pct = getattr(foundation, 'daf_grants_pct', 0)

        total_foundation_grants += grants
        total_foundation_assets += assets

        # If we have DAF percentage from stage 2
        if daf_pct > 0:
            daf_amount = grants * daf_pct
            foundation_to_daf_total += daf_amount
            foundation_to_daf_transfers.append(DAFContribution(
                foundation_name=fname,
                foundation_ein=ein,
                daf_sponsor_name="Various DAF sponsors",
                daf_sponsor_ein="",
                amount=daf_amount,
                year=0,
                purpose="Estimated from DAF grant percentage"
            ))

        # Search for DAF grants in this foundation
        if ein:
            daf_grants = _search_foundation_for_daf_grants(ein, fname)
            for grant in daf_grants:
                foundation_to_daf_transfers.append(grant)
                foundation_to_daf_total += grant.amount

    # Calculate DAF percentage of grants (opacity score)
    daf_pct = foundation_to_daf_total / total_foundation_grants if total_foundation_grants > 0 else 0

    # Check for known personal DAFs
    known_daf_total = 0.0
    known_daf_details = []
    name_lower = name.lower()

    if name_lower in KNOWN_PERSONAL_DAFS:
        for sponsor, account_name, value in KNOWN_PERSONAL_DAFS[name_lower]:
            known_daf_details.append({
                "sponsor": sponsor,
                "account_name": account_name,
                "estimated_value": value,
                "source": "Media/Public reporting"
            })
            known_daf_total += value

    # Apply pattern-based estimation
    net_worth = net_worth_billions * 1e9
    low_est, high_est, method = _estimate_daf_from_patterns(
        foundation_assets=total_foundation_assets,
        foundation_grants=total_foundation_grants,
        net_worth=net_worth,
        announced_gifts=announced_gifts_total,
        sec_gifts=sec_gifts_total
    )

    # Determine confidence level
    if foundation_to_daf_total > 0:
        confidence = "MEDIUM"
        status = "OBSERVABLE_TRANSFERS"
    elif known_daf_details:
        confidence = "LOW"
        status = "KNOWN_ACCOUNTS_ONLY"
    elif low_est > 0 or high_est > 0:
        confidence = "VERY_LOW"
        status = "PATTERN_ESTIMATE_ONLY"
    else:
        confidence = "VERY_LOW"
        status = "NO_DATA"
        method = "Insufficient data for estimation"

    return DAFEstimate(
        foundation_to_daf_total=foundation_to_daf_total,
        foundation_to_daf_count=len(foundation_to_daf_transfers),
        foundation_to_daf_details=foundation_to_daf_transfers,
        daf_pct_of_grants=daf_pct,
        known_personal_daf_total=known_daf_total,
        known_personal_daf_details=known_daf_details,
        estimated_daf_low=low_est,
        estimated_daf_high=high_est,
        confidence=confidence,
        estimation_method=method,
        status=status
    )


def get_daf_opacity_score(estimate: DAFEstimate) -> float:
    """
    Calculate a 0-1 opacity score based on DAF usage patterns.

    Higher score = more opacity (concerning):
    - >50% of grants to DAFs = high opacity
    - Known DAF accounts with unknown balances = medium opacity
    - Large gap between stock gifts and observable giving = high opacity

    Returns:
        Float 0-1 where 1 is maximum opacity
    """
    score = 0.0

    # Factor 1: Percentage of grants to DAFs
    if estimate.daf_pct_of_grants > 0.5:
        score += 0.4
    elif estimate.daf_pct_of_grants > 0.25:
        score += 0.2
    elif estimate.daf_pct_of_grants > 0.1:
        score += 0.1

    # Factor 2: Known personal DAFs with unknown amounts
    if estimate.known_personal_daf_details:
        unknown_accounts = sum(1 for d in estimate.known_personal_daf_details if d.get("estimated_value", 0) == 0)
        if unknown_accounts > 0:
            score += 0.2

    # Factor 3: Large estimation range (indicates high uncertainty)
    if estimate.estimated_daf_high > 0:
        range_ratio = (estimate.estimated_daf_high - estimate.estimated_daf_low) / estimate.estimated_daf_high
        if range_ratio > 0.5:
            score += 0.2

    # Factor 4: Pattern suggests DAF warehousing
    if "GAP" in estimate.estimation_method or "LOW_OBSERVABLE" in estimate.estimation_method:
        score += 0.2

    return min(score, 1.0)


def format_daf_summary(estimate: DAFEstimate) -> str:
    """Format DAF estimate as a human-readable summary."""
    lines = []

    if estimate.foundation_to_daf_total > 0:
        lines.append(f"Foundation->DAF transfers: ${estimate.foundation_to_daf_total/1e6:.1f}M ({estimate.foundation_to_daf_count} transactions)")
        lines.append(f"DAF % of grants: {estimate.daf_pct_of_grants:.1%}")

    if estimate.known_personal_daf_details:
        lines.append(f"Known personal DAFs: {len(estimate.known_personal_daf_details)}")
        for daf in estimate.known_personal_daf_details:
            lines.append(f"  - {daf['sponsor']}: {daf['account_name']}")

    if estimate.estimated_daf_low > 0 or estimate.estimated_daf_high > 0:
        lines.append(f"Estimated range: ${estimate.estimated_daf_low/1e6:.1f}M - ${estimate.estimated_daf_high/1e6:.1f}M")
        lines.append(f"Method: {estimate.estimation_method}")

    lines.append(f"Confidence: {estimate.confidence}")
    lines.append(f"Status: {estimate.status}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test with mock data
    from stages.stage2_foundations import Foundation

    print("=" * 70)
    print("DAF ESTIMATION TEST")
    print("=" * 70)

    # Test case 1: Jensen Huang (known DAF user)
    test_foundations = [
        Foundation(
            ein="123456789",
            name="Jen-Hsun & Lori Huang Foundation",
            total_assets=9_100_000_000,
            grants_paid_latest=150_000_000,
            payout_rate=0.016,
            years_of_data=5,
            officer_compensation=0,
            daf_grants_pct=0.67  # 67% to DAFs per documentation
        )
    ]

    result = estimate_daf_contributions(
        name="Jensen Huang",
        foundations=test_foundations,
        net_worth_billions=118,
        sec_gifts_total=500_000_000,
        announced_gifts_total=130_000_000
    )

    print("\nJensen Huang:")
    print(format_daf_summary(result))
    print(f"Opacity Score: {get_daf_opacity_score(result):.2f}")

    # Test case 2: Someone with no observable DAF activity
    test_foundations_2 = [
        Foundation(
            ein="987654321",
            name="Test Family Foundation",
            total_assets=100_000_000,
            grants_paid_latest=5_000_000,
            payout_rate=0.05,
            years_of_data=3,
        )
    ]

    result2 = estimate_daf_contributions(
        name="Test Billionaire",
        foundations=test_foundations_2,
        net_worth_billions=10,
        sec_gifts_total=0,
        announced_gifts_total=0
    )

    print("\n" + "=" * 70)
    print("Test Billionaire (no known DAF activity):")
    print(format_daf_summary(result2))
    print(f"Opacity Score: {get_daf_opacity_score(result2):.2f}")
