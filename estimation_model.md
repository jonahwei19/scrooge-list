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

**Working pipeline:** `pipeline.py` processes the full Forbes list (3,163 billionaires, 939 US).

**Run commands:**
```bash
# Test with 10 billionaires
python3 pipeline.py --test

# Top 50 US billionaires
python3 pipeline.py --limit 50 --country "United States"

# Full Forbes list
python3 pipeline.py
```

**Output:** CSV and JSON files in `output/` with:
- Foundation assets and grants (from 990-PF)
- Foundation/net-worth ratio
- Giving Pledge status (from IPS dataset, 401 pledgers)
- Red flags (low payout, pledge unfulfilled, no observable giving)

**Preliminary findings (top 50 US):**
- 11 billionaires with zero observable foundation giving despite $10B+ net worth
- Multiple Giving Pledge signers flagged as unfulfilled
- Several foundations below 5% payout minimum (CZI at 0.9%, Huang at 1.7%)

**Data gaps requiring manual fill:**
- Chronicle Big Gifts / Million Dollar List (no public API)
- SEC Form 4 gift transactions (needs EDGAR parsing)
- Known LLCs (CZI, Ballmer Group, Lost Horse) not in 990 database
