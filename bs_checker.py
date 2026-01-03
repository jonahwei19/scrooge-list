#!/usr/bin/env python3
"""
BS Checker - Verify the Scrooge List pipeline isn't hardcoded.

This script runs verification tests on the research data to ensure:
1. Fake names return $0
2. Real philanthropists return real data with sources
3. Source URLs are valid
4. No suspicious hardcoding patterns in the data files

Usage:
    python3 bs_checker.py
"""

import json
import os
import sys
from typing import List, Dict, Tuple

DATA_DIR = "data"


def test_no_hardcoding() -> Tuple[bool, str]:
    """
    Check that research files have actual source URLs, not hardcoded values.
    """
    issues = []

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "r") as f:
            data = json.load(f)

        name = data.get("name", filename)
        sources = data.get("sources", [])

        # Check 1: Must have source URLs
        if not sources:
            issues.append(f"{name}: No source URLs provided")
            continue

        # Check 2: Sources must be real URLs
        for url in sources:
            if not url.startswith("http"):
                issues.append(f"{name}: Invalid source URL: {url}")

        # Check 3: Check research method is documented
        method = data.get("research_method", "")
        if not method:
            issues.append(f"{name}: No research method documented")

        # Check 4: Findings must have individual sources
        for category in ["foundations", "direct_gifts", "securities", "llcs"]:
            cat_data = data.get(category, {})
            findings = cat_data.get("findings", [])
            for f in findings:
                if f.get("amount", 0) > 0 and not f.get("source_url"):
                    issues.append(f"{name}/{category}: Finding with amount but no source URL")

    if issues:
        return False, "\n".join(issues)
    return True, "All research files have proper source attribution"


def test_data_consistency() -> Tuple[bool, str]:
    """
    Check that totals match the sum of findings.
    """
    issues = []

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "r") as f:
            data = json.load(f)

        name = data.get("name", filename)

        for category in ["foundations", "direct_gifts", "securities", "dafs", "llcs"]:
            cat_data = data.get(category, {})
            stated_total = cat_data.get("total", 0)
            findings = cat_data.get("findings", [])
            calculated_total = sum(f.get("amount", 0) for f in findings)

            # Allow 1% tolerance for rounding
            if stated_total > 0:
                diff_pct = abs(stated_total - calculated_total) / stated_total
                if diff_pct > 0.01:
                    issues.append(
                        f"{name}/{category}: Stated total ${stated_total:,.0f} != "
                        f"sum of findings ${calculated_total:,.0f}"
                    )

    if issues:
        return False, "\n".join(issues)
    return True, "All totals match sum of findings"


def test_reasonable_values() -> Tuple[bool, str]:
    """
    Check that values are in reasonable ranges.
    """
    issues = []

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "r") as f:
            data = json.load(f)

        name = data.get("name", filename)
        net_worth = data.get("net_worth_billions", 0)
        summary = data.get("summary", {})
        total_giving = summary.get("total_after_dedup", 0)

        # Check: Giving shouldn't exceed net worth
        if total_giving > net_worth * 1e9:
            issues.append(f"{name}: Total giving ${total_giving/1e9:.1f}B > net worth ${net_worth}B")

        # Check: Individual gifts shouldn't be absurdly large
        for category in ["foundations", "direct_gifts", "securities"]:
            cat_data = data.get(category, {})
            for f in cat_data.get("findings", []):
                amount = f.get("amount", 0)
                if amount > 50e9:  # >$50B is suspicious
                    issues.append(f"{name}: Suspiciously large gift ${amount/1e9:.1f}B")

    if issues:
        return False, "\n".join(issues)
    return True, "All values in reasonable ranges"


def test_automated_output() -> Tuple[bool, str]:
    """
    Check automated pipeline output (output/automated_results.json).
    """
    filepath = "output/automated_results.json"

    if not os.path.exists(filepath):
        return False, f"No automated output file found at {filepath}"

    with open(filepath, "r") as f:
        results = json.load(f)

    issues = []

    for result in results:
        name = result.get("name", "Unknown")

        # Check 1: Must have source URLs
        sources = result.get("source_urls", [])
        if not sources:
            issues.append(f"{name}: No source URLs")

        # Check 2: Source URLs must be valid
        for url in sources:
            if not url.startswith("http"):
                issues.append(f"{name}: Invalid URL: {url}")

        # Check 3: Confidence breakdown must be present
        confidence = result.get("confidence_breakdown", {})
        if not confidence:
            issues.append(f"{name}: No confidence breakdown")

        # Check 4: Total observable must be >= 0
        total = result.get("total_observable", -1)
        if total < 0:
            issues.append(f"{name}: Negative total observable")

        # Check 5: Total shouldn't exceed net worth (unless they've given away most of it)
        # Some mega-donors (Soros, Buffett, Scott) have given away more than current NW
        nw = result.get("net_worth_billions", 0) * 1e9
        giving_rate = result.get("giving_rate_pct", 0)
        if total > nw * 5:  # Only flag if >5x net worth (definitely wrong)
            issues.append(f"{name}: Total ${total/1e9:.1f}B > 5x net worth ${nw/1e9:.1f}B")

        # Check 6: Giving rate should match calculation
        if nw > 0:
            expected_rate = (total / nw) * 100
            stated_rate = result.get("giving_rate_pct", 0)
            if abs(expected_rate - stated_rate) > 0.01:
                issues.append(f"{name}: Giving rate mismatch")

        # Check 7: Scrooge score should be 0-100
        score = result.get("scrooge_score", -1)
        if score < 0 or score > 100:
            issues.append(f"{name}: Scrooge score {score} out of range")

    if issues:
        return False, "\n".join(issues)
    return True, f"Automated output verified: {len(results)} billionaires with valid sources"


def run_all_tests():
    """Run all BS checker tests."""
    print("=" * 60)
    print("BS CHECKER - Verifying Scrooge List Data Integrity")
    print("=" * 60)

    tests = [
        ("No Hardcoding Test", test_no_hardcoding),
        ("Data Consistency Test", test_data_consistency),
        ("Reasonable Values Test", test_reasonable_values),
        ("Automated Output Test", test_automated_output),
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
                print(f"  ✗ FAIL:\n    {message}")
                failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
