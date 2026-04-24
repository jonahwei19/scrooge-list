# Scrooge List — Memory

## State as of 2026-04-24 (after v3 publish build)

**v3 build shipped.** 21 US billionaires researched end-to-end via parallel subagents; each has a `data/<slug>.v3.json` with every dollar URL-cited. Aggregated into `docs/scrooge_latest_v3.json` and per-subject `docs/profiles/<slug>.json`. Tier-based index + profile + methodology HTML is live.

**Tier distribution (v3):**
- Tier A Verified Low (2): Elon Musk ($811B NW, $500M obs, 4.1% of benchmark), Larry Page
- Tier B Probably Low (11): Ellison, Bezos, Brin, Huang, Ballmer, Schwarzman, Koch, Rob/Jim/Alice Walton, Griffin
- Tier C Opaque (1): Zuckerberg (CZI LLC)
- On Track (7): Buffett, Scott, Bloomberg, Dell, Knight, Dalio, Moskovitz

**Legacy v1/v2 state (still do not trust):**
- `docs/scrooge_latest.json` (v1/v2) — still present but misleading; 97.8% of records scored ≥90 because non-hardcoded billionaires defaulted to $0 observable.
- `main.py` + `stages/` — hardcoded seed pipeline; do not re-run.
- Original `CLAUDE.md` claims "Brave Search API" — false; never integrated in v1/v2.
- `bs_checker.py` — circular verification, do not use as evidence.
- DEMO_KEY for FEC in v1 — real key still needed if political pipeline is re-run.

**v3 tooling:**
- `aggregate_v3.py` — reads data/*.v3.json, normalizes tier strings (explicit-bracket-priority regex), writes docs/scrooge_latest_v3.json + copies per-subject JSON to docs/profiles/
- `generate_outreach.py` — builds one plain-text right-of-reply email per Tier A/B subject to `outreach/<slug>.txt`
- Parallel research agent prompts (referenced in git log) — each took ~5 min, dispatched 10 + 8 + 2 in three waves
- Every v3 record has `sources_all` array with URL + retrieved_at for every finding

## Publishability bar (from research agents)

- Every dollar of observable giving must have a source URL + retrieval date, surfaced in the published per-person profile.
- Tier-based classification (Verified Low / Probably Low / Unverifiable), NOT ordinal ranking of all 3,163.
- Pre-publication right-of-reply to every Tier-A named subject — single strongest defamation defense.
- Methodology page must explicitly disclose exclusions (DAFs, LLCs, anonymous, religious, foreign).
- Language: "We identified $X in documented giving" — NEVER "X has given only $Y."

## Published baselines to compare against

- **Forbes Philanthropy Score:** 1–5 scale; lifetime out-the-door / net worth; no per-person dollars published.
- **Chronicle of Philanthropy 50:** Top-50 only, explicitly opt-in transparent givers. MacKenzie Scott absent because she won't disclose DAF inflows.
- **Bloomberg:** 1–5 star confidence ratings on *wealth* (not giving). Excludes unverifiable assets.
- **IPS Giving Pledge at 15 (July 2025):** Only 9/256 pledgers fulfilled; ~80% of pledger contributions flow to intermediaries.
- **NPT 2025 DAF Report:** $326B in DAFs; 25.3% payout; 27% of individual giving now flows to DAFs.

## Honest error bar

Observable US 990/announcement giving captures ~40–70% of true lifetime giving. Residual is DAFs + LLCs + anonymous + religious + foreign + dynasty trusts.

## Defamation posture

- US public-figure standard: actual malice. Sourced estimates survive (Trump v. O'Brien 2011).
- No successful suit against Forbes/Bloomberg/IPS on giving lists.
- Protected: rhetorical hyperbole ("stingy") backed by disclosed facts.
- Not protected: categorical factual claims ("gave nothing") where anonymous giving is plausible.

## Non-US gap

With US-only stack, Arnault/Ambani/MBS/Tencent founders all show ~$0 — materially wrong.
**Three source adds close ~80%:** Hurun Philanthropy List (China), ICIJ Offshore Leaks bulk (global vehicle detection), Candid Premier + press scraping (Alliance Magazine, Les Echos, Nikkei, The National).

## Canonical deduplication rules

1. Pledge ≠ payment.
2. Foundation contribution ≠ foundation out-the-door.
3. Announced gift ≠ subsequent filed gift (same event, multiple sources).
4. DAF-routed announced gift = direct gift, not DAF opacity.
5. Multi-year pledge: lump in announce year (Chronicle) OR paid per 990 year (IRS) — pick one, document it.

## Key files (current)

**v3 (trusted):**
- `data/*.v3.json` — 21 per-subject research records, source-cited
- `docs/scrooge_latest_v3.json` — aggregated cohort; front-end reads this
- `docs/profiles/*.json` — per-subject JSON served to profile.html
- `docs/index.html` — tier-based ledger (v3)
- `docs/profile.html` — per-subject page
- `docs/methodology.html` — honest exclusion-first methodology
- `aggregate_v3.py` — aggregator
- `generate_outreach.py` — outreach email generator
- `outreach/*.txt` — 13 generated right-of-reply emails
- `PLAN.md` — full rebuild plan

**v1/v2 legacy (do not use):**
- `main.py` + `stages/` — hardcoded pipeline
- `pipeline_v2.py` + `run_research.py` + `full_pipeline.py` — three incomplete rewrites
- `docs/scrooge_latest.json` — v1 data; superseded by `_v3.json` (keep for historical diff only)

## Anti-patterns to avoid

- Don't add more hardcoded dicts. Every new fact needs a source URL.
- Don't rank Tier B/C ordinally. Only Tier A is ranked, and only where CIs don't overlap.
- Don't claim full coverage. The published methodology page must state the observable-only frame.
- Don't ship without right-of-reply. Even 1 week of outreach before publish beats the alternative.
