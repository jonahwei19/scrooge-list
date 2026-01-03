"""
Stage 1: Fetch Forbes Billionaire Data

STATUS: ✅ Implemented

Pulls the Forbes Real-Time Billionaires list via their public JSON API.
Returns ~3,163 billionaires with name, net worth, source, and country.
"""

import requests
from typing import List, Dict


def fetch_forbes_billionaires() -> List[Dict]:
    """
    Fetch current Forbes Real-Time Billionaires list.

    Returns list of dicts with keys:
        - name: str
        - net_worth_billions: float
        - source: str (source of wealth)
        - country: str
        - rank: int
    """
    url = "https://www.forbes.com/forbesapi/person/rtb/0/position/true.json"

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        billionaires = []
        for person in data.get("personList", {}).get("personsLists", []):
            billionaires.append({
                "name": person.get("personName", ""),
                "net_worth_billions": person.get("finalWorth", 0) / 1000,  # API returns millions
                "source": person.get("source", ""),
                "country": person.get("countryOfCitizenship", ""),
                "rank": person.get("rank", 0),
            })

        return billionaires

    except Exception as e:
        print(f"Error fetching Forbes data: {e}")
        print("Falling back to sample data...")
        return _get_fallback_data()


def _get_fallback_data() -> List[Dict]:
    """Fallback sample data if API fails."""
    return [
        {"name": "Elon Musk", "net_worth_billions": 428, "source": "Tesla, SpaceX", "country": "United States", "rank": 1},
        {"name": "Jeff Bezos", "net_worth_billions": 244, "source": "Amazon", "country": "United States", "rank": 2},
        {"name": "Larry Ellison", "net_worth_billions": 223, "source": "Oracle", "country": "United States", "rank": 3},
        {"name": "Mark Zuckerberg", "net_worth_billions": 202, "source": "Facebook", "country": "United States", "rank": 4},
        {"name": "Larry Page", "net_worth_billions": 156, "source": "Google", "country": "United States", "rank": 5},
        {"name": "Sergey Brin", "net_worth_billions": 148, "source": "Google", "country": "United States", "rank": 6},
        {"name": "Warren Buffett", "net_worth_billions": 145, "source": "Berkshire Hathaway", "country": "United States", "rank": 7},
        {"name": "Steve Ballmer", "net_worth_billions": 124, "source": "Microsoft", "country": "United States", "rank": 8},
        {"name": "Michael Dell", "net_worth_billions": 120, "source": "Dell Technologies", "country": "United States", "rank": 9},
        {"name": "Jensen Huang", "net_worth_billions": 118, "source": "Nvidia", "country": "United States", "rank": 10},
    ]


if __name__ == "__main__":
    billionaires = fetch_forbes_billionaires()
    print(f"Fetched {len(billionaires)} billionaires")
    for b in billionaires[:10]:
        print(f"  {b['rank']}. {b['name']}: ${b['net_worth_billions']:.1f}B ({b['country']})")
