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
- DAF contribution estimates and opacity scores
- Split-interest trust estimates (CLATs/CRATs)
- Red flags (low payout, pledge unfulfilled, DAF opacity, CLAT wealth transfer, etc.)
- Overall opacity score (0-1)

**Preliminary findings (top 50 US):**
- 11 billionaires with zero observable foundation giving despite $10B+ net worth
- Multiple Giving Pledge signers flagged as unfulfilled
- Several foundations below 5% payout minimum (CZI at 0.9%, Huang at 1.7%)
- High DAF opacity detected for several billionaires (>50% of grants to DAFs)
- Known CLAT wealth transfer patterns identified (Walton family)

**Data gaps requiring manual fill:**
- Chronicle Big Gifts / Million Dollar List (no public API)
- Known LLCs (CZI, Ballmer Group, Lost Horse) not in 990 database

---

## Stage 7: DAF Contribution Estimation

DAFs represent a $251B+ black box with no individual-level disclosure. We estimate DAF contributions through multiple indirect methods:

### Observable Data
- **Foundation→DAF transfers**: 990-PF Part XV shows grants to DAF sponsors (Fidelity Charitable, Schwab Charitable, etc.)
- **Known DAF sponsor EINs**: We track grants to 15+ major commercial DAF sponsors

### Estimation Methods
1. **DAF percentage of grants**: Calculate what fraction of foundation grants go to known DAF sponsors
2. **SEC Form 4 gap analysis**: If stock gifts exceed foundation inflows, the gap may indicate DAF contributions
3. **Known personal DAFs**: Track documented DAF accounts from media reports (e.g., Jensen Huang's "GeForce Fund")

### Opacity Score (0-1)
We calculate a DAF opacity score based on:
- Percentage of grants going to DAFs (>50% = high opacity)
- Known personal DAFs with unknown balances
- Large gap between SEC stock gifts and observable giving
- Foundation near minimum 5% payout

### Key DAF Sponsors Tracked
| EIN | Sponsor |
|-----|---------|
| 11-0303001 | Fidelity Charitable Gift Fund |
| 31-1640316 | Schwab Charitable Fund |
| 23-2888152 | Vanguard Charitable |
| 23-2844706 | National Philanthropic Trust |
| 20-5205488 | Silicon Valley Community Foundation |

### Confidence Level: LOW
We can only observe foundation→DAF transfers. Individual DAF account balances and grant recommendations remain invisible.

---

## Stage 8: Split-Interest Trust Estimation (CRTs/CLTs)

Split-interest trusts are vehicles where charitable and non-charitable beneficiaries share trust income or principal.

### Trust Types
| Type | How It Works | Charitable Impact |
|------|--------------|-------------------|
| CRT (Charitable Remainder Trust) | Donor gets income, charity gets remainder | Charity benefits at termination |
| CLT (Charitable Lead Trust) | Charity gets income, heirs get remainder | Annual charitable payments |
| CRAT/CRUT | Annuity/Unitrust versions of CRTs | Fixed vs. variable payments |
| CLAT/CLUT | Annuity/Unitrust versions of CLTs | Tax-efficient wealth transfer |

### The Walton Pattern
CLATs are often structured so 95%+ goes to heirs, with minimal charity:
- 30-year term with 2% annual charitable payments
- Charity receives small annual payments
- Heirs receive the appreciated remainder
- **This is legal tax minimization, not philanthropy**

### Data Sources
1. **Form 5227**: Filed annually, "open to public inspection" BUT no searchable database exists
2. **Media reports**: Investigative journalism has documented specific trusts (e.g., Walton CLATs)
3. **IRS Statistics of Income**: ~$121B in CRT assets, 70,000+ annual returns

### Estimation Methods
1. **Known trust database**: We track documented trusts from media reports
2. **Foundation correlation**: Large foundation assets correlate with CLAT activity
3. **News search**: Search for trust mentions in news coverage

### Red Flags for Split-Interest Trusts
- **CLAT_WEALTH_TRANSFER**: Trust structured primarily for heir benefit
- **LOW_CHARITABLE_RATE**: Less than 3% going to charity annually
- **FOUNDATION_RECYCLING**: CLAT payments going to grantor's own foundation

### Confidence Level: MEDIUM for known trusts, NEAR ZERO for discovery

---

## Overall Opacity Score

We calculate an overall opacity score (0-1) for each billionaire:

| Factor | Weight | Trigger |
|--------|--------|---------|
| Low observable giving ratio | 0.30 | <1% of net worth observable |
| High DAF usage | 0.25 | >50% of grants to DAFs |
| CLAT wealth transfer | 0.20 | Known wealth transfer pattern |
| Foundation at minimum payout | 0.10 | 4-5.5% payout rate |
| Unfulfilled pledge | 0.15 | Signed but not fulfilled |

**Interpretation:**
- 0.0-0.2: Low opacity (relatively transparent)
- 0.2-0.4: Moderate opacity
- 0.4-0.6: High opacity (significant non-disclosure)
- 0.6+: Very high opacity (maximizing non-disclosure)

---

## Taxonomy Analysis: Is This Complete?

### What This Pipeline Captures Well
1. **Foundation giving** (HIGH confidence) - 990-PF Part XV
2. **Securities gifts** (HIGH confidence for foundations) - SEC Form 4
3. **Announced gifts** (MEDIUM confidence) - Chronicle, MDL, news
4. **DAF transfers** (LOW confidence) - Foundation→DAF flows
5. **Split-interest trusts** (MEDIUM for known, LOW for discovery)

### What Remains Invisible
1. **Dynasty trusts** - No public registry in any US state
2. **Philanthropic LLCs** - No 990 filing (CZI model)
3. **Foreign giving** - No country discloses donor names
4. **Religious giving** - Churches are 990-exempt
5. **Direct DAF contributions** - Bypasses foundation entirely
6. **Anonymous gifts below $1M** - Not tracked in major databases

### Missing from Current Taxonomy
1. **Corporate philanthropy** - Billionaires control corporate giving programs
2. **Conservation easements** - Real estate donations with tax benefits
3. **Impact investing** - Not strictly charity but deploys capital for good
4. **Board seat giving** - Implied minimum giving for nonprofit governance

### Fundamental Limitation
For ~40% of giving channels, we have no estimation method. The Scrooge List is necessarily a **lower bound on giving**, not an upper bound on non-giving. Silence on the list might mean:
- Genuinely low giving, OR
- Very successful opacity, OR
- Giving through untraceable channels
