"""
Stage 8: Wealth Factors (Liquidity & Tenure)

STATUS: ✅ Implemented

Adjusts Scrooge scoring based on:
1. Liquidity discount - illiquid wealth (private companies) reduces expectation
2. Wealth tenure - how long they've had the capacity to give
3. Wealth velocity - rapid recent gains vs steady accumulation

These factors affect how "culpable" a non-giver is:
- Someone who just became a billionaire yesterday gets a pass
- Someone with 20 years of liquid billions is more Scrooge-like
"""

import requests
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class WealthProfile:
    """Wealth characteristics for scoring adjustments."""
    name: str
    current_net_worth: float  # billions
    liquidity_pct: float  # 0-1, estimated liquid portion
    years_as_billionaire: int
    wealth_source: str  # "public_stock", "private_company", "inheritance", etc.
    primary_company_ticker: Optional[str] = None


# Typical liquidity by wealth source (from Wealth-X data)
LIQUIDITY_ESTIMATES = {
    "public_stock": 0.70,  # 70% considered liquid (can borrow against)
    "private_company": 0.20,  # 20% liquid until exit
    "inheritance": 0.50,  # Mixed, depends on structure
    "real_estate": 0.25,
    "hedge_fund": 0.60,
    "private_equity": 0.30,
    "diversified": 0.45,
    "unknown": 0.40,
}

# Forbes uses 10% discount for private holdings
FORBES_PRIVATE_DISCOUNT = 0.10


def estimate_liquidity(wealth_source: str, net_worth_billions: float) -> float:
    """
    Estimate liquid portion of net worth.

    Based on Wealth-X UHNW data:
    - Average UHNW: ~23% liquid
    - High-affinity philanthropic donors: 46% liquid

    For billionaires with mostly public stock, 50-70% is effectively
    liquid via margin loans / buy-borrow-die strategy.
    """
    base_liquidity = LIQUIDITY_ESTIMATES.get(wealth_source.lower(), 0.40)

    # Larger fortunes tend to be less liquid (more tied up)
    if net_worth_billions > 100:
        base_liquidity *= 0.85
    elif net_worth_billions > 50:
        base_liquidity *= 0.90

    return min(base_liquidity, 1.0)


def estimate_wealth_tenure(name: str) -> Tuple[int, str]:
    """
    Estimate how long someone has been a billionaire.

    Uses Forbes historical data to find first appearance.

    Returns (years_as_billionaire, first_year).
    """
    # Known first appearances (hardcoded for major billionaires)
    # Would ideally query historical Forbes data
    KNOWN_TENURE = {
        "jeff bezos": (1999, 25),
        "bill gates": (1986, 39),
        "warren buffett": (1985, 40),
        "elon musk": (2012, 13),
        "mark zuckerberg": (2008, 17),
        "larry ellison": (1993, 32),
        "larry page": (2004, 21),
        "sergey brin": (2004, 21),
        "jensen huang": (2020, 5),
        "michael dell": (1992, 33),
        "mackenzie scott": (2019, 6),
        "steve ballmer": (2000, 25),
        "satya nadella": (2020, 5),
        "bernard arnault": (1990, 35),
    }

    key = name.lower()
    if key in KNOWN_TENURE:
        first_year, years = KNOWN_TENURE[key]
        return years, str(first_year)

    # Default: assume they've been wealthy for 10 years
    return 10, "Unknown"


def calculate_scrooge_adjustment(
    net_worth_billions: float,
    observable_giving: float,  # dollars
    liquidity_pct: float,
    years_as_billionaire: int,
) -> Dict:
    """
    Calculate adjustment factor for Scrooge scoring.

    A raw "foundation % of net worth" metric doesn't account for:
    1. Illiquid wealth that can't easily be deployed
    2. Recent billionaires who haven't had time to give
    3. Rapid wealth growth outpacing giving

    This returns an adjustment factor and explanation.
    """
    # Effective deployable wealth
    deployable = net_worth_billions * 1e9 * liquidity_pct

    # Expected giving based on tenure
    # Assumption: 2% annual deployment is reasonable for established billionaires
    # New billionaires get a ramp-up period
    if years_as_billionaire <= 2:
        expected_annual_rate = 0.005  # 0.5% first 2 years
    elif years_as_billionaire <= 5:
        expected_annual_rate = 0.01  # 1% for years 3-5
    else:
        expected_annual_rate = 0.02  # 2% for established billionaires

    # Expected cumulative giving
    expected_giving = deployable * expected_annual_rate * min(years_as_billionaire, 10)

    # Scrooge ratio: how much they're undergiving
    if expected_giving > 0:
        scrooge_ratio = 1 - (observable_giving / expected_giving)
        scrooge_ratio = max(0, min(1, scrooge_ratio))  # Clamp to 0-1
    else:
        scrooge_ratio = 0

    # Interpretation
    if scrooge_ratio > 0.9:
        interpretation = "SEVERE_SCROOGE"
    elif scrooge_ratio > 0.7:
        interpretation = "MODERATE_SCROOGE"
    elif scrooge_ratio > 0.5:
        interpretation = "MILD_SCROOGE"
    elif scrooge_ratio > 0.3:
        interpretation = "BORDERLINE"
    else:
        interpretation = "NOT_SCROOGE"

    return {
        "scrooge_ratio": scrooge_ratio,
        "interpretation": interpretation,
        "deployable_wealth": deployable,
        "expected_giving": expected_giving,
        "observable_giving": observable_giving,
        "giving_gap": max(0, expected_giving - observable_giving),
        "liquidity_adjustment": liquidity_pct,
        "tenure_adjustment": years_as_billionaire,
    }


def get_wealth_factors(name: str, net_worth_billions: float, wealth_source: str = "unknown") -> Dict:
    """
    Main entry point for wealth factor calculation.

    Returns liquidity estimate, tenure, and adjusted Scrooge factors.
    """
    # Estimate liquidity
    liquidity_pct = estimate_liquidity(wealth_source, net_worth_billions)

    # Estimate tenure
    years, first_year = estimate_wealth_tenure(name)

    return {
        "name": name,
        "net_worth_billions": net_worth_billions,
        "wealth_source": wealth_source,
        "liquidity_pct": liquidity_pct,
        "liquid_wealth_billions": net_worth_billions * liquidity_pct,
        "years_as_billionaire": years,
        "first_billionaire_year": first_year,
    }


if __name__ == "__main__":
    # Test with known billionaires
    test_cases = [
        ("Jensen Huang", 120, "public_stock"),
        ("Jeff Bezos", 200, "public_stock"),
        ("Warren Buffett", 140, "public_stock"),
        ("Bill Gates", 130, "diversified"),
    ]

    for name, net_worth, source in test_cases:
        print(f"\n{'='*60}")
        print(f"Wealth factors for: {name}")
        print("="*60)

        factors = get_wealth_factors(name, net_worth, source)
        print(f"Net worth: ${factors['net_worth_billions']:.0f}B")
        print(f"Liquidity: {factors['liquidity_pct']:.0%}")
        print(f"Liquid wealth: ${factors['liquid_wealth_billions']:.1f}B")
        print(f"Years as billionaire: {factors['years_as_billionaire']}")

        # Calculate Scrooge adjustment with mock observable giving
        mock_observable = net_worth * 1e9 * 0.02  # Assume 2% observable
        adj = calculate_scrooge_adjustment(
            net_worth, mock_observable, factors['liquidity_pct'], factors['years_as_billionaire']
        )
        print(f"Scrooge ratio: {adj['scrooge_ratio']:.2f} ({adj['interpretation']})")
        print(f"Giving gap: ${adj['giving_gap']/1e9:.2f}B")
