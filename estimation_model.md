# Estimating Billionaire Charitable Deployment

## The Formula

**Total Annual Giving = Foundation + DAF + Direct + Securities + Split-Interest + Dark**

Each term represents a distinct channel with different observability.

---

## Channel-by-Channel Assessment

**1. Foundation Giving**

Observable. Private foundations file Form 990-PF annually. Part XV lists every grant with recipient name and amount. ProPublica has 3M+ returns searchable via API. For any billionaire with a named foundation, we can see exactly what leaves the foundation each year.

**Limitation:** We see foundation *outflows*, not what the billionaire contributed to the foundation. A foundation can sit on assets for decades at 5% payout.

**Data source:** ProPublica Nonprofit Explorer API, IRS SOI microdata.

---

**2. DAF Contributions**

Not observable at individual level. $251B sits in DAFs with zero disclosure of who owns which account or where grants go. The Big 3 sponsors (Fidelity, Schwab, Vanguard) control ~70% and refuse to disclose.

**Estimation methods:**
- Track foundation→DAF transfers via 990-PF Part XV (foundations gave $3.2B to DAFs in 2022)
- Match SEC Form 4 stock gifts (marked "gift") with timing of charity noncash receipts
- DAF sponsor annual reports give aggregate payout rates

**Confidence:** Low for individuals, medium for aggregate patterns.

---

**3. Direct Gifts (Named/Announced)**

Partially observable. Major gifts ($1M+) are typically announced via press release. The Chronicle of Philanthropy tracks these. Million Dollar List has all $1M+ gifts since 2000. PatronView tracks 1.78M museum donations.

**Estimation methods:**
- Chronicle Big Gifts database (free, searchable)
- University/hospital press release scraping
- Named building/chair thresholds (hospital wing = $10-25M, endowed chair = $1.5-3.5M)
- Board seat minimums (68% of governing boards require $10K-100K+)

**Confidence:** Medium. We catch big announced gifts. We miss anonymous gifts and smaller donations.

---

**4. Securities Gifts**

Observable when made to foundations. SEC Form 4 requires insiders to report stock dispositions within 2 business days. "Gift" transactions are flagged. Cross-reference with foundation 990 contribution schedules.

**Limitation:** Stock donated directly to a DAF or public charity doesn't appear on Form 4 (only insider sales/gifts to non-charities require 4, gifts to charities are exempt from Section 16 reporting). So this only catches foundation contributions.

**Data source:** SEC EDGAR, OpenInsider.

**Confidence:** High for foundation contributions, zero for direct-to-charity stock gifts.

---

**5. Split-Interest Trusts (CRTs/CLTs)**

Technically observable. Form 5227 is filed annually and is "open to public inspection" per IRS. ~70,000 returns filed annually, $121B+ in assets (2012 data).

**The catch:** No searchable database exists. You must request individual returns by trust name/EIN. The IRS doesn't publish a list of who has these trusts.

**What we know:** The Waltons use CLATs extensively to transfer wealth tax-free to heirs while making charitable payments. Bloomberg documented specific trusts. These are primarily wealth transfer tools, not charitable deployment.

**Confidence:** Medium if you know trust exists, near zero for discovery.

---

**6. Dark Channels**

Not observable. This includes:

- **Dynasty trusts:** No public registry in any US state. South Dakota holds $360B+ in perpetual trusts with zero disclosure. "Quiet trust" laws allow hiding even from beneficiaries.

- **Philanthropic LLCs:** No 990 filing. CZI chose LLC structure specifically to avoid 5% payout. We only see what they choose to announce.

- **Foreign giving:** No country discloses donor names. US 990-PF Schedule F shows what US foundations grant abroad, but direct foreign giving is invisible.

- **Religious giving:** Churches are the only 501(c)(3)s exempt from 990 filing. Megachurch donations, tithing, synagogue/mosque giving are completely opaque.

**Confidence:** Near zero.

---

## What We Can Actually Estimate

| Channel | Observability | Best Data Source |
|---------|---------------|------------------|
| Foundation outflows | Full | 990-PF Part XV |
| Foundation inflows | Partial | Form 4 + 990 contributions |
| DAF | None (individual) | Aggregate sponsor reports |
| Named gifts | Partial | Chronicle, press releases |
| Securities to charity | None | Exempt from Form 4 |
| Split-interest trusts | Findable but not discoverable | Form 5227 requests |
| Dynasty/LLC/Foreign/Religious | None | --- |

---

## Pipeline for Forbes List

**Input:** Forbes Real-Time Billionaires (2,700+ people, updated daily via RTB-API)

**Step 1: Foundation matching**
For each billionaire, search ProPublica for foundations containing their name or known family office name. Pull 990-PF data: assets, grants paid, payout rate, officer compensation.

**Step 2: Chronicle/MDL cross-reference**
Search Chronicle Big Gifts and Million Dollar List for name matches. Sum announced giving.

**Step 3: Form 4 securities**
For billionaires with public company stakes, pull Form 4 filings. Filter for "gift" disposition codes. Sum transferred value.

**Step 4: Red flag scoring**
Flag individuals with:
- Foundation payout <5% (hoarding)
- Foundation→DAF grants >50% (opacity maximization)
- High foundation admin / family compensation
- No Chronicle/MDL appearances despite $10B+ net worth
- Political mega-donor not appearing in charitable databases

**Step 5: Giving Pledge cross-reference**
Check against IPS dataset of 256 pledgers. Only 9 have fulfilled; flag pledge-breakers.

**Output:** For each billionaire:
- Observable giving (foundation + announced)
- Estimated giving range (with confidence)
- Red flags
- Data gaps

---

## What Remains Unknowable

Even with perfect execution, we cannot observe:
- DAF balances or grants (individual level)
- Dynasty trust assets or distributions
- LLC philanthropic activity
- Direct foreign giving
- Religious giving
- Anonymous gifts below announcement threshold

For ~40% of giving channels, we have no estimation method. The Goodheart List will necessarily be a lower bound on giving, not an upper bound on non-giving.

---

## Implementation Status

**Working pipeline:** `main.py` processes the full Forbes list (3,163 billionaires, 939 US).

**Run commands:**
```bash
# Test with 10 billionaires
python3 main.py --test

# Top 50 US billionaires
python3 main.py --limit 50 --country "United States"

# Full Forbes list
python3 main.py
```

**Output:** CSV and JSON files in `output/` with:
- Foundation assets and grants (from 990-PF)
- Foundation/net-worth ratio
- Giving Pledge status (from IPS dataset, 256 pledgers)
- Red flags (low payout, pledge unfulfilled, no observable giving)
- Dark giving estimates (DAF transfers, LLC giving, inferred giving)
- Opacity score (0-100 based on giving channel choices)

**Preliminary findings (top 50 US):**
- 11 billionaires with zero observable foundation giving despite $10B+ net worth
- Multiple Giving Pledge signers flagged as unfulfilled
- Several foundations below 5% payout minimum (CZI at 0.9%, Huang at 1.7%)

---

## Stage 7: Dark Giving Estimation

The pipeline now includes estimation of opaque/dark giving channels. These are
**lower-bound estimates** with varying confidence levels.

### Channels Estimated

| Channel | Method | Confidence |
|---------|--------|------------|
| DAF Transfers | Track 990-PF grants to known DAF sponsors | LOW |
| Philanthropic LLCs | Announced grants from CZI, Ballmer Group, etc. | VERY LOW |
| Split-Interest Trusts | News mentions, SEC filings for trust signals | LOW |
| Anonymous Gifts | Board seat inference ($10K-100K per seat) | LOW-MEDIUM |
| Noncash Gifts | Art donation tracking, deed records | MEDIUM |
| Foreign Giving | 990-PF Schedule F (US foundations only) | LOW |
| Religious Giving | Religious school/charity 990s | VERY LOW |

### Channels NOT Estimable (Zero Visibility)

| Channel | Why Opaque | Scale |
|---------|------------|-------|
| Dynasty Trusts | No public registry in any US state | $360B+ (SD alone) |
| Philanthropic LLCs | No 990 filing requirement | Unknown |
| Direct Foreign Giving | No country discloses donor names | Unknown |
| Religious Giving | Churches exempt from 990 | Unknown |

### Opacity Score

Each billionaire receives an opacity score (0-100) based on giving channel choices:

- **+30 points**: Uses philanthropic LLC (no disclosure requirement)
- **+20 points**: >50% of foundation grants go to DAFs
- **+10 points**: 20-50% of foundation grants go to DAFs
- **+25 points**: $10B+ net worth with <$100M in foundations
- **+15 points**: Split-interest trust signals detected

Higher score = more opaque giving practices.

### Known Philanthropic LLCs Tracked

| Billionaire | LLC | Notes |
|-------------|-----|-------|
| Mark Zuckerberg | Chan Zuckerberg Initiative | Chose LLC to avoid 5% payout |
| Steve Ballmer | Ballmer Group | Economic mobility focus |
| Laurene Powell Jobs | Emerson Collective | Education, immigration |
| MacKenzie Scott | Lost Horse LLC | Rapid trust-based giving |
| Pierre Omidyar | Omidyar Network | Hybrid philanthropy/investing |

### DAF Sponsor EINs for Tracking

The pipeline tracks foundation grants to these known DAF sponsors:
- Fidelity Charitable (11-0303001)
- Schwab Charitable (31-1640316)
- Vanguard Charitable (23-2888152)
- National Philanthropic Trust (52-1658827)
- Silicon Valley Community Foundation (20-5205488)

### Board Seat Giving Inference

68% of nonprofit governing boards require minimum annual giving:

| Board Type | Typical Minimum |
|------------|-----------------|
| Major Museum (Met, MoMA) | $25,000 - $100,000 |
| Hospital Board | $10,000 - $50,000 |
| University Trustee | $25,000 - $100,000 |
| Symphony Board | $5,000 - $25,000 |

Pipeline searches for board memberships and applies conservative (low-end) estimates.

### Limitations

1. **Dynasty trusts are invisible**: $360B+ in South Dakota alone with zero disclosure
2. **LLCs self-report**: We only see what they announce
3. **DAF individual accounts private**: Only aggregate sponsor data available
4. **Religious giving completely opaque**: Churches exempt from 990 filing
5. **Board seat data incomplete**: Wikipedia/LittleSis don't capture all boards
