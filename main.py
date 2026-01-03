#!/usr/bin/env python3
"""
Scrooge List Pipeline

Estimates charitable deployment for Forbes billionaires.

Pipeline Stages:
1. Forbes Pull         - Fetch billionaire list (Implemented)
2. Foundation Match    - ProPublica 990-PF (Implemented)
3. Announced Gifts     - Chronicle/MDL (Implemented)
4. Securities Gifts    - SEC Form 4 (Implemented)
5. Red Flags           - Pattern detection (Implemented)
6. Giving Pledge       - IPS cross-reference (Implemented)
7. DAF Contributions   - DAF estimation (Implemented)
8. Split-Interest      - CRT/CLT estimation (Implemented)
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
from stages.stage5_red_flags import calculate_red_flags, calculate_opacity_score, BillionaireRecord
from stages.stage6_giving_pledge import load_giving_pledge_data, check_giving_pledge
from stages.stage7_daf import estimate_daf_contributions, get_daf_opacity_score, DAFEstimate
from stages.stage8_split_interest import estimate_split_interest_trusts, get_split_interest_red_flags, SplitInterestEstimate


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

    # Stage 3: Announced gifts
    announced_gifts_millions: float

    # Stage 4: Securities gifts
    securities_gifts_millions: float

    # Stage 5: Red flags
    red_flag_count: int
    red_flags: str

    # Stage 6: Giving Pledge
    giving_pledge_signed: bool
    giving_pledge_fulfilled: bool

    # Stage 7: DAF contributions
    daf_foundation_transfers_millions: float
    daf_pct_of_grants: float
    daf_opacity_score: float
    daf_confidence: str

    # Stage 8: Split-interest trusts
    split_interest_trust_count: int
    split_interest_assets_millions: float
    split_interest_annual_charitable_millions: float
    clat_wealth_transfer_millions: float
    is_wealth_transfer_pattern: bool
    split_interest_confidence: str

    # Derived
    observable_giving_rate: float
    total_estimated_giving_millions: float
    opacity_score: float
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

        # Stage 7: DAF contribution estimation
        daf_estimate = estimate_daf_contributions(
            name=name,
            foundations=foundations,
            net_worth_billions=net_worth,
            sec_gifts_total=securities_total,
            announced_gifts_total=announced_total
        )
        daf_opacity = get_daf_opacity_score(daf_estimate)

        # Stage 8: Split-interest trust estimation
        split_interest_estimate = estimate_split_interest_trusts(
            name=name,
            net_worth_billions=net_worth,
            foundation_assets=total_assets,
            foundation_grants=annual_grants
        )

        # Build record for Stage 5 (includes new estimates)
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
            daf_estimate=daf_estimate,
            split_interest_estimate=split_interest_estimate,
        )

        # Stage 5: Red flags (now includes DAF and split-interest flags)
        red_flags = calculate_red_flags(record)

        # Calculate derived metrics
        foundation_pct = total_assets / (net_worth * 1e9) if net_worth > 0 else 0
        observable = annual_grants + announced_total
        giving_rate = observable / (net_worth * 1e9) if net_worth > 0 else 0

        # Calculate opacity score
        opacity = calculate_opacity_score(record)

        # Total estimated giving (observable + DAF + split-interest charitable)
        total_estimated = (
            annual_grants +
            announced_total +
            securities_total +
            daf_estimate.foundation_to_daf_total +
            split_interest_estimate.known_annual_charitable
        )

        # Confidence based on data availability
        if len(foundations) > 0 and total_assets > 100_000_000:
            if daf_estimate.confidence in ["MEDIUM", "HIGH"]:
                confidence = "MEDIUM-HIGH"
            else:
                confidence = "MEDIUM"
        elif announced_total > 0 or securities_total > 0:
            confidence = "MEDIUM"
        elif daf_estimate.status != "NO_DATA" or split_interest_estimate.status != "NO_DATA":
            confidence = "LOW-MEDIUM"
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
            # DAF data
            daf_foundation_transfers_millions=daf_estimate.foundation_to_daf_total / 1e6,
            daf_pct_of_grants=daf_estimate.daf_pct_of_grants,
            daf_opacity_score=daf_opacity,
            daf_confidence=daf_estimate.confidence,
            # Split-interest trust data
            split_interest_trust_count=len(split_interest_estimate.known_trusts),
            split_interest_assets_millions=split_interest_estimate.known_trust_assets / 1e6,
            split_interest_annual_charitable_millions=split_interest_estimate.known_annual_charitable / 1e6,
            clat_wealth_transfer_millions=split_interest_estimate.clat_wealth_transfer_estimated / 1e6,
            is_wealth_transfer_pattern=split_interest_estimate.is_wealth_transfer_pattern,
            split_interest_confidence=split_interest_estimate.confidence,
            # Derived
            observable_giving_rate=giving_rate,
            total_estimated_giving_millions=total_estimated / 1e6,
            opacity_score=opacity,
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
        print("\n" + "=" * 70)
        print("TOP CONCERNS (lowest foundation/net-worth ratio)")
        print("=" * 70)
        print(f"\n{'Name':<25} {'Net Worth':>10} {'Fdn Assets':>10} {'Ratio':>7} {'Opacity':>7} {'Flags':>5}")
        print("-" * 75)
        for _, row in df.head(20).iterrows():
            print(f"{row['name'][:25]:<25} ${row['net_worth_billions']:>8.1f}B "
                  f"${row['foundation_assets_billions']:>8.2f}B "
                  f"{row['foundation_pct_of_net_worth']:>6.1%} "
                  f"{row['opacity_score']:>6.2f} "
                  f"{row['red_flag_count']:>5}")

        # Additional summary for DAF and split-interest activity
        print("\n" + "=" * 70)
        print("DAF & SPLIT-INTEREST TRUST ACTIVITY")
        print("=" * 70)

        daf_users = df[df['daf_pct_of_grants'] > 0.1]
        if len(daf_users) > 0:
            print(f"\nBillionaires with >10% grants to DAFs: {len(daf_users)}")
            for _, row in daf_users.head(10).iterrows():
                print(f"  {row['name'][:30]}: {row['daf_pct_of_grants']:.0%} to DAFs (opacity: {row['daf_opacity_score']:.2f})")

        clat_users = df[df['split_interest_trust_count'] > 0]
        if len(clat_users) > 0:
            print(f"\nBillionaires with known split-interest trusts: {len(clat_users)}")
            for _, row in clat_users.head(10).iterrows():
                wt_flag = " [WEALTH TRANSFER]" if row['is_wealth_transfer_pattern'] else ""
                print(f"  {row['name'][:30]}: {row['split_interest_trust_count']} trust(s), ${row['split_interest_assets_millions']:.0f}M{wt_flag}")

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
