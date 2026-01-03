#!/usr/bin/env python3
"""
Scrooge List Pipeline

Estimates charitable deployment for Forbes billionaires.

Pipeline Stages:
1. Forbes Pull      - Fetch billionaire list (✅ implemented)
2. Foundation Match - ProPublica 990-PF (✅ implemented)
3. Announced Gifts  - Chronicle/MDL (✅ implemented)
4. Securities Gifts - SEC Form 4 (✅ implemented)
5. Red Flags        - Pattern detection (✅ implemented)
6. Giving Pledge    - IPS cross-reference (✅ implemented)
7. Dark Giving      - Opaque channel estimation (✅ implemented)

Dark Giving covers estimation of opaque channels:
- DAF transfers from foundations
- Philanthropic LLC giving (CZI, Ballmer Group, etc.)
- Split-interest trust signals
- Anonymous gift inference (board seats, galas)
- Noncash gifts (art, real estate)
- Foreign giving (Schedule F)
- Religious institution giving
"""

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict

import pandas as pd

from stages.stage1_forbes import fetch_forbes_billionaires
from stages.stage2_foundations import match_foundations, Foundation
from stages.stage3_announced_gifts import search_announced_gifts
from stages.stage4_securities import search_sec_form4_gifts
from stages.stage5_red_flags import calculate_red_flags, BillionaireRecord
from stages.stage6_giving_pledge import load_giving_pledge_data, check_giving_pledge
from stages.stage7_dark_giving import estimate_dark_giving, calculate_opacity_score


OUTPUT_DIR = "output"


@dataclass
class PipelineResult:
    """Final output for a billionaire."""
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

    # Stage 7: Dark Giving
    dark_giving_estimate_millions: float
    dark_giving_confidence: str
    uses_llc: bool
    llc_name: str
    opacity_score: int
    opacity_flags: str

    # Derived
    observable_giving_rate: float
    total_estimated_giving_rate: float  # Includes dark giving
    confidence: str


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
        DataFrame with results sorted by foundation_pct_of_net_worth
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
    # STAGES 2-5: Process each billionaire
    # =========================================================================
    if verbose:
        print("\n" + "=" * 70)
        print("STAGES 2-5: Processing billionaires")
        print("=" * 70)

    results = []

    for i, person in enumerate(billionaires):
        name = person["name"]
        net_worth = person["net_worth_billions"]

        if verbose:
            print(f"\n[{i+1}/{len(billionaires)}] {name} (${net_worth:.1f}B)")

        # Stage 2: Foundation matching
        foundations = match_foundations(name)
        total_assets = sum(f.total_assets for f in foundations)
        annual_grants = sum(f.grants_paid_latest for f in foundations)

        # Stage 3: Announced gifts (Wikipedia + news)
        announced = search_announced_gifts(name)
        announced_total = announced["total_announced"]

        # Stage 4: Securities gifts (SEC EDGAR Form 4)
        securities = search_sec_form4_gifts(name)
        securities_total = securities["total_stock_gifts"]

        # Stage 6: Giving Pledge
        signed, fulfilled = check_giving_pledge(name, pledgers)

        # Stage 7: Dark Giving Estimation
        dark_giving = estimate_dark_giving(name, foundations)
        dark_total = dark_giving.total_dark_estimate
        opacity_score, opacity_explanations = calculate_opacity_score(
            name, net_worth, total_assets, dark_giving
        )

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
        observable = annual_grants + announced_total
        giving_rate = observable / (net_worth * 1e9) if net_worth > 0 else 0

        # Total estimated giving includes dark giving estimate
        total_estimated = observable + dark_total
        total_giving_rate = total_estimated / (net_worth * 1e9) if net_worth > 0 else 0

        # Confidence based on data availability
        if len(foundations) > 0 and total_assets > 100_000_000:
            confidence = "MEDIUM"
        elif announced_total > 0 or securities_total > 0:
            confidence = "MEDIUM-HIGH"
        elif dark_total > 0:
            confidence = "LOW"  # Dark giving adds uncertainty
        else:
            confidence = "LOW"

        # Combine all opacity flags
        all_opacity_flags = dark_giving.opacity_flags + opacity_explanations

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
            dark_giving_estimate_millions=dark_total / 1e6,
            dark_giving_confidence=dark_giving.overall_confidence,
            uses_llc=bool(dark_giving.llc_name),
            llc_name=dark_giving.llc_name,
            opacity_score=opacity_score,
            opacity_flags="; ".join(all_opacity_flags),
            observable_giving_rate=giving_rate,
            total_estimated_giving_rate=total_giving_rate,
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
    df = df.sort_values("foundation_pct_of_net_worth", ascending=True)

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

    # Print summary
    if verbose:
        print("\n" + "=" * 80)
        print("TOP CONCERNS (lowest foundation/net-worth ratio)")
        print("=" * 80)
        print(f"\n{'Name':<25} {'Net Worth':>10} {'Fdn Assets':>10} {'Dark Est':>10} {'Opacity':>8} {'Flags':>6}")
        print("-" * 80)
        for _, row in df.head(20).iterrows():
            print(f"{row['name'][:25]:<25} ${row['net_worth_billions']:>8.1f}B "
                  f"${row['foundation_assets_billions']:>8.2f}B "
                  f"${row['dark_giving_estimate_millions']:>8.1f}M "
                  f"{row['opacity_score']:>7} "
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
