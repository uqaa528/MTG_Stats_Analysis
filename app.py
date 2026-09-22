"""
MTG Tournament Stats — Streamlit app.

A small "IDE-like" analysis app for the tournament data stored in
mtg_stats.db. See README.md for how to populate/refresh the database before
running this app.
"""

import pandas as pd
import altair as alt
import streamlit as st

from src import data_access as da
from src.scoring import WEIGHTS, FORMULA_TEXT
from src.stats_engine import compute_core_stats

st.set_page_config(page_title="MTG Tournament Stats", layout="wide")

conn = da.get_conn()

st.title("🎴 MTG Tournament Stats Analyzer")

tournaments = da.list_tournaments(conn)
if tournaments.empty:
    st.warning(
        "No tournaments found in the database.\n\n"
        "Run `python scripts/import_csv.py` first, then `python scripts/recalculate_stats.py`."
    )
    st.stop()

tournaments["date_parsed"] = pd.to_datetime(tournaments["date"])
min_date = tournaments["date_parsed"].min().date()
max_date = tournaments["date_parsed"].max().date()

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

date_range = st.sidebar.date_input(
    "Tournament date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    date_from, date_to = date_range
else:
    date_from, date_to = min_date, max_date

MEASURE_LABELS = {
    "score": "Score",
    "top1_pct": "TOP1 %",
    "top4_pct": "TOP4 %",
    "below_top1_pct": "BelowTOP1 %",
    "top1_count": "TOP1 count",
    "top4_count": "TOP4 count",
    "below_top1_count": "BelowTOP1 count",
    "win_rate": "Win rate",
    "tournaments_played": "Tournaments played",
}

measure = st.sidebar.selectbox(
    "Chart measure",
    options=list(MEASURE_LABELS.keys()),
    format_func=lambda x: MEASURE_LABELS[x],
)

show_explanations = st.sidebar.checkbox("Show measure explanations", value=False)

# ---------------------------------------------------------------------------
# Leaderboard — computed fresh, using ONLY tournaments in the selected range
# ---------------------------------------------------------------------------
st.header("🏆 Leaderboard")
st.caption(
    f"Computed using only tournaments between **{date_from}** and **{date_to}** "
    "(re-derived on the fly, not just a filtered snapshot)."
)

tournaments_in_range = tournaments[
    (tournaments["date_parsed"].dt.date >= date_from)
    & (tournaments["date_parsed"].dt.date <= date_to)
]

all_results = da.list_results(conn)
metrics_by_player = compute_core_stats(tournaments_in_range, all_results)

leaderboard_rows = []
for player, m in metrics_by_player.items():
    leaderboard_rows.append(
        {
            "Player": player,
            "Score": round(m["score"], 2),
            "Tournaments": m["tournaments_played"],
            "TOP1": m["top1_count"],
            "TOP4": m["top4_count"],
            "BelowTOP1": m["below_top1_count"],
            "TOP1 %": round(m["top1_pct"], 1),
            "TOP4 %": round(m["top4_pct"], 1),
            "BelowTOP1 %": round(m["below_top1_pct"], 1),
            "Win rate %": round(m["win_rate"] * 100, 1),
            "TOP1 % (score-adj.)": round(m["top1_pct_adj"], 1),
            "TOP4 % (score-adj.)": round(m["top4_pct_adj"], 1),
            "BelowTOP1 % (score-adj.)": round(m["below_top1_pct_adj"], 1),
            "Win rate % (score-adj.)": round(m["win_rate_adj"] * 100, 1),
        }
    )

if leaderboard_rows:
    leaderboard_df = (
        pd.DataFrame(leaderboard_rows)
        .sort_values("Score", ascending=False)
        .reset_index(drop=True)
    )
    leaderboard_df.index += 1

    show_adjusted_cols = st.checkbox(
        "Show score-adjusted (shrunk) % columns used internally by Score",
        value=False,
    )
    if not show_adjusted_cols:
        leaderboard_df = leaderboard_df.drop(
            columns=[c for c in leaderboard_df.columns if "(score-adj.)" in c]
        )

    st.dataframe(leaderboard_df, use_container_width=True)
else:
    st.info("No results in the selected date range.")

# ---------------------------------------------------------------------------
# Score / measure over time chart
# ---------------------------------------------------------------------------
st.header("📈 Measure over time")

history = da.get_stats_history(conn, date_from=str(date_from), date_to=str(date_to))

if history.empty:
    st.info("No history data yet. Run `python scripts/recalculate_stats.py` to compute it.")
else:
    players_available = sorted(history["player_name"].unique())

    # Default to the top 8 scorers in the CURRENTLY SELECTED measure (by
    # their latest value within the date range), not just an arbitrary
    # alphabetical slice.
    latest_per_player = (
        history.sort_values("date").groupby("player_name").tail(1)
    )
    top8_for_measure = (
        latest_per_player.sort_values(measure, ascending=False)["player_name"]
        .head(8)
        .tolist()
    )
    default_players = [p for p in top8_for_measure if p in players_available]

    selected_players = st.multiselect(
        "Players to show", options=players_available, default=default_players
    )

    plot_df = history[history["player_name"].isin(selected_players)].copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])

    if plot_df.empty:
        st.info("Select at least one player to draw the chart.")
    else:
        chart = (
            alt.Chart(plot_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("date:T", title="Tournament date"),
                y=alt.Y(f"{measure}:Q", title=MEASURE_LABELS[measure]),
                color=alt.Color("player_name:N", title="Player"),
                tooltip=["player_name", "date:T", f"{measure}:Q"],
            )
            .interactive()
        )
        st.altair_chart(chart, use_container_width=True)

        # Always ALSO show Win rate over time, in addition to whatever
        # measure is selected above (unless the user already selected Win
        # rate itself, to avoid showing the exact same chart twice).
        if measure != "win_rate":
            st.subheader("📉 Win rate over time")
            win_rate_chart = (
                alt.Chart(plot_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("date:T", title="Tournament date"),
                    y=alt.Y("win_rate:Q", title=MEASURE_LABELS["win_rate"]),
                    color=alt.Color("player_name:N", title="Player"),
                    tooltip=["player_name", "date:T", "win_rate:Q"],
                )
                .interactive()
            )
            st.altair_chart(win_rate_chart, use_container_width=True)

# ---------------------------------------------------------------------------
# Ad-hoc SQL query panel ("IDE-like" exploration)
# ---------------------------------------------------------------------------
with st.expander("🔎 Run a custom SQL query (SELECT only)"):
    default_query = "SELECT * FROM results LIMIT 20;"
    query_text = st.text_area("SQL", value=default_query, height=100)
    if st.button("Run query"):
        try:
            result_df = da.run_readonly_query(conn, query_text)
            st.dataframe(result_df, use_container_width=True)
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

# ---------------------------------------------------------------------------
# Explanation panel (hidden by default)
# ---------------------------------------------------------------------------
if show_explanations:
    st.header("📖 Measure explanations")
    st.markdown(
        """
- **TOP1**: player's Points total equals the *highest* Points total achieved
  in that tournament. If several players tie for first, they **all** count
  as TOP1 for that event.
- **TOP4**: player finished in the top 4 of the tournament's official
  standings (by the Rank column reported by the tournament software).
- **BelowTOP1**: player did *not* reach TOP1, but their Points total equals
  the **second-highest distinct** Points total in that tournament. This
  protects players who — purely due to pairing randomness — ended up a tier
  below the winner(s), even if several players share that same near-miss
  result. Example: two players finish 2-1-0 (TOP1) and one finishes 1-1-1;
  if 1-1-1 is the next distinct points tier down, that player also counts
  as BelowTOP1.
- **Tournaments played**: number of tournaments (within the selected date
  range) the player has a result in.
- **Win rate**: `(match wins + 0.5 × match draws) / total matches played`.
  Draws are treated as "half a win" since an MTG draw isn't a loss.
- **% measures** (TOP1 %, TOP4 %, BelowTOP1 %): the corresponding count
  divided by tournaments played, × 100.
        """
    )

    st.subheader("Score formula")
    st.code(FORMULA_TEXT)
    st.markdown(
        "Weights are tuned so that **percentages matter most**, raw counts "
        "add a smaller boost on top, win rate contributes moderately, and "
        "simply **attending more tournaments contributes very little** on "
        "its own."
    )
    st.markdown(
        "**Why a single lucky tournament can't dominate the leaderboard:** "
        "the percentages used inside the Score formula are *shrinkage-adjusted* "
        "towards the league average using each player's sample size (Bayesian "
        "shrinkage). A player with 1 tournament and a single win has a raw "
        "100% Top1 rate, but their *adjusted* rate is pulled heavily toward "
        "the league average since 1 tournament is a tiny sample. A player "
        "with 10 tournaments and 5 wins (50%) keeps a rate much closer to "
        "their true 50%, since their much larger sample is trusted more. "
        "Enable the checkbox above the leaderboard table to see these "
        "adjusted percentages side-by-side with the raw ones."
    )
    st.json(WEIGHTS)

conn.close()
