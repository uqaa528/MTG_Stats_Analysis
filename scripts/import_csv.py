#!/usr/bin/env python3
"""
CLI command: scan tournament_data/*.csv and import tournament files into the
SQLite database, matched by filename. The tournament date is parsed straight
from the filename (expected format: YYYY_MM_DD.csv).

If a CSV for a tournament that's already in the database has changed (e.g.
you fixed some data in it), its existing results are replaced with the
current contents of the file, so re-running this script after editing a CSV
picks up the fix. Unchanged tournaments are left alone (and reported as
skipped).

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


def _rows_from_csv(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _existing_results(conn, tournament_id: int) -> list[tuple]:
    """Return the currently-stored results for a tournament, in a form
    comparable to what we'd build fresh from the CSV, so we can detect
    whether the file's content actually changed."""
    cur = conn.execute(
        """
        SELECT player_name, rank, points, wins, losses, draws
        FROM results WHERE tournament_id = ?
        ORDER BY player_name
        """,
        (tournament_id,),
    )
    return [tuple(row) for row in cur.fetchall()]


def _rows_to_comparable(rows: list[dict]) -> list[tuple]:
    comparable = []
    for row in rows:
        wld_match = WLD_RE.match(row.get("W-L-D", "").strip())
        if not wld_match:
            continue
        wins, losses, draws = (int(x) for x in wld_match.groups())
        comparable.append(
            (row["Name"].strip(), int(row["Rank"]), int(row["Points"]), wins, losses, draws)
        )
    comparable.sort(key=lambda r: r[0])
    return comparable


def _insert_results(conn, tournament_id: int, rows: list[dict]) -> int:
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
    return inserted_rows


def import_all(conn, data_dir: Path = DATA_DIR) -> tuple[int, int, int]:
    init_db(conn)
    csv_files = sorted(data_dir.glob("*.csv"))
    imported = 0
    updated = 0
    skipped = 0

    for csv_path in csv_files:
        existing = conn.execute(
            "SELECT id FROM tournaments WHERE filename = ?", (csv_path.name,)
        ).fetchone()

        rows = _rows_from_csv(csv_path)
        if not rows:
            print(f"  Skipping {csv_path.name}: no data rows")
            continue

        if existing:
            tournament_id = existing["id"]
            new_data = _rows_to_comparable(rows)
            old_data = _existing_results(conn, tournament_id)

            if new_data == old_data:
                skipped += 1
                continue

            conn.execute("DELETE FROM results WHERE tournament_id = ?", (tournament_id,))
            inserted_rows = _insert_results(conn, tournament_id, rows)
            conn.commit()
            updated += 1
            print(f"  Updated {csv_path.name} (data changed, {inserted_rows} results)")
            continue

        date_str = parse_date_from_filename(csv_path.name)
        if not date_str:
            print(f"  Skipping {csv_path.name}: could not parse date from filename")
            continue

        cur = conn.execute(
            "INSERT INTO tournaments (date, filename) VALUES (?, ?)",
            (date_str, csv_path.name),
        )
        tournament_id = cur.lastrowid

        inserted_rows = _insert_results(conn, tournament_id, rows)
        conn.commit()
        imported += 1
        print(f"  Imported {csv_path.name} -> date {date_str} ({inserted_rows} results)")

    print(
        f"\nDone. {imported} new tournament(s) imported, "
        f"{updated} updated (data changed), {skipped} unchanged (skipped)."
    )
    return imported, updated, skipped


if __name__ == "__main__":
    connection = get_connection()
    import_all(connection)
    connection.close()
