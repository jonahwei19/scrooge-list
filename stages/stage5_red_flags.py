"""
Stage 5: Red Flag Scoring

STATUS: Implemented

Calculates red flags based on foundation data, DAF usage, split-interest
trusts, and overall giving patterns.

Red Flag Categories:
1. LOW_PAYOUT: Foundation payout <5% (legal minimum)
2. DAF_TRANSFERS: >50% of grants go to DAFs (opacity)
3. HIGH_COMP: Officer compensation >10% of grants
4. NO_OBSERVABLE_GIVING: $10B+ net worth, <$100M observable
5. PLEDGE_UNFULFILLED: Signed Giving Pledge but hasn't fulfilled
6. DAF_OPACITY: High DAF usage with unknown account balances
7. CLAT_WEALTH_TRANSFER: Split-interest trusts primarily for heirs
8. FOUNDATION_RECYCLING: CLATs pay to grantor's own foundation
"""

from typing import List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from stages.stage7_daf import DAFEstimate
    from stages.stage8_split_interest import SplitInterestEstimate


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

    # New fields for DAF and split-interest trust data
    daf_estimate: Optional["DAFEstimate"] = None
    split_interest_estimate: Optional["SplitInterestEstimate"] = None


def calculate_red_flags(record: BillionaireRecord) -> List[str]:
    """
    Identify concerning patterns in giving data.

    Red Flags:
    - LOW_PAYOUT: Foundation payout <5% (legal minimum)
    - DAF_TRANSFERS: >50% of grants go to DAFs (opacity)
    - HIGH_COMP: Officer compensation >10% of grants
    - NO_OBSERVABLE_GIVING: $10B+ net worth, <$100M observable
    - PLEDGE_UNFULFILLED: Signed Giving Pledge but hasn't fulfilled
    - DAF_OPACITY: High DAF opacity score (unknown account balances)
    - CLAT_WEALTH_TRANSFER: Split-interest trusts primarily benefit heirs
    - LOW_CHARITABLE_RATE: CLAT pays <3% to charity annually
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

    # Flag 6: DAF opacity (from stage 7)
    if record.daf_estimate is not None:
        daf = record.daf_estimate
        # High DAF percentage of grants
        if daf.daf_pct_of_grants > 0.5:
            flags.append(f"DAF_OPACITY: {daf.daf_pct_of_grants:.0%} of grants go to DAFs")

        # Known personal DAFs with unknown balances
        if daf.known_personal_daf_details:
            unknown_count = sum(1 for d in daf.known_personal_daf_details if d.get("estimated_value", 0) == 0)
            if unknown_count > 0:
                flags.append(f"DAF_UNKNOWN_ACCOUNTS: {unknown_count} DAF account(s) with unknown balances")

        # Large foundation->DAF transfers
        if daf.foundation_to_daf_total > 50_000_000:  # >$50M to DAFs
            flags.append(f"DAF_WAREHOUSING: ${daf.foundation_to_daf_total/1e6:.0f}M transferred to DAFs")

    # Flag 7 & 8: Split-interest trust patterns (from stage 8)
    if record.split_interest_estimate is not None:
        sit = record.split_interest_estimate

        # CLAT primarily for wealth transfer
        if sit.is_wealth_transfer_pattern:
            flags.append(f"CLAT_WEALTH_TRANSFER: ${sit.clat_wealth_transfer_estimated/1e6:.0f}M going to heirs via CLATs")

        # Check individual trusts for concerning patterns
        for trust in sit.known_trusts:
            if trust.estimated_assets > 0:
                charitable_rate = trust.annual_charitable_payment / trust.estimated_assets
                if charitable_rate < 0.03:
                    flags.append(f"LOW_CHARITABLE_RATE: {trust.trust_name} pays only {charitable_rate:.1%} annually")

                # Foundation recycling: CLAT pays to grantor's own foundation
                grantor_last_name = trust.grantor_name.split()[-1].lower()
                for beneficiary in trust.charitable_beneficiaries:
                    if grantor_last_name in beneficiary.lower():
                        flags.append(f"FOUNDATION_RECYCLING: {trust.trust_name} pays to own foundation")
                        break

    return flags


def calculate_opacity_score(record: BillionaireRecord) -> float:
    """
    Calculate an overall opacity score (0-1) for a billionaire.

    Higher score = more opacity/less transparency in giving:
    - DAF usage without disclosure
    - CLAT wealth transfer structures
    - Low observable giving relative to net worth
    - Foundation near minimum payout

    Returns:
        Float 0-1 where 1 is maximum opacity
    """
    score = 0.0

    # Factor 1: Low observable giving ratio
    net_worth = record.net_worth_billions * 1e9
    if net_worth > 0:
        observable = record.total_foundation_assets + record.announced_gifts_total
        observable_ratio = observable / net_worth
        if observable_ratio < 0.01:  # <1% observable
            score += 0.3
        elif observable_ratio < 0.05:  # <5% observable
            score += 0.15

    # Factor 2: DAF opacity
    if record.daf_estimate is not None:
        if record.daf_estimate.daf_pct_of_grants > 0.5:
            score += 0.25
        elif record.daf_estimate.daf_pct_of_grants > 0.25:
            score += 0.1

    # Factor 3: CLAT wealth transfer
    if record.split_interest_estimate is not None:
        if record.split_interest_estimate.is_wealth_transfer_pattern:
            score += 0.2

    # Factor 4: Foundation at minimum payout
    for f in record.foundations:
        if hasattr(f, 'payout_rate') and hasattr(f, 'total_assets'):
            if 0.04 <= f.payout_rate <= 0.055 and f.total_assets > 100_000_000:
                score += 0.1
                break  # Only count once

    # Factor 5: Unfulfilled pledge
    if record.giving_pledge_signed and not record.giving_pledge_fulfilled:
        score += 0.15

    return min(score, 1.0)


if __name__ == "__main__":
    # Test with mock data
    from stages.stage2_foundations import Foundation

    print("=" * 70)
    print("RED FLAG SCORING TEST")
    print("=" * 70)

    # Test case 1: Basic red flags
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
    print("\nTest Billionaire (basic):")
    print("Red flags:")
    for f in flags:
        print(f"  - {f}")
    print(f"Opacity score: {calculate_opacity_score(test_record):.2f}")

    # Test case 2: With DAF data
    print("\n" + "=" * 70)
    print("Test with DAF estimate:")

    # Import DAF estimate (mock for testing)
    from dataclasses import dataclass as dc

    @dc
    class MockDAFEstimate:
        foundation_to_daf_total: float = 100_000_000
        foundation_to_daf_count: int = 5
        foundation_to_daf_details: list = None
        daf_pct_of_grants: float = 0.67
        known_personal_daf_total: float = 0
        known_personal_daf_details: list = None
        estimated_daf_low: float = 0
        estimated_daf_high: float = 0
        confidence: str = "MEDIUM"
        estimation_method: str = "test"
        status: str = "test"

        def __post_init__(self):
            if self.foundation_to_daf_details is None:
                self.foundation_to_daf_details = []
            if self.known_personal_daf_details is None:
                self.known_personal_daf_details = [{"estimated_value": 0}]

    test_record_2 = BillionaireRecord(
        name="DAF User",
        net_worth_billions=100,
        foundations=[
            Foundation(
                ein="456",
                name="DAF Heavy Foundation",
                total_assets=5_000_000_000,
                grants_paid_latest=250_000_000,
                payout_rate=0.05,
                years_of_data=10,
                daf_grants_pct=0.67,
            )
        ],
        giving_pledge_signed=False,
    )
    test_record_2.total_foundation_assets = 5_000_000_000
    test_record_2.daf_estimate = MockDAFEstimate()

    flags2 = calculate_red_flags(test_record_2)
    print("Red flags:")
    for f in flags2:
        print(f"  - {f}")
    print(f"Opacity score: {calculate_opacity_score(test_record_2):.2f}")
