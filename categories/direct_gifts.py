"""
DIRECT_GIFTS Category Estimator

Confidence: MEDIUM - Depends on media coverage

Data Flow:
1. Search news/press releases for gift announcements
2. Search Million Dollar List (via web)
3. Extract amounts with regex
4. Deduplicate by recipient + year + approximate amount
"""

import requests
import re
import time
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict


# Known major gifts from Chronicle of Philanthropy, news sources
# This serves as a seed database - LLM research adds to it
KNOWN_MAJOR_GIFTS = {
    "warren buffett": [
        {"recipient": "Bill & Melinda Gates Foundation", "amount": 56_000_000_000,
         "year": 2024, "description": "Cumulative Berkshire stock donations",
         "source_url": "https://www.philanthropy.com/article/warren-buffett", "is_pledge": False},
    ],
    "mackenzie scott": [
        {"recipient": "Various (direct giving)", "amount": 17_000_000_000,
         "year": 2024, "description": "Cumulative unrestricted gifts to 2000+ orgs",
         "source_url": "https://mackenzie-scott.medium.com/", "is_pledge": False},
    ],
    "bill gates": [
        {"recipient": "Gates Foundation", "amount": 59_000_000_000,
         "year": 2024, "description": "Endowment to foundation",
         "source_url": "https://www.gatesfoundation.org/", "is_pledge": False},
    ],
    "michael bloomberg": [
        {"recipient": "Johns Hopkins University", "amount": 3_400_000_000,
         "year": 2023, "description": "Largest gift to education in US history",
         "source_url": "https://www.bloomberg.org/", "is_pledge": False},
        {"recipient": "Various climate/arts/health", "amount": 14_000_000_000,
         "year": 2024, "description": "Cumulative Bloomberg Philanthropies",
         "source_url": "https://www.bloomberg.org/", "is_pledge": False},
    ],
    "larry ellison": [
        {"recipient": "USC", "amount": 200_000_000, "year": 2016,
         "description": "Cancer research center", "source_url": "https://news.usc.edu/88882/", "is_pledge": False},
        {"recipient": "Ellison Medical Foundation", "amount": 450_000_000, "year": 2013,
         "description": "Aging research grants disbursed", "source_url": "https://www.ellisonfoundation.org/", "is_pledge": False},
    ],
    "elon musk": [
        {"recipient": "St. Jude Children's Hospital", "amount": 55_000_000, "year": 2022,
         "description": "Inspiration4 mission donation", "source_url": "https://www.stjude.org/", "is_pledge": False},
        {"recipient": "XPRIZE Foundation", "amount": 100_000_000, "year": 2021,
         "description": "Carbon capture competition", "source_url": "https://www.xprize.org/", "is_pledge": True},
        {"recipient": "Fidelity Charitable", "amount": 5_700_000_000, "year": 2021,
         "description": "Tesla stock to DAF", "source_url": "https://www.bloomberg.com/news/articles/2022-02-15/musk-gave-5-7-billion-of-tesla-shares-to-charity-last-november", "is_pledge": False},
    ],
    "jeff bezos": [
        {"recipient": "Bezos Earth Fund", "amount": 10_000_000_000, "year": 2020,
         "description": "Climate change commitment", "source_url": "https://www.bezosearthfund.org/", "is_pledge": True},
        {"recipient": "Smithsonian", "amount": 200_000_000, "year": 2021,
         "description": "Air and Space Museum", "source_url": "https://www.si.edu/newsdesk/releases/bezos-200m", "is_pledge": False},
        {"recipient": "Fred Hutchinson Cancer Center", "amount": 710_000_000, "year": 2022,
         "description": "Cancer research", "source_url": "https://www.fredhutch.org/", "is_pledge": False},
    ],
    "mark zuckerberg": [
        {"recipient": "Newark Public Schools", "amount": 100_000_000, "year": 2010,
         "description": "Education reform", "source_url": "https://www.nytimes.com/2010/09/23/education/23newark.html", "is_pledge": False},
        {"recipient": "SF General Hospital", "amount": 75_000_000, "year": 2015,
         "description": "Zuckerberg SF General", "source_url": "https://www.sfchronicle.com/", "is_pledge": False},
    ],
    "phil knight": [
        {"recipient": "Stanford University", "amount": 400_000_000, "year": 2016,
         "description": "Knight-Hennessy Scholars", "source_url": "https://knight-hennessy.stanford.edu/", "is_pledge": False},
        {"recipient": "Oregon Health & Science University", "amount": 500_000_000, "year": 2013,
         "description": "Cancer research challenge grant", "source_url": "https://www.ohsu.edu/", "is_pledge": False},
    ],
    "george soros": [
        {"recipient": "Open Society Foundations", "amount": 32_000_000_000, "year": 2024,
         "description": "Cumulative endowment", "source_url": "https://www.opensocietyfoundations.org/", "is_pledge": False},
    ],
    "jim simons": [
        {"recipient": "Simons Foundation", "amount": 4_000_000_000, "year": 2024,
         "description": "Math and science research", "source_url": "https://www.simonsfoundation.org/", "is_pledge": False},
        {"recipient": "Stony Brook University", "amount": 500_000_000, "year": 2023,
         "description": "Various gifts", "source_url": "https://www.stonybrook.edu/", "is_pledge": False},
    ],
    "ray dalio": [
        {"recipient": "Various via Dalio Foundation", "amount": 2_000_000_000, "year": 2024,
         "description": "Ocean exploration, education", "source_url": "https://www.dalio.com/", "is_pledge": False},
    ],
    "dustin moskovitz": [
        {"recipient": "Good Ventures Foundation", "amount": 1_000_000_000, "year": 2024,
         "description": "Open Philanthropy grants for global health, AI safety",
         "source_url": "https://www.openphilanthropy.org/grants/", "is_pledge": False},
        {"recipient": "GiveWell Top Charities", "amount": 500_000_000, "year": 2024,
         "description": "Effective altruism grants via Good Ventures",
         "source_url": "https://www.givewell.org/about/impact", "is_pledge": False},
        {"recipient": "Asana Social Impact", "amount": 100_000_000, "year": 2023,
         "description": "Employee giving matching and direct grants",
         "source_url": "https://asana.com/company", "is_pledge": False},
    ],
    "cari tuna": [
        {"recipient": "Good Ventures Foundation", "amount": 500_000_000, "year": 2024,
         "description": "Co-founder Good Ventures, Open Philanthropy",
         "source_url": "https://www.openphilanthropy.org/about/team/cari-tuna", "is_pledge": False},
    ],
    "laurene powell jobs": [
        {"recipient": "Emerson Collective initiatives", "amount": 3_500_000_000, "year": 2024,
         "description": "Education, immigration, environment via LLC",
         "source_url": "https://www.emersoncollective.com/", "is_pledge": False},
        {"recipient": "XQ Institute", "amount": 100_000_000, "year": 2019,
         "description": "High school reform initiative",
         "source_url": "https://xqsuperschool.org/", "is_pledge": False},
    ],
    "steve ballmer": [
        {"recipient": "Ballmer Group initiatives", "amount": 2_000_000_000, "year": 2024,
         "description": "Economic mobility for children via philanthropic LLC",
         "source_url": "https://www.ballmergroup.org/", "is_pledge": False},
        {"recipient": "University of Michigan", "amount": 100_000_000, "year": 2023,
         "description": "Computer science and engineering",
         "source_url": "https://news.umich.edu/", "is_pledge": False},
    ],
}


@dataclass
class AnnouncedGift:
    """A publicly announced charitable gift."""
    recipient: str
    amount: float
    year: int
    description: str
    source_url: str
    is_pledge: bool  # True if pledge, False if disbursed


# Common gift size patterns
AMOUNT_PATTERNS = [
    (r'\$(\d+(?:\.\d+)?)\s*billion', 1e9),
    (r'\$(\d+(?:\.\d+)?)\s*B(?:\b|illion)', 1e9),
    (r'\$(\d+(?:\.\d+)?)\s*million', 1e6),
    (r'\$(\d+(?:\.\d+)?)\s*M(?:\b|illion)', 1e6),
    (r'\$(\d+(?:,\d{3})*(?:\.\d+)?)', 1),  # Raw dollar amount
]

# Keywords indicating pledge vs disbursement
PLEDGE_KEYWORDS = ['pledge', 'commit', 'promise', 'will donate', 'plans to give', 'announced']
DISBURSED_KEYWORDS = ['donated', 'gave', 'gift', 'contribution', 'granted', 'funded']


def extract_amount(text: str) -> Tuple[float, bool]:
    """
    Extract dollar amount from text.
    Returns (amount, is_pledge).
    """
    text_lower = text.lower()

    # Check if pledge or disbursement
    is_pledge = any(kw in text_lower for kw in PLEDGE_KEYWORDS)
    is_disbursed = any(kw in text_lower for kw in DISBURSED_KEYWORDS)

    # Default to pledge if unclear
    if is_disbursed and not is_pledge:
        is_pledge = False
    else:
        is_pledge = True

    for pattern, multiplier in AMOUNT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                num_str = match.group(1).replace(',', '')
                amount = float(num_str) * multiplier
                if amount >= 1_000_000:  # Only track $1M+
                    return amount, is_pledge
            except:
                continue

    return 0, True


def search_brave_for_gifts(name: str, api_key: str = None) -> List[Dict]:
    """
    Search Brave for announced gifts.
    Note: Requires Brave Search API key or use of MCP tool.
    For now, returns empty - actual search done via MCP.
    """
    # This would use Brave Search API if key provided
    # In practice, the LLM uses the MCP brave search tool
    return []


def search_wikipedia_philanthropy(name: str) -> List[Dict]:
    """
    Search Wikipedia for philanthropy section.
    """
    results = []
    try:
        # Search for person's Wikipedia page
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": name,
            "format": "json",
            "srlimit": 3,
        }
        resp = requests.get(search_url, params=params, timeout=10)
        if resp.status_code != 200:
            return []

        search_results = resp.json().get("query", {}).get("search", [])
        if not search_results:
            return []

        # Get the first page's content
        page_title = search_results[0]["title"]
        content_params = {
            "action": "query",
            "titles": page_title,
            "prop": "extracts",
            "explaintext": True,
            "format": "json",
        }

        resp = requests.get(search_url, params=content_params, timeout=10)
        if resp.status_code != 200:
            return []

        pages = resp.json().get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                continue

            extract = page_data.get("extract", "")

            # Look for philanthropy section
            sections = ["philanthropy", "charitable", "donations", "giving"]
            for section in sections:
                idx = extract.lower().find(section)
                if idx > -1:
                    # Get surrounding text
                    chunk = extract[max(0, idx-100):idx+2000]

                    # Extract any amounts mentioned
                    for pattern, multiplier in AMOUNT_PATTERNS:
                        for match in re.finditer(pattern, chunk, re.IGNORECASE):
                            try:
                                num_str = match.group(1).replace(',', '')
                                amount = float(num_str) * multiplier
                                if amount >= 1_000_000:
                                    results.append({
                                        "amount": amount,
                                        "context": chunk[max(0, match.start()-50):match.end()+100],
                                        "source": f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}",
                                    })
                            except:
                                continue
                    break

    except Exception as e:
        print(f"    Wikipedia error: {e}")

    return results


def search_million_dollar_list(name: str) -> List[Dict]:
    """
    Search Million Dollar List for major gifts.
    Note: MDL doesn't have a public API - this is a placeholder.
    Actual data would come from web scraping or LLM research.
    """
    # MDL at milliondollarlist.org tracks $1M+ gifts
    # No public API - would need to scrape or use LLM research
    return []


def estimate_direct_gifts(name: str, known_gifts: List[Dict] = None) -> Dict:
    """
    Estimate direct announced gifts for a billionaire.

    Args:
        name: Billionaire name
        known_gifts: Optional pre-researched gifts (from LLM research)

    Returns:
        Dict with gift data and confidence
    """
    print(f"  Researching direct gifts for {name}...")

    all_gifts = []

    # First check our known major gifts database
    name_lower = name.lower()
    db_gifts = KNOWN_MAJOR_GIFTS.get(name_lower, [])
    for gift in db_gifts:
        all_gifts.append(AnnouncedGift(
            recipient=gift.get("recipient", "Unknown"),
            amount=gift.get("amount", 0),
            year=gift.get("year", 2024),
            description=gift.get("description", ""),
            source_url=gift.get("source_url", ""),
            is_pledge=gift.get("is_pledge", False),
        ))

    # If we have additional pre-researched gifts, add those
    if known_gifts:
        for gift in known_gifts:
            all_gifts.append(AnnouncedGift(
                recipient=gift.get("recipient", "Unknown"),
                amount=gift.get("amount", 0),
                year=gift.get("year", 2024),
                description=gift.get("description", ""),
                source_url=gift.get("source_url", ""),
                is_pledge=gift.get("is_pledge", False),
            ))

    # Search Wikipedia
    wiki_results = search_wikipedia_philanthropy(name)
    for result in wiki_results:
        # These are raw extractions - lower confidence
        all_gifts.append(AnnouncedGift(
            recipient="Unknown (Wikipedia mention)",
            amount=result["amount"],
            year=2024,  # Unknown year
            description=result["context"][:200],
            source_url=result["source"],
            is_pledge=True,  # Assume pledge if we can't verify
        ))

    # Deduplicate by (recipient, year, amount bucket)
    seen = set()
    unique_gifts = []

    for gift in all_gifts:
        # Bucket by $10M increments
        bucket = int(gift.amount / 10_000_000)
        key = (gift.recipient.lower()[:20], gift.year, bucket)

        if key not in seen:
            seen.add(key)
            unique_gifts.append(gift)

    # Separate pledges from disbursements
    pledges = [g for g in unique_gifts if g.is_pledge]
    disbursed = [g for g in unique_gifts if not g.is_pledge]

    total_pledged = sum(g.amount for g in pledges)
    total_disbursed = sum(g.amount for g in disbursed)

    # Determine confidence
    if len(unique_gifts) > 3:
        confidence = "MEDIUM"
    elif len(unique_gifts) > 0:
        confidence = "LOW"
    else:
        confidence = "ZERO"

    print(f"    Found {len(unique_gifts)} unique gifts")
    print(f"    Disbursed: ${total_disbursed/1e6:.1f}M, Pledged: ${total_pledged/1e6:.1f}M")

    return {
        "category": "DIRECT_GIFTS",
        "billionaire": name,
        "gifts": [asdict(g) for g in unique_gifts],
        "total_disbursed": total_disbursed,
        "total_pledged": total_pledged,
        "total_all": total_pledged + total_disbursed,
        "gift_count": len(unique_gifts),
        "confidence": confidence,
        "source_urls": list(set(g.source_url for g in unique_gifts if g.source_url)),
    }


if __name__ == "__main__":
    # Test with sample known gifts (as if from LLM research)
    test_gifts = {
        "Larry Ellison": [
            {"recipient": "USC", "amount": 200_000_000, "year": 2016,
             "description": "Cancer research center", "source_url": "https://news.usc.edu/", "is_pledge": False},
            {"recipient": "Ellison Medical Foundation", "amount": 1_000_000_000, "year": 2013,
             "description": "Aging research", "source_url": "https://ellison.usc.edu/", "is_pledge": False},
        ],
        "Elon Musk": [
            {"recipient": "St. Jude", "amount": 55_000_000, "year": 2022,
             "description": "Children's hospital", "source_url": "https://stjude.org/", "is_pledge": False},
            {"recipient": "OpenAI", "amount": 50_000_000, "year": 2015,
             "description": "AI safety research", "source_url": "https://openai.com/", "is_pledge": False},
        ],
    }

    for name, gifts in test_gifts.items():
        print(f"\n{'='*60}")
        result = estimate_direct_gifts(name, known_gifts=gifts)
        print(f"\nSummary for {name}:")
        print(f"  Total disbursed: ${result['total_disbursed']/1e6:.1f}M")
        print(f"  Confidence: {result['confidence']}")
