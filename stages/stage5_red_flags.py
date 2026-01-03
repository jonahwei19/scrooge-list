"""
Stage 5: Red Flag Scoring

STATUS: ✅ Implemented

Calculates red flags based on foundation data and giving patterns.
"""

from typing import List
from dataclasses import dataclass


@dataclass
class BillionaireRecord:
    """Accumulated data for a billionaire."""
    name: str
    net_worth_billions: float
    foundations: list
    total_foundation_assets: float = 0
    annual_foundation_grants: float = 0
    announced_gifts_total: float = 0
    sec_form4_gifts: float = 0
    giving_pledge_signed: bool = False
    giving_pledge_fulfilled: bool = False


def calculate_red_flags(record: BillionaireRecord) -> List[str]:
    """
    Identify concerning patterns in giving data.

    Red Flags:
    - LOW_PAYOUT: Foundation payout <5% (legal minimum)
    - DAF_TRANSFERS: >50% of grants go to DAFs (opacity)
    - HIGH_COMP: Officer compensation >10% of grants
    - NO_OBSERVABLE_GIVING: $10B+ net worth, <$100M observable
    - PLEDGE_UNFULFILLED: Signed Giving Pledge but hasn't fulfilled
    """
    flags = []

    # Flag 1: Foundation payout below 5% minimum
    for f in record.foundations:
        if hasattr(f, 'payout_rate') and hasattr(f, 'total_assets'):
            if f.payout_rate < 0.05 and f.total_assets > 10_000_000:
                flags.append(f"LOW_PAYOUT: {f.name} at {f.payout_rate:.1%}")

    # Flag 2: High foundation→DAF transfers
    for f in record.foundations:
        if hasattr(f, 'daf_grants_pct') and f.daf_grants_pct > 0.5:
            flags.append(f"DAF_TRANSFERS: {f.name} sends {f.daf_grants_pct:.0%} to DAFs")

    # Flag 3: High officer compensation relative to grants
    for f in record.foundations:
        if hasattr(f, 'officer_compensation') and hasattr(f, 'grants_paid_latest'):
            if f.officer_compensation > 0 and f.grants_paid_latest > 0:
                comp_ratio = f.officer_compensation / f.grants_paid_latest
                if comp_ratio > 0.1:
                    flags.append(f"HIGH_COMP: {f.name} officer comp is {comp_ratio:.0%} of grants")

    # Flag 4: No observable giving despite high net worth
    if record.net_worth_billions >= 10:
        total_observable = record.total_foundation_assets + record.announced_gifts_total
        if total_observable < 100_000_000:
            flags.append(f"NO_OBSERVABLE_GIVING: ${record.net_worth_billions:.0f}B net worth, <$100M observable")

    # Flag 5: Giving Pledge signed but not fulfilled
    if record.giving_pledge_signed and not record.giving_pledge_fulfilled:
        flags.append("PLEDGE_UNFULFILLED")

    return flags


if __name__ == "__main__":
    # Test with mock data
    from stages.stage2_foundations import Foundation

    test_record = BillionaireRecord(
        name="Test Billionaire",
        net_worth_billions=50,
        foundations=[
            Foundation(
                ein="123",
                name="Test Foundation",
                total_assets=100_000_000,
                grants_paid_latest=2_000_000,
                payout_rate=0.02,
                years_of_data=5,
            )
        ],
        giving_pledge_signed=True,
    )
    test_record.total_foundation_assets = 100_000_000

    flags = calculate_red_flags(test_record)
    print("Red flags:")
    for f in flags:
        print(f"  - {f}")
