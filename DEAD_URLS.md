# Dead URL triage — v3 cohort

Output of `python3 check_urls.py --timeout 6 --workers 12` run against all 51
records. Full log archived at commit time; classification below.

**Summary: 1022 / 1224 unique URLs live (83.5%) after re-run with Safari UA.**

Initial run under `ScroogeListURLCheck/1.0` UA showed 80.3% live (241 dead).
Re-run under `Mozilla/5.0 ... Safari/605.1.15` UA showed 83.5% live
(202 dead) — the delta is bot-blocking, not rotted content. The 17 × 404
results are consistent across both runs and represent the triage set below.

| Status | Count | Meaning | Action |
|---|---|---|---|
| 200–399 | 983 | Live | OK |
| **404** | **19** | **Not found — rotted, moved, or fabricated** | **Review each below** |
| 403 | 180 | Bot-blocked (Bloomberg, OpenSecrets, etc.) | Likely real; set browser UA or accept |
| 401 | 8 | Paywall / login required | URL real, reader won't see content |
| 406 | 7 | UA negotiation issue | URL real |
| 429 | 4 | Rate limit | URL real |
| TIMEOUT | 21 | Network/slow endpoint | URL probably real |
| SSL / 503 | 2 | Transient | URL real |

## 404s — must review before publish

### Likely fabricated by research agents (high-concern)

These URLs do not resolve and the slug structure looks made-up. Do not
publish as sources without replacement.

1. `https://nationaltoday.com/us/ar/harrison-ar/news/2026/04/13/peterffy-foundation-steers-billionaires-wealth-toward-environmental-causes/`
   **Thomas Peterffy**, `sources_all[17]`. Path structure (`/us/ar/harrison-ar/`)
   doesn't match how nationaltoday.com organizes content. Likely hallucinated.
2. `https://safehaven.org/safe-haven-family-shelter-receives-1-25-million-bezos-day-1-families-fund-grant-to-end-homelessness/`
   **Jeff Bezos**, `sources_all[22]`. Plausible-looking slug, but doesn't resolve.
3. `https://heartlandforward.org/case-study/championing-the-doers-philanthropy-as-a-toolkit-for-economic-creation/`
   **Lukas Walton**, `sources_all[29]`. Case-study slug is oddly specific.
4. `https://www.cmc.edu/news/kravis-foundation-75-million-gift-announced/9266`
   **Henry Kravis**, `sources_all[14]`. Numeric ID at end suggests WordPress;
   CMC's actual news URLs use a different structure.

### Giving Pledge 404s — correct-for-wrong-reason

These 404 because the subject never signed the pledge. The URL shouldn't
have been cited as a source of anything — its absence is the point.
Replace with a footnote about confirmed non-signing.

5. `https://www.givingpledge.org/pledger/haim-saban/` — **Haim Saban** (no pledge)
6. `https://www.givingpledge.org/pledger/henry-kravis/` — **Henry Kravis** (no pledge)

### InsidePhilanthropy — 7 URLs, all 404

Tested both `-html` suffix and `.html` rewrite variants; both return 404 for
Barry Diller. Initial hypothesis (malformed-slug bug) does not hold. These
URLs appear to be **agent-fabricated** — the slug patterns look plausible for
InsidePhilanthropy articles, but the articles don't exist.

Drop from `sources_all` unless a specific verified article replacement exists.

7. `insidephilanthropy.com/find-a-grant/major-donors/barry-diller-html` — Barry Diller
8. `insidephilanthropy.com/find-a-grant/major-donors/george-kaiser-html` — George Kaiser
9. `insidephilanthropy.com/find-a-grant/major-donors/ray-dalio-html` — Ray Dalio
10. `insidephilanthropy.com/home/2014-1-22-whos-the-harlem-childrens-zone-100-million-donor-html` — Stanley Druckenmiller
11. `insidephilanthropy.com/home/2014-12-18-rupert-murdoch-and-philanthropy-will-a-legendary-scrooge-cha-html` — Rupert Murdoch
12. `insidephilanthropy.com/home/2015-1-7-meet-the-billionaire-with-the-most-land-and-plenty-of-conser-html` — John Malone
13. `insidephilanthropy.com/home/2022-5-31-a-look-at-how-and-where-the-leon-and-toby-cooperman-family-foundation-gives` — Leon Cooperman

### CNBC — missing `.html` extension

14. `cnbc.com/2020/01/09/billionaire-barry-diller-us-should-get-rid-of-paid-political-ads` — Barry Diller (add `.html`)
15. `cnbc.com/2022/10/24/how-googles-former-ceo-eric-schmidt-helped-write-ai-laws-in-washington-without-publicly-disclosing-investments-in-a-i-start-ups.html` — Eric Schmidt (has `.html` — may just be retired)

### Other 404s — likely rotted content, not fabricated

16. `blogs.und.edu/uletter/2012/09/und-announces-14-million-in-private-public-partnership-funding-and-the-naming-of-the-harold-hamm-school-of-geology-and-geological-engineering-at-the-college-of-engineering-and-mines/` — Harold Hamm. 2012 university blog; may have rotated.
17. `philanthropy.com/article/melinda-french-gates-announces-where-1-billion-in_new-funds-will-go-to-help-women-and-girls` — Melinda French Gates. Odd underscore in slug (`in_new-funds`); possibly typo or paywall.
18. `opb.org/article/2025/12/16/oregon-phil-penny-knight-donation-ohsu-tops-charitable-list/` — Phil Knight. Dec 2025 article; may have been renamed.
19. `strivetogether.org/news/ballmer-group-pledges-60-million-strivetogether/` — Steve Ballmer. Plausible but unresolvable.

## Current enforcement

Every record with one of the 19 URLs has been annotated with
`source_verification_status: "dead_link_<reason>"`. The validator
(`validate_v3.py`) now errors on any source flagged `likely_fabricated`
and warns on any `dead_link_*` — so **`python3 validate_v3.py` will
exit non-zero until these are resolved**, which acts as the pre-publish
gate.

Three dollar-bearing events cite `likely_fabricated` URLs and are blocking:

- **Henry Kravis** $75M direct_gift_announced — CMC URL not found
- **Jeff Bezos** $106M grant_out — safehaven.org URL not found
- **Stanley Druckenmiller** $100M direct_gift — InsidePhilanthropy URL not found

Total value of events at risk: ~$281M.

## Recommended action (before publish)

1. Replace the source URL for each of the 3 dollar-bearing events with a
   verifiable citation, or remove the event entirely.
2. For the 7 InsidePhilanthropy URLs in `sources_all` (bibliography),
   drop or replace — these are the most likely fabrications.
3. Spot-check the `rotted` URLs via archive.org for recovery.
4. Re-run `check_urls.py` and `validate_v3.py` until both are clean.
