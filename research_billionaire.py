#!/usr/bin/env python3
"""
Research a single billionaire's charitable giving across all categories.

This script is designed to be called by Claude Code as a subagent task.
It searches the web for giving in each category and returns structured results.

Usage:
    python3 research_billionaire.py "Larry Ellison" 245.0 "United States"
"""

import json
import sys
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Finding:
    """A single found instance of charitable giving."""
    amount: float
    recipient: str
    year: str
    category: str
    source_url: str
    description: str
    confidence: str  # HIGH, MEDIUM, LOW


@dataclass
class CategoryResult:
    """Results for one giving category."""
    category: str
    total: float
    findings: List[Finding]
    confidence: str
    notes: str


@dataclass
class ResearchResult:
    """Complete research result for one billionaire."""
    name: str
    net_worth_billions: float
    country: str
    research_date: str

    # By category
    foundations: CategoryResult
    dafs: CategoryResult
    direct_gifts: CategoryResult
    securities: CategoryResult
    split_interest: CategoryResult
    llcs: CategoryResult
    religious: CategoryResult
    anonymous: CategoryResult

    # Aggregates
    total_found: float
    total_after_dedup: float
    duplicates_removed: float
    all_sources: List[str]


def save_result(result: ResearchResult, output_dir: str = "data"):
    """Save research result to JSON file."""
    os.makedirs(output_dir, exist_ok=True)

    # Clean filename
    safe_name = result.name.replace(" ", "_").replace("&", "and").lower()
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")

    filepath = os.path.join(output_dir, f"{safe_name}.json")

    with open(filepath, "w") as f:
        json.dump(asdict(result), f, indent=2, default=str)

    print(f"Saved: {filepath}")
    return filepath


def load_cached_result(name: str, output_dir: str = "data") -> Optional[ResearchResult]:
    """Load cached result if exists and recent."""
    safe_name = name.replace(" ", "_").replace("&", "and").lower()
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")

    filepath = os.path.join(output_dir, f"{safe_name}.json")

    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)

        # Check if recent (within 7 days)
        research_date = data.get("research_date", "")
        if research_date:
            try:
                date = datetime.fromisoformat(research_date)
                age = datetime.now() - date
                if age.days < 7:
                    print(f"Using cached result from {research_date}")
                    return data
            except:
                pass

    return None


def create_empty_category(category: str) -> CategoryResult:
    """Create an empty category result."""
    return CategoryResult(
        category=category,
        total=0.0,
        findings=[],
        confidence="ZERO",
        notes="Not yet researched"
    )


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 research_billionaire.py <name> <net_worth_billions> <country>")
        print("Example: python3 research_billionaire.py 'Larry Ellison' 245.0 'United States'")
        sys.exit(1)

    name = sys.argv[1]
    net_worth = float(sys.argv[2])
    country = sys.argv[3]

    print(f"\n{'='*60}")
    print(f"Researching: {name}")
    print(f"Net Worth: ${net_worth}B")
    print(f"Country: {country}")
    print(f"{'='*60}\n")

    # Check cache first
    cached = load_cached_result(name)
    if cached:
        print(json.dumps(cached, indent=2))
        return

    # Create empty result structure
    # The actual research will be done by the Claude subagent
    result = ResearchResult(
        name=name,
        net_worth_billions=net_worth,
        country=country,
        research_date=datetime.now().isoformat(),
        foundations=create_empty_category("FOUNDATIONS"),
        dafs=create_empty_category("DAFS"),
        direct_gifts=create_empty_category("DIRECT_GIFTS"),
        securities=create_empty_category("SECURITIES"),
        split_interest=create_empty_category("SPLIT_INTEREST"),
        llcs=create_empty_category("LLCS"),
        religious=create_empty_category("RELIGIOUS"),
        anonymous=create_empty_category("ANONYMOUS"),
        total_found=0.0,
        total_after_dedup=0.0,
        duplicates_removed=0.0,
        all_sources=[],
    )

    # Print as JSON for the calling agent to parse
    print("\n--- RESEARCH TEMPLATE ---")
    print("The Claude subagent should fill in the findings for each category.")
    print("Search queries to use:")
    print(f'  - "{name}" foundation 990 grants')
    print(f'  - "{name}" donated million billion gift')
    print(f'  - "{name}" philanthropy charity')
    print(f'  - "{name}" donor advised fund')
    print(f'  - "{name}" stock gift securities')
    print("\n--- EMPTY RESULT STRUCTURE ---")
    print(json.dumps(asdict(result), indent=2, default=str))


if __name__ == "__main__":
    main()
