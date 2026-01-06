# DAF Data Sources for Scrooge List

## The DAF Visibility Problem

DAFs have **no individual account-level disclosure requirements**. We can see:
- Money going INTO DAFs (via SEC Form 4 stock gifts, 990-PF foundation grants)
- Aggregate DAF sponsor data (total contributions, total grants)

We CANNOT see:
- Individual account balances
- Where grants from specific accounts go
- Whether money is being "warehoused" or actively deployed

## Available Data Sources

### 1. DAF Sponsor 990 Filings (Schedule D)
**Access:** ProPublica Nonprofit Explorer, IRS 990 bulk data
**What it shows:** Total contributions received, total grants made by sponsor
**Limitation:** Aggregate only, no individual donor data

Major sponsors to track:
- Fidelity Charitable (EIN: 11-0303001) - $14.9B granted in 2024
- Schwab Charitable (EIN: 31-1640316)
- Vanguard Charitable (EIN: 23-2888152)
- National Philanthropic Trust (EIN: 52-1934107)
- Silicon Valley Community Foundation (EIN: 20-5205488)
- Goldman Sachs Philanthropy Fund (EIN: 45-2831855)

### 2. Foundation 990-PF Part XV Grants
**Access:** ProPublica API, IRS 990 XML bulk data
**What it shows:** Foundation grants to DAF sponsors (visible as "contributions parked")
**Limitation:** ProPublica API doesn't expose Part XV details; need to parse XML

When a foundation grants to "Fidelity Charitable Gift Fund," that's:
- Counted as a foundation "grant" in 990-PF
- But it's actually PARKED giving, not deployed to charity

### 3. SEC Form 4 Stock Gifts
**Access:** SEC EDGAR API
**What it shows:** Transaction code "G" for gifts, including to DAF sponsors
**Limitation:** Need to match recipient names to known DAF sponsors

### 4. DAF Research Collaborative Dataset
**Access:** https://data.givingtuesday.org/dafs
**What it shows:** Account-level data from 111 participating sponsors
- 9 years of activity
- 50,000+ accounts
- 600,000+ inbound contributions
- 2.25 million+ outbound grants
**Limitation:** Anonymized, aggregate statistics only

### 5. Fidelity/Schwab Annual Giving Reports
**Access:** Public PDFs
**What it shows:**
- Top recipient categories
- Average grant size ($4,600 in 2023)
- Payout rates (88% of accounts make grants annually)
- Crypto contributions ($786M in 2024)
**Limitation:** No individual donor identification

## Estimation Methods

### Method 1: Foundation→DAF Transfer Detection
Parse 990-PF XML to find grants where recipient name contains:
- "Fidelity Charitable"
- "Schwab Charitable"
- "Vanguard Charitable"
- "National Philanthropic Trust"
- "Community Foundation" (many are DAF sponsors)

### Method 2: Net Worth Proxy
Industry data suggests UHNW individuals contribute ~0.3% of net worth to DAFs annually.
Formula: `annual_daf_estimate = net_worth * 0.003`

### Method 3: SEC Form 4 Gift Matching
When Form 4 shows stock gift to a DAF sponsor, that's visible parked giving.

### Method 4: Giving Pledge Correlation
68% of Giving Pledge signers use DAFs extensively. Apply 1.5x multiplier for pledgers.

## What Remains Unknowable

1. **Cash contributions to DAFs** - No disclosure whatsoever
2. **DAF grant destinations** - Which charities receive from specific accounts
3. **DAF account balances** - How much is warehoused vs deployed
4. **Payout timing** - When (if ever) funds will reach operating charities

## Regulatory Landscape (as of 2024)

Proposed regulations pending since 2023:
- Definition clarifications (what counts as a DAF)
- Potential payout requirements
- Enhanced disclosure rules

As of December 2024, IRS has not finalized any new regulations. The 2006 rules remain in place.

## Implementation Priority

1. **HIGH:** Parse 990-PF XML for Foundation→DAF grants (quantifiable)
2. **MEDIUM:** Match SEC Form 4 gifts to DAF sponsors (quantifiable)
3. **LOW:** Net worth proxy estimation (educated guess)
