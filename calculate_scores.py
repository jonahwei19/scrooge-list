#!/usr/bin/env python3
"""
Calculate Scrooge Scores for all billionaires using v3 methodology.

Formula: Scrooge Score = 100 × (1 - Giving Ratio)
Where: Giving Ratio = Total Lifetime Giving / (Net Worth × Liquidity Adjustment)
Capped at 0-100
"""

import json
from datetime import datetime

def calculate_scrooge_score(net_worth_billions, total_giving_millions, liquidity_factor):
    """
    Calculate Scrooge Score (0-100).
    Higher = less giving relative to capacity.
    """
    if net_worth_billions <= 0:
        return None  # Skip deceased or invalid

    # Convert to same units (millions)
    net_worth_millions = net_worth_billions * 1000

    # Liquid wealth available for giving
    liquid_wealth = net_worth_millions * liquidity_factor

    if liquid_wealth <= 0:
        return 50.0

    # Giving ratio
    giving_ratio = total_giving_millions / liquid_wealth

    # Score: 100 if 0% giving, 0 if 100%+ giving
    score = max(0, min(100, (1 - giving_ratio) * 100))

    return round(score, 2)


def main():
    # Load data
    with open('/tmp/scrooge-list/scrooge_data_v3.json', 'r') as f:
        data = json.load(f)

    # Calculate scores for each entry
    results = []
    for entry in data:
        net_worth = entry.get('net_worth_billions', 0)
        giving = entry.get('total_lifetime_giving_millions', 0)
        liquidity = entry.get('liquidity_factor', 0.3)

        score = calculate_scrooge_score(net_worth, giving, liquidity)

        # Calculate giving rate
        if net_worth > 0:
            giving_rate = giving / (net_worth * 1000) * 100
        else:
            giving_rate = None

        result = {
            'rank': entry.get('rank'),
            'name': entry.get('name'),
            'country': entry.get('country'),
            'net_worth_billions': net_worth,
            'total_giving_millions': giving,
            'liquidity_factor': liquidity,
            'scrooge_score': score,
            'giving_rate_pct': round(giving_rate, 3) if giving_rate else None,
            'giving_pledge_signed': entry.get('giving_pledge_signed', False),
            'source_of_wealth': entry.get('source_of_wealth'),
            'notes': entry.get('notes'),
        }
        results.append(result)

    # Filter out deceased (net_worth = 0)
    living = [r for r in results if r['net_worth_billions'] > 0 and r['scrooge_score'] is not None]
    deceased = [r for r in results if r['net_worth_billions'] <= 0]

    # Sort by scrooge score (highest first = worst philanthropists)
    living_sorted = sorted(living, key=lambda x: x['scrooge_score'], reverse=True)

    # Add rankings
    for i, r in enumerate(living_sorted):
        r['scrooge_rank'] = i + 1

    # Create output
    output = {
        'metadata': {
            'generated': datetime.now().isoformat(),
            'methodology': 'v3 - Pure giving ratio (no red flags, no pledge penalties)',
            'formula': 'Scrooge Score = 100 × (1 - Giving Ratio)',
            'giving_ratio_formula': 'Giving Ratio = Total Lifetime Giving / (Net Worth × Liquidity Factor)',
            'total_billionaires': len(living_sorted),
            'deceased_excluded': len(deceased),
        },
        'rankings': living_sorted,
        'deceased': deceased,
    }

    # Save output
    with open('/tmp/scrooge-list/scrooge_scores_v3.json', 'w') as f:
        json.dump(output, f, indent=2)

    # Print top 20 scrooges (worst philanthropists)
    print("\n🎄 TOP 20 SCROOGES (Least Generous Relative to Wealth) 🎄\n")
    print(f"{'Rank':<5} {'Name':<30} {'Net Worth':<12} {'Giving':<12} {'Score':<8} {'Pledge'}")
    print("-" * 85)

    for r in living_sorted[:20]:
        pledge = "✓" if r['giving_pledge_signed'] else ""
        print(f"{r['scrooge_rank']:<5} {r['name']:<30} ${r['net_worth_billions']:<10.1f}B ${r['total_giving_millions']:<10.0f}M {r['scrooge_score']:<8.2f} {pledge}")

    # Print top 20 saints (most generous)
    print("\n\n🎁 TOP 20 SAINTS (Most Generous Relative to Wealth) 🎁\n")
    print(f"{'Rank':<5} {'Name':<30} {'Net Worth':<12} {'Giving':<12} {'Score':<8} {'Pledge'}")
    print("-" * 85)

    saints = living_sorted[-20:][::-1]
    for r in saints:
        pledge = "✓" if r['giving_pledge_signed'] else ""
        print(f"{r['scrooge_rank']:<5} {r['name']:<30} ${r['net_worth_billions']:<10.1f}B ${r['total_giving_millions']:<10.0f}M {r['scrooge_score']:<8.2f} {pledge}")

    # Summary stats
    print("\n\n📊 SUMMARY STATISTICS 📊\n")
    scores = [r['scrooge_score'] for r in living_sorted]
    avg_score = sum(scores) / len(scores)
    median_score = sorted(scores)[len(scores)//2]

    pledge_signers = [r for r in living_sorted if r['giving_pledge_signed']]
    non_signers = [r for r in living_sorted if not r['giving_pledge_signed']]

    print(f"Average Scrooge Score: {avg_score:.2f}")
    print(f"Median Scrooge Score: {median_score:.2f}")
    print(f"Giving Pledge Signers: {len(pledge_signers)} ({len(pledge_signers)/len(living_sorted)*100:.1f}%)")

    if pledge_signers:
        avg_signer = sum(r['scrooge_score'] for r in pledge_signers) / len(pledge_signers)
        avg_non_signer = sum(r['scrooge_score'] for r in non_signers) / len(non_signers)
        print(f"  - Signers avg score: {avg_signer:.2f}")
        print(f"  - Non-signers avg score: {avg_non_signer:.2f}")

    print(f"\nTotal wealth represented: ${sum(r['net_worth_billions'] for r in living_sorted):.1f}B")
    print(f"Total giving represented: ${sum(r['total_giving_millions'] for r in living_sorted)/1000:.1f}B")

    print(f"\n✅ Saved to /tmp/scrooge-list/scrooge_scores_v3.json")


if __name__ == '__main__':
    main()
