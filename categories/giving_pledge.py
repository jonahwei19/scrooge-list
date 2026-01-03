"""
GIVING PLEDGE Signer Verification

The Giving Pledge is a commitment by wealthy individuals to give away
the majority (>50%) of their wealth to philanthropy.

Started in 2010 by Warren Buffett and Bill Gates.

IMPORTANT: The pledge is NOT legally binding. It's a moral commitment.
Many signers have not yet fulfilled their pledges.

This module:
1. Tracks confirmed pledge signers
2. Estimates pledge fulfillment rates
3. Compares pledged amounts to actual giving
"""

import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class PledgeSigner:
    """A Giving Pledge signer."""
    name: str
    sign_year: int
    net_worth_at_sign: float
    current_net_worth: float
    pledged_amount: float  # >50% of wealth at sign time
    observable_giving: float
    fulfillment_rate: float  # observable / pledged
    letter_url: str  # Link to their pledge letter


# Complete list of US billionaire Giving Pledge signers
# Source: https://givingpledge.org/
GIVING_PLEDGE_SIGNERS = {
    "warren buffett": {
        "sign_year": 2010,
        "net_worth_at_sign": 47_000_000_000,
        "current_net_worth": 146_800_000_000,
        "observable_giving": 56_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=177",
        "notes": "Founder. Giving to Gates Foundation annually.",
    },
    "bill gates": {
        "sign_year": 2010,
        "net_worth_at_sign": 53_000_000_000,
        "current_net_worth": 129_000_000_000,
        "observable_giving": 59_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=178",
        "notes": "Founder. Gates Foundation + Breakthrough Energy.",
    },
    "melinda french gates": {
        "sign_year": 2010,
        "net_worth_at_sign": 0,  # Joint with Bill at time
        "current_net_worth": 12_000_000_000,
        "observable_giving": 0,  # Counted under Bill
        "letter_url": "https://givingpledge.org/pledger?pledgerId=178",
        "notes": "Founder. Now independent from Gates Foundation.",
    },
    "mark zuckerberg": {
        "sign_year": 2010,
        "net_worth_at_sign": 6_900_000_000,
        "current_net_worth": 215_000_000_000,
        "observable_giving": 7_220_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=188",
        "notes": "With Priscilla Chan. CZI is an LLC, not tracked by 990.",
    },
    "priscilla chan": {
        "sign_year": 2010,
        "net_worth_at_sign": 0,  # Joint with Mark
        "current_net_worth": 0,  # Counted under Mark
        "observable_giving": 0,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=188",
        "notes": "CZI co-founder.",
    },
    "michael bloomberg": {
        "sign_year": 2010,
        "net_worth_at_sign": 18_000_000_000,
        "current_net_worth": 96_000_000_000,
        "observable_giving": 17_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=170",
        "notes": "Bloomberg Philanthropies. Climate, arts, education.",
    },
    "larry ellison": {
        "sign_year": 2010,
        "net_worth_at_sign": 28_000_000_000,
        "current_net_worth": 245_000_000_000,
        "observable_giving": 1_200_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=172",
        "notes": "Ellison Foundation. LOW fulfillment so far.",
    },
    "george soros": {
        "sign_year": 2010,
        "net_worth_at_sign": 14_200_000_000,
        "current_net_worth": 7_200_000_000,
        "observable_giving": 32_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=185",
        "notes": "Has given MORE than current net worth. OSF.",
    },
    "mackenzie scott": {
        "sign_year": 2019,
        "net_worth_at_sign": 36_600_000_000,
        "current_net_worth": 36_000_000_000,
        "observable_giving": 17_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=393",
        "notes": "Fastest disbursement rate. Direct giving model.",
    },
    "ray dalio": {
        "sign_year": 2011,
        "net_worth_at_sign": 6_000_000_000,
        "current_net_worth": 19_100_000_000,
        "observable_giving": 2_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=190",
        "notes": "Dalio Foundation. Ocean exploration, education.",
    },
    "dustin moskovitz": {
        "sign_year": 2010,
        "net_worth_at_sign": 1_400_000_000,
        "current_net_worth": 11_400_000_000,
        "observable_giving": 3_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=181",
        "notes": "Good Ventures. Effective altruism focus.",
    },
    "cari tuna": {
        "sign_year": 2010,
        "net_worth_at_sign": 0,  # Joint with Dustin
        "current_net_worth": 0,
        "observable_giving": 0,  # Counted under Dustin
        "letter_url": "https://givingpledge.org/pledger?pledgerId=181",
        "notes": "Open Philanthropy co-founder.",
    },
    "elon musk": {
        "sign_year": 2012,
        "net_worth_at_sign": 2_000_000_000,
        "current_net_worth": 277_000_000_000,
        "observable_giving": 5_955_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=232",
        "notes": "Musk Foundation + DAF. LOW relative to wealth.",
    },
    "phil knight": {
        "sign_year": 2013,
        "net_worth_at_sign": 18_000_000_000,
        "current_net_worth": 47_300_000_000,
        "observable_giving": 2_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=248",
        "notes": "Knight Foundation. Oregon/Stanford.",
    },
    "jim simons": {
        "sign_year": 2010,
        "net_worth_at_sign": 10_600_000_000,
        "current_net_worth": 31_400_000_000,
        "observable_giving": 4_500_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=184",
        "notes": "Simons Foundation. Math and science.",
    },
    "stephen schwarzman": {
        "sign_year": 2010,
        "net_worth_at_sign": 4_700_000_000,
        "current_net_worth": 41_500_000_000,
        "observable_giving": 1_000_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=183",
        "notes": "MIT, Oxford, Tsinghua. LOW rate.",
    },
    "david geffen": {
        "sign_year": 2010,
        "net_worth_at_sign": 5_500_000_000,
        "current_net_worth": 9_900_000_000,
        "observable_giving": 800_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=173",
        "notes": "Geffen Foundation. UCLA, arts.",
    },
    "reid hoffman": {
        "sign_year": 2012,
        "net_worth_at_sign": 1_800_000_000,
        "current_net_worth": 2_500_000_000,
        "observable_giving": 200_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=231",
        "notes": "Hoffman Foundation.",
    },
    "john arnold": {
        "sign_year": 2010,
        "net_worth_at_sign": 3_500_000_000,
        "current_net_worth": 3_300_000_000,
        "observable_giving": 1_500_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=167",
        "notes": "Arnold Ventures. Criminal justice, education.",
    },
    "laura arnold": {
        "sign_year": 2010,
        "net_worth_at_sign": 0,
        "current_net_worth": 0,
        "observable_giving": 0,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=167",
        "notes": "Arnold Ventures co-founder.",
    },
    "marc benioff": {
        "sign_year": 2012,
        "net_worth_at_sign": 2_200_000_000,
        "current_net_worth": 7_300_000_000,
        "observable_giving": 500_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=225",
        "notes": "Salesforce 1-1-1 model. Health, education.",
    },
    "jeff skoll": {
        "sign_year": 2010,
        "net_worth_at_sign": 3_500_000_000,
        "current_net_worth": 5_600_000_000,
        "observable_giving": 1_200_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=186",
        "notes": "Skoll Foundation. Social entrepreneurship.",
    },
    "pierre omidyar": {
        "sign_year": 2010,
        "net_worth_at_sign": 7_200_000_000,
        "current_net_worth": 8_100_000_000,
        "observable_giving": 1_500_000_000,
        "letter_url": "https://givingpledge.org/pledger?pledgerId=182",
        "notes": "Omidyar Network. Democracy, technology.",
    },
}


def calculate_fulfillment(signer: Dict) -> float:
    """
    Calculate pledge fulfillment rate.

    The pledge is to give >50% of wealth (at sign time or lifetime).
    """
    pledged = signer.get("net_worth_at_sign", 0) * 0.5
    observable = signer.get("observable_giving", 0)

    if pledged > 0:
        return min(1.0, observable / pledged)
    return 0.0


def get_giving_pledge_status(name: str) -> Dict:
    """
    Check if billionaire is a Giving Pledge signer and their status.

    Returns:
        Dict with pledge status and fulfillment analysis
    """
    print(f"  Checking Giving Pledge status for {name}...")

    name_lower = name.lower()

    if name_lower not in GIVING_PLEDGE_SIGNERS:
        print(f"    Not a Giving Pledge signer")
        return {
            "is_signer": False,
            "billionaire": name,
            "reason": "Not found in Giving Pledge database",
            "source_url": "https://givingpledge.org/",
        }

    signer = GIVING_PLEDGE_SIGNERS[name_lower]
    fulfillment = calculate_fulfillment(signer)

    pledged_amount = signer.get("net_worth_at_sign", 0) * 0.5

    # Classify fulfillment status
    if fulfillment >= 1.0:
        status = "FULFILLED"
        status_note = "Has met or exceeded pledge commitment"
    elif fulfillment >= 0.5:
        status = "ON_TRACK"
        status_note = "Making significant progress"
    elif fulfillment >= 0.1:
        status = "BEHIND"
        status_note = "Some giving but below expectations"
    else:
        status = "MINIMAL"
        status_note = "Very little progress toward pledge"

    print(f"    Signer since {signer['sign_year']}")
    print(f"    Fulfillment: {fulfillment*100:.1f}% - {status}")

    return {
        "is_signer": True,
        "billionaire": name,
        "sign_year": signer["sign_year"],
        "net_worth_at_sign": signer["net_worth_at_sign"],
        "current_net_worth": signer["current_net_worth"],
        "pledged_amount": pledged_amount,
        "observable_giving": signer["observable_giving"],
        "fulfillment_rate": fulfillment,
        "status": status,
        "status_note": status_note,
        "notes": signer.get("notes", ""),
        "letter_url": signer["letter_url"],
        "source_url": "https://givingpledge.org/",
    }


def get_all_signers_analysis() -> List[Dict]:
    """
    Analyze all Giving Pledge signers and their fulfillment.
    """
    results = []

    for name, signer in GIVING_PLEDGE_SIGNERS.items():
        if signer.get("net_worth_at_sign", 0) > 0:  # Skip spouses counted elsewhere
            fulfillment = calculate_fulfillment(signer)
            results.append({
                "name": name.title(),
                "sign_year": signer["sign_year"],
                "pledged": signer["net_worth_at_sign"] * 0.5,
                "observable": signer["observable_giving"],
                "fulfillment_rate": fulfillment,
            })

    # Sort by fulfillment rate
    results.sort(key=lambda x: x["fulfillment_rate"], reverse=True)

    return results


if __name__ == "__main__":
    # Test specific signers
    test_names = ["Warren Buffett", "Larry Ellison", "Elon Musk", "MacKenzie Scott"]

    for name in test_names:
        print(f"\n{'='*60}")
        result = get_giving_pledge_status(name)
        if result["is_signer"]:
            print(f"\nSummary for {name}:")
            print(f"  Pledged: ${result['pledged_amount']/1e9:.1f}B")
            print(f"  Observable: ${result['observable_giving']/1e9:.1f}B")
            print(f"  Status: {result['status']}")

    # Show all signers ranked
    print(f"\n\n{'='*60}")
    print("GIVING PLEDGE FULFILLMENT RANKINGS")
    print("="*60)

    analysis = get_all_signers_analysis()
    for i, s in enumerate(analysis[:10], 1):
        print(f"{i}. {s['name']}: {s['fulfillment_rate']*100:.0f}% "
              f"(${s['observable']/1e9:.1f}B / ${s['pledged']/1e9:.1f}B pledged)")
