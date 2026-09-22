#!/usr/bin/env python3
"""
CLI command: scan tournament_data/*.csv and import any NEW tournament files
into the SQLite database (skips files that were already imported, matched by
filename). The tournament date is parsed straight from the filename
(expected format: YYYY_MM_DD.csv).

Usage:
    python scripts/import_csv.py
"""

import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.db import get_connection, init_db

DATA_DIR = REPO_ROOT / "data" / "tournament_data"
DATE_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})")
WLD_RE = re.compile(r"(\d+)-(\d+)-(\d+)")


def parse_date_from_filename(filename: str) -> str | None:
    m = DATE_RE.search(filename)
    if not m:
        return None
    year, month, day = m.groups()
    return f"{year}-{month}-{day}"


def import_all(conn, data_dir: Path = DATA_DIR) -> tuple[int, int]:
    init_db(conn)
    csv_files = sorted(data_dir.glob("*.csv"))
    imported = 0
    skipped = 0

    for csv_path in csv_files:
        exists = conn.execute(
            "SELECT id FROM tournaments WHERE filename = ?", (csv_path.name,)
        ).fetchone()
        if exists:
            skipped += 1
            continue

        date_str = parse_date_from_filename(csv_path.name)
        if not date_str:
            print(f"  Skipping {csv_path.name}: could not parse date from filename")
            continue

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        if not rows:
            print(f"  Skipping {csv_path.name}: no data rows")
            continue

        cur = conn.execute(
            "INSERT INTO tournaments (date, filename) VALUES (?, ?)",
            (date_str, csv_path.name),
        )
        tournament_id = cur.lastrowid

        inserted_rows = 0
        for row in rows:
            wld_match = WLD_RE.match(row.get("W-L-D", "").strip())
            if not wld_match:
                continue
            wins, losses, draws = (int(x) for x in wld_match.groups())

            conn.execute(
                """
                INSERT INTO results
                    (tournament_id, player_name, rank, points, wins, losses, draws)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tournament_id,
                    row["Name"].strip(),
                    int(row["Rank"]),
                    int(row["Points"]),
                    wins,
                    losses,
                    draws,
                ),
            )
            inserted_rows += 1

        conn.commit()
        imported += 1
        print(f"  Imported {csv_path.name} -> date {date_str} ({inserted_rows} results)")

    print(f"\nDone. {imported} new tournament(s) imported, {skipped} already existed (skipped).")
    return imported, skipped


if __name__ == "__main__":
    connection = get_connection()
    import_all(connection)
    connection.close()
