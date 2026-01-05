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

## Data Sources

| Category | Source | Confidence |
|----------|--------|------------|
| Foundation giving | 990-PF filings (ProPublica) | HIGH |
| Announced gifts | Chronicle of Philanthropy, news, Wikipedia | MEDIUM |
| Securities gifts | SEC Form 4 (transaction code "G") | MEDIUM |
| Giving Pledge status | Official pledge database | HIGH |
| Political giving | FEC OpenData | HIGH |
| DAF contributions | Foundation→DAF transfers + estimates | LOW |
| Philanthropic LLCs | Media coverage only | LOW |

## What Remains Unknowable

- **DAF individual accounts** — $251B with zero disclosure
- **Dynasty trusts** — South Dakota alone has $360B+, no public registry
- **Philanthropic LLCs** — no filing requirement
- **Foreign giving** — no country discloses donor names
- **Religious giving** — churches exempt from 990

## Web App Features

- **Liquidity discount toggle** — adjust for illiquid wealth
- **Size-adjusted ranking** — weight by absolute wealth
- **Filters** — by country, pledge status, search by name
- **Sortable columns** — rank by any metric

## Running Locally

```bash
cd docs && python3 -m http.server 8000
```

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
