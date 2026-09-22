"""
Data access module: all reads/writes to the SQLite database go through here,
using plain, simple SQL statements. This is the module the Streamlit app and
the CLI scripts use to talk to the database.
"""

import sqlite3
import pandas as pd

from .db import get_connection, init_db


def get_conn() -> sqlite3.Connection:
    """Convenience helper: open a connection and make sure schema exists."""
    conn = get_connection()
    init_db(conn)
    return conn


def list_tournaments(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM tournaments ORDER BY date", conn)


def list_results(conn: sqlite3.Connection, tournament_id: int | None = None) -> pd.DataFrame:
    if tournament_id is not None:
        return pd.read_sql_query(
            "SELECT * FROM results WHERE tournament_id = ?", conn, params=(tournament_id,)
        )
    return pd.read_sql_query("SELECT * FROM results", conn)


def get_results_with_dates(conn: sqlite3.Connection) -> pd.DataFrame:
    """All results joined with their tournament date/filename."""
    query = """
        SELECT r.*, t.date AS tournament_date, t.filename
        FROM results r
        JOIN tournaments t ON r.tournament_id = t.id
        ORDER BY t.date
    """
    return pd.read_sql_query(query, conn)


def get_distinct_players(conn: sqlite3.Connection) -> list[str]:
    df = pd.read_sql_query(
        "SELECT DISTINCT player_name FROM results ORDER BY player_name", conn
    )
    return df["player_name"].tolist()


def get_stats_history(
    conn: sqlite3.Connection,
    date_from: str | None = None,
    date_to: str | None = None,
    players: list[str] | None = None,
) -> pd.DataFrame:
    query = "SELECT * FROM player_stats_history WHERE 1=1"
    params: list = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if players:
        placeholders = ",".join("?" for _ in players)
        query += f" AND player_name IN ({placeholders})"
        params.extend(players)
    query += " ORDER BY date"
    return pd.read_sql_query(query, conn, params=params)


def run_readonly_query(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    """Run an arbitrary SELECT query (for the app's ad-hoc query panel)."""
    stripped = sql.strip().lower()
    if not stripped.startswith("select"):
        raise ValueError("Only SELECT statements are allowed.")
    return pd.read_sql_query(sql, conn)
