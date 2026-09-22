#!/usr/bin/env python3
"""
List all unique names across all tournament CSV files and suggest groups of
names that likely refer to the same person (OCR variants, typos, etc.).

This does NOT auto-merge anything - it only prints suggestions for the user
to confirm manually.
"""

import csv
import re
import difflib
from pathlib import Path
from collections import Counter

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "tournament_data"


def normalize(name):
    """Normalize a name for comparison purposes (not for display)."""
    n = name.lower().strip()
    n = re.sub(r'[^a-ząćęłńóśźż\s]', '', n)
    n = re.sub(r'\s+', ' ', n)
    return n.strip()


def collect_names():
    counter = Counter()
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('Name', '').strip()
                if name:
                    counter[name] += 1
    return counter


def group_similar(names, threshold=0.72):
    """Group names using sequence similarity + normalization heuristics."""
    names = list(names)
    used = set()
    groups = []

    for i, n1 in enumerate(names):
        if n1 in used:
            continue
        group = [n1]
        used.add(n1)
        norm1 = normalize(n1)
        # also try prefix-based match (handles truncated names like "Konrad Ga")
        for n2 in names[i + 1:]:
            if n2 in used:
                continue
            norm2 = normalize(n2)
            ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()
            prefix_match = (
                len(norm1) >= 4 and len(norm2) >= 4 and
                (norm1.startswith(norm2) or norm2.startswith(norm1))
            )
            # token-based match: same first name + prefix of last name, or vice versa
            tokens1, tokens2 = norm1.split(), norm2.split()
            token_match = False
            if tokens1 and tokens2:
                if tokens1[0] == tokens2[0] and len(tokens1) > 1 and len(tokens2) > 1:
                    if tokens1[1].startswith(tokens2[1][:4]) or tokens2[1].startswith(tokens1[1][:4]):
                        token_match = True
                # last names swapped/matching even if first name OCR'd differently
                if len(tokens1) > 1 and len(tokens2) > 1 and tokens1[-1] == tokens2[-1]:
                    token_match = True

            if ratio >= threshold or prefix_match or token_match:
                group.append(n2)
                used.add(n2)

        groups.append(group)

    return groups


def main():
    counter = collect_names()
    all_names = sorted(counter.keys())

    print(f"Found {len(all_names)} unique name strings across all CSV files\n")
    print("=" * 70)
    print("ALL UNIQUE NAMES (with occurrence count):")
    print("=" * 70)
    for name in all_names:
        print(f"  {name!r:40s}  (appears {counter[name]}x)")

    print("\n" + "=" * 70)
    print("SUGGESTED GROUPS (likely same person - PLEASE CONFIRM):")
    print("=" * 70)

    groups = group_similar(all_names)
    multi_groups = [g for g in groups if len(g) > 1]

    if not multi_groups:
        print("No likely duplicate groups found.")
    else:
        for idx, group in enumerate(multi_groups, 1):
            print(f"\nGroup {idx}:")
            for name in sorted(group, key=lambda n: -counter[n]):
                print(f"  - {name!r:40s} (appears {counter[name]}x)")

    print(f"\n{len(multi_groups)} candidate group(s) suggested out of "
          f"{len(all_names)} unique name strings.")
    print("\n>>> Nothing has been changed. Please confirm the canonical name")
    print(">>> for each group before any merging is applied.")


if __name__ == "__main__":
    main()
