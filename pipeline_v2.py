#!/usr/bin/env python3
"""
Scrooge List Pipeline v2 - Taxonomy-Driven

This pipeline estimates charitable giving by CATEGORY, not by data source.
Each category is researched independently, then results are summed with deduplication.

Categories:
1. FOUNDATIONS - 990-PF data, grants paid
2. DAFS - Donor-advised funds (opaque)
3. DIRECT_GIFTS - Named/announced gifts
4. SECURITIES - Stock gifts
5. SPLIT_INTEREST - CRTs, CLTs
6. PHILANTHROPIC_LLCS - CZI, Ballmer Group, etc.
7. RELIGIOUS - Tithing, church donations
8. ANONYMOUS - Dark channels, undisclosed

For each category, we use an LLM agent to search the web and extract giving data.
This avoids hardcoding and uses fuzzy matching via natural language.
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime

# Categories to research
GIVING_CATEGORIES = [
    "FOUNDATIONS",
    "DAFS",
    "DIRECT_GIFTS",
    "SECURITIES",
    "SPLIT_INTEREST",
    "PHILANTHROPIC_LLCS",
    "RELIGIOUS",
    "ANONYMOUS",
]


@dataclass
class GivingFinding:
    """A single found instance of charitable giving."""
    amount: float
    recipient: str
    year: str
    category: str
    source_url: str
    description: str
    confidence: str  # HIGH, MEDIUM, LOW


@dataclass
class BillionaireGiving:
    """Complete giving profile for one billionaire."""
    name: str
    net_worth_billions: float
    country: str

    # Category-by-category results
    foundations_total: float
    foundations_findings: List[dict]

    dafs_total: float
    dafs_findings: List[dict]

    direct_gifts_total: float
    direct_gifts_findings: List[dict]

    securities_total: float
    securities_findings: List[dict]

    split_interest_total: float
    split_interest_findings: List[dict]

    llcs_total: float
    llcs_findings: List[dict]

    religious_total: float
    religious_findings: List[dict]

    anonymous_total: float
    anonymous_findings: List[dict]

    # Aggregates
    total_observable: float  # High/medium confidence
    total_estimated: float   # Including low confidence
    total_after_dedup: float
    duplicates_removed: float

    # Score
    scrooge_score: float
    giving_rate: float
    confidence: str

    # Metadata
    research_date: str
    sources_used: List[str]


def research_category_with_agent(name: str, category: str) -> Dict:
    """
    Use Claude as a subagent to research giving in a specific category.

    This is the key function - instead of hardcoded lookups, we ask Claude
    to search the web and extract structured data.

    Returns a dict with findings, total, and confidence.
    """
    # This would be called via subprocess to claude-code or via API
    # For now, we define the interface

    # The actual implementation will use:
    # - Brave Search API via MCP
    # - WebFetch to read source pages
    # - Structured output extraction

    return {
        "category": category,
        "findings": [],
        "total": 0.0,
        "confidence": "LOW",
        "sources": [],
        "notes": "Not yet implemented"
    }


def check_for_duplicates(findings: List[GivingFinding]) -> tuple[List[GivingFinding], float]:
    """
    Identify and remove duplicate gifts that appear in multiple categories.

    Returns: (deduplicated_findings, amount_removed)
    """
    # Group by recipient + approximate year + approximate amount
    seen = {}
    deduped = []
    removed_total = 0.0

    for f in findings:
        # Key: recipient (normalized) + year + amount bucket
        key = (
            f.recipient.lower().strip()[:30],
            f.year[:4] if f.year else "unknown",
            round(f.amount / 1_000_000)  # Round to nearest million
        )

        if key in seen:
            # Duplicate - keep the one with higher confidence
            existing = seen[key]
            conf_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
            if conf_order.get(f.confidence, 0) > conf_order.get(existing.confidence, 0):
                removed_total += existing.amount
                seen[key] = f
            else:
                removed_total += f.amount
        else:
            seen[key] = f

    return list(seen.values()), removed_total


def calculate_scrooge_score(
    net_worth_billions: float,
    total_giving: float,
    liquidity_pct: float = 0.3,
    years_as_billionaire: int = 10,
) -> float:
    """
    Calculate Scrooge Score (0-100).

    Higher = more Scrooge-like (less giving relative to capacity).

    Based on: 10% of liquid wealth over 10 years is the benchmark.
    """
    if net_worth_billions <= 0:
        return 50.0

    liquid_wealth = net_worth_billions * 1e9 * liquidity_pct
    expected_giving = liquid_wealth * 0.10  # 10% benchmark

    if expected_giving <= 0:
        return 50.0

    giving_ratio = total_giving / expected_giving

    # Score: 100 if 0% of expected, 0 if 100%+ of expected
    base_score = max(0, min(100, (1 - giving_ratio) * 100))

    # Tenure adjustment: longer billionaire = higher expectation
    if years_as_billionaire > 10:
        tenure_penalty = min(10, (years_as_billionaire - 10) * 0.5)
        base_score = min(100, base_score + tenure_penalty)

    return round(base_score, 1)


def run_pipeline_for_billionaire(name: str, net_worth_billions: float, country: str) -> BillionaireGiving:
    """
    Run the full taxonomy-driven pipeline for one billionaire.

    This orchestrates research across all categories, deduplicates,
    and computes the final score.
    """
    all_findings = []
    category_results = {}

    # Research each category
    for category in GIVING_CATEGORIES:
        result = research_category_with_agent(name, category)
        category_results[category] = result

        # Convert findings to GivingFinding objects
        for f in result.get("findings", []):
            all_findings.append(GivingFinding(
                amount=f.get("amount", 0),
                recipient=f.get("recipient", "Unknown"),
                year=f.get("year", "Unknown"),
                category=category,
                source_url=f.get("source_url", ""),
                description=f.get("description", ""),
                confidence=f.get("confidence", "LOW"),
            ))

    # Deduplicate
    deduped_findings, removed = check_for_duplicates(all_findings)

    # Calculate totals by category
    cat_totals = {cat: 0.0 for cat in GIVING_CATEGORIES}
    for f in deduped_findings:
        cat_totals[f.category] += f.amount

    # Observable = HIGH + MEDIUM confidence
    observable = sum(f.amount for f in deduped_findings if f.confidence in ["HIGH", "MEDIUM"])
    estimated = sum(f.amount for f in deduped_findings)

    # Sources used
    sources = list(set(f.source_url for f in deduped_findings if f.source_url))

    # Scrooge score
    score = calculate_scrooge_score(
        net_worth_billions=net_worth_billions,
        total_giving=estimated,
    )

    return BillionaireGiving(
        name=name,
        net_worth_billions=net_worth_billions,
        country=country,
        foundations_total=cat_totals["FOUNDATIONS"],
        foundations_findings=[asdict(f) for f in deduped_findings if f.category == "FOUNDATIONS"],
        dafs_total=cat_totals["DAFS"],
        dafs_findings=[asdict(f) for f in deduped_findings if f.category == "DAFS"],
        direct_gifts_total=cat_totals["DIRECT_GIFTS"],
        direct_gifts_findings=[asdict(f) for f in deduped_findings if f.category == "DIRECT_GIFTS"],
        securities_total=cat_totals["SECURITIES"],
        securities_findings=[asdict(f) for f in deduped_findings if f.category == "SECURITIES"],
        split_interest_total=cat_totals["SPLIT_INTEREST"],
        split_interest_findings=[asdict(f) for f in deduped_findings if f.category == "SPLIT_INTEREST"],
        llcs_total=cat_totals["PHILANTHROPIC_LLCS"],
        llcs_findings=[asdict(f) for f in deduped_findings if f.category == "PHILANTHROPIC_LLCS"],
        religious_total=cat_totals["RELIGIOUS"],
        religious_findings=[asdict(f) for f in deduped_findings if f.category == "RELIGIOUS"],
        anonymous_total=cat_totals["ANONYMOUS"],
        anonymous_findings=[asdict(f) for f in deduped_findings if f.category == "ANONYMOUS"],
        total_observable=observable,
        total_estimated=estimated,
        total_after_dedup=estimated,
        duplicates_removed=removed,
        scrooge_score=score,
        giving_rate=estimated / (net_worth_billions * 1e9) if net_worth_billions > 0 else 0,
        confidence="LOW",  # Will be updated based on actual data quality
        research_date=datetime.now().isoformat(),
        sources_used=sources,
    )


if __name__ == "__main__":
    # Test with a single billionaire
    result = run_pipeline_for_billionaire(
        name="Larry Ellison",
        net_worth_billions=245.0,
        country="United States"
    )
    print(json.dumps(asdict(result), indent=2, default=str))
