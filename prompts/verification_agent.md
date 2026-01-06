# Billionaire Philanthropy Verification Agent Prompt

## Your Task
Research and verify the charitable giving of **{BILLIONAIRE_NAME}** (net worth: ${NET_WORTH}B, country: {COUNTRY}, wealth source: {WEALTH_SOURCE}).

## What We're Looking For

### COUNTED as charitable giving:
- Foundation grants to EXTERNAL operating charities (from 990-PF filings)
- Direct gifts to nonprofits (universities, hospitals, museums, etc.)
- Stock donations to charities (SEC Form 4 code "G" to actual charities)
- DAF grants OUT to operating charities (rarely visible)

### NOT COUNTED:
- Foundation ASSETS (only count grants disbursed)
- Pledges (only count when money moves)
- Political donations (Super PACs, campaigns, dark money)
- Foundation transfers to their own DAF (parked, not deployed)
- Self-dealing grants to orgs they control for personal benefit
- Corporate foundation giving (unless clearly from personal wealth)
- Art collections/private museums structured as companies
- Court-mandated settlements or remediation

## Language & Regional Considerations

For non-US billionaires, search in their native language AND English:

| Country | Search Terms to Use |
|---------|---------------------|
| Germany | "Stiftung", "Spende", "Philanthropie", "Wohltätigkeit" |
| France | "Fondation", "Don", "Mécénat", "Philanthropie" |
| Spain/LatAm | "Fundación", "Donación", "Filantropía" |
| Italy | "Fondazione", "Donazione", "Filantropia" |
| China | "基金会" (foundation), "捐款" (donation), "慈善" (charity) |
| Japan | "財団" (foundation), "寄付" (donation), "慈善事業" |
| India | Foundation, charitable trust, CSR spending |
| Russia | "Фонд", "Благотворительность", "Пожертвование" |
| Brazil | "Fundação", "Doação", "Filantropia" |

Also check regional philanthropy rankings:
- Hurun China Philanthropy List
- EdelGive Hurun India Philanthropy List
- Forbes Asia Heroes of Philanthropy
- Chronicle of Philanthropy (US focus)

## Research Steps

1. **Search for their foundation(s)**
   - US: ProPublica Nonprofit Explorer, Grantmakers.io, Candid
   - Look for "[Name] Foundation", "[Name] Family Foundation", "[Name] Charitable Trust"
   - Get CUMULATIVE GRANTS over all years, not just annual or assets

2. **Check SEC Form 4 for stock gifts**
   - SEC EDGAR for transaction code "G" (gift)
   - Note: Stock to own foundation is funding, not external giving
   - Stock to DAF sponsors (Fidelity, Schwab, Vanguard) is parked

3. **Search for announced major gifts**
   - Chronicle of Philanthropy, university announcements
   - Hospital/medical center naming gifts
   - Museum, arts, cultural institution gifts
   - Verify amounts are ACTUAL gifts, not pledges

4. **Check for DAF usage**
   - Look for grants to: Fidelity Charitable, Schwab Charitable, Vanguard Charitable, Silicon Valley Community Foundation, National Philanthropic Trust
   - This is PARKED giving - note separately

5. **Check Giving Pledge status**
   - givingpledge.org - are they a signatory?
   - Note: Pledge is intention, not action

## Output Format

Return a JSON object with this structure:

```json
{
  "name": "{BILLIONAIRE_NAME}",
  "total_lifetime_giving_millions": <number>,
  "giving_breakdown": {
    "foundation_grants": <number or "unknown">,
    "university_gifts": <number or 0>,
    "hospital_gifts": <number or 0>,
    "direct_gifts": <number or 0>,
    "daf_transfers": <number or 0>,
    "other": <number or 0>,
    "notes": "<detailed research notes explaining each source>"
  },
  "verification": {
    "990_pf": {
      "status": "found|not_found|not_applicable",
      "amount_millions": <number or null>,
      "note": "<foundation name, EIN if found, years covered>",
      "url": "<ProPublica or source URL>"
    },
    "sec_form4": {
      "status": "found|not_found|not_applicable",
      "amount_millions": <number or null>,
      "note": "<description of stock gifts found>",
      "url": "<SEC EDGAR URL>"
    },
    "foundation_reports": {
      "status": "found|not_found|not_applicable",
      "amount_millions": <number or null>,
      "note": "<cumulative grants from Grantmakers.io or annual reports>",
      "url": "<source URL>"
    },
    "news_verified": {
      "status": "found|not_found",
      "amount_millions": <number or null>,
      "note": "<specific announced gifts with amounts>",
      "url": "<news source URL>"
    }
  },
  "sources": ["<url1>", "<url2>", ...],
  "giving_pledge": "yes|no|partial|99% pledge",
  "confidence": "HIGH|MEDIUM|LOW",
  "red_flags": ["<any concerns about data quality>"]
}
```

## Critical Rules

1. **Be specific** - Don't say "substantial giving" without amounts
2. **Distinguish assets vs grants** - A $10B foundation with $500M grants = $500M giving
3. **Track DAF separately** - Foundation→DAF transfers are parked, not deployed
4. **Verify, don't assume** - Round numbers ($100M, $500M) often indicate estimates, not verified data
5. **Note country limitations** - Non-US foundations often have minimal disclosure
6. **Include sources** - Every claim needs a URL

## Common Pitfalls to Avoid

- Counting foundation ASSETS as giving (only count GRANTS)
- Counting pledges before disbursement
- Missing that a "charitable foundation" is actually a DAF
- Conflating corporate giving with personal giving
- Assuming Giving Pledge signers have given substantially (many haven't)
- Double-counting (stock gift → foundation → charity)
