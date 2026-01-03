"""
Giving Category Modules

Each category represents a distinct channel through which billionaires can deploy wealth charitably.
The pipeline sums estimates across all categories, with deduplication to avoid double-counting.

Categories:
1. Foundations - 990-PF filings, grants paid
2. DAFs - Donor-advised funds (opaque, estimate only)
3. Direct Gifts - Named/announced gifts to charities
4. Securities - Stock gifts via Form 4 or direct
5. Split-Interest Trusts - CRTs, CLTs, etc.
6. Philanthropic LLCs - CZI, Ballmer Group, etc.
7. Religious - Tithing, church donations
8. Anonymous/Dark - Dynasty trusts, foreign, undisclosed

Each module exports:
- research_category(name: str) -> CategoryResult
- CategoryResult dataclass with amount, confidence, sources, details
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class Confidence(Enum):
    HIGH = "HIGH"       # Observable data (990-PF, announced gifts)
    MEDIUM = "MEDIUM"   # Partial data (news, SEC filings)
    LOW = "LOW"         # Estimates based on proxies
    ZERO = "ZERO"       # Pure speculation


@dataclass
class CategoryResult:
    """Result from researching a single giving category for a billionaire."""
    category: str
    amount_low: float      # Conservative estimate
    amount_mid: float      # Best estimate
    amount_high: float     # Upper bound
    confidence: Confidence
    sources: List[str]     # URLs or data sources used
    details: str           # Human-readable explanation
    raw_findings: List[dict]  # Specific gifts/grants found

    def to_dict(self):
        return {
            "category": self.category,
            "amount_low": self.amount_low,
            "amount_mid": self.amount_mid,
            "amount_high": self.amount_high,
            "confidence": self.confidence.value,
            "sources": self.sources,
            "details": self.details,
            "raw_findings": self.raw_findings,
        }
