"""
DEDUPLICATION Module

The same money can appear multiple times:
1. Stock transfer TO foundation (Form 4)
2. Foundation RECEIVES contribution (990-PF)
3. Foundation GRANTS to charity (990-PF Part XV)
4. Same grant announced in press release
5. Same grant counted as "direct gift"

Strategy:
1. Priority order: Foundation grants > Direct gifts > Securities > DAF
2. Recipient matching: Skip if gift goes to billionaire's own foundation
3. Amount bucketing: Group by (recipient, year, round(amount/1M))
4. Pledge vs disbursement: Track separately
"""

from typing import List, Dict, Tuple, Set
from dataclasses import dataclass
import re


@dataclass
class UnifiedGift:
    """A deduplicated gift record."""
    category: str  # FOUNDATIONS, DIRECT_GIFTS, SECURITIES, DAFS, LLCS
    recipient: str
    amount: float
    year: int
    is_pledge: bool
    source_url: str
    confidence: str


# Priority order for deduplication (higher = preferred)
CATEGORY_PRIORITY = {
    "FOUNDATIONS": 5,      # Most reliable - actual grants paid
    "PHILANTHROPIC_LLCS": 4,  # Self-reported but usually accurate
    "DIRECT_GIFTS": 3,     # News/press releases
    "SECURITIES": 2,       # Form 4 - may be to foundation (double count)
    "DAFS": 1,             # Usually estimates
}


def normalize_recipient(recipient: str) -> str:
    """
    Normalize recipient name for matching.
    Removes common suffixes, lowercases, strips whitespace.
    """
    if not recipient:
        return ""

    name = recipient.lower().strip()

    # Remove common suffixes and abbreviations
    suffixes = [
        "foundation", "fund", "trust", "inc", "incorporated",
        "llc", "corp", "corporation", "university", "univ", "college",
        "hospital", "medical center", "center", "institute",
        "childrens", "children's", "memorial",
    ]

    # Keep removing suffixes until none match
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if name.endswith(f" {suffix}"):
                name = name[:-len(suffix)-1].strip()
                changed = True

    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)

    # Collapse whitespace
    name = ' '.join(name.split())

    return name


def recipient_match_score(name1: str, name2: str) -> float:
    """
    Calculate similarity between two recipient names.
    Returns 0-1 score.
    """
    n1 = normalize_recipient(name1)
    n2 = normalize_recipient(name2)

    if not n1 or not n2:
        return 0

    # Exact match
    if n1 == n2:
        return 1.0

    # One contains the other
    if n1 in n2 or n2 in n1:
        return 0.9

    # Word overlap
    words1 = set(n1.split())
    words2 = set(n2.split())

    if not words1 or not words2:
        return 0

    overlap = len(words1 & words2)
    total = len(words1 | words2)

    return overlap / total


def is_foundation_transfer(
    gift_recipient: str,
    billionaire_foundations: List[str]
) -> bool:
    """
    Check if a gift is to the billionaire's own foundation.
    These should be excluded to avoid double-counting.
    """
    if not billionaire_foundations:
        return False

    for foundation in billionaire_foundations:
        if recipient_match_score(gift_recipient, foundation) > 0.7:
            return True

    return False


def create_dedup_key(recipient: str, year: int, amount: float) -> Tuple:
    """
    Create a key for grouping potential duplicates.
    Buckets by: (normalized recipient, year, amount bucket)
    """
    norm_recipient = normalize_recipient(recipient)

    # Further simplify - just first 20 chars of normalized name
    # This helps catch "Stanford University" vs "Stanford Univ"
    short_name = norm_recipient[:20] if norm_recipient else ""

    # $10M buckets to catch similar amounts
    amount_bucket = int(amount / 10_000_000)

    return (short_name, year, amount_bucket)


def deduplicate_gifts(
    all_gifts: List[Dict],
    billionaire_foundations: List[str] = None
) -> Tuple[List[UnifiedGift], Dict]:
    """
    Deduplicate gifts across categories.

    Args:
        all_gifts: List of gifts from all categories, each with:
            - category: str
            - recipient: str
            - amount: float
            - year: int
            - is_pledge: bool
            - source_url: str
            - confidence: str
        billionaire_foundations: Names of billionaire's own foundations

    Returns:
        (deduplicated_gifts, stats)
    """
    if billionaire_foundations is None:
        billionaire_foundations = []

    # Step 1: Filter out transfers to own foundation
    filtered = []
    foundation_transfers = 0

    for gift in all_gifts:
        if is_foundation_transfer(gift.get("recipient", ""), billionaire_foundations):
            foundation_transfers += 1
        else:
            filtered.append(gift)

    # Step 2: Group by dedup key
    groups: Dict[Tuple, List[Dict]] = {}

    for gift in filtered:
        key = create_dedup_key(
            gift.get("recipient", "Unknown"),
            gift.get("year", 2024),
            gift.get("amount", 0)
        )

        if key not in groups:
            groups[key] = []
        groups[key].append(gift)

    # Step 3: For each group, keep highest priority category
    deduplicated = []
    duplicates_removed = 0

    for key, group in groups.items():
        if len(group) == 1:
            g = group[0]
            deduplicated.append(UnifiedGift(
                category=g.get("category", "UNKNOWN"),
                recipient=g.get("recipient", "Unknown"),
                amount=g.get("amount", 0),
                year=g.get("year", 2024),
                is_pledge=g.get("is_pledge", False),
                source_url=g.get("source_url", ""),
                confidence=g.get("confidence", "LOW"),
            ))
        else:
            # Multiple gifts in same bucket - keep highest priority
            sorted_group = sorted(
                group,
                key=lambda g: CATEGORY_PRIORITY.get(g.get("category", ""), 0),
                reverse=True
            )
            winner = sorted_group[0]
            duplicates_removed += len(group) - 1

            deduplicated.append(UnifiedGift(
                category=winner.get("category", "UNKNOWN"),
                recipient=winner.get("recipient", "Unknown"),
                amount=winner.get("amount", 0),
                year=winner.get("year", 2024),
                is_pledge=winner.get("is_pledge", False),
                source_url=winner.get("source_url", ""),
                confidence=winner.get("confidence", "LOW"),
            ))

    # Separate pledges from disbursements
    pledges = [g for g in deduplicated if g.is_pledge]
    disbursed = [g for g in deduplicated if not g.is_pledge]

    stats = {
        "original_count": len(all_gifts),
        "foundation_transfers_removed": foundation_transfers,
        "duplicates_removed": duplicates_removed,
        "final_count": len(deduplicated),
        "pledges_count": len(pledges),
        "disbursed_count": len(disbursed),
        "total_pledged": sum(g.amount for g in pledges),
        "total_disbursed": sum(g.amount for g in disbursed),
        "dedup_percentage": duplicates_removed / len(all_gifts) * 100 if all_gifts else 0,
    }

    return deduplicated, stats


def aggregate_by_category(gifts: List[UnifiedGift]) -> Dict[str, float]:
    """
    Sum amounts by category after deduplication.
    """
    by_category = {}
    for gift in gifts:
        if gift.category not in by_category:
            by_category[gift.category] = 0
        by_category[gift.category] += gift.amount
    return by_category


if __name__ == "__main__":
    # Test deduplication
    test_gifts = [
        # Same gift appearing in multiple sources
        {"category": "FOUNDATIONS", "recipient": "Stanford University", "amount": 100_000_000,
         "year": 2023, "is_pledge": False, "source_url": "https://propublica.org", "confidence": "HIGH"},
        {"category": "DIRECT_GIFTS", "recipient": "Stanford Univ", "amount": 100_000_000,
         "year": 2023, "is_pledge": False, "source_url": "https://news.com", "confidence": "MEDIUM"},

        # Transfer to own foundation (should be removed)
        {"category": "SECURITIES", "recipient": "Musk Foundation", "amount": 500_000_000,
         "year": 2022, "is_pledge": False, "source_url": "https://sec.gov", "confidence": "MEDIUM"},

        # Unique gift
        {"category": "DIRECT_GIFTS", "recipient": "St. Jude Children's Hospital", "amount": 55_000_000,
         "year": 2022, "is_pledge": False, "source_url": "https://stjude.org", "confidence": "MEDIUM"},

        # Pledge vs disbursement (different)
        {"category": "DIRECT_GIFTS", "recipient": "Red Cross", "amount": 10_000_000,
         "year": 2024, "is_pledge": True, "source_url": "https://news.com", "confidence": "LOW"},
        {"category": "FOUNDATIONS", "recipient": "Red Cross", "amount": 5_000_000,
         "year": 2024, "is_pledge": False, "source_url": "https://propublica.org", "confidence": "HIGH"},
    ]

    billionaire_foundations = ["Musk Foundation", "Elon Musk Foundation"]

    print("Testing deduplication...")
    print(f"Input: {len(test_gifts)} gifts")

    deduped, stats = deduplicate_gifts(test_gifts, billionaire_foundations)

    print(f"\nResults:")
    print(f"  Foundation transfers removed: {stats['foundation_transfers_removed']}")
    print(f"  Duplicates removed: {stats['duplicates_removed']}")
    print(f"  Final gift count: {stats['final_count']}")
    print(f"  Dedup percentage: {stats['dedup_percentage']:.1f}%")

    print(f"\nDeduplicated gifts:")
    for gift in deduped:
        print(f"  - {gift.recipient}: ${gift.amount/1e6:.1f}M ({gift.category})")

    by_cat = aggregate_by_category(deduped)
    print(f"\nBy category:")
    for cat, total in by_cat.items():
        print(f"  {cat}: ${total/1e6:.1f}M")
