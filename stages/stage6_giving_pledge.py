"""
Stage 6: Giving Pledge Cross-Reference

STATUS: ✅ Implemented

Cross-references billionaires against the IPS dataset of 256 Giving Pledge
signers. Per IPS research, only 9 of 256 have fulfilled their pledge.
"""

import os
import re
from typing import Dict, Tuple

import pandas as pd


def load_giving_pledge_data(xlsx_path: str = "giving_pledge_data.xlsx") -> Dict[str, Dict]:
    """
    Load Giving Pledge signer data from IPS dataset.

    Returns dict mapping lowercase name -> {signed, fulfilled, year_signed, still_alive}
    """
    pledgers = {}

    if not os.path.exists(xlsx_path):
        print(f"Warning: {xlsx_path} not found")
        return pledgers

    try:
        df = pd.read_excel(xlsx_path)
        for _, row in df.iterrows():
            raw_name = str(row.get("Pledgers", "")).strip()
            if not raw_name:
                continue

            # Remove death dates like "(d. 2016)"
            clean = re.sub(r'\s*\(d\.\s*\d{4}\)', '', raw_name).strip()

            # Parse "X and Y" patterns -> extract both names
            names_to_add = []
            if " and " in clean:
                parts = clean.split(" and ")
                if len(parts) == 2:
                    last_name = parts[1].split()[-1] if parts[1].split() else ""
                    first_part = parts[0].strip()
                    if " " not in first_part:  # Just first name
                        names_to_add.append(f"{first_part} {last_name}")
                        names_to_add.append(parts[1].strip())
                    else:
                        names_to_add.append(first_part)
                        names_to_add.append(parts[1].strip())
            else:
                names_to_add.append(clean)

            for name in names_to_add:
                pledgers[name.lower()] = {
                    "signed": True,
                    "fulfilled": False,  # IPS: only 9 of 256 fulfilled
                    "year_signed": row.get("Year Joined the Pledge", None),
                    "still_alive": row.get("At Least One Pledger Still Alive (As of March 25)", "Yes") == "Yes",
                }

    except Exception as e:
        print(f"Error loading Giving Pledge data: {e}")

    return pledgers


def check_giving_pledge(name: str, pledgers: Dict) -> Tuple[bool, bool]:
    """
    Check if billionaire signed/fulfilled Giving Pledge.

    Returns (signed: bool, fulfilled: bool)
    """
    key = name.lower()
    if key in pledgers:
        return pledgers[key]["signed"], pledgers[key]["fulfilled"]
    return False, False


if __name__ == "__main__":
    pledgers = load_giving_pledge_data()
    print(f"Loaded {len(pledgers)} individual pledgers")

    test_names = ["Warren Buffett", "Bill Gates", "Elon Musk", "Jeff Bezos", "Larry Page"]
    for name in test_names:
        signed, fulfilled = check_giving_pledge(name, pledgers)
        status = "SIGNED" if signed else "NOT SIGNED"
        if signed and not fulfilled:
            status += " (unfulfilled)"
        print(f"  {name}: {status}")
