#!/usr/bin/env python3
"""
Scrooge List Pipeline

Estimates charitable deployment for Forbes billionaires.

Pipeline Stages:
1. Forbes Pull      - Fetch billionaire list (✅ implemented)
2. Foundation Match - ProPublica 990-PF (✅ implemented)
3. Announced Gifts  - Wikipedia/MDL/News (✅ implemented)
4. Securities Gifts - SEC Form 4 (✅ implemented)
5. Red Flags        - Pattern detection (✅ implemented)
6. Giving Pledge    - IPS cross-reference (✅ implemented)
7. Political Giving - FEC/OpenSecrets (✅ implemented)
8. Wealth Factors   - Liquidity & tenure (✅ implemented)
9. Dark Estimates   - DAF/LLC/Anonymous/Religious (✅ implemented)

Output: Scrooge score combining all channels with confidence weighting.
"""

import argparse
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd

from stages.stage1_forbes import fetch_forbes_billionaires
from stages.stage2_foundations import match_foundations, Foundation
from stages.stage3_announced_gifts import search_announced_gifts
from stages.stage4_securities import search_sec_form4_gifts
from stages.stage5_red_flags import calculate_red_flags, BillionaireRecord
from stages.stage6_giving_pledge import load_giving_pledge_data, check_giving_pledge
from stages.stage7_political import search_political_giving, calculate_political_giving_ratio
from stages.stage8_wealth_factors import get_wealth_factors, calculate_scrooge_adjustment
from stages.stage9_dark_estimates import estimate_all_dark_channels


OUTPUT_DIR = "output"


@dataclass
class PipelineResult:
    """Final output for a billionaire."""
    # Basic info
    name: str
    net_worth_billions: float
    source: str
    country: str

    # Stage 2: Foundations
    foundation_count: int
    foundation_assets_billions: float
    annual_grants_millions: float
    foundation_pct_of_net_worth: float

    # Stage 3: Announced
    announced_gifts_millions: float

    # Stage 4: Securities
    securities_gifts_millions: float

    # Stage 5: Red flags
    red_flag_count: int
    red_flags: str

    # Stage 6: Giving Pledge
    giving_pledge_signed: bool
    giving_pledge_fulfilled: bool

    # Stage 7: Political
    political_giving_millions: float
    political_charitable_ratio: float

    # Stage 8: Wealth factors
    liquidity_pct: float
    years_as_billionaire: int
    liquid_wealth_billions: float

    # Stage 9: Dark estimates
    dark_estimate_millions: float
    dark_confidence: str

    # Derived scores
    total_observable_millions: float
    total_estimated_millions: float
    observable_giving_rate: float
    scrooge_score: float  # 0-100, higher = more Scrooge-like
    confidence: str


def calculate_scrooge_score(
    net_worth_billions: float,
    total_observable: float,
    total_estimated: float,
    liquidity_pct: float,
    years_as_billionaire: int,
    giving_pledge_signed: bool,
    red_flag_count: int,
) -> float:
    """
    Calculate the Scrooge Score (0-100).

    Higher score = more Scrooge-like (less giving relative to capacity).

    Components:
    1. Observable giving as % of liquid wealth (40% weight)
    2. Tenure penalty: longer = higher expectation (20% weight)
    3. Pledge breach penalty (20% weight)
    4. Red flag penalty (20% weight)
    """
    # Deployable wealth (adjusted for liquidity)
    deployable = net_worth_billions * 1e9 * liquidity_pct

    # Component 1: Observable giving ratio (inverted - more giving = lower score)
    if deployable > 0:
        giving_ratio = total_observable / deployable
        # Expected: 10% of liquid wealth over 10 years is reasonable
        expected_ratio = 0.10
        component_1 = max(0, min(40, (1 - giving_ratio / expected_ratio) * 40))
    else:
        component_1 = 20  # No deployable wealth info

    # Component 2: Tenure penalty (longer = higher expectation)
    if years_as_billionaire <= 3:
        component_2 = 0  # New billionaires get a pass
    elif years_as_billionaire <= 10:
        component_2 = (years_as_billionaire - 3) * 2  # 0-14 points
    else:
        component_2 = min(20, 14 + (years_as_billionaire - 10))  # Max 20

    # Component 3: Pledge breach penalty
    if giving_pledge_signed:
        # Check if they're meeting pledge targets
        if total_observable >= deployable * 0.25:
            component_3 = 0  # On track
        elif total_observable >= deployable * 0.10:
            component_3 = 10  # Behind
        else:
            component_3 = 20  # Severely behind
    else:
        component_3 = 5  # Small penalty for not signing

    # Component 4: Red flag penalty
    component_4 = min(20, red_flag_count * 5)

    # Total score
    score = component_1 + component_2 + component_3 + component_4
    return min(100, max(0, score))


def run_pipeline(
    limit: int = None,
    country_filter: str = None,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Run the full Scrooge List pipeline.

    Args:
        limit: Max billionaires to process
        country_filter: Filter by country (e.g., "United States")
        verbose: Print progress

    Returns:
        DataFrame with results sorted by scrooge_score descending
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # =========================================================================
    # STAGE 1: Fetch Forbes billionaire data
    # =========================================================================
    if verbose:
        print("\n" + "=" * 70)
        print("STAGE 1: Fetching Forbes billionaire data")
        print("=" * 70)

    billionaires = fetch_forbes_billionaires()
    if verbose:
        print(f"  Fetched {len(billionaires)} billionaires")

    if country_filter:
        billionaires = [b for b in billionaires if b.get("country") == country_filter]
        if verbose:
            print(f"  Filtered to {len(billionaires)} in {country_filter}")

    if limit:
        billionaires = billionaires[:limit]
        if verbose:
            print(f"  Limited to top {limit}")

    # =========================================================================
    # STAGE 6: Load Giving Pledge data (do this once upfront)
    # =========================================================================
    if verbose:
        print("\n" + "=" * 70)
        print("STAGE 6: Loading Giving Pledge data")
        print("=" * 70)

    pledgers = load_giving_pledge_data()
    if verbose:
        print(f"  Loaded {len(pledgers)} pledgers from IPS dataset")

    # =========================================================================
    # STAGES 2-9: Process each billionaire
    # =========================================================================
    if verbose:
        print("\n" + "=" * 70)
        print("STAGES 2-9: Processing billionaires")
        print("=" * 70)

    results = []

    for i, person in enumerate(billionaires):
        name = person["name"]
        net_worth = person["net_worth_billions"]
        wealth_source = person.get("source", "")

        if verbose:
            print(f"\n[{i+1}/{len(billionaires)}] {name} (${net_worth:.1f}B)")

        # Stage 2: Foundation matching
        foundations = match_foundations(name)
        total_assets = sum(f.total_assets for f in foundations)
        annual_grants = sum(f.grants_paid_latest for f in foundations)

        # Stage 3: Announced gifts
        announced = search_announced_gifts(name)
        announced_total = announced["total_announced"]

        # Stage 4: Securities gifts
        securities = search_sec_form4_gifts(name)
        securities_total = securities["total_stock_gifts"]

        # Stage 6: Giving Pledge
        signed, fulfilled = check_giving_pledge(name, pledgers)

        # Stage 7: Political giving
        political = search_political_giving(name)
        political_total = political["total_political"]

        # Stage 8: Wealth factors
        wealth_factors = get_wealth_factors(name, net_worth, wealth_source)

        # Stage 9: Dark estimates
        dark = estimate_all_dark_channels(
            name=name,
            net_worth_billions=net_worth,
            foundations=foundations,
            giving_pledge_signed=signed,
        )
        dark_mid = dark["weighted_estimate"]

        # Build record for Stage 5
        record = BillionaireRecord(
            name=name,
            net_worth_billions=net_worth,
            foundations=foundations,
            total_foundation_assets=total_assets,
            annual_foundation_grants=annual_grants,
            announced_gifts_total=announced_total,
            sec_form4_gifts=securities_total,
            giving_pledge_signed=signed,
            giving_pledge_fulfilled=fulfilled,
        )

        # Stage 5: Red flags
        red_flags = calculate_red_flags(record)

        # Calculate derived metrics
        foundation_pct = total_assets / (net_worth * 1e9) if net_worth > 0 else 0

        # Total observable = foundation grants + announced + securities
        observable = annual_grants + announced_total + securities_total

        # Total estimated = observable + dark estimate
        total_estimated = observable + dark_mid

        giving_rate = observable / (net_worth * 1e9) if net_worth > 0 else 0

        # Political/charitable ratio
        pc_ratio = calculate_political_giving_ratio(political_total, observable)

        # Scrooge score
        scrooge_score = calculate_scrooge_score(
            net_worth_billions=net_worth,
            total_observable=observable,
            total_estimated=total_estimated,
            liquidity_pct=wealth_factors["liquidity_pct"],
            years_as_billionaire=wealth_factors["years_as_billionaire"],
            giving_pledge_signed=signed,
            red_flag_count=len(red_flags),
        )

        # Confidence based on data availability
        if len(foundations) > 0 and total_assets > 100_000_000:
            confidence = "MEDIUM-HIGH"
        elif announced_total > 0 or securities_total > 0:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Build result
        result = PipelineResult(
            name=name,
            net_worth_billions=net_worth,
            source=person.get("source", ""),
            country=person.get("country", ""),
            foundation_count=len(foundations),
            foundation_assets_billions=total_assets / 1e9,
            annual_grants_millions=annual_grants / 1e6,
            foundation_pct_of_net_worth=foundation_pct,
            announced_gifts_millions=announced_total / 1e6,
            securities_gifts_millions=securities_total / 1e6,
            red_flag_count=len(red_flags),
            red_flags="; ".join(red_flags),
            giving_pledge_signed=signed,
            giving_pledge_fulfilled=fulfilled,
            political_giving_millions=political_total / 1e6,
            political_charitable_ratio=pc_ratio["ratio"] if pc_ratio["ratio"] != float("inf") else 999,
            liquidity_pct=wealth_factors["liquidity_pct"],
            years_as_billionaire=wealth_factors["years_as_billionaire"],
            liquid_wealth_billions=wealth_factors["liquid_wealth_billions"],
            dark_estimate_millions=dark_mid / 1e6,
            dark_confidence=dark.get("confidence", "LOW"),
            total_observable_millions=observable / 1e6,
            total_estimated_millions=total_estimated / 1e6,
            observable_giving_rate=giving_rate,
            scrooge_score=scrooge_score,
            confidence=confidence,
        )
        results.append(result)

    # =========================================================================
    # OUTPUT
    # =========================================================================
    if verbose:
        print("\n" + "=" * 70)
        print("GENERATING OUTPUT")
        print("=" * 70)

    # Convert to DataFrame
    df = pd.DataFrame([asdict(r) for r in results])
    df = df.sort_values("scrooge_score", ascending=False)  # Highest Scrooge first

    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = f"{OUTPUT_DIR}/scrooge_list_{timestamp}.csv"
    df.to_csv(csv_path, index=False)
    if verbose:
        print(f"  Saved: {csv_path}")

    json_path = f"{OUTPUT_DIR}/scrooge_list_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2, default=str)
    if verbose:
        print(f"  Saved: {json_path}")

    # Also save latest.json for web app
    latest_path = f"{OUTPUT_DIR}/scrooge_latest.json"
    with open(latest_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2, default=str)

    # Print summary
    if verbose:
        print("\n" + "=" * 70)
        print("SCROOGE RANKINGS (highest Scrooge score first)")
        print("=" * 70)
        print(f"\n{'Name':<25} {'Net Worth':>10} {'Observable':>12} {'Scrooge':>8} {'Flags':>6}")
        print("-" * 70)
        for _, row in df.head(20).iterrows():
            print(f"{row['name'][:25]:<25} ${row['net_worth_billions']:>8.1f}B "
                  f"${row['total_observable_millions']:>10.1f}M "
                  f"{row['scrooge_score']:>7.1f} "
                  f"{row['red_flag_count']:>6}")

    return df


def main():
    parser = argparse.ArgumentParser(
        description="Scrooge List Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py --test              # Test with 10 billionaires
  python3 main.py --limit 50          # Top 50 billionaires
  python3 main.py --country "United States" --limit 100
  python3 main.py                     # Full Forbes list (~3000)
        """
    )
    parser.add_argument("--limit", type=int, help="Max billionaires to process")
    parser.add_argument("--country", type=str, help="Filter by country")
    parser.add_argument("--test", action="store_true", help="Test mode (10 billionaires)")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")

    args = parser.parse_args()

    if args.test:
        run_pipeline(limit=10, verbose=not args.quiet)
    else:
        run_pipeline(limit=args.limit, country_filter=args.country, verbose=not args.quiet)


if __name__ == "__main__":
    main()
