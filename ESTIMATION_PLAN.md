# Scrooge List Estimation Plan

## Category-by-Category OSINT Strategy

### 1. FOUNDATIONS (Confidence: HIGH)

**What we're estimating:** Annual grants paid out by billionaire-controlled private foundations.

**Data Sources:**
1. **ProPublica Nonprofit Explorer API** - Primary source
   - Search by name variations + "foundation"
   - Pull EIN, then fetch 990-PF data
   - Fields: `totassetsend`, `grsrcptspublicuse`, `totfuncexpns`, `totcntrbs`

2. **Known Foundation EINs** - For top billionaires, we can maintain a verified list
   - Larry Ellison Foundation: 94-3269827
   - Chan Zuckerberg Initiative Foundation: 45-5002209
   - Musk Foundation: 85-2133087
   - Bezos Family Foundation: 91-2073258

3. **Foundation Directory (Candid)** - Secondary verification

**Estimation Logic:**
```
For each billionaire:
  1. Search ProPublica for "{LastName} Foundation", "{FullName} Foundation"
  2. Filter results to likely matches (name similarity > 0.7)
  3. For each match, fetch 990-PF filing
  4. Sum grants_paid across all years (avoid double-counting annual vs cumulative)
  5. Track payout rate for red flags (<5% is below IRS minimum)
```

**Deduplication Risk:** LOW - 990-PF grants are actual outflows, not pledges

---

### 2. DIRECT_GIFTS (Confidence: MEDIUM)

**What we're estimating:** Named/announced gifts to charities, universities, hospitals.

**Data Sources:**
1. **Chronicle of Philanthropy Big Gifts** - Tracks $1M+ gifts
   - No public API, but can search their site
   - URL pattern: `https://www.philanthropy.com/article/how-the-biggest-donors-gave-in-{year}`

2. **Million Dollar List (Indiana University)** - Academic database
   - `https://milliondollarlist.org/`
   - Searchable by donor name

3. **University/Hospital Press Releases** - Via web search
   - Search: `"{Name}" donated million OR billion site:edu`
   - Search: `"{Name}" gift announcement site:pr.newswire.com`

4. **Named Buildings/Chairs** - Threshold estimation
   - Hospital wing: $10-50M
   - University building: $25-100M
   - Endowed chair: $1.5-5M

**Estimation Logic:**
```
For each billionaire:
  1. Search Chronicle of Philanthropy for name
  2. Search MDL for donor record
  3. Web search for press releases with gift amounts
  4. Extract amounts with regex: \$[\d.]+\s*(million|billion)
  5. Deduplicate by recipient + year + approximate amount
  6. Track pledge vs. disbursed status
```

**Deduplication Risk:** MEDIUM - Same gift may appear in multiple sources

---

### 3. SECURITIES (Confidence: MEDIUM)

**What we're estimating:** Stock gifts to foundations/charities (exempt from Form 4 for direct charity gifts, but visible for foundation transfers).

**Data Sources:**
1. **SEC EDGAR Form 4** - Insider transactions
   - Transaction code "G" = gift
   - Need CIK for each billionaire
   - API: `https://data.sec.gov/submissions/CIK{padded_cik}.json`

2. **CIK Lookup** - Map names to CIKs
   - API: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={name}&type=&dateb=&owner=include&count=40&search_text=`

3. **OpenInsider** - Aggregates Form 4 data
   - Easier to scrape than raw EDGAR

**Estimation Logic:**
```
For each billionaire:
  1. Look up CIK from SEC database
  2. Fetch all Form 4 filings
  3. Filter to transaction code "G" (gift)
  4. Sum share values at transaction date
  5. NOTE: Direct charity gifts are EXEMPT from Form 4 - we only see foundation transfers
```

**Deduplication Risk:** HIGH - Stock to foundation may also appear in foundation 990

---

### 4. DAFS (Confidence: LOW)

**What we're estimating:** Contributions to donor-advised funds (Fidelity Charitable, Schwab Charitable, etc.)

**Data Sources:**
1. **Foundation 990-PF Part XV** - Shows grants TO DAF sponsors
   - Search for grants to "Fidelity Charitable", "Schwab Charitable", "Vanguard Charitable"
   - This shows foundation → DAF transfers

2. **DAF Sponsor Annual Reports** - Aggregate only
   - Fidelity Charitable publishes total AUM and grants
   - No individual donor data

3. **Net Worth Proxy** - Industry estimates
   - ~0.3% of UHNW portfolios go to DAFs annually
   - Very rough estimate

**Estimation Logic:**
```
For each billionaire:
  1. Check foundation 990s for DAF grants (visible in Part XV)
  2. If no foundation data, estimate: net_worth * 0.003 (industry average)
  3. Flag as LOW confidence
```

**Deduplication Risk:** MEDIUM - DAF contribution may be counted both as foundation grant and DAF estimate

---

### 5. PHILANTHROPIC_LLCS (Confidence: MEDIUM for known, ZERO for unknown)

**What we're estimating:** Giving through LLC structures (no 990 filing required).

**Known LLCs:**
- Chan Zuckerberg Initiative (LLC) - Self-reports at chanzuckerberg.com
- Emerson Collective (Laurene Powell Jobs) - Minimal disclosure
- Ballmer Group - Some transparency
- Lost Horse Capital (Patagonia) - Known structure

**Data Sources:**
1. **LLC Websites** - Self-reported grants
   - CZI: `https://chanzuckerberg.com/grants-ventures/grants/`
   - Ballmer: `https://www.ballmergroup.org/`

2. **News/Press Releases** - Announced grants
   - Search: `"{LLC name}" grant million`

3. **990 Recipients** - Reverse lookup
   - If a nonprofit received a grant from "Chan Zuckerberg Initiative", it appears on THEIR 990

**Estimation Logic:**
```
For each billionaire:
  1. Check known LLC database for matches
  2. If match, fetch from LLC website or news
  3. If unknown, estimate: $0 (can't observe)
```

**Deduplication Risk:** LOW - LLCs are separate from foundations

---

### 6. SPLIT_INTEREST_TRUSTS (Confidence: LOW)

**What we're estimating:** CRTs, CLTs, and other split-interest trusts.

**Data Sources:**
1. **Form 5227** - Filed annually but NOT searchable
   - Must know trust name/EIN to request

2. **News/Court Filings** - For famous cases
   - Walton family CLATs are documented
   - Search: `"{Name}" charitable trust` or `"{Name}" CLAT`

3. **Estate Planning Articles** - Mentions of structures used

**Estimation Logic:**
```
For each billionaire:
  1. Web search for "{Name}" + charitable trust / CLT / CRT
  2. If found in news, record estimated value
  3. Otherwise: $0 (not observable)
```

**Deduplication Risk:** LOW - These are separate structures

---

### 7. RELIGIOUS (Confidence: ZERO)

**What we're estimating:** Tithing, church donations, religious organization gifts.

**Data Sources:**
1. **None direct** - Churches exempt from 990

2. **Self-disclosure** - Some billionaires mention faith
   - E.g., Phil Anschutz known for religious giving

3. **Tithing Norms** - By denomination
   - LDS: 10% of income expected
   - Catholic: 2-5% common
   - Evangelical: 5-10% common

**Estimation Logic:**
```
For each billionaire:
  1. Search for religious affiliation
  2. If found and practicing: estimate tithing rate * annual income
  3. Otherwise: $0 (not observable)
  4. Always flag as ZERO confidence
```

**Deduplication Risk:** LOW

---

### 8. ANONYMOUS (Confidence: ZERO)

**What we're estimating:** Dark channels - dynasty trusts, foreign giving, anonymous gifts.

**Data Sources:**
1. **None** - By definition unobservable

2. **Industry Estimates** - UHNW giving norms
   - Anonymous giving: ~10-20% of total giving
   - Dynasty trusts: $500B+ exists but no donor linkage

**Estimation Logic:**
```
If we want to include estimates:
  anonymous_estimate = observable_giving * 0.15  # 15% hidden assumption

Otherwise: $0
```

**Deduplication Risk:** N/A

---

## Deduplication Strategy

**Problem:** The same money can appear multiple times:
1. Stock transfer TO foundation (Form 4)
2. Foundation RECEIVES contribution (990-PF)
3. Foundation GRANTS to charity (990-PF Part XV)
4. Same grant announced in press release
5. Same grant counted as "direct gift"

**Solution:**
```
1. PRIORITY ORDER: Foundation grants > Direct gifts > Securities > DAF
   - Foundation grants are ACTUAL deployment to charities
   - Direct gifts may be to foundations (double count)
   - Securities may fund foundation contributions

2. RECIPIENT MATCHING:
   - If direct gift recipient = billionaire's foundation → skip (already in foundation)
   - If securities gift recipient = billionaire's foundation → skip

3. AMOUNT BUCKETING:
   - Group gifts by (recipient, year, round(amount/1M))
   - If same bucket appears in multiple categories → keep highest confidence

4. PLEDGE VS DISBURSEMENT:
   - Track "pledge" vs "disbursed" flag
   - Default: count disbursed only, show pledges separately
```

---

## Implementation Order

1. **foundations.py** - Fix ProPublica API integration
2. **securities.py** - Add CIK lookup automation
3. **direct_gifts.py** - Add web search with extraction
4. **llcs.py** - Known LLC database + self-report scraping
5. **dafs.py** - Foundation-to-DAF transfer detection
6. **deduplication.py** - Cross-category duplicate removal
7. **estimator.py** - Main orchestrator

---

## Quality Metrics

For each billionaire, track:
- `source_count`: Number of distinct sources
- `confidence_score`: Weighted by category confidence
- `dedup_percentage`: How much was removed as duplicates
- `pledge_vs_disbursed_ratio`: What fraction is pledged but not deployed
