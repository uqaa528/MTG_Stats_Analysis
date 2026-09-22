#!/usr/bin/env python3
"""
Validate CSV files in tournament_data folder.
Checks:
1. CSV format is correct (has Rank, Name, Points, W-L-D columns)
2. Points match W-L-D stats: Points = 3*Wins + 1*Draws + 0*Losses
"""

import csv
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "tournament_data"

EXPECTED_HEADER = ['Rank', 'Name', 'Points', 'W-L-D']


def validate_file(csv_path):
    """Validate a single CSV file. Returns list of issue strings (empty if OK)."""
    issues = []

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        issues.append("File is empty (no header row)")
        return issues

    header = rows[0]
    if header != EXPECTED_HEADER:
        issues.append(f"Unexpected header: {header} (expected {EXPECTED_HEADER})")

    data_rows = rows[1:]
    if not data_rows:
        issues.append("No data rows found")
        return issues

    for i, row in enumerate(data_rows, start=2):  # line 2 is first data row
        if len(row) != 4:
            issues.append(f"Line {i}: wrong number of columns ({len(row)}): {row}")
            continue

        rank, name, points, wld = row

        # Validate rank
        if not rank.strip().isdigit():
            issues.append(f"Line {i}: Rank is not a number: '{rank}'")

        # Validate name
        if not name.strip():
            issues.append(f"Line {i}: Name is empty")

        # Validate points
        if not points.strip().lstrip('-').isdigit():
            issues.append(f"Line {i}: Points is not a number: '{points}'")

        # Validate W-L-D format
        wld_match = re.fullmatch(r'(\d+)-(\d+)-(\d+)', wld.strip())
        if not wld_match:
            issues.append(f"Line {i}: W-L-D not in expected format 'W-L-D': '{wld}'")
            continue

        wins, losses, draws = (int(x) for x in wld_match.groups())

        # Validate points formula: 3*W + 1*D
        expected_points = 3 * wins + 1 * draws
        try:
            actual_points = int(points.strip())
        except ValueError:
            actual_points = None

        if actual_points is not None and actual_points != expected_points:
            issues.append(
                f"Line {i}: Points mismatch for '{name}' - "
                f"W-L-D={wld} implies {expected_points} pts (3*{wins}+1*{draws}), "
                f"but CSV has {actual_points} pts"
            )

    return issues


def main():
    csv_files = sorted(DATA_DIR.glob("*.csv"))

    if not csv_files:
        print("No CSV files found in tournament_data folder!")
        return

    print(f"Validating {len(csv_files)} CSV files in {DATA_DIR}\n")
    print("=" * 70)

    total_issues = 0
    files_with_issues = 0

    for csv_path in csv_files:
        issues = validate_file(csv_path)
        if issues:
            files_with_issues += 1
            total_issues += len(issues)
            print(f"\n❌ {csv_path.name} ({len(issues)} issue(s)):")
            for issue in issues:
                print(f"   - {issue}")
        else:
            print(f"✅ {csv_path.name}: OK")

    print("\n" + "=" * 70)
    print(f"Summary: {len(csv_files) - files_with_issues}/{len(csv_files)} files valid, "
          f"{files_with_issues} file(s) with a total of {total_issues} issue(s)")


if __name__ == "__main__":
    main()
