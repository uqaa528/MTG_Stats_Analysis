#!/usr/bin/env python3
"""
CLI command: recompute the player_stats_history table from scratch, based on
whatever is currently in the tournaments/results tables.

Run this after importing new CSVs (via scripts/import_csv.py) to refresh
all measures and scores.

Usage:
    python scripts/recalculate_stats.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.db import get_connection, init_db
from src.stats_engine import build_history

if __name__ == "__main__":
    connection = get_connection()
    init_db(connection)
    n_rows = build_history(connection)
    print(f"Recalculated stats history: {n_rows} row(s) written to player_stats_history.")
    connection.close()
