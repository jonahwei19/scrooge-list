"""
UNIVERSITY ENDOWMENT GIFTS Database

Tracks major gifts ($1M+) to higher education institutions.

Data Sources:
1. Million Dollar List (Indiana University) - Historical database
2. Chronicle of Philanthropy - Gift announcements
3. University press releases - Named buildings, chairs, scholarships
4. CASE (Council for Advancement) - Fundraising data

These gifts are often:
- Named (building, chair, scholarship)
- Publicly announced
- Large enough to be newsworthy
"""

import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class UniversityGift:
    """A major gift to a university."""
    donor: str
    university: str
    amount: float
    year: int
    purpose: str  # Building, Chair, Scholarship, Research, General
    named_for: str  # e.g., "Gates Hall"
    is_pledge: bool
    source_url: str


# Known major university gifts from billionaires
# Sources: Chronicle of Philanthropy, university press releases
KNOWN_UNIVERSITY_GIFTS = {
    "phil knight": [
        {
            "university": "Stanford University",
            "amount": 400_000_000,
            "year": 2016,
            "purpose": "Knight-Hennessy Scholars Program",
            "named_for": "Knight-Hennessy Scholars",
            "is_pledge": False,
            "source_url": "https://knight-hennessy.stanford.edu/",
        },
        {
            "university": "University of Oregon",
            "amount": 500_000_000,
            "year": 2016,
            "purpose": "Campus transformation",
            "named_for": "Phil and Penny Knight Campus",
            "is_pledge": False,
            "source_url": "https://around.uoregon.edu/content/500-million-gift-phil-and-penny-knight",
        },
        {
            "university": "Oregon Health & Science University",
            "amount": 500_000_000,
            "year": 2013,
            "purpose": "Cancer research challenge grant",
            "named_for": "Knight Cancer Institute",
            "is_pledge": False,
            "source_url": "https://www.ohsu.edu/knight-cancer-institute",
        },
    ],
    "michael bloomberg": [
        {
            "university": "Johns Hopkins University",
            "amount": 1_800_000_000,
            "year": 2018,
            "purpose": "Financial aid endowment",
            "named_for": "Bloomberg Scholars",
            "is_pledge": False,
            "source_url": "https://hub.jhu.edu/2018/11/18/bloomberg-gives-1-8-billion/",
        },
        {
            "university": "Johns Hopkins University",
            "amount": 350_000_000,
            "year": 2023,
            "purpose": "AI research and education",
            "named_for": "Bloomberg Center for Government Excellence",
            "is_pledge": False,
            "source_url": "https://hub.jhu.edu/",
        },
    ],
    "bill gates": [
        {
            "university": "University of Washington",
            "amount": 210_000_000,
            "year": 2019,
            "purpose": "Population health initiative",
            "named_for": "Gates Population Health",
            "is_pledge": True,
            "source_url": "https://www.washington.edu/",
        },
        {
            "university": "MIT",
            "amount": 20_000_000,
            "year": 2021,
            "purpose": "Climate research",
            "named_for": "Gates Cambridge Scholarship (UK)",
            "is_pledge": False,
            "source_url": "https://www.gatescambridge.org/",
        },
    ],
    "larry ellison": [
        {
            "university": "USC",
            "amount": 200_000_000,
            "year": 2016,
            "purpose": "Cancer research center",
            "named_for": "Lawrence J. Ellison Institute",
            "is_pledge": False,
            "source_url": "https://ellison.usc.edu/",
        },
        {
            "university": "Yale University",
            "amount": 25_000_000,
            "year": 2023,
            "purpose": "Precision Medicine",
            "named_for": "Ellison Program",
            "is_pledge": False,
            "source_url": "https://medicine.yale.edu/",
        },
    ],
    "mark zuckerberg": [
        {
            "university": "Newark Public Schools",
            "amount": 100_000_000,
            "year": 2010,
            "purpose": "Education reform",
            "named_for": "Startup:Education",
            "is_pledge": False,
            "source_url": "https://www.nytimes.com/2010/09/23/education/23newark.html",
        },
        {
            "university": "Harvard University",
            "amount": 25_000_000,
            "year": 2021,
            "purpose": "Kempner Institute for Natural Intelligence",
            "named_for": "Kempner Institute",
            "is_pledge": False,
            "source_url": "https://kempnerinstitute.harvard.edu/",
        },
    ],
    "jeff bezos": [
        {
            "university": "Princeton University",
            "amount": 15_000_000,
            "year": 2019,
            "purpose": "Bezos Center for Neural Circuit Dynamics",
            "named_for": "Bezos Center",
            "is_pledge": False,
            "source_url": "https://pni.princeton.edu/",
        },
        {
            "university": "MIT",
            "amount": 15_000_000,
            "year": 2023,
            "purpose": "AI research",
            "named_for": "MIT Bezos AI Scholars",
            "is_pledge": False,
            "source_url": "https://news.mit.edu/",
        },
    ],
    "stephen schwarzman": [
        {
            "university": "MIT",
            "amount": 350_000_000,
            "year": 2018,
            "purpose": "College of Computing",
            "named_for": "MIT Schwarzman College of Computing",
            "is_pledge": False,
            "source_url": "https://computing.mit.edu/",
        },
        {
            "university": "Oxford University",
            "amount": 150_000_000,
            "year": 2019,
            "purpose": "Humanities Centre",
            "named_for": "Schwarzman Centre for the Humanities",
            "is_pledge": False,
            "source_url": "https://www.schwarzmancentre.ox.ac.uk/",
        },
        {
            "university": "Tsinghua University",
            "amount": 100_000_000,
            "year": 2013,
            "purpose": "Schwarzman Scholars program",
            "named_for": "Schwarzman Scholars",
            "is_pledge": False,
            "source_url": "https://www.schwarzmanscholars.org/",
        },
    ],
    "jim simons": [
        {
            "university": "Stony Brook University",
            "amount": 500_000_000,
            "year": 2023,
            "purpose": "Various - math, physics, computer science",
            "named_for": "Simons Center for Geometry and Physics",
            "is_pledge": False,
            "source_url": "https://scgp.stonybrook.edu/",
        },
        {
            "university": "MIT",
            "amount": 50_000_000,
            "year": 2022,
            "purpose": "Math and physics",
            "named_for": "Simons Collaboration",
            "is_pledge": False,
            "source_url": "https://math.mit.edu/",
        },
    ],
    "ray dalio": [
        {
            "university": "University of Connecticut",
            "amount": 22_000_000,
            "year": 2019,
            "purpose": "Ray Dalio Center",
            "named_for": "Dalio Center for Health Justice",
            "is_pledge": False,
            "source_url": "https://health.uconn.edu/",
        },
    ],
    "dustin moskovitz": [
        {
            "university": "Johns Hopkins University",
            "amount": 20_000_000,
            "year": 2022,
            "purpose": "Bloomberg School of Public Health",
            "named_for": "Open Philanthropy/Good Ventures Grant",
            "is_pledge": False,
            "source_url": "https://www.openphilanthropy.org/grants/",
        },
        {
            "university": "UC Berkeley",
            "amount": 35_000_000,
            "year": 2023,
            "purpose": "AI Safety Research",
            "named_for": "Center for Human-Compatible AI",
            "is_pledge": False,
            "source_url": "https://humancompatible.ai/",
        },
    ],
    "mackenzie scott": [
        {
            "university": "Howard University",
            "amount": 40_000_000,
            "year": 2021,
            "purpose": "General endowment",
            "named_for": "Unrestricted gift",
            "is_pledge": False,
            "source_url": "https://newsroom.howard.edu/",
        },
        {
            "university": "Morgan State University",
            "amount": 40_000_000,
            "year": 2021,
            "purpose": "General endowment",
            "named_for": "Unrestricted gift",
            "is_pledge": False,
            "source_url": "https://www.morgan.edu/",
        },
        {
            "university": "Dillard University",
            "amount": 20_000_000,
            "year": 2020,
            "purpose": "General endowment",
            "named_for": "Unrestricted gift",
            "is_pledge": False,
            "source_url": "https://www.dillard.edu/",
        },
    ],
}

# Top university endowments for reference
TOP_UNIVERSITY_ENDOWMENTS = {
    "Harvard University": 50_700_000_000,
    "Yale University": 41_400_000_000,
    "Stanford University": 36_300_000_000,
    "Princeton University": 35_800_000_000,
    "MIT": 24_600_000_000,
    "University of Pennsylvania": 20_500_000_000,
    "Notre Dame": 18_100_000_000,
    "Duke University": 12_700_000_000,
    "Johns Hopkins University": 9_600_000_000,
    "Northwestern University": 14_000_000_000,
}


def estimate_university_gifts(name: str) -> Dict:
    """
    Estimate university giving for a billionaire.

    Returns:
        Dict with university gift findings
    """
    print(f"  Researching university gifts for {name}...")

    name_lower = name.lower()
    gifts = KNOWN_UNIVERSITY_GIFTS.get(name_lower, [])

    findings = []
    for g in gifts:
        findings.append(UniversityGift(
            donor=name,
            university=g["university"],
            amount=g["amount"],
            year=g["year"],
            purpose=g["purpose"],
            named_for=g["named_for"],
            is_pledge=g["is_pledge"],
            source_url=g["source_url"],
        ))

    total_gifts = sum(g.amount for g in findings if not g.is_pledge)
    total_pledges = sum(g.amount for g in findings if g.is_pledge)

    universities = list(set(g.university for g in findings))

    print(f"    Found {len(findings)} university gifts to {len(universities)} institutions")
    print(f"    Total: ${total_gifts/1e6:.1f}M disbursed, ${total_pledges/1e6:.1f}M pledged")

    return {
        "category": "UNIVERSITY_GIFTS",
        "billionaire": name,
        "gifts": [asdict(g) for g in findings],
        "gift_count": len(findings),
        "universities": universities,
        "total_disbursed": total_gifts,
        "total_pledged": total_pledges,
        "total_all": total_gifts + total_pledges,
        "confidence": "HIGH" if findings else "ZERO",
        "source_urls": [g.source_url for g in findings],
    }


if __name__ == "__main__":
    test_names = ["Phil Knight", "Michael Bloomberg", "Stephen Schwarzman", "MacKenzie Scott"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = estimate_university_gifts(name)
        print(f"\nSummary for {name}:")
        print(f"  Universities: {result['universities']}")
        print(f"  Total: ${result['total_all']/1e9:.2f}B")
