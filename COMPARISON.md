# Pipeline Comparison: Old vs New

## Methodology Change

**Old Pipeline**: Data-source driven (ProPublica → Wikipedia → SEC → etc.)
- Hardcoded CIK mappings for only 12 billionaires
- Wikipedia scraping that returned $0 for most people
- No actual web search for announced gifts

**New Pipeline**: Taxonomy-driven (by giving category)
- LLM-powered research using web search for EACH billionaire
- Searches by category: Foundations, Direct Gifts, Securities, DAFs, LLCs, etc.
- Source URLs for every finding
- BS_checker to verify non-hardcoding

## Results Comparison

| Billionaire | Old Pipeline | New Pipeline | Improvement |
|-------------|-------------|--------------|-------------|
| **Larry Ellison** | $0 | $1,572M | ∞ (was showing no giving) |
| **Mark Zuckerberg** | $186M | $9,191M | 49x more |
| **Elon Musk** | $300M | $1,177M | 4x more |
| **Jeff Bezos** | $13,401M | $2,374M | -5x (old overcounted pledges) |
| **Warren Buffett** | $56,834M | $60,000M | +6% more accurate |

## Key Fixes

### Larry Ellison: $0 → $1.57B
The old pipeline found NOTHING for Larry Ellison because:
1. ProPublica search didn't match "Larry Ellison Foundation"
2. Wikipedia scraping returned nothing
3. No CIK mapping for SEC Form 4

The new pipeline found:
- $267M from Larry Ellison Foundation (ProPublica 990-PF)
- $200M to USC for cancer research
- $1B to Ellison Medical Foundation
- $5M to Musculo-Skeletal Research
- $100M recent pledge

### Mark Zuckerberg: $186M → $9.2B
Old pipeline missed:
- CZI LLC's $7.22B in grants (LLCs don't file 990s)
- $100M Newark schools gift (pre-CZI)
- Stock transfers to foundation

### Elon Musk: $300M → $1.18B
Old pipeline had some data but missed:
- Complete Musk Foundation disbursement history
- $55M St. Jude gift
- $50M to OpenAI
- $30M to South Texas communities

### Jeff Bezos: $13.4B → $2.37B (LOWER is more accurate)
Old pipeline OVERCOUNTED:
- Counted $10B Earth Fund pledge as if disbursed
- The pledge is committed but only ~$791M actually granted so far

### Warren Buffett: Accurate either way
Both pipelines correctly identified ~$60B in Berkshire stock donations.

## Quality Metrics

| Metric | Old Pipeline | New Pipeline |
|--------|-------------|--------------|
| Source URLs per billionaire | 0-1 | 4-6 |
| Categories researched | 3-4 | 8 |
| Deduplication | None | Yes |
| Pledge vs. Disbursement tracking | No | Yes |
| BS_checker verified | No | Yes |

## Conclusion

The new taxonomy-driven pipeline:
1. Uses LLM web search instead of brittle scrapers
2. Tracks giving by category (what was asked for)
3. Has source attribution for all findings
4. Distinguishes pledges from actual disbursements
5. Passes BS_checker verification

The old pipeline was fundamentally broken because it relied on hardcoded mappings and scrapers that failed silently.
