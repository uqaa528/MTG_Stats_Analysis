#!/usr/bin/env python3
"""
Apply the canonical NAME_MAP (from name_mapping.py) to the Name column of
every CSV file in tournament_data/, normalizing all OCR variants to the
confirmed correct Polish names.

Any raw name found in the CSVs that is NOT present in NAME_MAP is left
unchanged and reported as a warning so it can be reviewed manually.
"""

import csv
from pathlib import Path

# Allow running this file directly as a script (python src/ocr/apply_name_mapping.py)
# as well as as part of the package.
try:
    from .name_mapping import NAME_MAP
except ImportError:  # pragma: no cover - fallback for direct script execution
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from name_mapping import NAME_MAP

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "tournament_data"


def apply_mapping():
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    unmapped = set()
    total_changed = 0
    files_changed = 0

    for csv_path in csv_files:
        with open(csv_path, newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))

        if not rows:
            continue

        header, data_rows = rows[0], rows[1:]
        changed_here = 0
        new_rows = []

        for row in data_rows:
            if len(row) != 4:
                new_rows.append(row)
                continue
            rank, name, points, wld = row
            if name in NAME_MAP:
                new_name = NAME_MAP[name]
                if new_name != name:
                    changed_here += 1
                name = new_name
            else:
                unmapped.add(name)
            new_rows.append([rank, name, points, wld])

        if changed_here:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(new_rows)
            files_changed += 1
            total_changed += changed_here
            print(f"Updated {changed_here} row(s) in {csv_path.name}")

    print(f"\nDone. {files_changed} file(s) touched, {total_changed} row(s) renamed.")

    if unmapped:
        print(f"\n⚠️  {len(unmapped)} name string(s) found in CSVs but NOT in NAME_MAP "
              f"(left unchanged):")
        for name in sorted(unmapped):
            print(f"   - {name!r}")
    else:
        print("\n✅ Every name in the CSVs was covered by NAME_MAP.")


if __name__ == "__main__":
    apply_mapping()
