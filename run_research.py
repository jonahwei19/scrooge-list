#!/usr/bin/env python3
"""
Scrooge List Research Pipeline

This script orchestrates research for billionaire giving using Claude subagents.
Each billionaire is researched across all giving categories using web search.

Usage:
    python3 run_research.py --name "Larry Ellison" --net-worth 245.0
    python3 run_research.py --forbes-top 50
    python3 run_research.py --from-file billionaires.json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import List, Dict, Optional

# Giving categories to research
CATEGORIES = [
    "FOUNDATIONS",
    "DIRECT_GIFTS",
    "SECURITIES",
    "DAFS",
    "SPLIT_INTEREST",
    "PHILANTHROPIC_LLCS",
    "RELIGIOUS",
    "ANONYMOUS",
]

DATA_DIR = "data"
OUTPUT_DIR = "output"


def load_forbes_list(limit: int = None) -> List[Dict]:
    """Load Forbes billionaires from Stage 1."""
    from stages.stage1_forbes import fetch_forbes_billionaires

    billionaires = fetch_forbes_billionaires()
    if limit:
        billionaires = billionaires[:limit]
    return billionaires


def get_cached_result(name: str) -> Optional[Dict]:
    """Check if we have cached research for this billionaire."""
    safe_name = name.replace(" ", "_").replace("&", "and").lower()
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")

    filepath = os.path.join(DATA_DIR, f"{safe_name}.json")

    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)

        # Check freshness (7 days)
        research_date = data.get("research_date", "")
        if research_date:
            try:
                date = datetime.fromisoformat(research_date.replace("Z", "+00:00"))
                age = datetime.now() - date.replace(tzinfo=None)
                if age.days < 7:
                    return data
            except:
                pass

    return None


def calculate_scrooge_score(
    net_worth_billions: float,
    total_giving: float,
    liquidity_pct: float = 0.3,
    years_as_billionaire: int = 10,
) -> float:
    """
    Calculate Scrooge Score (0-100).
    Higher = more Scrooge-like (less giving relative to capacity).
    """
    if net_worth_billions <= 0:
        return 50.0

    liquid_wealth = net_worth_billions * 1e9 * liquidity_pct
    expected_giving = liquid_wealth * 0.10  # 10% benchmark

    if expected_giving <= 0:
        return 50.0

    giving_ratio = total_giving / expected_giving
    base_score = max(0, min(100, (1 - giving_ratio) * 100))

    # Tenure adjustment
    if years_as_billionaire > 10:
        tenure_penalty = min(10, (years_as_billionaire - 10) * 0.5)
        base_score = min(100, base_score + tenure_penalty)

    return round(base_score, 1)


def aggregate_results(data_dir: str = DATA_DIR) -> List[Dict]:
    """Aggregate all individual research files into a summary."""
    results = []

    for filename in os.listdir(data_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r") as f:
                data = json.load(f)

            # Extract key metrics
            summary = data.get("summary", {})

            result = {
                "name": data.get("name", "Unknown"),
                "net_worth_billions": data.get("net_worth_billions", 0),
                "country": data.get("country", "Unknown"),
                "research_date": data.get("research_date", ""),

                # By category
                "foundations_total": data.get("foundations", {}).get("total", 0),
                "direct_gifts_total": data.get("direct_gifts", {}).get("total", 0),
                "securities_total": data.get("securities", {}).get("total", 0),
                "dafs_total": data.get("dafs", {}).get("total", 0),
                "llcs_total": data.get("llcs", {}).get("total", 0),

                # Aggregates
                "total_found": summary.get("total_after_dedup", 0),
                "total_observable_millions": summary.get("total_after_dedup", 0) / 1e6,
                "giving_rate_pct": summary.get("giving_rate_pct", 0),

                # Sources count
                "source_count": len(data.get("sources", [])),
            }

            # Calculate Scrooge score
            result["scrooge_score"] = calculate_scrooge_score(
                net_worth_billions=result["net_worth_billions"],
                total_giving=result["total_found"],
            )

            results.append(result)

    # Sort by Scrooge score (highest first = most Scrooge-like)
    results.sort(key=lambda x: x["scrooge_score"], reverse=True)

    return results


def save_scrooge_list(results: List[Dict]):
    """Save the aggregated Scrooge List."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save timestamped version
    filepath = os.path.join(OUTPUT_DIR, f"scrooge_list_{timestamp}.json")
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved: {filepath}")

    # Save latest version for web app
    latest_path = os.path.join("docs", "scrooge_latest.json")
    with open(latest_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Updated: {latest_path}")


def print_summary(results: List[Dict]):
    """Print a summary table."""
    print("\n" + "=" * 80)
    print("SCROOGE LIST - Ranked by Scrooge Score (higher = less giving)")
    print("=" * 80)
    print(f"\n{'Name':<30} {'Net Worth':>12} {'Observable':>12} {'Score':>8}")
    print("-" * 80)

    for r in results[:20]:
        print(f"{r['name'][:30]:<30} ${r['net_worth_billions']:>10.1f}B "
              f"${r['total_observable_millions']:>10.1f}M "
              f"{r['scrooge_score']:>7.1f}")


def main():
    parser = argparse.ArgumentParser(description="Scrooge List Research Pipeline")
    parser.add_argument("--name", type=str, help="Research a single billionaire by name")
    parser.add_argument("--net-worth", type=float, help="Net worth in billions (with --name)")
    parser.add_argument("--forbes-top", type=int, help="Research top N from Forbes list")
    parser.add_argument("--aggregate", action="store_true", help="Aggregate existing research into Scrooge List")
    parser.add_argument("--country", type=str, help="Filter Forbes list by country")

    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    if args.aggregate:
        results = aggregate_results()
        save_scrooge_list(results)
        print_summary(results)
        return

    if args.name:
        # Single billionaire research
        cached = get_cached_result(args.name)
        if cached:
            print(f"Using cached research for {args.name}")
            print(json.dumps(cached, indent=2))
        else:
            print(f"Need to research {args.name} - use Claude subagent")
            print(f"Search queries to run:")
            print(f'  - "{args.name}" foundation 990 ProPublica grants')
            print(f'  - "{args.name}" donated million billion philanthropy')
            print(f'  - "{args.name}" charity gift university hospital')
        return

    if args.forbes_top:
        print(f"Loading top {args.forbes_top} from Forbes...")
        billionaires = load_forbes_list(args.forbes_top)

        if args.country:
            billionaires = [b for b in billionaires if b.get("country") == args.country]

        print(f"Found {len(billionaires)} billionaires to research")

        for i, b in enumerate(billionaires):
            name = b["name"]
            net_worth = b["net_worth_billions"]

            cached = get_cached_result(name)
            if cached:
                print(f"[{i+1}/{len(billionaires)}] {name}: Using cached data")
            else:
                print(f"[{i+1}/{len(billionaires)}] {name}: NEEDS RESEARCH")

        print("\nTo research uncached billionaires, run Claude subagents for each.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
