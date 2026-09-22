"""
Stats engine: computes per-player tournament measures.

Key measure definitions:
- TOP1: player's Points total equals the highest Points total achieved in
  that tournament (if several players tie for first, they ALL count as TOP1).
- TOP4: player finished in the top 4 of the tournament's official standings
  (by the Rank column from the tournament software).
- BelowTOP1: player did NOT reach TOP1, but their Points total equals the
  *second-highest distinct* Points total in that tournament. This protects
  players who, purely due to pairing randomness, ended up a tier below the
  winner(s) even though several players share that same near-miss result
  (e.g. two players at 2-1-0 and one at 1-1-1: if 1-1-1 is the next distinct
  tier down, that player also qualifies as BelowTOP1).
- Tournament presence: number of tournaments (in the given set) a player has
  a result in.
- Win rate: (match wins + 0.5 * match draws) / total matches played. Draws
  are treated as "half a win" since MTG draws are not full losses.
"""

import pandas as pd

from .scoring import (
    compute_score,
    shrink_rate,
    SHRINKAGE_K_TOURNAMENTS,
    SHRINKAGE_K_MATCHES,
)


def compute_core_stats(tournaments_df: pd.DataFrame, results_df: pd.DataFrame) -> dict:
    """
    Compute per-player cumulative metrics across exactly the given set of
    tournaments (order doesn't matter for the totals, only membership does).

    tournaments_df: rows with at least an 'id' column (the tournaments to
        include).
    results_df: full results table (tournament_id, player_name, rank,
        points, wins, losses, draws).

    Returns: dict mapping player_name -> metrics dict.
    """
    tournament_ids = set(tournaments_df["id"].tolist())
    subset = results_df[results_df["tournament_id"].isin(tournament_ids)]

    players: dict = {}

    def ensure(name: str) -> dict:
        if name not in players:
            players[name] = {
                "tournaments_played": 0,
                "top1_count": 0,
                "top4_count": 0,
                "below_top1_count": 0,
                "match_wins": 0,
                "match_losses": 0,
                "match_draws": 0,
            }
        return players[name]

    for tid in tournament_ids:
        t_results = subset[subset["tournament_id"] == tid]
        if t_results.empty:
            continue

        distinct_points = sorted(t_results["points"].unique(), reverse=True)
        top_points = distinct_points[0]
        second_points = distinct_points[1] if len(distinct_points) > 1 else None

        for _, row in t_results.iterrows():
            m = ensure(row["player_name"])
            m["tournaments_played"] += 1
            m["match_wins"] += int(row["wins"])
            m["match_losses"] += int(row["losses"])
            m["match_draws"] += int(row["draws"])

            is_top1 = row["points"] == top_points
            is_below1 = (
                not is_top1
                and second_points is not None
                and row["points"] == second_points
            )
            is_top4 = row["rank"] <= 4

            if is_top1:
                m["top1_count"] += 1
            if is_below1:
                m["below_top1_count"] += 1
            if is_top4:
                m["top4_count"] += 1

    for m in players.values():
        tp = m["tournaments_played"]
        m["top1_pct"] = 100.0 * m["top1_count"] / tp if tp else 0.0
        m["top4_pct"] = 100.0 * m["top4_count"] / tp if tp else 0.0
        m["below_top1_pct"] = 100.0 * m["below_top1_count"] / tp if tp else 0.0

        total_matches = m["match_wins"] + m["match_losses"] + m["match_draws"]
        m["win_rate"] = (
            (m["match_wins"] + 0.5 * m["match_draws"]) / total_matches
            if total_matches
            else 0.0
        )
        m["total_matches"] = total_matches

    # --- League-wide averages (weighted by sample size), used as the prior
    # for Bayesian shrinkage below. This makes a single lucky tournament (or
    # a short winning streak of matches) far less able to inflate a
    # player's score, while consistent performers across many tournaments
    # converge to their true raw rate. ---
    total_tp = sum(m["tournaments_played"] for m in players.values())
    total_matches_all = sum(m["total_matches"] for m in players.values())

    league_top1_rate = (
        sum(m["top1_count"] for m in players.values()) / total_tp if total_tp else 0.0
    )
    league_top4_rate = (
        sum(m["top4_count"] for m in players.values()) / total_tp if total_tp else 0.0
    )
    league_below1_rate = (
        sum(m["below_top1_count"] for m in players.values()) / total_tp if total_tp else 0.0
    )
    league_win_rate = (
        sum(m["win_rate"] * m["total_matches"] for m in players.values()) / total_matches_all
        if total_matches_all
        else 0.0
    )

    for m in players.values():
        tp = m["tournaments_played"]
        tm = m["total_matches"]

        m["top1_pct_adj"] = 100.0 * shrink_rate(
            m["top1_count"], tp, league_top1_rate, SHRINKAGE_K_TOURNAMENTS
        )
        m["top4_pct_adj"] = 100.0 * shrink_rate(
            m["top4_count"], tp, league_top4_rate, SHRINKAGE_K_TOURNAMENTS
        )
        m["below_top1_pct_adj"] = 100.0 * shrink_rate(
            m["below_top1_count"], tp, league_below1_rate, SHRINKAGE_K_TOURNAMENTS
        )
        m["win_rate_adj"] = shrink_rate(
            m["win_rate"] * tm, tm, league_win_rate, SHRINKAGE_K_MATCHES
        )

        m["score"] = compute_score(m)

    return players


def build_history(conn) -> int:
    """
    Rebuild the player_stats_history table from scratch: for every
    tournament (in chronological order), compute each player's CUMULATIVE
    metrics using every tournament up to and including that date. This
    produces a "career progression" snapshot per player per tournament date,
    which is what powers the "score over time" chart.
    """
    tournaments = pd.read_sql_query("SELECT * FROM tournaments ORDER BY date", conn)
    results = pd.read_sql_query("SELECT * FROM results", conn)

    conn.execute("DELETE FROM player_stats_history")
    conn.commit()

    rows_to_insert = []
    for i in range(len(tournaments)):
        prefix = tournaments.iloc[: i + 1]
        current = tournaments.iloc[i]
        metrics = compute_core_stats(prefix, results)

        for player, m in metrics.items():
            rows_to_insert.append(
                (
                    player,
                    int(current["id"]),
                    current["date"],
                    m["tournaments_played"],
                    m["top1_count"],
                    m["top4_count"],
                    m["below_top1_count"],
                    m["top1_pct"],
                    m["top4_pct"],
                    m["below_top1_pct"],
                    m["match_wins"],
                    m["match_losses"],
                    m["match_draws"],
                    m["win_rate"],
                    m["score"],
                )
            )

    conn.executemany(
        """
        INSERT INTO player_stats_history (
            player_name, tournament_id, date, tournaments_played,
            top1_count, top4_count, below_top1_count,
            top1_pct, top4_pct, below_top1_pct,
            match_wins, match_losses, match_draws, win_rate, score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_to_insert,
    )
    conn.commit()
    return len(rows_to_insert)
