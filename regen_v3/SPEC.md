# regen_v3 — Reproducible URL-Search Regenerator

**Goal.** Replace hand-curated `data/<subject>.v3.json` records with a deterministic
pipeline driven by web search. NOT a ProPublica/SEC/FEC API integration —
this is the "URL searching, standard and reproducible" path.

Same input (subject id + query plan) ⇒ same output. Cache everything.

## Pipeline

```
subject_id ──► queries.py ──► search.py ──► verify.py ──► extract.py ──► merge.py ──► data/<subject>.v3.json
                  │              │              │             │              │
              query plan    Brave API +     URL liveness   Anthropic API   merge with existing
              (per role)    disk cache      (browser UA)   structured tool   manual events
```

Each stage caches output keyed by sha256 of input. Re-runs are free.

## Module map (no overlap)

| File | Owner | Responsibility |
|---|---|---|
| `regen_v3/queries.py` | A1 | Per-subject query plan: `(role, query_string, priority)` tuples. Deterministic. |
| `regen_v3/search.py` | A2 | Brave Search REST wrapper + `regen_v3/cache/search/<sha>.json`. |
| `regen_v3/verify.py` | (host) | URL liveness pre-filter. Reuses `check_urls.check_one`. |
| `regen_v3/extract.py` | A3 | URL+snippet → structured event candidate via Anthropic API (temp=0). Cache by URL sha. |
| `regen_v3/merge.py` | A4 | Merge candidates into existing v3 record. Dedupe. Update provenance. |
| `regen_v3/cli.py` | (host) | Top-level orchestration (`python3 -m regen_v3 --subject henry_kravis`). |
| `regen_v3/cache/` | — | Gitignored. `search/` + `extract/` subdirs. |

## Canonical event_role enum (from `aggregate_v3.CANONICAL_EVENT_ROLES`)

```
grant_out, direct_gift, transfer_in, pledge, no_pledge, announcement,
political, private_investment, corporate_gift, reference_only
```

Observable (count toward giving total): `grant_out`, `direct_gift` only.

## Per-subject query plan (queries.py output shape)

```python
[
  {"role": "pledge",      "query": '"Henry Kravis" "giving pledge"',                "priority": 1},
  {"role": "no_pledge",   "query": '"Henry Kravis" "did not sign" "giving pledge"',  "priority": 2},
  {"role": "grant_out",   "query": '"Marie-Josée and Henry R. Kravis Foundation"',  "priority": 1},
  {"role": "grant_out",   "query": 'Kravis Foundation 990-PF',                       "priority": 2},
  {"role": "direct_gift", "query": '"Henry Kravis" donates million',                 "priority": 1},
  {"role": "direct_gift", "query": '"Henry Kravis" gift OR donation',                "priority": 2},
  {"role": "announcement","query": '"Henry Kravis" pledges OR commits OR announces', "priority": 1},
  {"role": "political",   "query": '"Henry Kravis" FEC contribution',                "priority": 2},
  ...
]
```

~12-15 queries per subject. Pull subject metadata (name, foundation names, spouse,
EIN if known) from existing `data/<subject>.v3.json` `person` and `detected_vehicles`
blocks.

## Search result shape (search.py)

```json
{
  "query": "...",
  "retrieved_at": "2026-04-25T17:32:11Z",
  "results": [
    {"url": "...", "title": "...", "description": "...", "age": "..."},
    ...
  ],
  "_cache_key": "<sha256>",
  "_provider": "brave-search-api-v1"
}
```

Top 10 per query. Cached forever (re-fetch only if `--refresh`).

## Domain filter (search.py)

**Allowlist** (high signal): forbes.com, reuters.com, bloomberg.com, cnbc.com,
philanthropy.com (Chronicle of Philanthropy), wsj.com, nytimes.com, washingtonpost.com,
opb.org, npr.org, propublica.org, candid.org, foundationcenter.org,
*.edu (university press), 990pf-related domains, fec.gov, sec.gov, irs.gov,
givingpledge.org, givinginstitute.org.

**Blocklist** (proven-fabricated or low-signal): insidephilanthropy.com,
nationaltoday.com, safehaven.org (when slug looks fabricated), heartlandforward.org
(case-study slugs), and explicit URLs in `DEAD_URLS.md` listed as `likely_fabricated`.

**Pass-through**: everything else flows through but gets `confidence: medium` or lower
in extraction.

## Extractor contract (extract.py)

Input: `{url, title, snippet, role_hint, subject_name}` (+ optional fetched page text)
Output: 0..N candidate events:

```json
{
  "event_role": "grant_out",            // canonical enum
  "year": 2024,
  "date": "2024-03-15",                  // optional, ISO-8601
  "date_precision": "month|year|day",
  "donor_entity": "string",
  "recipient": "string",
  "amount_usd": 75000000,                // null if not stated
  "source_type": "press_release | news_article | 990-PF | sec_filing | university_press",
  "source_url": "(echoed from input)",
  "confidence": "high|medium|low",
  "extraction_note": "1 sentence on what the snippet actually said",
  "extraction_evidence": "verbatim snippet substring under 30 words"
}
```

Use Anthropic Claude (`claude-haiku-4-5`) with **temperature=0**, structured tool use
(`extract_event` tool with the schema above). If Anthropic API key absent, exit with
clear error — don't fall back to regex (would defeat reproducibility claim).

Cache results keyed by `sha256(url + snippet + role_hint)`. Same input ⇒ same output.

## Merge contract (merge.py)

Input: existing `data/<subject>.v3.json` + list of candidate events.

Behavior:
1. **Preserve manual events.** Anything tagged `provenance: "manual"` (or unprefixed with provenance) stays. Candidates do not overwrite manual entries.
2. **Dedupe candidates** by `(amount_usd, year, event_role)`. Tolerance: 5% on amount.
3. **Annotate provenance** on every new event:
   ```json
   "provenance": "regen_v3",
   "regen_run_id": "<utc-iso>",
   "regen_query": "(query string that surfaced this URL)",
   "regen_extractor_model": "claude-haiku-4-5"
   ```
4. **Update top-level**: append `regen_v3` to `generated_by` (e.g., `"manual + regen_v3@2026-04-25"`).
5. **Bibliography**: every URL discovered (even if extraction yielded no event) goes to `sources_all` with `regen_v3` provenance.
6. **Refuse to write** if any candidate has `source_url` matching a `DEAD_URLS.md likely_fabricated` entry.

## CLI (cli.py)

```
python3 -m regen_v3 --subject henry_kravis              # full pipeline, write merged record
python3 -m regen_v3 --subject henry_kravis --dry-run    # don't write, print diff
python3 -m regen_v3 --subject henry_kravis --candidates-only  # stop after extract.py, dump candidates JSON
python3 -m regen_v3 --all                                # all 51 subjects
python3 -m regen_v3 --refresh                            # bypass search cache
python3 -m regen_v3 --replace-fabricated                 # only run for subjects flagged in DEAD_URLS.md
```

Exits non-zero if validate_v3.py fails on the merged record.

## Reproducibility checklist

- [ ] Search cache key = sha256(query). Query plan deterministic per subject.
- [ ] Extractor temperature = 0. Cache keyed on full input.
- [ ] Merge dedupe is total order: `(year, role, amount_usd)`. Stable sort.
- [ ] All timestamps written as UTC ISO-8601.
- [ ] No randomness in any layer.

## Out of scope (do NOT do)

- Page-content scraping beyond what Brave returns in snippets (let extractor work from snippet + URL alone for v1; can fetch page later if needed).
- ProPublica / SEC EDGAR / FEC API calls. That's a separate route.
- LLM-driven query generation. Queries are templated.
- Any auto-publish or commit. Always stops at write-to-disk.
