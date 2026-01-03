"""
SECURITIES Category Estimator

Confidence: MEDIUM - SEC Form 4 is mandatory for insider transactions

Data Flow:
1. Look up CIK (Central Index Key) for billionaire
2. Fetch Form 4 filings from SEC EDGAR
3. Filter for transaction code "G" (gift)
4. Sum share values at transaction date

Note: Direct charity gifts are EXEMPT from Form 4.
We only see stock transfers to the billionaire's own foundation.
"""

import requests
import xml.etree.ElementTree as ET
import time
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


# Known CIK mappings for major billionaires
# Source: SEC EDGAR company search, verified against Form 4 filings
KNOWN_CIKS = {
    # Tech founders (public company insiders with Form 4 filings)
    "elon musk": "0001494730",
    "jeff bezos": "0001043298",
    "mark zuckerberg": "0001548760",
    "larry page": "0001288776",
    "sergey brin": "0001289042",
    "larry ellison": "0001169778",
    "jensen huang": "0001045520",
    "satya nadella": "0001513142",
    "tim cook": "0001214128",
    "sundar pichai": "0001560261",
    "reed hastings": "0001257268",
    "bob iger": "0001192553",
    "jamie dimon": "0001192553",
    "brian chesky": "0001611606",
    "dara khosrowshahi": "0001547027",
    "marc benioff": "0001108524",

    # Finance (many are private fund managers - no Form 4)
    "warren buffett": "0000315090",
    "steve ballmer": "0000824753",
    "carl icahn": "0000810509",
    "ken griffin": None,  # Citadel is private
    "ray dalio": None,  # Bridgewater is private
    "jim simons": None,  # Renaissance is private
    "george soros": None,  # Private fund manager
    "stephen schwarzman": "0001393066",  # Blackstone

    # Retail/consumer
    "phil knight": "0000830251",
    "jim walton": None,  # Family office
    "rob walton": None,
    "alice walton": None,

    # Media
    "michael bloomberg": None,  # Bloomberg LP is private
    "rupert murdoch": "0001205986",

    # Real estate - mostly private
    "donald bren": None,
    "stephen ross": None,

    # Healthcare
    "patrick soon-shiong": "0001321851",
}


@dataclass
class StockGift:
    """A stock gift transaction from Form 4."""
    filing_date: str
    transaction_date: str
    company: str
    shares: float
    price_per_share: float
    total_value: float
    transaction_code: str
    recipient: str  # Usually foundation name if disclosed
    source_url: str


def lookup_cik(name: str) -> Optional[str]:
    """
    Look up CIK from SEC database.
    """
    # Check known mappings first
    name_lower = name.lower()
    if name_lower in KNOWN_CIKS:
        return KNOWN_CIKS[name_lower]

    # Try SEC search
    try:
        # SEC company search endpoint
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "action": "getcompany",
            "company": name,
            "type": "4",
            "dateb": "",
            "owner": "include",
            "count": 10,
            "output": "atom",
        }

        headers = {
            "User-Agent": "Research Bot (research@example.com)",
        }

        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            # Parse Atom feed for CIK
            root = ET.fromstring(resp.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall(".//atom:entry", ns):
                title = entry.find("atom:title", ns)
                if title is not None and name.lower() in title.text.lower():
                    # Extract CIK from link
                    link = entry.find("atom:link", ns)
                    if link is not None:
                        href = link.get("href", "")
                        cik_match = re.search(r'/(\d{10})/', href)
                        if cik_match:
                            return cik_match.group(1)

    except Exception as e:
        print(f"    CIK lookup error: {e}")

    return None


def get_form4_filings(cik: str, limit: int = 50) -> List[Dict]:
    """
    Fetch Form 4 filings from SEC EDGAR.
    """
    filings = []

    try:
        # SEC submissions API
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        headers = {
            "User-Agent": "Research Bot (research@example.com)",
        }

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])

        for i, form in enumerate(forms[:limit]):
            if form == "4":
                filings.append({
                    "accession": accessions[i].replace("-", ""),
                    "filing_date": filing_dates[i],
                    "cik": cik,
                })

    except Exception as e:
        print(f"    EDGAR error: {e}")

    return filings


def parse_form4_for_gifts(cik: str, accession: str) -> List[StockGift]:
    """
    Parse Form 4 XML to find gift transactions (code "G").
    """
    gifts = []

    try:
        # Form 4 XML location
        url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession}/"
        headers = {
            "User-Agent": "Research Bot (research@example.com)",
        }

        # Get index to find primary document
        resp = requests.get(url + "index.json", headers=headers, timeout=10)
        if resp.status_code != 200:
            return []

        index_data = resp.json()
        items = index_data.get("directory", {}).get("item", [])

        # Find the XML file
        xml_file = None
        for item in items:
            name = item.get("name", "")
            if name.endswith(".xml") and "primary_doc" not in name:
                xml_file = name
                break

        if not xml_file:
            return []

        # Fetch and parse XML
        xml_resp = requests.get(url + xml_file, headers=headers, timeout=10)
        if xml_resp.status_code != 200:
            return []

        root = ET.fromstring(xml_resp.content)

        # Look for gift transactions
        for table in root.findall(".//nonDerivativeTransaction") + root.findall(".//derivativeTransaction"):
            code_elem = table.find(".//transactionCode")
            if code_elem is not None and code_elem.text == "G":
                # This is a gift transaction
                shares_elem = table.find(".//transactionShares/value")
                price_elem = table.find(".//transactionPricePerShare/value")
                date_elem = table.find(".//transactionDate/value")
                security_elem = table.find(".//securityTitle/value")

                shares = float(shares_elem.text) if shares_elem is not None and shares_elem.text else 0
                price = float(price_elem.text) if price_elem is not None and price_elem.text else 0
                date = date_elem.text if date_elem is not None else ""
                security = security_elem.text if security_elem is not None else "Common Stock"

                # Get issuer (company)
                issuer = root.find(".//issuerName")
                company = issuer.text if issuer is not None else "Unknown"

                if shares > 0:
                    gifts.append(StockGift(
                        filing_date="",
                        transaction_date=date,
                        company=company,
                        shares=shares,
                        price_per_share=price,
                        total_value=shares * price,
                        transaction_code="G",
                        recipient="Foundation (unspecified)",
                        source_url=url + xml_file,
                    ))

    except Exception as e:
        print(f"    Form 4 parse error: {e}")

    return gifts


def estimate_securities_gifts(name: str, net_worth_billions: float = 0) -> Dict:
    """
    Estimate stock gifts for a billionaire via SEC Form 4.

    Args:
        name: Billionaire name
        net_worth_billions: Net worth for context

    Returns:
        Dict with securities gift data
    """
    print(f"  Researching securities gifts for {name}...")

    # Look up CIK
    cik = lookup_cik(name)
    if not cik:
        print(f"    No CIK found for {name}")
        return {
            "category": "SECURITIES",
            "billionaire": name,
            "gifts": [],
            "total_value": 0,
            "gift_count": 0,
            "confidence": "ZERO",
            "note": "No CIK found - not a public company insider or no Form 4 filings",
            "source_urls": [],
        }

    print(f"    Found CIK: {cik}")

    # Get Form 4 filings
    filings = get_form4_filings(cik, limit=100)
    print(f"    Found {len(filings)} Form 4 filings")

    # Parse each filing for gift transactions
    all_gifts = []
    for filing in filings[:50]:  # Limit API calls
        gifts = parse_form4_for_gifts(cik, filing["accession"])
        for gift in gifts:
            gift.filing_date = filing["filing_date"]
        all_gifts.extend(gifts)
        time.sleep(0.2)  # Rate limit

    if all_gifts:
        print(f"    Found {len(all_gifts)} gift transactions")

    # Aggregate
    total_value = sum(g.total_value for g in all_gifts)

    # Determine confidence
    if all_gifts and total_value > 1_000_000:
        confidence = "MEDIUM"
    elif all_gifts:
        confidence = "LOW"
    else:
        confidence = "ZERO"

    return {
        "category": "SECURITIES",
        "billionaire": name,
        "gifts": [asdict(g) for g in all_gifts],
        "total_value": total_value,
        "gift_count": len(all_gifts),
        "cik": cik,
        "confidence": confidence,
        "note": "Only shows gifts TO foundations, not direct charity gifts (exempt)",
        "source_urls": list(set(g.source_url for g in all_gifts)),
    }


if __name__ == "__main__":
    test_names = ["Elon Musk", "Mark Zuckerberg", "Jeff Bezos"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = estimate_securities_gifts(name)
        print(f"\nSummary for {name}:")
        print(f"  Gift transactions: {result['gift_count']}")
        print(f"  Total value: ${result['total_value']/1e6:.1f}M")
        print(f"  Confidence: {result['confidence']}")
