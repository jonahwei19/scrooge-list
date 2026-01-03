"""
Stage 8: Wealth Accumulation Analysis (The Real Signal)

STATUS: ✅ Implemented

KEY INSIGHT: If money goes down, it's going somewhere. If wealth is growing
at or above market rates, the billionaire is NOT deploying capital charitably.

This is far more reliable than tracking opaque giving channels.
The wealth accumulation rate IS the inverse of the giving rate.

Formula:
    Implied Max Giving = Prior Net Worth × (1 + Market Return) - Current Net Worth

If this is negative (wealth grew faster than market), giving ceiling is ~0%.
If this is positive, that's the MAXIMUM they could have given.

Sources:
- Forbes historical billionaire data (RTB-API has daily since 2020)
- S&P 500 returns for market benchmark
- Known liquidity events (stock sales via Form 4)
"""

import requests
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


# ============================================================================
# MARKET BENCHMARKS
# ============================================================================

# S&P 500 annual returns (for comparison)
SP500_ANNUAL_RETURNS = {
    2024: 0.23,   # 23% (through most of year)
    2023: 0.24,   # 24%
    2022: -0.19,  # -19%
    2021: 0.27,   # 27%
    2020: 0.16,   # 16%
    2019: 0.29,   # 29%
    2018: -0.06,  # -6%
    2017: 0.19,   # 19%
    2016: 0.10,   # 10%
    2015: -0.01,  # -1%
}

# Average annual return for calculations
AVERAGE_MARKET_RETURN = 0.10  # 10% long-term average


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class WealthAccumulationAnalysis:
    """Analysis of wealth changes vs market returns."""

    # Historical data
    net_worth_current: float  # Current net worth in billions
    net_worth_prior: float    # Net worth 1 year ago (or earliest available)
    years_between: float      # Years between measurements

    # Market comparison
    market_return_period: float      # What market returned over period
    expected_wealth_growth: float    # Prior × (1 + market return)
    actual_wealth_growth: float      # Current - Prior

    # The key metrics
    wealth_growth_rate: float        # Actual annual growth rate
    excess_growth_rate: float        # Growth above market (if positive, not giving)
    implied_giving_ceiling: float    # Max they could have given (if negative, 0)
    implied_giving_ceiling_pct: float  # As percentage of wealth

    # Verdict
    accumulation_verdict: str  # "ACCUMULATING", "FLAT", "DEPLOYING"
    confidence: str


@dataclass
class HistoricalNetWorth:
    """Historical net worth data point."""
    date: str
    net_worth_billions: float
    rank: int
    source: str


# ============================================================================
# FORBES HISTORICAL DATA
# ============================================================================

# Known historical net worth for top billionaires (from Forbes archives)
# Format: {name_lower: [(year, net_worth_billions), ...]}
HISTORICAL_NET_WORTH = {
    "elon musk": [
        (2020, 27.0),
        (2021, 151.0),
        (2022, 219.0),
        (2023, 180.0),
        (2024, 195.0),
        (2025, 400.0),  # Approximate current
    ],
    "jeff bezos": [
        (2020, 113.0),
        (2021, 177.0),
        (2022, 171.0),
        (2023, 114.0),
        (2024, 194.0),
        (2025, 233.0),
    ],
    "mark zuckerberg": [
        (2020, 54.7),
        (2021, 97.0),
        (2022, 67.0),
        (2023, 106.0),
        (2024, 177.0),
        (2025, 200.0),
    ],
    "bill gates": [
        (2020, 98.0),
        (2021, 124.0),
        (2022, 129.0),
        (2023, 104.0),
        (2024, 128.0),
        (2025, 107.0),  # Declining due to giving!
    ],
    "warren buffett": [
        (2020, 67.5),
        (2021, 96.0),
        (2022, 118.0),
        (2023, 106.0),
        (2024, 133.0),
        (2025, 141.0),
    ],
    "larry ellison": [
        (2020, 59.0),
        (2021, 93.0),
        (2022, 106.0),
        (2023, 107.0),
        (2024, 141.0),
        (2025, 200.0),
    ],
    "larry page": [
        (2020, 50.9),
        (2021, 91.5),
        (2022, 111.0),
        (2023, 114.0),
        (2024, 114.0),
        (2025, 156.0),
    ],
    "sergey brin": [
        (2020, 49.1),
        (2021, 89.0),
        (2022, 107.0),
        (2023, 110.0),
        (2024, 110.0),
        (2025, 148.0),
    ],
    "steve ballmer": [
        (2020, 52.7),
        (2021, 68.7),
        (2022, 91.0),
        (2023, 80.0),
        (2024, 121.0),
        (2025, 123.0),
    ],
    "jensen huang": [
        (2020, 4.1),
        (2021, 7.6),
        (2022, 19.0),
        (2023, 25.0),
        (2024, 77.0),
        (2025, 117.0),  # Massive accumulation
    ],
    "michael dell": [
        (2020, 22.9),
        (2021, 36.0),
        (2022, 50.0),
        (2023, 52.0),
        (2024, 65.0),
        (2025, 100.0),
    ],
    "mackenzie scott": [
        (2020, 36.0),
        (2021, 53.0),
        (2022, 43.6),
        (2023, 35.0),  # Declining due to giving!
        (2024, 36.0),
        (2025, 33.0),  # Continued giving
    ],
    "charles koch": [
        (2020, 38.2),
        (2021, 46.4),
        (2022, 60.0),
        (2023, 59.0),
        (2024, 58.0),
        (2025, 66.0),
    ],
    "jim walton": [
        (2020, 54.6),
        (2021, 60.2),
        (2022, 68.0),
        (2023, 58.0),
        (2024, 72.0),
        (2025, 87.0),
    ],
    "rob walton": [
        (2020, 54.1),
        (2021, 59.5),
        (2022, 67.0),
        (2023, 57.0),
        (2024, 71.0),
        (2025, 87.0),
    ],
    "alice walton": [
        (2020, 54.4),
        (2021, 61.8),
        (2022, 65.0),
        (2023, 56.0),
        (2024, 72.0),
        (2025, 85.0),
    ],
}


def get_historical_net_worth(name: str) -> List[Tuple[int, float]]:
    """Get historical net worth data for a billionaire."""
    key = name.lower()
    if key in HISTORICAL_NET_WORTH:
        return HISTORICAL_NET_WORTH[key]
    return []


def fetch_forbes_historical(name: str) -> List[HistoricalNetWorth]:
    """
    Fetch historical net worth from Forbes RTB-API.

    The RTB-API has daily data going back to ~2020.
    """
    history = []

    # Try to fetch from RTB-API (would need to implement date range queries)
    # For now, use our cached historical data

    return history


# ============================================================================
# WEALTH ACCUMULATION ANALYSIS
# ============================================================================

def calculate_market_return(start_year: int, end_year: int) -> float:
    """Calculate cumulative market return between years."""
    cumulative = 1.0
    for year in range(start_year, end_year):
        if year in SP500_ANNUAL_RETURNS:
            cumulative *= (1 + SP500_ANNUAL_RETURNS[year])
        else:
            cumulative *= (1 + AVERAGE_MARKET_RETURN)
    return cumulative - 1


def analyze_wealth_accumulation(
    name: str,
    current_net_worth: float,  # In billions
    lookback_years: int = 5
) -> WealthAccumulationAnalysis:
    """
    Analyze whether billionaire is accumulating or deploying wealth.

    KEY INSIGHT: If wealth is growing at or above market rates,
    they mathematically cannot be giving away significant amounts.

    Returns:
        WealthAccumulationAnalysis with implied giving ceiling
    """
    current_year = 2025
    prior_year = current_year - lookback_years

    # Get historical data
    history = get_historical_net_worth(name)

    if history:
        # Find closest prior year data
        prior_data = [(y, nw) for y, nw in history if y <= prior_year]
        if prior_data:
            prior_year_actual, prior_net_worth = max(prior_data, key=lambda x: x[0])
            years_between = current_year - prior_year_actual
        else:
            # Use earliest available
            prior_year_actual, prior_net_worth = history[0]
            years_between = current_year - prior_year_actual
    else:
        # No historical data - use current and assume 5 years back
        # Estimate prior wealth as current / (1.10)^5 (market growth)
        prior_net_worth = current_net_worth / (1.10 ** lookback_years)
        prior_year_actual = prior_year
        years_between = lookback_years

    # Calculate market return over period
    market_return = calculate_market_return(prior_year_actual, current_year)

    # Expected wealth if just held at market rate
    expected_wealth = prior_net_worth * (1 + market_return)

    # Actual change
    actual_change = current_net_worth - prior_net_worth
    expected_change = expected_wealth - prior_net_worth

    # Wealth growth rate (annualized)
    if prior_net_worth > 0 and years_between > 0:
        wealth_growth_rate = (current_net_worth / prior_net_worth) ** (1 / years_between) - 1
    else:
        wealth_growth_rate = 0

    # Annualized market return
    annual_market = (1 + market_return) ** (1 / years_between) - 1 if years_between > 0 else AVERAGE_MARKET_RETURN

    # Excess growth (above market)
    excess_growth = wealth_growth_rate - annual_market

    # Implied giving ceiling
    # If wealth grew more than expected, ceiling is 0 (or negative, meaning impossible)
    # If wealth grew less than expected, the difference is max possible giving
    implied_ceiling_billions = expected_wealth - current_net_worth
    implied_ceiling_pct = implied_ceiling_billions / expected_wealth if expected_wealth > 0 else 0

    # Determine verdict
    if implied_ceiling_billions < 0:
        # Wealth grew faster than market - definitely not giving significantly
        verdict = "ACCUMULATING"
        implied_ceiling_billions = 0
        implied_ceiling_pct = 0
    elif implied_ceiling_pct < 0.05:
        verdict = "FLAT"  # Could be giving up to 5%
    else:
        verdict = "DEPLOYING"  # Possible significant giving

    # Confidence based on data availability
    confidence = "HIGH" if history else "MEDIUM"

    return WealthAccumulationAnalysis(
        net_worth_current=current_net_worth,
        net_worth_prior=prior_net_worth,
        years_between=years_between,
        market_return_period=market_return,
        expected_wealth_growth=expected_change,
        actual_wealth_growth=actual_change,
        wealth_growth_rate=wealth_growth_rate,
        excess_growth_rate=excess_growth,
        implied_giving_ceiling=implied_ceiling_billions,
        implied_giving_ceiling_pct=implied_ceiling_pct,
        accumulation_verdict=verdict,
        confidence=confidence,
    )


def calculate_giving_ceiling(
    name: str,
    current_net_worth: float,
    years: int = 5
) -> Tuple[float, float, str]:
    """
    Calculate maximum possible giving based on wealth accumulation.

    Returns:
        (ceiling_in_billions, ceiling_as_percent, verdict)
    """
    analysis = analyze_wealth_accumulation(name, current_net_worth, years)
    return (
        analysis.implied_giving_ceiling,
        analysis.implied_giving_ceiling_pct,
        analysis.accumulation_verdict
    )


# ============================================================================
# SPECIFIC ACCUMULATOR DETECTION
# ============================================================================

def detect_rapid_accumulators(
    billionaires: List[Dict],
    threshold_multiplier: float = 2.0
) -> List[Dict]:
    """
    Identify billionaires whose wealth has grown faster than 2x market returns.

    These are definitionally not giving away significant amounts.
    """
    accumulators = []

    for person in billionaires:
        name = person.get("name", "")
        current_nw = person.get("net_worth_billions", 0)

        analysis = analyze_wealth_accumulation(name, current_nw, 5)

        if analysis.excess_growth_rate > (AVERAGE_MARKET_RETURN * (threshold_multiplier - 1)):
            accumulators.append({
                "name": name,
                "current_net_worth": current_nw,
                "prior_net_worth": analysis.net_worth_prior,
                "annual_growth_rate": analysis.wealth_growth_rate,
                "excess_over_market": analysis.excess_growth_rate,
                "verdict": "RAPID_ACCUMULATOR",
            })

    return accumulators


# ============================================================================
# COUNTEREXAMPLE: ACTUAL DEPLOYERS
# ============================================================================

def detect_wealth_deployers(billionaires: List[Dict]) -> List[Dict]:
    """
    Identify billionaires whose wealth has declined or grown slower than market.

    These are actually deploying capital (could be giving OR spending).
    """
    deployers = []

    for person in billionaires:
        name = person.get("name", "")
        current_nw = person.get("net_worth_billions", 0)

        analysis = analyze_wealth_accumulation(name, current_nw, 5)

        if analysis.implied_giving_ceiling > 0:
            deployers.append({
                "name": name,
                "current_net_worth": current_nw,
                "prior_net_worth": analysis.net_worth_prior,
                "implied_max_giving": analysis.implied_giving_ceiling,
                "implied_giving_pct": analysis.implied_giving_ceiling_pct,
                "verdict": analysis.accumulation_verdict,
            })

    return deployers


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def get_accumulation_analysis(name: str, net_worth_billions: float) -> Dict:
    """
    Main entry point for wealth accumulation analysis.

    Returns dict with:
    - wealth_growth_rate: Annual growth rate
    - excess_growth: Growth above market returns
    - implied_giving_ceiling_billions: Max they could have given
    - implied_giving_ceiling_pct: As percent of wealth
    - verdict: ACCUMULATING, FLAT, or DEPLOYING
    """
    analysis = analyze_wealth_accumulation(name, net_worth_billions)

    return {
        "prior_net_worth": analysis.net_worth_prior,
        "years_analyzed": analysis.years_between,
        "wealth_growth_rate": analysis.wealth_growth_rate,
        "market_return": analysis.market_return_period / analysis.years_between if analysis.years_between > 0 else 0,
        "excess_growth": analysis.excess_growth_rate,
        "implied_giving_ceiling_billions": analysis.implied_giving_ceiling,
        "implied_giving_ceiling_pct": analysis.implied_giving_ceiling_pct,
        "verdict": analysis.accumulation_verdict,
        "confidence": analysis.confidence,
    }


# ============================================================================
# TEST CODE
# ============================================================================

if __name__ == "__main__":
    test_cases = [
        # Rapid accumulators (definitely not giving)
        ("Elon Musk", 400.0),
        ("Jensen Huang", 117.0),
        ("Larry Ellison", 200.0),
        ("Larry Page", 156.0),

        # Possible deployers
        ("Bill Gates", 107.0),
        ("MacKenzie Scott", 33.0),
        ("Warren Buffett", 141.0),

        # Unknown
        ("Jeff Bezos", 233.0),
        ("Mark Zuckerberg", 200.0),
    ]

    print("=" * 90)
    print("WEALTH ACCUMULATION ANALYSIS")
    print("If wealth grows >= market rate, they're NOT giving significantly")
    print("=" * 90)
    print(f"\n{'Name':<25} {'Prior NW':>10} {'Current':>10} {'Growth':>8} {'vs Mkt':>8} {'Ceiling':>10} {'Verdict':<15}")
    print("-" * 90)

    for name, current_nw in test_cases:
        result = get_accumulation_analysis(name, current_nw)

        print(f"{name:<25} "
              f"${result['prior_net_worth']:>8.1f}B "
              f"${current_nw:>8.1f}B "
              f"{result['wealth_growth_rate']:>7.0%} "
              f"{result['excess_growth']:>+7.0%} "
              f"${result['implied_giving_ceiling_billions']:>8.1f}B "
              f"{result['verdict']:<15}")

    print("\n" + "=" * 90)
    print("INTERPRETATION:")
    print("- ACCUMULATING: Wealth grew faster than market. Giving ceiling = 0%")
    print("- FLAT: Wealth roughly matched market. Could be giving small amounts")
    print("- DEPLOYING: Wealth grew slower than market. Difference is max possible giving")
    print("=" * 90)
