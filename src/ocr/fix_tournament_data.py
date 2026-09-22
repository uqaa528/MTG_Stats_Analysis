#!/usr/bin/env python3
"""
Fix tournament CSV files:
1. Recompute Points from W-L-D (Points = 3*Wins + 1*Draws) since W-L-D is
   far more reliably OCR'd than the Points column.
2. Clean up Name fields to strip stray trailing digits/symbols that leaked
   in from OCR column misalignment.
"""

import csv
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "tournament_data"


def clean_name(name):
    name = name.strip()
    name = name.replace(')', '').replace('(', '').replace('{', '').replace('}', '')
    name = name.replace('\\', '').replace('|', '').replace('§', '').replace('$', '')
    name = name.replace('[', '').replace(']', '').replace('~', '')
    name = re.sub(r'\.+$', '', name)
    # Strip trailing stray digit(s) that leaked from the Points column
    name = re.sub(r'\s+\d+$', '', name)
    # Strip trailing single stray non-letter tokens (e.g. "if", "i", "S", "6")
    name = re.sub(r'\s+[a-zA-Z]{1,2}$', lambda m: '' if m.group(0).strip().lower() in
                  ('i', 'if', 's', 'he', 'ss') else m.group(0), name)
    name = ' '.join(name.split())
    return name.strip()


def fix_file(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    if not rows:
        return 0

    header, data_rows = rows[0], rows[1:]
    fixed_count = 0
    new_rows = []

    for row in data_rows:
        if len(row) != 4:
            new_rows.append(row)
            continue

        rank, name, points, wld = row
        original_name, original_points = name, points

        wld_match = re.fullmatch(r'(\d+)-(\d+)-(\d+)', wld.strip())
        if wld_match:
            wins, losses, draws = (int(x) for x in wld_match.groups())
            correct_points = str(3 * wins + 1 * draws)
            if points.strip() != correct_points:
                points = correct_points

        name = clean_name(name)

        if name != original_name or points != original_points:
            fixed_count += 1

        new_rows.append([rank, name, points, wld])

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(new_rows)

    return fixed_count


def main():
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    total_fixed = 0
    files_touched = 0

    for csv_path in csv_files:
        fixed = fix_file(csv_path)
        if fixed:
            files_touched += 1
            total_fixed += fixed
            print(f"Fixed {fixed} row(s) in {csv_path.name}")

    print(f"\nDone. {files_touched} file(s) touched, {total_fixed} row(s) fixed.")


if __name__ == "__main__":
    main()
