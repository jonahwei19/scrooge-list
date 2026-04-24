# Scrooge List — Publish Plan

**Date:** 2026-04-23
**Status:** Rebuild-to-publish. Current pipeline is mostly hardcoded seed data; not publishable.

---

## The blunt findings (from 4 parallel research agents)

### Audit of current code
- **97.8% of 3,163 billionaires score ≥90** because anyone not in a hardcoded `KNOWN_*` dict defaults to $0 observable → score 100. Bimodal, not real.
- **`sources_used` field is EMPTY** in `docs/scrooge_latest.json` for all 3,163 records. Per-billionaire research files (`data/*.json`) have URLs, but the aggregation strips them.
- **CLAUDE.md falsely claims "Brave Search API for each billionaire."** Brave is never called. `run_research.py` is a stub that prints "NEEDS RESEARCH."
- **`main.py` v1 is what actually produces output.** `pipeline_v2.py` and `full_pipeline.py` are skeletons.
- **`bs_checker.py` is circular** — validates the hardcoded dicts against themselves.
- **`data_quality: "HIGH"` is hardcoded** on every record, regardless of whether any research happened.

### What credible publishers actually do
- **Forbes Philanthropy Score:** 1–5 scale, lifetime out-the-door / net worth. Doesn't publish dollar figures per person. Criticized by IPS/Inside Philanthropy for letting foundations game "out-the-door."
- **Chronicle of Philanthropy 50:** Counts gifts *into* foundations/DAFs, explicitly only top-50 transparent givers. Punts on opaque donors by not ranking them.
- **Bloomberg:** 1–5 star *confidence* ratings on wealth (not giving). Excludes unverifiable assets rather than estimating.
- **IPS Giving Pledge at 15 (July 2025):** Only 9 of 256 pledgers have fulfilled; 32 living US pledgers are 283% wealthier than at signing; ~80% of pledger contributions flow to foundations/DAFs (intermediaries).
- **Bank of America/Lilly HNW Study 2024:** 69% of older HNW donors give anonymously at least sometimes.
- **NPT 2025 DAF Report:** $326B in DAFs, 25.3% payout; 27% of all individual charitable dollars now flow to DAFs.

### The unavoidable error bar
Observable 990/public-announcement giving plausibly captures **40–70% of true lifetime giving** for a US billionaire. The residual is DAFs, LLCs, anonymous, religious, foreign, and dynasty-trust giving. No credible ranking can claim full coverage.

### Non-US gap
With the current US-only stack, Arnault ≈ $0, Ambani ≈ $0, MBS ≈ $0, Tencent/Alibaba founders ≈ $0 — all materially wrong. Three source adds close ~80% of this gap: **Hurun Philanthropy List (China), ICIJ Offshore Leaks bulk import, Candid Premier + press scraping** of Alliance Magazine / Les Echos / Nikkei / The National.

### Defamation
- US public-figure standard = actual malice. Precedent is in our favor (Trump v. O'Brien 2011 — sourced estimates survive summary judgment).
- No known successful suit against Forbes, Bloomberg, or IPS on giving lists.
- **Single most effective defense:** pre-publication right-of-reply to every named subject. This directly rebuts reckless-disregard claims.
- Safe language: "We identified $X in publicly documented giving" NEVER "they have given only $X." Rhetorical hyperbole ("stingy") is protected as long as it rests on disclosed facts.

---

## Product shape (the actually-publishable version)

**Scope down. Drop the "rank all 3,163 billionaires" goal — it's fraudulent with available data.**

Replace with a tiered approach:

### Tier A — The Scrooge List (top 20–30)
- Only US billionaires where we have HIGH-confidence observable-giving data AND we can bound hidden-giving capacity tightly.
- Ranked ordinally ONLY where confidence intervals don't overlap (Bloomberg-style).
- Every dollar cited with source URL + retrieval date.
- Pre-publication outreach to every named subject; their response (or "declined") published verbatim.

### Tier B — "Probably Low" (next 50–100)
- Low observable giving + presence of at least one opaque vehicle (DAF, LLC, offshore trust).
- NOT ranked ordinally. Presented alphabetically or by net worth.
- Framed as "we can't verify their giving is higher; here's what we see."

### Tier C — "Unverifiable" (everyone else)
- Listed with a disclaimer and a form for "add a citation."

### Per-person profile
- Headline: net worth, observable giving, ratio, tier.
- **Detected giving vehicles:** foundation (EIN), DAF evidence, LLC, offshore entity, pledge status. Each is a dimension of hidden-giving capacity.
- **Timeline of cited gifts** (pledge date ≠ payment date — shown separately).
- **Confidence interval** (`observable` to `observable + estimated_hidden_upper`).
- **Red flags** (low payout, high officer comp, DAF-heavy grants).
- **Right-of-reply box** — either subject's response or "no response to 2026-MM-DD outreach."
- **Source log** — every citation, timestamped.

### Methodology page (docs/methodology.html)
- Explicitly discloses exclusions (following Chronicle's model).
- Publishes the confidence-bound model with citations.
- Changelog for corrections.

---

## Deduplication rules (the hard problem)

These are the cross-category collisions we must handle:

1. **Pledge ≠ payment.** Buffett's annual Berkshire transfer to Gates Foundation is a payment; the Giving Pledge signed in 2010 is the *commitment* — don't double-count.
2. **Foundation contribution ≠ foundation out-the-door.** Zuckerberg transferring $5B of stock to CZI Foundation is an "into" event; CZI's grants out are separate. Forbes credits out-the-door only; IPS credits neither and prefers "terminal giving."
3. **Announced gift ≠ subsequent filed gift.** A WSJ story about "Ellison gives $100M to USC" may show up later in USC's 990, in SEC Form 4, and in the Ellison Foundation's 990. Three rows, one event.
4. **DAF-routed gift.** A gift the donor announces publicly that is actually routed through their DAF — counted in donor's direct-giving category, not DAF opacity.
5. **Multi-year pledge.** $1B over 10 years appears as one news event; payments trickle across 10 years of 990s. Chronicle counts as lump in announcement year; IRS/990 counts as paid year.

**The fix:** canonical-event deduplication. Every gift line-item gets:
- `canonical_event_id` (hash of donor + recipient + month + rounded-amount)
- `source_type` (announcement / 990 / SEC Form 4 / state registry / etc.)
- `event_role` (pledge / payment / transfer-into / grant-out)
- Rolled up per donor with rules: only one "payment" role per canonical event counts toward observable giving.

---

## Scoring formula v3

Drop the continuous 0–100 score as published headline — use it internally only. Publish tiers.

**Observable giving (primary signal):**
```
observable = sum(cited_gifts) where event_role in {payment, grant-out, direct-gift}
           + sum(pledge-fulfillment-adjusted pledges for deceased pledgers)
```

**Hidden-giving capacity (uncertainty):**
```
hidden_upper = 0
if has_DAF:    hidden_upper += 0.005 × net_worth    # cohort DAF-share adjusted
if has_LLC:    hidden_upper += 0.01  × net_worth    # we literally cannot see
if has_offshore_entity: hidden_upper += 0.01 × net_worth
if known_religious_affiliation: hidden_upper += 0.02 × liquid_wealth × years_as_billionaire
# (these coefficients are cohort estimates from BofA/Lilly + NPT + IPS)
```

**Expected giving (denominator):**
```
expected = 0.10 × liquid_wealth × min(years_as_billionaire / 10, 1)
```

**Tier classification (the published output):**
```
if observable / expected > 1.0:                                         → "On track" (not Scrooge)
elif observable / expected > 0.5:                                       → "Moderate"
elif (observable + hidden_upper) / expected < 0.2 AND has_clean_denom:  → "Verified Low" (Tier A)
elif observable / expected < 0.2:                                       → "Probably Low" (Tier B)
else:                                                                   → "Unverifiable"
```

Only Tier A gets ranked ordinally. Ranking is by `(observable + hidden_upper) / expected`, ascending.

---

## Execution phases

### Phase 0 — Ground truth (start here, small batch)
- **0.1** Pick ONE billionaire (Larry Ellison — top of current list) and build the reference implementation end-to-end. Every dollar cited with URL. Output: `data/larry_ellison.v3.json`. If Ellison's ratio really is ~0.4%, the thesis survives first contact. If it moves materially with better search, the current list is garbage.
- **0.2** Validate the profile-page schema against this one record before writing any scrapers.

### Phase 1 — Real pulls for US cohort
- **1.1** Real ProPublica 990-PF integration (EIN + fuzzy name match, not a hardcoded list). Use the bulk `.jsonl` dumps, not the web search.
- **1.2** Real SEC Form 4 G-transaction parser (donor → recipient entity CIK + amount). Not hardcoded.
- **1.3** Real FEC API (get an actual API key; DEMO_KEY rate-limits out).
- **1.4** Giving Pledge scrape + IPS 2025 dataset import (the 9-of-256-fulfilled dataset).
- **1.5** Brave Search-based press discovery per billionaire → LLM extraction into canonical-event rows.

### Phase 2 — Global cohort
- **2.1** Hurun Philanthropy List scraper (annual, China cohort).
- **2.2** ICIJ Offshore Leaks bulk import (name-match Forbes list → flag vehicles).
- **2.3** UK Charity Commission, Canada T3010, Australia ACNC bulk loaders (foundation-enumeration for billionaires, even if donor-name fields are empty).
- **2.4** Press scrapers: Alliance Magazine (English global), Les Echos (French), Nikkei (Japanese), The National (UAE).

### Phase 3 — Deduplication + classification
- **3.1** Canonical-event deduplication (hash + LLM reconciliation for fuzzy matches).
- **3.2** Hidden-giving capacity model (per-vehicle uplift coefficients; documented).
- **3.3** Tier classifier (A/B/C).

### Phase 4 — Publishing infrastructure
- **4.1** Per-person profile page template (every dollar = clickable source).
- **4.2** Methodology page (`docs/methodology.html` — already has a skeleton).
- **4.3** Right-of-reply workflow: generate outreach email per Tier-A subject; intake their response; publish verbatim.
- **4.4** Changelog / corrections page.
- **4.5** Legal review (self-review against defamation checklist; consider outside counsel for Tier A).

### Phase 5 — Publish
- **5.1** Tier A (top 20) only as first release.
- **5.2** Tier B as "work in progress" section.
- **5.3** Tier C hidden behind "methodology + invite corrections" frame.

---

## Non-goals

- Ranking the full Forbes 3,163 ordinally. Not doing it.
- Per-person 100-point "Scrooge Score." Internal only.
- Claiming coverage of giving through anonymous/religious/foreign channels. We explicitly don't.
- Shipping the current v1 pipeline's output as-is. Don't.

---

## Open questions for Jonah

1. **Scope:** start with US-only Tier A (top 20), or include global? Global adds ~2 weeks for Hurun+press scrapers. US-only is 3–5 days of focused work.
2. **Budget:** Altrata Wealth-X is ~$50–250K/yr and genuinely collapses the global gap. Free stack covers ~60%. Any budget?
3. **Voice:** Hard-edged ("Billionaires hiding their hoards") or restrained/empirical ("Observable giving, tiered by certainty")? Affects legal posture.
4. **Right-of-reply:** 1-week outreach window before publish? Longer?
5. **Publishing venue:** GitHub Pages (current) is fine for draft. For launch, consider Substack cross-post + explicit data access.
