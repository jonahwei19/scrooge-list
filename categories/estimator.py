"""
MAIN ESTIMATOR

Orchestrates all category estimators and produces final giving estimate.

Flow:
1. Run FOUNDATIONS estimator (ProPublica API)
2. Run DIRECT_GIFTS estimator (news/Wikipedia)
3. Run SECURITIES estimator (SEC EDGAR Form 4)
4. Run DAFS estimator (foundation transfers + NW proxy)
5. Run LLCS estimator (known LLC database)
6. Run DEDUPLICATION (remove double-counting)
7. Calculate Scrooge Score
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from .foundations import estimate_foundation_giving
from .direct_gifts import estimate_direct_gifts
from .securities import estimate_securities_gifts
from .dafs import estimate_daf_giving
from .llcs import estimate_llc_giving
from .trusts import estimate_split_interest_trusts
from .political import estimate_political_giving
from .deduplication import deduplicate_gifts, aggregate_by_category, UnifiedGift


@dataclass
class ScroogeResult:
    """Final result for a billionaire."""
    name: str
    net_worth_billions: float
    country: str
    research_date: str

    # Category totals (pre-dedup)
    foundations_total: float
    direct_gifts_total: float
    securities_total: float
    dafs_total: float
    llcs_total: float
    trusts_total: float
    political_total: float  # Context only, not counted as charity

    # Deduplication
    pre_dedup_total: float
    dedup_removed: float
    foundation_transfers_removed: int

    # Final numbers
    total_observable: float
    giving_rate_pct: float

    # Confidence and sources
    source_count: int
    confidence_breakdown: Dict[str, str]
    red_flags: List[str]
    source_urls: List[str]

    # Scrooge Score
    scrooge_score: float


def calculate_scrooge_score(
    giving_rate: float,
    years_as_billionaire: int = 10,
    is_pledge_signer: bool = False,
    red_flag_count: int = 0,
) -> float:
    """
    Calculate Scrooge Score (0-100, higher = more Scrooge-like).

    Components:
    - Giving gap (40%): 1 - (observable / expected), where expected = 10% of liquid
    - Years penalty (20%): Scales with tenure
    - Pledge breach (20%): Penalty if signed Giving Pledge but giving < 10%
    - Red flags (20%): 5 points per flag
    """
    # Expected giving rate = 10% of liquid wealth
    expected_rate = 10.0

    # Giving gap: how far below expected
    giving_gap = max(0, (expected_rate - giving_rate) / expected_rate)
    giving_gap = min(1.0, giving_gap)  # Cap at 1.0

    # Years penalty: 0 for <3 years, scales to max at 20+ years
    if years_as_billionaire < 3:
        years_penalty = 0
    else:
        years_penalty = min(1.0, (years_as_billionaire - 3) / 17)

    # Pledge breach: 1.0 if signed but not on track
    pledge_breach = 1.0 if (is_pledge_signer and giving_rate < 10.0) else 0.0

    # Red flags: 5 points each, max 20 points (normalized to 0-1)
    flag_penalty = min(1.0, red_flag_count * 0.25)

    # Weighted sum
    score = (
        giving_gap * 40 +
        years_penalty * 20 +
        pledge_breach * 20 +
        flag_penalty * 20
    )

    # If giving rate > 10%, score goes to 0
    if giving_rate >= 10.0:
        score = 0

    return round(score, 1)


def estimate_billionaire(
    name: str,
    net_worth_billions: float,
    country: str = "United States",
    known_direct_gifts: List[Dict] = None,
    known_llc_grants: List[Dict] = None,
    years_as_billionaire: int = 10,
    is_pledge_signer: bool = False,
) -> ScroogeResult:
    """
    Run full estimation pipeline for a single billionaire.

    Args:
        name: Full name
        net_worth_billions: Forbes net worth
        country: Country of residence
        known_direct_gifts: Pre-researched direct gifts (from LLM research)
        known_llc_grants: Pre-researched LLC grants (from LLM research)
        years_as_billionaire: Tenure for scoring
        is_pledge_signer: Whether signed Giving Pledge

    Returns:
        ScroogeResult with all data
    """
    print(f"\n{'='*60}")
    print(f"Estimating giving for: {name}")
    print(f"Net worth: ${net_worth_billions}B")
    print(f"{'='*60}")

    all_source_urls = []
    confidence_breakdown = {}
    red_flags = []

    # 1. FOUNDATIONS
    foundations_result = estimate_foundation_giving(name, net_worth_billions)
    foundations_total = foundations_result["annual_grants"]
    confidence_breakdown["FOUNDATIONS"] = foundations_result["confidence"]
    all_source_urls.extend(foundations_result.get("source_urls", []))
    red_flags.extend(foundations_result.get("red_flags", []))

    # Get foundation names for deduplication
    billionaire_foundations = [f["name"] for f in foundations_result.get("foundations", [])]

    # 2. DIRECT GIFTS
    direct_result = estimate_direct_gifts(name, known_gifts=known_direct_gifts)
    direct_total = direct_result["total_disbursed"]
    confidence_breakdown["DIRECT_GIFTS"] = direct_result["confidence"]
    all_source_urls.extend(direct_result.get("source_urls", []))

    # 3. SECURITIES
    securities_result = estimate_securities_gifts(name, net_worth_billions)
    securities_total = securities_result["total_value"]
    confidence_breakdown["SECURITIES"] = securities_result["confidence"]
    all_source_urls.extend(securities_result.get("source_urls", []))

    # 4. DAFs
    foundation_eins = [f["ein"] for f in foundations_result.get("foundations", [])]
    daf_result = estimate_daf_giving(name, net_worth_billions, foundation_eins)
    daf_total = daf_result["total_used"]
    confidence_breakdown["DAFS"] = daf_result["confidence"]
    if daf_result.get("red_flag"):
        red_flags.append("HIGH_DAF_TRANSFERS")

    # 5. PHILANTHROPIC LLCs
    llc_result = estimate_llc_giving(name, net_worth_billions, known_llc_grants)
    llc_total = llc_result["total"]
    confidence_breakdown["LLCS"] = llc_result["confidence"]
    all_source_urls.extend(llc_result.get("source_urls", []))

    # 6. SPLIT-INTEREST TRUSTS
    trust_result = estimate_split_interest_trusts(name)
    trust_total = trust_result["annual_payout"]  # Use annual payout, not total value
    confidence_breakdown["TRUSTS"] = trust_result["confidence"]
    all_source_urls.extend(trust_result.get("source_urls", []))

    # 7. POLITICAL GIVING (context only - not counted as charity)
    political_result = estimate_political_giving(name)
    political_total = political_result["total"]
    confidence_breakdown["POLITICAL"] = political_result["confidence"]
    # Note: Political giving is NOT added to charitable total

    # Collect all gifts for deduplication
    all_gifts = []

    # Foundation grants
    for f in foundations_result.get("foundations", []):
        all_gifts.append({
            "category": "FOUNDATIONS",
            "recipient": "Various (foundation grants)",
            "amount": f["latest_grants"],
            "year": f["latest_year"],
            "is_pledge": False,
            "source_url": f["source_url"],
            "confidence": foundations_result["confidence"],
        })

    # Direct gifts
    for g in direct_result.get("gifts", []):
        all_gifts.append({
            "category": "DIRECT_GIFTS",
            "recipient": g["recipient"],
            "amount": g["amount"],
            "year": g["year"],
            "is_pledge": g.get("is_pledge", False),
            "source_url": g.get("source_url", ""),
            "confidence": direct_result["confidence"],
        })

    # Securities
    for g in securities_result.get("gifts", []):
        all_gifts.append({
            "category": "SECURITIES",
            "recipient": g.get("recipient", "Foundation"),
            "amount": g["total_value"],
            "year": int(g["transaction_date"][:4]) if g.get("transaction_date") else 2024,
            "is_pledge": False,
            "source_url": g["source_url"],
            "confidence": securities_result["confidence"],
        })

    # LLC grants
    for g in llc_result.get("grants", []):
        all_gifts.append({
            "category": "PHILANTHROPIC_LLCS",
            "recipient": g["recipient"],
            "amount": g["amount"],
            "year": g["year"],
            "is_pledge": False,
            "source_url": g.get("source_url", ""),
            "confidence": llc_result["confidence"],
        })

    # Trust payouts
    for t in trust_result.get("trusts", []):
        all_gifts.append({
            "category": "SPLIT_INTEREST_TRUSTS",
            "recipient": "Charity (via trust)",
            "amount": t["annual_payout"],
            "year": 2024,
            "is_pledge": False,
            "source_url": t.get("source_url", ""),
            "confidence": trust_result["confidence"],
        })

    # Run deduplication
    deduped_gifts, dedup_stats = deduplicate_gifts(all_gifts, billionaire_foundations)

    # Pre-dedup total (not including political - that's context only)
    pre_dedup_total = foundations_total + direct_total + securities_total + llc_total + trust_total

    # Post-dedup total
    total_observable = sum(g.amount for g in deduped_gifts if not g.is_pledge)

    # Add DAF (not deduplicated - different channel)
    # Note: Only add if confidence isn't ZERO (meaning we have some data)
    if daf_result["confidence"] != "ZERO":
        total_observable += daf_result["observed_total"]  # Only observed, not NW estimate

    # Calculate giving rate
    giving_rate = (total_observable / (net_worth_billions * 1e9)) * 100

    # Add red flags
    if total_observable < 100_000_000 and net_worth_billions > 10:
        red_flags.append("NO_OBSERVABLE_GIVING")

    # Calculate Scrooge score
    scrooge_score = calculate_scrooge_score(
        giving_rate,
        years_as_billionaire,
        is_pledge_signer,
        len(red_flags),
    )

    print(f"\n{'='*60}")
    print(f"SUMMARY for {name}")
    print(f"{'='*60}")
    print(f"  Foundations: ${foundations_total/1e6:.1f}M")
    print(f"  Direct gifts: ${direct_total/1e6:.1f}M")
    print(f"  Securities: ${securities_total/1e6:.1f}M")
    print(f"  DAFs observed: ${daf_result['observed_total']/1e6:.1f}M")
    print(f"  LLCs: ${llc_total/1e6:.1f}M")
    print(f"  Trusts (annual): ${trust_total/1e6:.1f}M")
    print(f"  Political (context): ${political_total/1e6:.1f}M")
    print(f"  ---")
    print(f"  Pre-dedup total: ${pre_dedup_total/1e6:.1f}M")
    print(f"  Duplicates removed: {dedup_stats['duplicates_removed']}")
    print(f"  Foundation transfers removed: {dedup_stats['foundation_transfers_removed']}")
    print(f"  ---")
    print(f"  TOTAL OBSERVABLE: ${total_observable/1e6:.1f}M")
    print(f"  Giving rate: {giving_rate:.2f}%")
    print(f"  Scrooge score: {scrooge_score}")

    return ScroogeResult(
        name=name,
        net_worth_billions=net_worth_billions,
        country=country,
        research_date=datetime.now().isoformat(),
        foundations_total=foundations_total,
        direct_gifts_total=direct_total,
        securities_total=securities_total,
        dafs_total=daf_total,
        llcs_total=llc_total,
        trusts_total=trust_total,
        political_total=political_total,
        pre_dedup_total=pre_dedup_total,
        dedup_removed=dedup_stats['duplicates_removed'],
        foundation_transfers_removed=dedup_stats['foundation_transfers_removed'],
        total_observable=total_observable,
        giving_rate_pct=giving_rate,
        source_count=len(set(all_source_urls)),
        confidence_breakdown=confidence_breakdown,
        red_flags=red_flags,
        source_urls=list(set(all_source_urls)),
        scrooge_score=scrooge_score,
    )


def run_batch(billionaires: List[Dict], output_file: str = None) -> List[ScroogeResult]:
    """
    Run estimation for a batch of billionaires.

    Args:
        billionaires: List of dicts with name, net_worth_billions, country, etc.
        output_file: Optional path to save results

    Returns:
        List of ScroogeResult
    """
    results = []

    for b in billionaires:
        result = estimate_billionaire(
            name=b["name"],
            net_worth_billions=b["net_worth_billions"],
            country=b.get("country", "United States"),
            known_direct_gifts=b.get("known_direct_gifts"),
            known_llc_grants=b.get("known_llc_grants"),
            years_as_billionaire=b.get("years_as_billionaire", 10),
            is_pledge_signer=b.get("is_pledge_signer", False),
        )
        results.append(result)

    # Sort by Scrooge score descending
    results.sort(key=lambda r: r.scrooge_score, reverse=True)

    if output_file:
        with open(output_file, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        print(f"\nResults saved to {output_file}")

    return results


if __name__ == "__main__":
    # Comprehensive test with 15 billionaires
    test_billionaires = [
        # Tech founders
        {"name": "Elon Musk", "net_worth_billions": 718.0, "country": "United States",
         "is_pledge_signer": False, "years_as_billionaire": 12},
        {"name": "Jeff Bezos", "net_worth_billions": 238.7, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 25},
        {"name": "Mark Zuckerberg", "net_worth_billions": 223.0, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 16,
         "known_llc_grants": [{"recipient": "Various", "amount": 7_220_000_000, "year": 2024,
          "purpose": "CZI cumulative", "source_url": "https://chanzuckerberg.com"}]},
        {"name": "Larry Ellison", "net_worth_billions": 245.0, "country": "United States",
         "is_pledge_signer": False, "years_as_billionaire": 35},
        {"name": "Bill Gates", "net_worth_billions": 129.0, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 38},

        # Finance
        {"name": "Warren Buffett", "net_worth_billions": 146.8, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 38},
        {"name": "Jim Simons", "net_worth_billions": 31.4, "country": "United States",
         "is_pledge_signer": False, "years_as_billionaire": 25},
        {"name": "Ray Dalio", "net_worth_billions": 19.1, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 20},
        {"name": "George Soros", "net_worth_billions": 7.2, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 35},

        # Retail
        {"name": "Jim Walton", "net_worth_billions": 108.0, "country": "United States",
         "is_pledge_signer": False, "years_as_billionaire": 30},
        {"name": "Phil Knight", "net_worth_billions": 47.3, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 30},

        # Media
        {"name": "Michael Bloomberg", "net_worth_billions": 96.0, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 25},

        # Mega donors
        {"name": "MacKenzie Scott", "net_worth_billions": 36.0, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 5},

        # Other tech
        {"name": "Jensen Huang", "net_worth_billions": 127.0, "country": "United States",
         "is_pledge_signer": False, "years_as_billionaire": 5},
        {"name": "Dustin Moskovitz", "net_worth_billions": 11.4, "country": "United States",
         "is_pledge_signer": True, "years_as_billionaire": 12,
         "known_llc_grants": [{"recipient": "Various (Open Philanthropy)", "amount": 3_000_000_000,
          "year": 2024, "purpose": "EA/GH grants", "source_url": "https://www.openphilanthropy.org/"}]},
    ]

    results = run_batch(test_billionaires, output_file="output/automated_results.json")

    print("\n\nFINAL SCROOGE RANKINGS:")
    print("="*80)
    print(f"{'Name':<25} {'Net Worth':>12} {'Observable':>14} {'Rate':>8} {'Score':>8}")
    print("-"*80)
    for r in results:
        print(f"{r.name:<25} ${r.net_worth_billions:>10.1f}B ${r.total_observable/1e9:>11.2f}B {r.giving_rate_pct:>7.2f}% {r.scrooge_score:>7.1f}")
