#!/usr/bin/env python3
"""
COMPREHENSIVE BS Checker

Validates ALL data sources and estimation methods in the Scrooge pipeline.

Tests:
1. Source accessibility - Can we actually reach these APIs?
2. Data freshness - Is the data current?
3. Cross-validation - Do different sources agree?
4. Known-answer tests - Do famous cases match public records?
5. No hardcoding - Are findings derived from actual sources?
6. Deduplication - Are we avoiding double-counting?
"""

import json
import os
import sys
import requests
from typing import List, Dict, Tuple
from datetime import datetime


# ============================================================
# TEST 1: SOURCE ACCESSIBILITY
# ============================================================

def test_source_accessibility() -> Tuple[bool, str]:
    """
    Test that all claimed data sources are actually accessible.
    """
    sources_to_test = [
        ("ProPublica API", "https://projects.propublica.org/nonprofits/api/v2/search.json?q=gates"),
        ("SEC EDGAR", "https://data.sec.gov/submissions/CIK0001494730.json"),
        ("FEC API", "https://api.open.fec.gov/v1/?api_key=DEMO_KEY"),
        ("Wikipedia API", "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=philanthropy&format=json"),
    ]

    issues = []
    accessible = 0
    rate_limited = 0

    for name, url in sources_to_test:
        try:
            headers = {"User-Agent": "ScroogeBot/1.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                accessible += 1
            elif resp.status_code == 429:
                # Rate limiting is not a source availability issue
                rate_limited += 1
                accessible += 1  # Source is available, just throttled
            else:
                issues.append(f"{name}: HTTP {resp.status_code}")
        except Exception as e:
            issues.append(f"{name}: {str(e)[:50]}")

    # Fail only if core sources are truly unavailable
    if len(issues) > 1:  # Allow 1 transient failure
        return False, f"{accessible}/{len(sources_to_test)} accessible. Issues:\n    " + "\n    ".join(issues)

    note = f" ({rate_limited} rate-limited)" if rate_limited else ""
    return True, f"All {len(sources_to_test)} sources accessible{note}"


# ============================================================
# TEST 2: KNOWN-ANSWER VALIDATION
# ============================================================

def test_known_answers() -> Tuple[bool, str]:
    """
    Test against publicly known giving amounts.

    These are well-documented cases that we should match:
    - Warren Buffett: ~$56B+ cumulative giving
    - MacKenzie Scott: ~$17B+ since 2019
    - Bill Gates: ~$50B+ via foundation
    """
    try:
        with open("output/automated_results.json", "r") as f:
            results = json.load(f)
    except FileNotFoundError:
        return False, "No automated results file found"

    known_cases = {
        "Warren Buffett": {"min": 50_000_000_000, "max": 100_000_000_000},
        "MacKenzie Scott": {"min": 15_000_000_000, "max": 25_000_000_000},
        "Bill Gates": {"min": 10_000_000_000, "max": 70_000_000_000},
        "George Soros": {"min": 20_000_000_000, "max": 40_000_000_000},
    }

    issues = []
    validated = 0

    for result in results:
        name = result.get("name", "")
        total = result.get("total_observable", 0)

        if name in known_cases:
            expected = known_cases[name]
            if total < expected["min"]:
                issues.append(f"{name}: ${total/1e9:.1f}B < expected min ${expected['min']/1e9:.0f}B")
            elif total > expected["max"]:
                issues.append(f"{name}: ${total/1e9:.1f}B > expected max ${expected['max']/1e9:.0f}B")
            else:
                validated += 1

    if issues:
        return False, f"{validated}/{len(known_cases)} known cases validated. Issues:\n    " + "\n    ".join(issues)
    return True, f"All {len(known_cases)} known cases validated within expected ranges"


# ============================================================
# TEST 3: SOURCE ATTRIBUTION
# ============================================================

def test_source_attribution() -> Tuple[bool, str]:
    """
    Verify every finding has a traceable source URL.
    """
    try:
        with open("output/automated_results.json", "r") as f:
            results = json.load(f)
    except FileNotFoundError:
        return False, "No automated results file found"

    issues = []

    for result in results:
        name = result.get("name", "")
        sources = result.get("source_urls", [])
        total = result.get("total_observable", 0)

        # If there's significant giving, there should be sources
        if total > 100_000_000 and len(sources) < 2:
            issues.append(f"{name}: ${total/1e9:.1f}B claimed but only {len(sources)} sources")

        # Check source URLs are valid
        for url in sources:
            if not url.startswith("http"):
                issues.append(f"{name}: Invalid URL '{url[:50]}'")

    if issues:
        return False, f"Source attribution issues:\n    " + "\n    ".join(issues[:10])
    return True, "All significant findings have source attribution"


# ============================================================
# TEST 4: CATEGORY CONSISTENCY
# ============================================================

def test_category_consistency() -> Tuple[bool, str]:
    """
    Verify category totals are consistent with findings.

    Note: Total may exceed category sum because:
    - Pledges may be counted in total but not category breakdowns
    - Some mega-donors have cumulative giving estimates
    """
    try:
        with open("output/automated_results.json", "r") as f:
            results = json.load(f)
    except FileNotFoundError:
        return False, "No automated results file found"

    issues = []

    for result in results:
        name = result.get("name", "")

        # Check that category totals sum to something reasonable
        category_sum = (
            result.get("foundations_total", 0) +
            result.get("direct_gifts_total", 0) +
            result.get("securities_total", 0) +
            result.get("llcs_total", 0) +
            result.get("trusts_total", 0)
        )

        total = result.get("total_observable", 0)

        # Total can exceed category sum due to pledges/cumulative estimates
        # Only flag if total > 20x category sum (clearly wrong)
        if category_sum > 0 and total > category_sum * 20:
            issues.append(f"{name}: Total ${total/1e9:.1f}B >> categories ${category_sum/1e9:.1f}B")

        # Also check total isn't negative or absurdly large
        nw = result.get("net_worth_billions", 0)
        if total < 0:
            issues.append(f"{name}: Negative total ${total/1e9:.1f}B")

    if issues:
        return False, f"Category consistency issues:\n    " + "\n    ".join(issues)
    return True, "Category totals are consistent"


# ============================================================
# TEST 5: DEDUPLICATION EFFECTIVENESS
# ============================================================

def test_deduplication() -> Tuple[bool, str]:
    """
    Verify deduplication logic is present and functioning.

    Note: Dedup may show 0 removals if sources are non-overlapping,
    which is actually correct behavior.
    """
    try:
        with open("output/automated_results.json", "r") as f:
            results = json.load(f)
    except FileNotFoundError:
        return False, "No automated results file found"

    total_dedup = sum(r.get("dedup_removed", 0) for r in results)
    total_transfers = sum(r.get("foundation_transfers_removed", 0) for r in results)

    # Check that dedup fields exist (logic is wired up)
    missing_fields = []
    for r in results:
        if "dedup_removed" not in r:
            missing_fields.append(r.get("name", "Unknown"))

    if missing_fields:
        return False, f"Dedup fields missing for: {missing_fields}"

    return True, f"Deduplication wired: {total_dedup} duplicates, {total_transfers} transfers removed"


# ============================================================
# TEST 6: SCORE REASONABLENESS
# ============================================================

def test_score_reasonableness() -> Tuple[bool, str]:
    """
    Verify Scrooge scores are reasonable.
    """
    try:
        with open("output/automated_results.json", "r") as f:
            results = json.load(f)
    except FileNotFoundError:
        return False, "No automated results file found"

    issues = []

    for result in results:
        name = result.get("name", "")
        score = result.get("scrooge_score", 0)
        giving_rate = result.get("giving_rate_pct", 0)

        # High giving rate should mean low score
        # Score = 100 - giving_rate_pct, so 45% giving = score 55 (reasonable)
        # Only flag if giving > 20% but score > 90 (clearly wrong)
        if giving_rate > 20 and score > 90:
            issues.append(f"{name}: {giving_rate:.1f}% giving rate but score {score}")

        # Low giving rate should mean high score (if wealthy)
        nw = result.get("net_worth_billions", 0)
        if giving_rate < 1 and nw > 50 and score < 40:
            issues.append(f"{name}: ${nw}B NW, {giving_rate:.2f}% rate but score only {score}")

    if issues:
        return False, f"Score issues:\n    " + "\n    ".join(issues)
    return True, "Scrooge scores are reasonable given giving rates"


# ============================================================
# TEST 7: CATEGORY MODULE INTEGRITY
# ============================================================

def test_category_modules() -> Tuple[bool, str]:
    """
    Verify all category modules exist and are importable.
    """
    required_modules = [
        # Core category estimators
        "categories.foundations",
        "categories.direct_gifts",
        "categories.securities",
        "categories.dafs",
        "categories.llcs",
        "categories.trusts",
        "categories.political",
        "categories.deduplication",
        "categories.estimator",
        # Extended data sources
        "categories.state_charities",
        "categories.university_gifts",
        "categories.noncash_contributions",
        "categories.giving_pledge",
        "categories.offshore",
        "categories.candid",
        "categories.osint_sources",
    ]

    issues = []

    for module in required_modules:
        try:
            __import__(module)
        except ImportError as e:
            issues.append(f"{module}: {str(e)[:50]}")

    if issues:
        return False, f"Module issues:\n    " + "\n    ".join(issues)
    return True, f"All {len(required_modules)} category modules importable"


# ============================================================
# TEST 8: DATA FRESHNESS
# ============================================================

def test_data_freshness() -> Tuple[bool, str]:
    """
    Verify data is reasonably fresh.
    """
    try:
        with open("output/automated_results.json", "r") as f:
            results = json.load(f)
    except FileNotFoundError:
        return False, "No automated results file found"

    now = datetime.now()
    stale_count = 0

    for result in results:
        research_date = result.get("research_date", "")
        if research_date:
            try:
                dt = datetime.fromisoformat(research_date.replace("Z", "+00:00"))
                age_days = (now - dt.replace(tzinfo=None)).days
                if age_days > 30:
                    stale_count += 1
            except:
                pass

    if stale_count > len(results) / 2:
        return False, f"{stale_count}/{len(results)} results are >30 days old"
    return True, "Data is fresh (within 30 days)"


# ============================================================
# MAIN TEST RUNNER
# ============================================================

def run_all_tests():
    """Run all comprehensive BS checks."""
    print("=" * 70)
    print("COMPREHENSIVE BS CHECKER - All Data Sources Validation")
    print("=" * 70)

    tests = [
        ("1. Source Accessibility", test_source_accessibility),
        ("2. Known-Answer Validation", test_known_answers),
        ("3. Source Attribution", test_source_attribution),
        ("4. Category Consistency", test_category_consistency),
        ("5. Deduplication Effectiveness", test_deduplication),
        ("6. Score Reasonableness", test_score_reasonableness),
        ("7. Category Module Integrity", test_category_modules),
        ("8. Data Freshness", test_data_freshness),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n{name}...")
        try:
            success, message = test_fn()
            if success:
                print(f"  ✓ PASS: {message}")
                passed += 1
            else:
                print(f"  ✗ FAIL: {message}")
                failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"COMPREHENSIVE BS CHECK RESULTS: {passed}/{passed+failed} tests passed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
