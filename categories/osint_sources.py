"""
COMPREHENSIVE OSINT SOURCES for Billionaire Philanthropy Research

This module catalogs ALL available data sources for philanthropic research,
organized by accessibility and reliability.

Sources are categorized as:
- TIER 1: Official government/regulatory filings
- TIER 2: Aggregated databases (ProPublica, Candid, etc.)
- TIER 3: News/press/self-reported
- TIER 4: Alternative sources (including .onion if accessible)
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class DataSource:
    name: str
    url: str
    data_type: str
    confidence: str
    access_method: str
    notes: str


# ============================================================
# TIER 1: OFFICIAL GOVERNMENT/REGULATORY SOURCES
# These are the gold standard - mandatory legal filings
# ============================================================

TIER_1_SOURCES = [
    DataSource(
        name="IRS Form 990/990-PF",
        url="https://www.irs.gov/charities-non-profits/form-990-series-downloads",
        data_type="Foundation assets, grants, officer compensation",
        confidence="HIGH",
        access_method="Bulk XML download, free",
        notes="Primary source for all foundation data. Updated annually.",
    ),
    DataSource(
        name="SEC EDGAR Form 4",
        url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4",
        data_type="Insider stock transactions including gifts",
        confidence="HIGH",
        access_method="Free API, rate limited",
        notes="Transaction code G = gift. Only shows foundation transfers, not direct charity.",
    ),
    DataSource(
        name="SEC 13F Holdings",
        url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F",
        data_type="Institutional holdings (for family offices)",
        confidence="HIGH",
        access_method="Free API",
        notes="Some billionaire family offices file 13F.",
    ),
    DataSource(
        name="FEC Individual Contributions",
        url="https://api.open.fec.gov/",
        data_type="Political contributions",
        confidence="HIGH",
        access_method="Free API with key",
        notes="Complete federal political giving record.",
    ),
    DataSource(
        name="State Charity Registrations",
        url="Various by state",
        data_type="Registration, compliance, financial summaries",
        confidence="HIGH",
        access_method="Free, per-state databases",
        notes="CA, NY, MA, FL have searchable databases.",
    ),
    DataSource(
        name="IRS Form 5227 (Split-Interest Trusts)",
        url="N/A - not publicly searchable",
        data_type="CLATs, CRATs, CRTs",
        confidence="HIGH for filed data, ZERO for discovery",
        access_method="FOIA request only",
        notes="Filed annually but NOT in public search. Must know trust name.",
    ),
    DataSource(
        name="County Property Records",
        url="Various county assessor websites",
        data_type="Real estate gifts, conservation easements",
        confidence="HIGH",
        access_method="Free, per-county",
        notes="Tracks land donations, deed transfers to nonprofits.",
    ),
]


# ============================================================
# TIER 2: AGGREGATED DATABASES
# Compiled from Tier 1 sources, easier to search
# ============================================================

TIER_2_SOURCES = [
    DataSource(
        name="ProPublica Nonprofit Explorer",
        url="https://projects.propublica.org/nonprofits/api",
        data_type="990 summaries, searchable",
        confidence="HIGH",
        access_method="Free API",
        notes="Best free source. Parsed 990 data for all nonprofits.",
    ),
    DataSource(
        name="Candid (GuideStar + Foundation Directory)",
        url="https://candid.org/",
        data_type="Complete nonprofit data, grant tracking",
        confidence="HIGH",
        access_method="Subscription API (~$1000/year)",
        notes="Most comprehensive. Includes grant-level detail.",
    ),
    DataSource(
        name="Open990",
        url="https://www.open990.org/",
        data_type="990 data in JSON format",
        confidence="HIGH",
        access_method="Free API",
        notes="Machine-readable 990 data.",
    ),
    DataSource(
        name="OpenSecrets",
        url="https://www.opensecrets.org/",
        data_type="Political giving, lobbying",
        confidence="HIGH",
        access_method="Free API with key",
        notes="Aggregates FEC data with additional analysis.",
    ),
    DataSource(
        name="Million Dollar List",
        url="https://milliondollarlist.org/",
        data_type="$1M+ gifts to higher education",
        confidence="MEDIUM",
        access_method="Free search",
        notes="Academic database, may be incomplete.",
    ),
    DataSource(
        name="ICIJ Offshore Leaks Database",
        url="https://offshoreleaks.icij.org/",
        data_type="Offshore entities, Panama/Pandora Papers",
        confidence="HIGH for included data",
        access_method="Free search",
        notes="Includes some foundation/trust structures in tax havens.",
    ),
]


# ============================================================
# TIER 3: NEWS / PRESS / SELF-REPORTED
# Valuable but requires verification
# ============================================================

TIER_3_SOURCES = [
    DataSource(
        name="Chronicle of Philanthropy",
        url="https://www.philanthropy.com/",
        data_type="Gift announcements, philanthropy news",
        confidence="MEDIUM-HIGH",
        access_method="Subscription for full access",
        notes="Industry standard for major gift tracking.",
    ),
    DataSource(
        name="Inside Philanthropy",
        url="https://www.insidephilanthropy.com/",
        data_type="Donor profiles, grant analysis",
        confidence="MEDIUM",
        access_method="Subscription",
        notes="Deep dives on major donors.",
    ),
    DataSource(
        name="Giving Pledge Website",
        url="https://givingpledge.org/",
        data_type="Pledge letters, signer list",
        confidence="HIGH for signers, LOW for fulfillment",
        access_method="Free",
        notes="Self-reported commitments, not verified giving.",
    ),
    DataSource(
        name="Forbes Philanthropy",
        url="https://www.forbes.com/philanthropy/",
        data_type="Philanthropy rankings, profiles",
        confidence="MEDIUM",
        access_method="Free",
        notes="Annual philanthropy score methodology is opaque.",
    ),
    DataSource(
        name="Wikipedia Philanthropy Sections",
        url="https://en.wikipedia.org/",
        data_type="Summary of public giving",
        confidence="LOW-MEDIUM",
        access_method="Free API",
        notes="Crowdsourced, may be incomplete or outdated.",
    ),
    DataSource(
        name="University Press Releases",
        url="Various .edu sites",
        data_type="Named gift announcements",
        confidence="MEDIUM-HIGH",
        access_method="Free, web search",
        notes="Official announcements of major gifts.",
    ),
    DataSource(
        name="LLC/Foundation Websites",
        url="e.g., chanzuckerberg.com, ballmergroup.org",
        data_type="Self-reported grants",
        confidence="MEDIUM",
        access_method="Free",
        notes="LLCs don't file 990s, so self-disclosure is only source.",
    ),
]


# ============================================================
# TIER 4: ALTERNATIVE / SPECIALIZED SOURCES
# Requires more effort to access, variable reliability
# ============================================================

TIER_4_SOURCES = [
    DataSource(
        name="ICIJ Data (Full Datasets)",
        url="https://www.icij.org/investigations/",
        data_type="Leaked documents, offshore structures",
        confidence="HIGH for raw data",
        access_method="Journalistic access or bulk downloads",
        notes="Panama Papers, Paradise Papers, Pandora Papers.",
    ),
    DataSource(
        name="Court Records (PACER)",
        url="https://pacer.uscourts.gov/",
        data_type="Lawsuits, estates, trust disputes",
        confidence="HIGH",
        access_method="Paid access ($0.10/page)",
        notes="Estate litigation reveals trust structures.",
    ),
    DataSource(
        name="Probate Records",
        url="County-specific",
        data_type="Estate distributions, charitable bequests",
        confidence="HIGH",
        access_method="County courthouse or online",
        notes="Reveals posthumous giving plans.",
    ),
    DataSource(
        name="Swiss FINMA Register",
        url="https://www.finma.ch/en/",
        data_type="Swiss foundation registrations",
        confidence="MEDIUM",
        access_method="Limited public access",
        notes="Some US billionaires have Swiss foundations.",
    ),
    DataSource(
        name="UK Charity Commission",
        url="https://www.gov.uk/government/organisations/charity-commission",
        data_type="UK-registered charities",
        confidence="HIGH",
        access_method="Free API",
        notes="Tracks UK operations of US billionaire foundations.",
    ),
    DataSource(
        name="Luxembourg RCSL",
        url="https://www.rcsl.lu/",
        data_type="Luxembourg foundation registry",
        confidence="MEDIUM",
        access_method="Paid access",
        notes="Some use Luxembourg structures.",
    ),
    DataSource(
        name="Tor-Accessible Archives",
        url=".onion addresses",
        data_type="Leaked documents, alternative archives",
        confidence="VARIABLE",
        access_method="Tor browser required",
        notes="Includes WikiLeaks mirrors, document dumps. Requires verification.",
    ),
    DataSource(
        name="Private Equity/VC Databases",
        url="PitchBook, Crunchbase, CB Insights",
        data_type="Investment data (for LLC activities)",
        confidence="MEDIUM",
        access_method="Subscription",
        notes="LLCs like CZI make investments, tracked here.",
    ),
]


# ============================================================
# SOURCE RELIABILITY MATRIX
# ============================================================

def get_source_reliability() -> Dict[str, Dict]:
    """
    Return reliability matrix for all sources.
    """
    return {
        "TIER_1": {
            "sources": len(TIER_1_SOURCES),
            "reliability": "HIGHEST",
            "note": "Legal filings, mandatory disclosure",
            "recommended": True,
        },
        "TIER_2": {
            "sources": len(TIER_2_SOURCES),
            "reliability": "HIGH",
            "note": "Aggregated from Tier 1, easier access",
            "recommended": True,
        },
        "TIER_3": {
            "sources": len(TIER_3_SOURCES),
            "reliability": "MEDIUM",
            "note": "Requires verification, may be incomplete",
            "recommended": True,
        },
        "TIER_4": {
            "sources": len(TIER_4_SOURCES),
            "reliability": "VARIABLE",
            "note": "Specialized access, mixed reliability",
            "recommended": "Case-by-case",
        },
    }


def get_all_sources() -> List[DataSource]:
    """Return all cataloged sources."""
    return TIER_1_SOURCES + TIER_2_SOURCES + TIER_3_SOURCES + TIER_4_SOURCES


def print_source_catalog():
    """Print formatted source catalog."""
    all_sources = get_all_sources()

    print(f"\n{'='*80}")
    print("COMPREHENSIVE OSINT SOURCE CATALOG FOR PHILANTHROPIC RESEARCH")
    print(f"{'='*80}")
    print(f"Total sources cataloged: {len(all_sources)}")
    print()

    for tier_name, sources in [
        ("TIER 1: Official Government/Regulatory", TIER_1_SOURCES),
        ("TIER 2: Aggregated Databases", TIER_2_SOURCES),
        ("TIER 3: News/Press/Self-Reported", TIER_3_SOURCES),
        ("TIER 4: Alternative/Specialized", TIER_4_SOURCES),
    ]:
        print(f"\n{tier_name}")
        print("-" * 60)
        for s in sources:
            print(f"  {s.name}")
            print(f"    URL: {s.url}")
            print(f"    Data: {s.data_type}")
            print(f"    Confidence: {s.confidence}")
            print(f"    Access: {s.access_method}")
            print()


if __name__ == "__main__":
    print_source_catalog()
    print("\nReliability Matrix:")
    for tier, info in get_source_reliability().items():
        print(f"  {tier}: {info['sources']} sources, {info['reliability']} reliability")
