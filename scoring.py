"""
Scoring model: defines how a single arbitrary "Score" is computed for each
player from their tournament measures. Kept in one place so both the stats
engine (which writes history to the DB) and the Streamlit app (which shows
the formula/weights to the user) stay in sync.

Design intent (per product requirement):
- % measures (Top1 %, Top4 %, BelowTop1 %) should matter MOST.
- Raw counts (Top1 count, Top4 count, BelowTop1 count) should matter, but less.
- Win rate matters, but less than the tournament-tier measures.
- Simply attending more tournaments should contribute VERY LITTLE on its own.
- Players who score high in a SINGLE tournament and never appear again should
  NOT out-score players who consistently perform well across many
  tournaments. Consistency across a larger sample should be rewarded.

How the "one-hit-wonder" problem is solved
-------------------------------------------
Raw percentages (e.g. Top1 % = Top1 count / Tournaments played) are
statistically unreliable with a small sample: a player with 1 tournament and
1 win has a "perfect" 100% Top1 rate, which would otherwise score almost as
well as a player with 10 tournaments and 5 wins (50%).

To fix this, percentages (and win rate) are passed through **Bayesian
shrinkage** (a credibility-weighted average) before being used in the score:

    adjusted_rate = (count + K * league_average_rate) / (n + K)

This blends the player's own rate with the league-wide average rate, using K
as the number of "phantom average tournaments" assumed as a prior. With few
tournaments played (n small), the result is pulled strongly toward the
league average (so a lucky single win doesn't inflate the score). As a
player accumulates more tournaments (n >> K), the adjusted rate converges to
their true raw rate - rewarding proven, repeated consistency.

Raw (unadjusted) percentages are still shown in the app for transparency;
only the SCORE itself is computed from the shrinkage-adjusted values.
"""

# Number of "phantom average tournaments" assumed as a prior when computing
# Top1 % / Top4 % / BelowTop1 % for the score. Higher = more skepticism
# towards small sample sizes.
SHRINKAGE_K_TOURNAMENTS = 4.0

# Same idea but for win rate, expressed in "phantom matches" (tournaments
# have multiple rounds, so a larger constant is used).
SHRINKAGE_K_MATCHES = 10.0

WEIGHTS = {
    "top1_pct": 40.0,
    "top4_pct": 20.0,
    "below_top1_pct": 15.0,
    "top1_count": 5.0,
    "top4_count": 3.0,
    "below_top1_count": 2.0,
    "win_rate": 10.0,
    "tournaments_played": 0.5,
}

FORMULA_TEXT = f"""Score =
    {WEIGHTS['top1_pct']:g} * (Top1 %-adj / 100)
  + {WEIGHTS['top4_pct']:g} * (Top4 %-adj / 100)
  + {WEIGHTS['below_top1_pct']:g} * (BelowTop1 %-adj / 100)
  + {WEIGHTS['top1_count']:g} * Top1 count
  + {WEIGHTS['top4_count']:g} * Top4 count
  + {WEIGHTS['below_top1_count']:g} * BelowTop1 count
  + {WEIGHTS['win_rate']:g} * Win rate-adj (0-1)
  + {WEIGHTS['tournaments_played']:g} * Tournaments played

where "-adj" means the raw rate has been shrunk towards the league average
using Bayesian shrinkage with K={SHRINKAGE_K_TOURNAMENTS:g} phantom
tournaments (K={SHRINKAGE_K_MATCHES:g} phantom matches for win rate):

    adjusted_rate = (count + K * league_average_rate) / (n + K)

This prevents a single lucky tournament from producing an inflated 100%
rate, while rewarding players who consistently perform well across MANY
tournaments (their adjusted rate converges to their true raw rate as
tournaments played grows).
"""


def shrink_rate(count: float, n: float, league_average_rate: float, k: float) -> float:
    """Bayesian-shrink a rate (count/n) towards a league average, using k
    phantom observations as the prior strength. Returns a rate in the same
    scale as league_average_rate (e.g. 0-1 or 0-100)."""
    return (count + k * league_average_rate) / (n + k) if (n + k) > 0 else league_average_rate


def compute_score(metrics: dict) -> float:
    """metrics must contain: top1_pct, top4_pct, below_top1_pct (0-100),
    top1_count, top4_count, below_top1_count, win_rate (0-1),
    tournaments_played. If present, the shrinkage-adjusted variants
    (top1_pct_adj, top4_pct_adj, below_top1_pct_adj, win_rate_adj) are used
    instead of the raw ones - falling back to raw values if not provided."""
    top1_pct = metrics.get("top1_pct_adj", metrics["top1_pct"])
    top4_pct = metrics.get("top4_pct_adj", metrics["top4_pct"])
    below_top1_pct = metrics.get("below_top1_pct_adj", metrics["below_top1_pct"])
    win_rate = metrics.get("win_rate_adj", metrics["win_rate"])

    return (
        WEIGHTS["top1_pct"] * (top1_pct / 100.0)
        + WEIGHTS["top4_pct"] * (top4_pct / 100.0)
        + WEIGHTS["below_top1_pct"] * (below_top1_pct / 100.0)
        + WEIGHTS["top1_count"] * metrics["top1_count"]
        + WEIGHTS["top4_count"] * metrics["top4_count"]
        + WEIGHTS["below_top1_count"] * metrics["below_top1_count"]
        + WEIGHTS["win_rate"] * win_rate
        + WEIGHTS["tournaments_played"] * metrics["tournaments_played"]
    )
