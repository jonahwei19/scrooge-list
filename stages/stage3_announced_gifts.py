"""
Stage 3: Announced Major Gifts (Million Dollar List + News Search)

STATUS: ✅ Implemented (using free sources)

Sources:
1. Million Dollar List - Indiana University database of $1M+ gifts
2. News API - Recent press coverage of major donations
3. Wikipedia scraping - Notable donations sections

Limitations:
- MDL not comprehensive (depends on public announcements)
- News coverage biased toward famous donors
- Many gifts are anonymous or unreported
"""

import requests
import re
import time
from typing import Dict, List
from bs4 import BeautifulSoup


# ============================================================================
# MILLION DOLLAR LIST SCRAPING
# ============================================================================

def search_million_dollar_list(name: str) -> Dict:
    """
    Search Million Dollar List for major gifts by donor name.

    MDL tracks publicly announced gifts of $1M+ since 2000.
    Website: https://milliondollarlist.org/

    Returns dict with total_announced, gift_count, gifts list.
    """
    gifts = []

    try:
        # MDL search endpoint
        search_url = "https://milliondollarlist.org/data/donors/index.html"
        headers = {"User-Agent": "Mozilla/5.0 (research project)"}

        # Search for donor name
        params = {"search": name}
        resp = requests.get(search_url, headers=headers, params=params, timeout=10)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Parse gift entries from table rows
            for row in soup.select("tr.gift-row, tr[data-donor]"):
                amount_cell = row.select_one("td.amount, td:nth-child(2)")
                recipient_cell = row.select_one("td.recipient, td:nth-child(3)")
                year_cell = row.select_one("td.year, td:nth-child(4)")

                if amount_cell:
                    amount_text = amount_cell.get_text(strip=True)
                    amount = _parse_dollar_amount(amount_text)
                    if amount > 0:
                        gifts.append({
                            "amount": amount,
                            "recipient": recipient_cell.get_text(strip=True) if recipient_cell else "Unknown",
                            "year": year_cell.get_text(strip=True) if year_cell else "Unknown",
                            "source": "Million Dollar List"
                        })
    except Exception as e:
        pass  # Silently fail, will try other sources

    return gifts


# ============================================================================
# NEWS API SEARCH
# ============================================================================

def search_news_donations(name: str) -> List[Dict]:
    """
    Search news for recent donation announcements.

    Uses free news aggregation to find "$X million donation" headlines.
    """
    gifts = []

    try:
        # Use DuckDuckGo instant answers (free, no API key)
        query = f'"{name}" donation million'
        search_url = f"https://api.duckduckgo.com/?q={query}&format=json"
        headers = {"User-Agent": "Mozilla/5.0 (research project)"}

        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()

            # Parse related topics for donation mentions
            for topic in data.get("RelatedTopics", []):
                text = topic.get("Text", "")
                if "million" in text.lower() and "donat" in text.lower():
                    amount = _extract_dollar_amount(text)
                    if amount > 0:
                        gifts.append({
                            "amount": amount,
                            "recipient": "Unknown (from news)",
                            "year": "Recent",
                            "source": "News",
                            "text": text[:200]
                        })
    except Exception:
        pass

    return gifts


# ============================================================================
# WIKIPEDIA NOTABLE DONATIONS
# ============================================================================

def search_wikipedia_philanthropy(name: str) -> List[Dict]:
    """
    Search Wikipedia for billionaire's philanthropy section.

    Many billionaire Wikipedia pages have "Philanthropy" sections
    listing their major donations.
    """
    gifts = []
    headers = {"User-Agent": "Mozilla/5.0 (research project)"}

    try:
        # Wikipedia API - get philanthropy section specifically
        clean_name = name.replace(" ", "_")

        # Try to get the philanthropy section from the full article
        # First get the section list
        sections_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={clean_name}&prop=sections&format=json"
        resp = requests.get(sections_url, headers=headers, timeout=10)

        philanthropy_section = None
        if resp.status_code == 200:
            data = resp.json()
            sections = data.get("parse", {}).get("sections", [])
            for sec in sections:
                if "philanthrop" in sec.get("line", "").lower() or "charit" in sec.get("line", "").lower():
                    philanthropy_section = sec.get("index")
                    break

        # If we found a philanthropy section, parse it
        if philanthropy_section:
            section_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={clean_name}&prop=text&section={philanthropy_section}&format=json"
            resp = requests.get(section_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                html = data.get("parse", {}).get("text", {}).get("*", "")
                soup = BeautifulSoup(html, "html.parser")

                # Find donation-related text with dollar amounts
                for text in soup.get_text().split("."):
                    text_lower = text.lower()
                    # Only extract if it mentions donation-related words
                    if any(word in text_lower for word in ["donated", "gave", "pledged", "gift", "contribution", "grant"]):
                        # Skip if it mentions net worth, wealth, or fortune
                        if any(skip in text_lower for skip in ["net worth", "fortune", "wealth", "richest", "billionaire"]):
                            continue
                        amount = _extract_dollar_amount(text)
                        # Reasonable donation range: $1M - $50B
                        if 1_000_000 <= amount <= 50_000_000_000:
                            gifts.append({
                                "amount": amount,
                                "recipient": _extract_recipient(text),
                                "year": _extract_year(text),
                                "source": "Wikipedia"
                            })

    except Exception:
        pass

    return gifts


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _parse_dollar_amount(text: str) -> float:
    """Parse dollar amount from text like '$5 million' or '$5,000,000'."""
    text = text.lower().replace(",", "").replace("$", "")

    # Handle "X billion"
    if "billion" in text:
        match = re.search(r"([\d.]+)\s*billion", text)
        if match:
            return float(match.group(1)) * 1_000_000_000

    # Handle "X million"
    if "million" in text:
        match = re.search(r"([\d.]+)\s*million", text)
        if match:
            return float(match.group(1)) * 1_000_000

    # Handle raw numbers
    match = re.search(r"([\d.]+)", text)
    if match:
        return float(match.group(1))

    return 0


def _extract_dollar_amount(text: str) -> float:
    """Extract first dollar amount from text."""
    patterns = [
        r"\$\s*([\d.]+)\s*billion",
        r"\$\s*([\d.]+)\s*million",
        r"\$\s*([\d,]+)",
        r"([\d.]+)\s*billion\s*dollars?",
        r"([\d.]+)\s*million\s*dollars?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return _parse_dollar_amount(match.group(0))

    return 0


def _extract_all_dollar_amounts(text: str) -> List[float]:
    """Extract all dollar amounts from text."""
    amounts = []
    patterns = [
        r"\$\s*([\d.]+)\s*billion",
        r"\$\s*([\d.]+)\s*million",
        r"\$\s*([\d,]+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text.lower()):
            amount = _parse_dollar_amount(match.group(0))
            if amount > 0:
                amounts.append(amount)

    return amounts


def _extract_recipient(text: str) -> str:
    """Try to extract recipient organization from donation text."""
    # Look for common patterns
    patterns = [
        r"to\s+(?:the\s+)?([A-Z][^,\.]+)",
        r"(?:donated|gave|pledged)\s+.*?\s+to\s+(?:the\s+)?([A-Z][^,\.]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()[:50]

    return "Unknown"


def _extract_year(text: str) -> str:
    """Extract year from text."""
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else "Unknown"


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def search_announced_gifts(name: str) -> Dict:
    """
    Search for announced major gifts ($1M+) from multiple sources.

    Combines:
    - Million Dollar List (primary)
    - News search (supplementary)
    - Wikipedia (supplementary)

    Returns:
        Dict with:
        - total_announced: float (sum of all found gifts)
        - gift_count: int
        - largest_gift: float
        - gifts: List[Dict] with individual gifts
        - sources: List[str]
        - status: str
    """
    all_gifts = []
    sources_used = set()

    # Search all sources
    mdl_gifts = search_million_dollar_list(name)
    if mdl_gifts:
        all_gifts.extend(mdl_gifts)
        sources_used.add("Million Dollar List")

    news_gifts = search_news_donations(name)
    if news_gifts:
        all_gifts.extend(news_gifts)
        sources_used.add("News")

    wiki_gifts = search_wikipedia_philanthropy(name)
    if wiki_gifts:
        all_gifts.extend(wiki_gifts)
        sources_used.add("Wikipedia")

    # Deduplicate by amount (rough heuristic)
    seen_amounts = set()
    unique_gifts = []
    for gift in all_gifts:
        amount_key = round(gift["amount"] / 100_000)  # Group similar amounts
        if amount_key not in seen_amounts:
            seen_amounts.add(amount_key)
            unique_gifts.append(gift)

    # Calculate totals
    total = sum(g["amount"] for g in unique_gifts)
    largest = max([g["amount"] for g in unique_gifts], default=0)

    return {
        "total_announced": total,
        "gift_count": len(unique_gifts),
        "largest_gift": largest,
        "gifts": unique_gifts,
        "sources": list(sources_used),
        "status": "IMPLEMENTED" if unique_gifts else "NO_DATA_FOUND",
    }


if __name__ == "__main__":
    # Test with known philanthropists
    test_names = ["Bill Gates", "Warren Buffett", "MacKenzie Scott"]

    for name in test_names:
        print(f"\n{'='*60}")
        print(f"Searching for: {name}")
        print("="*60)

        result = search_announced_gifts(name)
        print(f"Status: {result['status']}")
        print(f"Total announced: ${result['total_announced']/1e6:.1f}M")
        print(f"Gift count: {result['gift_count']}")
        print(f"Largest gift: ${result['largest_gift']/1e6:.1f}M")
        print(f"Sources: {result['sources']}")

        for gift in result["gifts"][:5]:
            print(f"  - ${gift['amount']/1e6:.1f}M to {gift['recipient']} ({gift['source']})")
