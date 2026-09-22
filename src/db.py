"""
Database layer: connection helper + schema definition for the MTG stats app.
"""

import sqlite3
from pathlib import Path

# Repo root is two levels up from this file (src/db.py -> src/ -> root/).
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "mtg_stats.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,       -- ISO format YYYY-MM-DD, parsed from filename
    filename TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player_name TEXT NOT NULL,
    rank INTEGER NOT NULL,
    points INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    draws INTEGER NOT NULL,
    UNIQUE(tournament_id, player_name)
);

CREATE TABLE IF NOT EXISTS player_stats_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT NOT NULL,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    tournaments_played INTEGER NOT NULL,
    top1_count INTEGER NOT NULL,
    top4_count INTEGER NOT NULL,
    below_top1_count INTEGER NOT NULL,
    top1_pct REAL NOT NULL,
    top4_pct REAL NOT NULL,
    below_top1_pct REAL NOT NULL,
    match_wins INTEGER NOT NULL,
    match_losses INTEGER NOT NULL,
    match_draws INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    score REAL NOT NULL,
    UNIQUE(player_name, tournament_id)
);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't already exist."""
    conn.executescript(SCHEMA)
    conn.commit()


if __name__ == "__main__":
    # Running this file directly just makes sure the DB + schema exist.
    conn = get_connection()
    init_db(conn)
    print(f"Database ready at: {DB_PATH}")
    conn.close()
