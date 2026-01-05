# Scrooge List

An inverse Forbes list — ranks billionaires by how little of their fortune they've deployed for charity.

**[View the live Scrooge List](https://jonahwei19.github.io/scrooge-list/)**

## The Scrooge Score

The Scrooge Score (0-100) measures undergiving relative to capacity. Higher = more Scrooge-like.

```
Scrooge Score = 100 × (1 - Giving Ratio)

Where: Giving Ratio = Total Lifetime Giving / (Net Worth × Liquidity Factor)
```

A score of 100 means 0% giving. A score of 0 means giving ≥ 100% of liquid wealth.

### Liquidity Factors

Not all wealth is equally liquid. We discount expectations accordingly:

| Wealth Type | Factor | Rationale |
|-------------|--------|-----------|
| Diversified investments | 0.70 | Highly liquid |
| Public company (diversified) | 0.50 | Some stock sales needed |
| Public company (concentrated) | 0.30 | Major founder, stock sales = control loss |
| Private company | 0.20 | Hard to liquidate |
| Real estate heavy | 0.25 | Illiquid assets |
| Inherited/mixed | 0.40 | Typically more diversified |

### Size-Adjusted Ranking

The web app offers a "size-adjusted" mode that weights scores by absolute wealth using log₁₀(net worth). This surfaces mega-billionaires who give a low percentage — someone with $200B giving 1% appears worse than someone with $2B giving 1%, because the absolute "missing" philanthropy is vastly larger.

## Key Distinctions

The methodology makes three critical distinctions:

1. **DISBURSED, not pledged** — Only count money that has left the billionaire's control
2. **EXTERNAL, not self-controlled** — DAF transfers to the billionaire's own DAF don't count as charity
3. **GRANTS, not foundation assets** — A $10B foundation that grants $50M/year is $50M of giving

Example: Elon Musk's foundation has $14B in assets but grants 78% to entities he controls. Actual external giving: ~$270M.

## Verification Pipeline

Each estimate goes through a multi-stage verification process:

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: ProPublica 990-PF API                              │
│   - Search for foundations by billionaire name              │
│   - Pull cumulative grants across all available years       │
│   - Confidence: HIGH                                        │
├─────────────────────────────────────────────────────────────┤
│ Stage 2: SEC EDGAR Form 4                                   │
│   - Search for stock gifts (transaction code "G")           │
│   - Aggregate gift values                                   │
│   - Confidence: MEDIUM                                      │
├─────────────────────────────────────────────────────────────┤
│ Stage 3: Web Search (News/Announcements)                    │
│   - Chronicle of Philanthropy, Forbes, major news           │
│   - Direct gift announcements                               │
│   - Confidence: MEDIUM                                      │
├─────────────────────────────────────────────────────────────┤
│ Stage 4: Cross-Validation                                   │
│   - Compare sources, flag discrepancies > 2x                │
│   - Weighted average (990-PF: 3x, SEC: 2x, Web: 1x)         │
│   - Calculate confidence score                              │
└─────────────────────────────────────────────────────────────┘
```

Run the verification script:

```bash
python3 verify_billionaire.py "Larry Ellison"  # Single billionaire
python3 verify_billionaire.py --batch          # All suspicious entries
```

## Data Sources

| Category | Source | Confidence | API/Access |
|----------|--------|------------|------------|
| Foundation giving | 990-PF filings (ProPublica) | HIGH | [API](https://projects.propublica.org/nonprofits/api) |
| Grants data | Candid/GuideStar | HIGH | [API](https://developer.candid.org/) |
| University mega-gifts | Chronicle of Higher Education | MEDIUM | Manual |
| Announced gifts | Chronicle of Philanthropy, news | MEDIUM | Manual |
| Securities gifts | SEC Form 4 (code "G") | MEDIUM | [EDGAR](https://www.sec.gov/cgi-bin/browse-edgar) |
| Giving Pledge status | Official pledge database | HIGH | Manual |
| DAF contributions | Foundation→DAF transfers | LOW | 990-PF only |
| Philanthropic LLCs | Media coverage only | LOW | Manual |

### Additional Data Sources (Active)

| Source | Use Case | Access |
|--------|----------|--------|
| **Grantmakers.io** | Cumulative disbursements by year | [Profile pages](https://www.grantmakers.io/profiles/) |
| **GivingTuesday 990 Data API** | Bulk 990 data, 6 endpoints | [API](https://990data.givingtuesday.org/asset-bank/) |
| **Hurun India Philanthropy List** | Indian billionaire giving | [Annual report](https://www.hurun.net/) |
| **TIME100 Philanthropy** | Annual top 100 philanthropists | [Annual list](https://time.com/collections/time100-philanthropy-2025/) |

### Potential Future Data Sources

- **CASE Voluntary Support of Education** — university donation tracking ($61.5B in FY2024). Annual survey but requires institutional membership. Could cross-reference announced mega-gifts.
- **Foundation Maps (Candid)** — grant flow visualization showing where money goes
- **Inside Philanthropy** — donor profiles and giving estimates (subscription required)
- **Candid Foundation Directory** — 239,000+ grantmaker profiles, requires subscription
- **IRS 990 Bulk Data (AWS)** — raw XML filings at `s3://irs-form-990`. Free but requires parsing.
- **Nonprofit Open Data Collective** — R packages for building research databases from 990 e-files
- **Forbes 2024 Biggest Higher Ed Gifts** — 12+ gifts of $100M+ in 2024 alone, useful for verification

## What Remains Unknowable

- **DAF individual accounts** — $251B with zero disclosure
- **Dynasty trusts** — South Dakota alone has $360B+, no public registry
- **Philanthropic LLCs** — no filing requirement
- **Foreign giving** — no country discloses donor names
- **Religious giving** — churches exempt from 990

## What We Explicitly Exclude

- **Political donations** — Super PAC, dark money, and campaign contributions are not philanthropy (e.g., Timothy Mellon's $151.5M to MAGA Inc. in 2024)
- **Art collection spending** — Private art museums structured as companies (like Pinault Collection) are personal assets, not charity
- **Art loans to museums** — Keeping artwork on "loan" to a museum while retaining ownership is not a donation
- **Court-mandated compensation** — Environmental remediation funds (like Grupo México's $150M Río Sonora trust) are settlements, not voluntary giving
- **Employee stock gifts** — Giving stock to employees (like Ernest Garcia III's $35M) is compensation, not charity
- **Corporate foundation giving** — When clearly funded by company profits, not personal wealth (though this line is blurry for family businesses)

## Web App Features

- **Liquidity discount toggle** — adjust for illiquid wealth
- **Size-adjusted ranking** — weight by absolute wealth
- **Verifiable vs. unverifiable toggle** — show only hard-documented giving or include news estimates
- **Filters** — by country, pledge status, search by name
- **Sortable columns** — rank by any metric
- **Giving pipeline UI** — click any billionaire to see giving breakdown by type with source verification

### Verifiable vs. Unverifiable Giving

Each billionaire's giving is now split into two categories:

| Category | Sources | Display |
|----------|---------|---------|
| **Verifiable** | 990-PF filings, SEC Form 4 | Green column |
| **Unverifiable** | News/announcements only | Yellow column |

Toggle "Include Unverifiable Giving" to switch between:
- **ON (default)**: Total giving = verifiable + unverifiable
- **OFF**: Only count hard-documented giving from 990-PF and SEC filings

This helps distinguish between billionaires with well-documented philanthropy vs. those relying on news coverage.

## Running Locally

```bash
cd docs && python3 -m http.server 8000
```

## Verification Log

Corrections made through data verification:

| Date | Billionaire | Old Value | New Value | Source |
|------|-------------|-----------|-----------|--------|
| Jan 2026 | Jensen Huang | $125M | $333M | Grantmakers.io 990-PF cumulative |
| Jan 2026 | Robert Pera | $2M | $0.6M | ProPublica shows $0 foundation grants |
| Jan 2026 | Larry Page | $150M | $180M | Grantmakers.io - 82% of grants to DAFs, only ~$180M to operating charities |
| Jan 2026 | Charles Koch | $1.8B | $1.04B | Grantmakers.io cumulative (Forbes estimate inflated by Stand Together network) |
| Jan 2026 | Jim Simons | unchanged | $3.08B verified | Grantmakers.io 2014-2024 cumulative (Forbes $6B includes pre-2014 + direct gifts) |
| Jan 2026 | Zhang Yiming | $120M | $280M | Hurun China Philanthropy 2024 (joint with Liang Rubo) |
| Jan 2026 | Tadashi Yanai | $150M | $270M | Kyoto U $94M, UCLA $58M, UNHCR $20M, scholarships |
| Jan 2026 | Israel Englander | $50M | $150M | Foundation + Weill Cornell naming gifts (largest donor to $1.5B campaign) |
| Jan 2026 | Eduardo Saverin | $50M | $60M | Dana-Farber $40M, Singapore American School $15.5M |
| Jan 2026 | Vlad Tenev | $2M | $0.125M | Only verified: $125K to TJ High School. $2M was corporate donation |
| Jan 2026 | Stan Kroenke | $25M | $32M | Kroenke Family Foundation 990-PF + Kroenke Sports Charities |
| Jan 2026 | Zhong Shanshan | $150M | $140M | Nongfu Spring confirms 900M RMB + Zhuji donation 2024 |
| Jan 2026 | Jerry Jones | $50M | $90M | Two foundations (EIN 75-2808490 + 20-4346960) + Medal of Honor $20M |
| Jan 2026 | Ernest Garcia II | $30M | $55M | Garcia Family Foundation 990-PF + $20M UArizona 2025 |
| Jan 2026 | Ernest Garcia III | $35M | $5M | $35M was employee stock gift, not charity. Minimal verified giving |
| Jan 2026 | Mark Mateschitz | $50M | unknown | Personal giving not disclosed. Wings for Life is public fundraising |
| Jan 2026 | Giovanni Ferrero | $300M | $12M | Only €10M COVID donation verified. Fondazione Ferrero is employee-focused |
| Jan 2026 | Jacqueline Mars | $150M | $20M | Kennedy Center $10M, Smithsonian $5M. Mars family extremely private |
| Jan 2026 | Alain Wertheimer | $200M | $60M | Fondation Chanel is corporate ($110M/yr), personal giving opaque |
| Jan 2026 | Gerard Wertheimer | $200M | $60M | Same as Alain - philanthropy via corporate Fondation Chanel |
| Jan 2026 | François Pinault | $400M | $104M | €100M Notre-Dame + €3M Victor Hugo house. Pinault Collection is private company, not charity |
| Jan 2026 | Germán Larrea | $30M | $100M | Fundación Grupo México ~$87M/yr. Río Sonora $150M was court-mandated |
| Jan 2026 | John Mars | $100M | $50M | Mars Foundation $2M/yr (shared), Mount Vernon $25M, Yale $2M. Notoriously private |
| Jan 2026 | Lukas Walton | $200M | $500M | Builders Initiative Foundation (EIN 82-1503941) $1.65B assets, ~$99M/yr grants |
| Jan 2026 | Beate Heister | $50M | $0 | NO documented charitable giving. Siepmann-Stiftung is family trust, not charity |
| Jan 2026 | Karl Albrecht Jr. | $50M | $0 | Same as Beate Heister - Albrecht heirs have no public charitable record |
| Jan 2026 | Robin Zeng | $50M | $210M | CNY 1.37B (~$206M) to Shanghai Jiao Tong University (Dec 2021) |
| Jan 2026 | Robert Pera | $0.6M | $1.2M | Re-verified: $1M Conley match, $100K St. Jude, $75K food bank. #1 Scrooge confirmed |
| Jan 2026 | Stephen Schwarzman | $1.2B | $1.1B | Two foundations (EIN 47-4634539 + 45-4757735). ~$100M/yr combined. Giving Pledge 2020 |
| Jan 2026 | Ken Griffin | $2B | $2B | Uses DAF with NO disclosure. $2B claimed but unverifiable. NOT Giving Pledge |
| Jan 2026 | Klaus-Michael Kühne | $800M | $600M | Swiss foundation, no disclosure. EUR 300M Hamburg Opera (2025) largest gift |
| Jan 2026 | Daniel Gilbert | $1.5B | $1B | Foundation wound down 2024. $375M Henry Ford, $500M Detroit pledge. Giving Pledge 2012 |
| Jan 2026 | Miriam Adelson | $1B | $1.5B | Two foundations ~$1.2B verified. Political donations ($284M) excluded |

## Limitations

1. **Announced gifts** depend on media coverage — smaller billionaires underrepresented
2. **Form 4 gifts** only capture foundation-bound stock — direct charity gifts are exempt
3. **Name matching** is fuzzy — may miss some foundations or include false positives
4. **Data lag** — 990-PF filings are 6-12 months behind
5. **Round estimates** ($100M, $500M) for many billionaires indicate placeholders, not verified data

## Contributing

Pull requests welcome. Priority areas:

1. Better name matching for foundations
2. Additional sources for announced gifts
3. Historical trend tracking
