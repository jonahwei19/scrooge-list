# Scrooge Score Methodology v3

## Overview

The Scrooge Score measures how little of their wealth billionaires have deployed for charitable purposes. Higher score = less giving relative to capacity.

## Key Changes from v2

1. **Removed red flag weighting** - confusing and arbitrary
2. **Removed pledge breach penalty** - not relevant to core measurement
3. **Simplified to pure giving ratio** - cleaner, more defensible
4. **Better estimates** - using verified sources, not round numbers

## Formula

```
Scrooge Score = 100 × (1 - Giving Ratio)

Where:
  Giving Ratio = Total Lifetime Giving / (Net Worth × Liquidity Adjustment)

  Capped at 0-100
```

## Liquidity Adjustment

Not all wealth is equally liquid. We adjust expected giving capacity:

| Wealth Source | Liquidity Factor |
|---------------|------------------|
| Diversified investments | 0.70 |
| Public company founder (diversified) | 0.50 |
| Public company founder (concentrated) | 0.30 |
| Private company | 0.20 |
| Real estate heavy | 0.25 |
| Inherited/mixed | 0.40 |

## Data Sources by Category

### 1. Foundation Giving (HIGH confidence)
- ProPublica 990-PF filings
- Foundation websites
- Annual reports

### 2. Direct Announced Gifts (MEDIUM-HIGH confidence)
- News coverage
- University announcements
- Chronicle of Philanthropy
- Giving Pledge letters

### 3. Philanthropic LLCs (MEDIUM confidence)
- Annual reports (CZI, Ballmer Group)
- News coverage
- IRS disclosures where available

### 4. Donor-Advised Funds (LOW confidence)
- Only observable through foundation transfers
- Estimated at 0.3% of net worth as floor

### 5. Securities Gifts (MEDIUM confidence)
- SEC Form 4 filings
- Stock transfer announcements

## Validation

Each estimate should be validated against:
1. At least 2 independent sources
2. Plausibility check (giving rate vs wealth trajectory)
3. Cross-reference with Giving Pledge status

## Categories Not Counted

- Political donations (different purpose)
- Pledges not yet fulfilled (only count disbursed)
- Foundation assets (only count grants out)
