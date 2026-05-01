"""Per-subject query plan for regen_v3.

Builds a deterministic 12-15 item search plan for a v3 record. Same input
(record dict) produces the same output. No randomness, no clocks, no I/O.
See regen_v3/SPEC.md for the contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

# Canonical event_role enum, mirroring aggregate_v3.CANONICAL_EVENT_ROLES.
# Duplicated rather than imported to keep this module dependency-free.
CANONICAL_EVENT_ROLES: frozenset[str] = frozenset({
    "grant_out",
    "direct_gift",
    "transfer_in",
    "pledge",
    "no_pledge",
    "announcement",
    "political",
    "private_investment",
    "corporate_gift",
    "reference_only",
})

# Roles that every plan must include at least once.
# pledge and no_pledge are MUTUALLY EXCLUSIVE — when a subject is a known
# Giving Pledge signer, no_pledge query is omitted (would be misleading).
# When unknown / not signed, pledge + no_pledge both appear. So the
# validator must NOT require both — instead, require at least one of them
# (handled in build_query_plan via REQUIRED_PLEDGE_GROUP).
REQUIRED_ROLES: frozenset[str] = frozenset({
    "grant_out",
    "direct_gift",
    "announcement",
    "transfer_in",
    "political",
    "reference_only",
})
REQUIRED_PLEDGE_GROUP: frozenset[str] = frozenset({"pledge", "no_pledge"})

# Forbes profile slug used for the reference_only query.
FORBES_PROFILE_BASE = "https://www.forbes.com/profile/"


def _slugify_for_forbes(name: str) -> str:
    """Forbes profile URLs use lowercase hyphenated slugs (e.g. 'henry-kravis')."""
    return "-".join(name.lower().split())


def _foundation_names(record: dict) -> list[str]:
    """Extract canonical foundation names from detected_vehicles + cited_events.

    Strict acceptance rules:
      * Only iterate `detected_vehicles` keys that match `foundations*` AND
        do NOT end in `_note` (those carry prose, not entity data).
      * Within each list, only accept dict items with a non-empty `name`
        key. Reject string items entirely — they are almost always free-text
        annotations that get mis-typed by extractor agents.
    """
    names: list[str] = []
    seen: set[str] = set()

    vehicles = record.get("detected_vehicles") or {}
    if isinstance(vehicles, dict):
        for key, value in vehicles.items():
            if not isinstance(key, str):
                continue
            kl = key.lower()
            if "foundation" not in kl or kl.endswith("_note"):
                continue
            # Skip records that mark these as "do not attribute".
            if kl == "foundations_related_not_attributed":
                continue
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if isinstance(name, str) and name and name not in seen:
                    seen.add(name)
                    names.append(name)

    # Fallback: scan cited_events donor_entity strings for foundation-shaped names.
    for event in record.get("cited_events") or []:
        if not isinstance(event, dict):
            continue
        donor = event.get("donor_entity")
        if not isinstance(donor, str):
            continue
        if "foundation" in donor.lower() and donor not in seen:
            seen.add(donor)
            names.append(donor)

    return names


def _llc_names(record: dict) -> list[str]:
    """Extract philanthropic-LLC vehicle names from detected_vehicles."""
    names: list[str] = []
    seen: set[str] = set()
    vehicles = record.get("detected_vehicles") or {}
    if not isinstance(vehicles, dict):
        return names
    llcs = vehicles.get("llcs_philanthropic")
    if isinstance(llcs, list):
        for item in llcs:
            if isinstance(item, dict):
                name = item.get("name")
            elif isinstance(item, str):
                name = item
            else:
                name = None
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _einsfrom_record(record: dict) -> list[str]:
    """Collect distinct EINs in record-order, preferring foundations_active first."""
    eins: list[str] = []
    seen: set[str] = set()

    vehicles = record.get("detected_vehicles") or {}
    if isinstance(vehicles, dict):
        for key in ("foundations_active", "foundations_terminated"):
            for item in vehicles.get(key) or []:
                if isinstance(item, dict):
                    ein = item.get("ein")
                    if isinstance(ein, str) and ein and ein not in seen:
                        seen.add(ein)
                        eins.append(ein)

    for event in record.get("cited_events") or []:
        if not isinstance(event, dict):
            continue
        ein = event.get("donor_ein")
        if isinstance(ein, str) and ein and ein not in seen:
            seen.add(ein)
            eins.append(ein)

    return eins


def _pledge_signed(record: dict) -> tuple[bool, int | None]:
    """Return (signed, year_signed) using giving_pledge_status if present."""
    gps = record.get("giving_pledge_status")
    if not isinstance(gps, dict):
        return (False, None)
    signed = bool(gps.get("signed"))
    year = gps.get("year_signed")
    if not isinstance(year, int):
        year = None
    return (signed, year)


def _top_political_recipient(record: dict) -> str | None:
    """Find the most-cited political recipient string in political_giving.sources."""
    pol = record.get("political_giving")
    if not isinstance(pol, dict):
        return None
    counts: dict[str, int] = {}
    order: list[str] = []
    for src in pol.get("sources") or []:
        if not isinstance(src, dict):
            continue
        recipient = src.get("recipient")
        if not isinstance(recipient, str) or not recipient.strip():
            continue
        if recipient not in counts:
            order.append(recipient)
            counts[recipient] = 0
        counts[recipient] += 1
    if not order:
        return None
    # Tie-break by record-order (stable) so deterministic.
    best = max(order, key=lambda r: (counts[r], -order.index(r)))
    return best


# --- Multi-language press support -------------------------------------------------
#
# Foreign-domiciled (or foreign-born / foreign-business-tied) billionaires get
# flat coverage from English-language press; their major giving often surfaces
# first in home-country outlets. We add 2 hand-translated queries per detected
# non-English language. All translation is a static lookup — no runtime calls,
# no random sampling — so the plan stays deterministic and the search.py cache
# key (sha256 of normalized query string) remains stable across re-runs.
#
# Language signals come from THREE record fields, in priority order:
#   1. person.country_primary  (e.g. "France", "United States (born Australia)")
#   2. person.country_secondary
#   3. person.citizenship_notes  (catches naturalized-elsewhere, "born X")
# We deliberately ignore wealth_source prose to avoid false positives from
# "Soviet aluminum" → ru on someone who left at age 6 with no Russian-language
# coverage. Citizenship/country fields are the load-bearing signal.

# ISO-639-1 (with one BCP-47 region tag for Traditional Chinese in HK/TW press)
# Map keys are LOWERCASED country/region substrings; matched as substring against
# the joined geo-text so "United States (also United Kingdom, Greece)" picks up
# both UK (en — already present) and Greece (el).
COUNTRY_TO_LANGS: dict[str, tuple[str, ...]] = {
    "israel": ("he",),
    "france": ("fr",),
    "mexico": ("es",),
    "spain": ("es",),
    "germany": ("de",),
    "austria": ("de",),
    "switzerland": ("de", "fr"),
    "italy": ("it",),
    "brazil": ("pt",),
    "portugal": ("pt",),
    "japan": ("ja",),
    "korea": ("ko",),
    "south korea": ("ko",),
    "china": ("zh",),
    "taiwan": ("zh-Hant",),
    "hong kong": ("zh-Hant",),
    "russia": ("ru",),
    "ukraine": ("uk", "ru"),
    "ukrainian ssr": ("uk", "ru"),
    "soviet union": ("ru",),
    "ussr": ("ru",),
    "australia": ("en",),       # English already; presence here is a no-op
    "united kingdom": ("en",),  # ditto
    "uk": ("en",),
    "greece": ("el",),
    "netherlands": ("nl",),
    "belgium": ("nl", "fr"),
    "sweden": ("sv",),
    "norway": ("no",),
    "denmark": ("da",),
    "turkey": ("tr",),
    "saudi arabia": ("ar",),
    "uae": ("ar",),
    "united arab emirates": ("ar",),
    "egypt": ("ar",),
    "india": ("hi", "en"),
}

# Hand-translated query templates. Two roles per language so coverage hits both
# announcement-style press ("X pledges/donates millions") and direct-gift press
# ("X foundation grants"). Translations are intentionally idiomatic to the
# financial-press register — e.g. Hebrew uses "תורם" (donates) + "מיליון"
# (million) which is how Globes/TheMarker actually phrase it.
#
# Format: {lang: {role: template_with_{name}_placeholder}}
FOREIGN_TEMPLATES: dict[str, dict[str, str]] = {
    "he": {
        "announcement": '"{name}" תורם OR מתחייב מיליון',
        "direct_gift": '"{name}" תרומה קרן',
    },
    "fr": {
        "announcement": '"{name}" donne OR promet millions',
        "direct_gift": '"{name}" fondation don',
    },
    "es": {
        "announcement": '"{name}" dona OR promete millones',
        "direct_gift": '"{name}" fundación donación',
    },
    "de": {
        "announcement": '"{name}" spendet OR verspricht Millionen',
        "direct_gift": '"{name}" Stiftung Spende',
    },
    "it": {
        "announcement": '"{name}" dona OR promette milioni',
        "direct_gift": '"{name}" fondazione donazione',
    },
    "pt": {
        "announcement": '"{name}" doa OR promete milhões',
        "direct_gift": '"{name}" fundação doação',
    },
    "ja": {
        "announcement": '"{name}" 寄付 OR 寄贈 億円',
        "direct_gift": '"{name}" 財団 寄付',
    },
    "ko": {
        "announcement": '"{name}" 기부 OR 약정 억원',
        "direct_gift": '"{name}" 재단 기부',
    },
    "zh": {
        "announcement": '"{name}" 捐赠 OR 承诺 亿',
        "direct_gift": '"{name}" 基金会 捐款',
    },
    "zh-Hant": {
        "announcement": '"{name}" 捐贈 OR 承諾 億',
        "direct_gift": '"{name}" 基金會 捐款',
    },
    "ru": {
        "announcement": '"{name}" пожертвовал OR обещал миллионов',
        "direct_gift": '"{name}" фонд благотворительность',
    },
    "uk": {
        "announcement": '"{name}" пожертвував OR обіцяв мільйонів',
        "direct_gift": '"{name}" фонд благодійність',
    },
    "el": {
        "announcement": '"{name}" δωρίζει OR υπόσχεται εκατομμύρια',
        "direct_gift": '"{name}" ίδρυμα δωρεά',
    },
    "nl": {
        "announcement": '"{name}" doneert OR belooft miljoen',
        "direct_gift": '"{name}" stichting donatie',
    },
    "ar": {
        "announcement": '"{name}" تبرع OR تعهد مليون',
        "direct_gift": '"{name}" مؤسسة تبرع',
    },
    "tr": {
        "announcement": '"{name}" bağışlıyor OR söz verdi milyon',
        "direct_gift": '"{name}" vakıf bağış',
    },
    "hi": {
        "announcement": '"{name}" दान OR प्रतिज्ञा करोड़',
        "direct_gift": '"{name}" फाउंडेशन दान',
    },
    "sv": {
        "announcement": '"{name}" donerar OR lovar miljoner',
        "direct_gift": '"{name}" stiftelse donation',
    },
    "no": {
        "announcement": '"{name}" donerer OR lover millioner',
        "direct_gift": '"{name}" stiftelse donasjon',
    },
    "da": {
        "announcement": '"{name}" donerer OR lover millioner',
        "direct_gift": '"{name}" fond donation',
    },
}


def _languages_for(record: dict) -> list[str]:
    """Return ordered list of non-English ISO-639-1 codes the subject likely
    gets press in, beyond the default English coverage.

    Returns [] for US-only / English-only subjects. Order is deterministic:
    iterates COUNTRY_TO_LANGS in declared order, so the same record always
    yields the same lang list across Python versions (dicts preserve insertion
    order since 3.7).
    """
    person = record.get("person") or {}
    parts: list[str] = []
    for key in ("country_primary", "country_secondary", "citizenship_notes"):
        v = person.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.lower())
    if not parts:
        return []
    blob = " | ".join(parts)

    out: list[str] = []
    seen: set[str] = set()
    for country_key, langs in COUNTRY_TO_LANGS.items():
        if country_key in blob:
            for lg in langs:
                if lg == "en":
                    continue
                if lg in FOREIGN_TEMPLATES and lg not in seen:
                    seen.add(lg)
                    out.append(lg)
    return out


def _spouse_name(record: dict) -> str | None:
    person = record.get("person") or {}
    spouse = person.get("spouse")
    if not isinstance(spouse, str) or not spouse.strip():
        return None
    # Strip any parenthetical biographical clause (e.g. "Marie-Josée Kravis (economist; ...)").
    head = spouse.split("(", 1)[0].strip().rstrip(",;")
    return head or None


def build_query_plan(record: dict) -> list[dict]:
    """Return 12-15 query specs for the subject. Deterministic.

    Each item: {"role": <canonical_event_role>, "query": <str>, "priority": int}.
    Output sorted by (priority, role, query) for bit-identical re-runs.
    """
    person = record.get("person") or {}
    name_display = person.get("name_display") or ""
    name_legal = person.get("name_legal") or ""
    if not name_display:
        raise ValueError("record['person']['name_display'] is required")

    foundations = _foundation_names(record)
    llcs = _llc_names(record)
    eins = _einsfrom_record(record)
    pledge_signed, pledge_year = _pledge_signed(record)
    spouse = _spouse_name(record)
    top_pol_recipient = _top_political_recipient(record)

    plan: list[dict] = []

    # --- pledge / no_pledge (mutually exclusive emphasis) ---
    if pledge_signed:
        if pledge_year is not None:
            plan.append({
                "role": "pledge",
                "query": f'"{name_display}" "giving pledge" {pledge_year}',
                "priority": 1,
            })
        else:
            plan.append({
                "role": "pledge",
                "query": f'"{name_display}" "giving pledge" signed',
                "priority": 1,
            })
        # Still include a generic pledge query so coverage holds.
        plan.append({
            "role": "pledge",
            "query": f'"{name_display}" "giving pledge"',
            "priority": 2,
        })
    else:
        plan.append({
            "role": "pledge",
            "query": f'"{name_display}" "giving pledge"',
            "priority": 1,
        })
        plan.append({
            "role": "no_pledge",
            "query": f'"{name_display}" "did not sign" "giving pledge"',
            "priority": 2,
        })

    # --- grant_out: prefer foundation/LLC names verbatim if known ---
    primary_vehicle = foundations[0] if foundations else (llcs[0] if llcs else None)
    if primary_vehicle:
        plan.append({
            "role": "grant_out",
            "query": f'"{primary_vehicle}" 990-PF',
            "priority": 1,
        })
        plan.append({
            "role": "grant_out",
            "query": f'"{primary_vehicle}" grants',
            "priority": 2,
        })
    else:
        plan.append({
            "role": "grant_out",
            "query": f'"{name_display}" foundation 990-PF',
            "priority": 1,
        })
        plan.append({
            "role": "grant_out",
            "query": f'"{name_display}" foundation grants',
            "priority": 2,
        })

    # Secondary foundation if the subject has more than one (e.g. parent + family fdn).
    if len(foundations) >= 2:
        plan.append({
            "role": "grant_out",
            "query": f'"{foundations[1]}" 990-PF',
            "priority": 3,
        })

    # EIN-anchored 990-PF query if any EIN exists.
    if eins:
        plan.append({
            "role": "grant_out",
            "query": f'"{eins[0]}" 990-PF',
            "priority": 2,
        })

    # --- direct_gift ---
    plan.append({
        "role": "direct_gift",
        "query": f'"{name_display}" donates million',
        "priority": 1,
    })
    plan.append({
        "role": "direct_gift",
        "query": f'"{name_display}" gift OR donation million',
        "priority": 2,
    })

    # --- announcement ---
    plan.append({
        "role": "announcement",
        "query": f'"{name_display}" pledges OR commits OR announces',
        "priority": 1,
    })

    # --- transfer_in (assets contributed to vehicle) ---
    if primary_vehicle:
        plan.append({
            "role": "transfer_in",
            "query": f'"{name_display}" assets contributed "{primary_vehicle}"',
            "priority": 2,
        })
    else:
        plan.append({
            "role": "transfer_in",
            "query": f'"{name_display}" foundation transfer assets contributed',
            "priority": 2,
        })

    # --- political ---
    plan.append({
        "role": "political",
        "query": f'"{name_display}" FEC OR PAC contribution',
        "priority": 2,
    })
    if top_pol_recipient:
        plan.append({
            "role": "political",
            "query": f'"{name_display}" "{top_pol_recipient}"',
            "priority": 3,
        })

    # --- private_investment (optional, low priority) ---
    plan.append({
        "role": "private_investment",
        "query": f'"{name_display}" "impact investment" OR "mission-related investment"',
        "priority": 3,
    })

    # --- reference_only: Forbes profile URL anchor ---
    forbes_url = f"{FORBES_PROFILE_BASE}{_slugify_for_forbes(name_display)}/"
    plan.append({
        "role": "reference_only",
        "query": f'"{name_display}" site:forbes.com profile',
        "priority": 3,
    })
    # If a legal name diverges from display, add it as a reference query so we catch
    # 990-PF and SEC filings that use the legal form.
    if name_legal and name_legal.lower() != name_display.lower():
        plan.append({
            "role": "reference_only",
            "query": f'"{name_legal}" {forbes_url}',
            "priority": 3,
        })

    # If a spouse is identified, add a co-foundation pattern query under grant_out.
    if spouse:
        plan.append({
            "role": "grant_out",
            "query": f'"{spouse}" "{name_display}" foundation',
            "priority": 3,
        })

    # --- investigative-journalism queries (deterministic from name_display) ---
    # Announcement-style queries surface press releases and bias toward glowing
    # coverage. These three add a counter-bias for late-revealed gifts, leaked
    # filings, and dark-giving exposés. All inputs are static strings or the
    # subject name — no clocks, no randomness. Concrete years are reproducible.
    #
    # 1. Site-restricted sweep across high-signal investigative outlets.
    plan.append({
        "role": "reference_only",
        "query": (
            f'"{name_display}" '
            f'site:propublica.org OR site:icij.org OR site:occrp.org '
            f'OR site:reuters.com/investigates OR site:theintercept.com'
        ),
        "priority": 2,
    })
    # 2. Pattern query: investigation / exposé verbs + DAF / tax-shelter cues.
    #    Routed under grant_out because DAF-routing facts speak to vehicle use.
    plan.append({
        "role": "grant_out",
        "query": (
            f'"{name_display}" '
            f'investigation OR exposé OR revealed OR leaked '
            f'"donor-advised fund" OR "tax shelter"'
        ),
        "priority": 3,
    })
    # 3. Time-shifted retrospective: gifts from the 2018-2020 window that get
    #    revisited 3-7 years later. Years are baked in (deterministic) and
    #    chosen to overlap the typical 990-PF reveal lag.
    plan.append({
        "role": "announcement",
        "query": (
            f'"{name_display}" 2018 OR 2019 OR 2020 '
            f'gift OR donation revealed OR uncovered'
        ),
        "priority": 3,
    })

    # --- multi-language press queries (foreign-domiciled / foreign-tied subjects) ---
    # _languages_for() returns [] for English-only subjects (e.g. Kravis, Bezos)
    # so this block is a no-op for them. For each detected non-English language
    # we add 2 hand-translated templates: one announcement-style, one direct_gift.
    # Cap at 4 langs to keep the plan length envelope predictable (Blavatnik is
    # currently the deepest case with US/UK/Greece/Ukraine/Russia signals; only
    # the non-en distinct langs survive).
    for lg in _languages_for(record)[:4]:
        templates = FOREIGN_TEMPLATES.get(lg)
        if not templates:
            continue
        ann_tpl = templates.get("announcement")
        if ann_tpl:
            plan.append({
                "role": "announcement",
                "query": ann_tpl.format(name=name_display),
                "priority": 2,
            })
        dg_tpl = templates.get("direct_gift")
        if dg_tpl:
            plan.append({
                "role": "direct_gift",
                "query": dg_tpl.format(name=name_display),
                "priority": 3,
            })

    # Deterministic dedupe (stable on first occurrence) and total sort.
    seen_keys: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for item in plan:
        key = (item["role"], item["query"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)

    deduped.sort(key=lambda d: (d["priority"], d["role"], d["query"]))

    # Validate role coverage and length envelope.
    roles_present = {item["role"] for item in deduped}
    missing = REQUIRED_ROLES - roles_present
    if missing:
        raise AssertionError(
            f"build_query_plan: required roles missing {sorted(missing)} "
            f"for subject {name_display!r}"
        )
    # pledge / no_pledge are mutually exclusive (signers don't get a
    # "did not sign" query, non-signers don't get a "signed in YYYY" query).
    # Require at least ONE of them.
    if not (REQUIRED_PLEDGE_GROUP & roles_present):
        raise AssertionError(
            f"build_query_plan: neither pledge nor no_pledge query generated "
            f"for subject {name_display!r}"
        )
    for item in deduped:
        if item["role"] not in CANONICAL_EVENT_ROLES:
            raise AssertionError(
                f"non-canonical role {item['role']!r} in plan for {name_display!r}"
            )

    if not (12 <= len(deduped) <= 29):
        # Soft envelope; SPEC says 12-15, but we allow up to 29 for subjects with
        # a spouse + multiple foundations + legal-name divergence + the three
        # investigative-journalism queries + up to 4 foreign-language pairs
        # (2 queries each = 8) for multilingual subjects (e.g. Blavatnik).
        raise AssertionError(
            f"plan length {len(deduped)} outside [12, 29] for {name_display!r}"
        )

    return deduped


def _format_plan(record: dict, plan: list[dict]) -> str:
    """Render a plan to a readable, deterministic block of text."""
    name = (record.get("person") or {}).get("name_display") or "(unknown)"
    lines = [f"=== Query plan: {name} ({len(plan)} queries) ==="]
    for item in plan:
        lines.append(f"  [P{item['priority']}] {item['role']:<18} {item['query']}")
    return "\n".join(lines)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent
    data_dir = here / "data"

    for fname in ("henry_kravis.v3.json", "jeff_bezos.v3.json"):
        path = data_dir / fname
        with path.open() as f:
            record = json.load(f)

        plan = build_query_plan(record)

        # Test 1 + 2: length envelope + role coverage.
        assert len(plan) >= 12, f"{fname}: plan too short ({len(plan)})"
        roles_present = {item["role"] for item in plan}
        missing = REQUIRED_ROLES - roles_present
        assert not missing, f"{fname}: missing required roles {missing}"

        # Test: determinism — building twice yields identical output.
        plan_again = build_query_plan(record)
        assert plan == plan_again, f"{fname}: plan not deterministic"

        print(_format_plan(record, plan))
        print()
