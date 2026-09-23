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
- A tournament with more rounds is harder to win outright than a short one,
  so a Top1/Top4/BelowTop1 result from a longer tournament should count for
  a bit more than the same result from a short one.

How the "one-hit-wonder" problem is solved
-------------------------------------------
Raw percentages (e.g. Top1 % = Top1 count / Tournaments played) are
statistically unreliable with a small sample: a player with 1 tournament and
1 win has a "perfect" 100% Top1 rate, which would otherwise score almost as
well as a player with 10 tournaments and 5 wins (50%).

**Step 1 - Bayesian shrinkage.** To fix this, percentages (and win rate) are
passed through Bayesian shrinkage (a credibility-weighted average) before
being used in the score:

    adjusted_rate = (count + K * league_average_rate) / (n + K)

This blends the player's own rate with the league-wide average rate, using K
as the number of "phantom average tournaments" assumed as a prior. With few
tournaments played (n small), the result is pulled strongly toward the
league average (so a lucky single win doesn't inflate the score). As a
player accumulates more tournaments (n >> K), the adjusted rate converges to
their true raw rate - rewarding proven, repeated consistency.

Raw (unadjusted) percentages are still shown in the app for transparency;
only the SCORE itself is computed from the shrinkage-adjusted values.

**Step 2 - round-weighted counts.** Raw COUNTS (Top1 count, Top4 count,
BelowTop1 count) are a second way the same one-hit-wonder problem can sneak
back in: unlike percentages, a flat "+5 points per Top1 finish" bonus
doesn't care whether that Top1 came from 1 tournament or 20 - so a single
lucky win could still out-score a player who consistently performs well but
hasn't won outright. On top of that, not all tournaments are equally hard to
win: a 4-round Swiss tournament is a much sterner test than a quick 2-round
one, so a Top1 finish in the former should count for more. To capture both,
raw counts are replaced by ROUND-WEIGHTED counts: each Top1/Top4/BelowTop1
result contributes `rounds_played_in_that_tournament / ROUND_REFERENCE`
instead of a flat `1` (see `ROUND_REFERENCE` below).

**Step 3 - logarithmic, capped confidence.** A THIRD, subtler way the
one-hit-wonder problem can sneak back in: shrinkage anchors a low-sample
player's adjusted rate towards the LEAGUE-WIDE average - but that average
can itself be quite generous (many tournaments here have only a handful of
players, so "finishing in the top 4" is easy in a small field). A brand-new
player who has proven NOTHING yet (say, lost every match of their only
tournament) would otherwise still get shrunk towards that generous league
average and end up with a deceptively decent-looking score.

To fix this, every rate-derived score component (the 3 percentages, the 3
round-weighted counts, and win rate) is scaled by a **confidence factor**
reflecting how much evidence actually backs it up, before being added to
the score. Confidence grows LOGARITHMICALLY with the player's tournaments
(or matches) played, and CAPS OUT (reaches 1.0, i.e. full credit) once a
player has played a fixed fraction of a "full season" worth of
tournaments/matches (a FIXED reference size - see CONFIDENCE_REFERENCE_*
below - not the league's running total, so the bar doesn't keep moving as
more tournaments get played over time):

    threshold = CONFIDENCE_CAP_FRACTION * CONFIDENCE_REFERENCE_TOURNAMENTS
    confidence = min(1, log(1 + n) / log(1 + threshold))

With `CONFIDENCE_CAP_FRACTION = 0.7` and `CONFIDENCE_REFERENCE_TOURNAMENTS =
20`, a player who has played 14+ tournaments gets full (1.0x) confidence -
anything less is scaled down, but the logarithm means confidence rises
quickly at first (so a genuinely solid sample, e.g. 13 tournaments, still
earns strong - not punishing - credit, close to 1.0x) and only flattens
out as it approaches the cap. Crucially, using a FIXED reference (not the
league's ever-growing tournament count) means a player with a genuinely
strong, well-established sample is never penalized just because some other
player has attended even more tournaments - only raw sample SIZE matters,
not sample size RELATIVE TO whoever has played the most. The same idea
applies to win rate, using total matches played and a fixed
CONFIDENCE_REFERENCE_MATCHES as the reference instead of tournaments.
"""

# Number of "phantom average tournaments" assumed as a prior when computing
# Top1 % / Top4 % / BelowTop1 % for the score. Higher = more skepticism
# towards small sample sizes.
SHRINKAGE_K_TOURNAMENTS = 4.0

# Same idea but for win rate, expressed in "phantom matches" (tournaments
# have multiple rounds, so a larger constant is used).
SHRINKAGE_K_MATCHES = 10.0

# Confidence reaches its maximum (1.0x credit) once a player has played this
# FRACTION of a "full season" worth of tournaments/matches (see
# CONFIDENCE_REFERENCE_TOURNAMENTS / CONFIDENCE_REFERENCE_MATCHES below).
# Lower = easier to reach full confidence with fewer tournaments played.
CONFIDENCE_CAP_FRACTION = 0.7

# What counts as "a full season" for confidence purposes. Deliberately a
# FIXED, absolute number - NOT the league's total tournament count so far -
# because the total grows over time as more tournaments get played. If the
# threshold scaled with the ever-growing league total, a player with a
# genuinely large, well-established sample (e.g. 13 tournaments, a strong
# 71% win rate) could still be penalized relative to a player who has
# simply attended even MORE tournaments (e.g. 27) but with a mediocre win
# rate - exactly the "raw volume beats real performance" problem this whole
# confidence mechanism exists to prevent. Anchoring to a fixed, realistic
# season length avoids that: once a player has played a genuinely solid
# sample (independent of how long the league happens to have existed),
# they get full credit.
CONFIDENCE_REFERENCE_TOURNAMENTS = 20.0
CONFIDENCE_REFERENCE_MATCHES = 60.0

# Reference round-count used to weight Top1/Top4/BelowTop1 raw counts by how
# hard a tournament actually was to win: a tournament with this many rounds
# contributes a full 1.0x per result; more rounds = more credit, fewer
# rounds = less credit (see `round_difficulty_weight()`).
ROUND_REFERENCE = 4.0

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
    confT * (
        {WEIGHTS['top1_pct']:g} * (Top1 %-adj / 100)
      + {WEIGHTS['top4_pct']:g} * (Top4 %-adj / 100)
      + {WEIGHTS['below_top1_pct']:g} * (BelowTop1 %-adj / 100)
      + {WEIGHTS['top1_count']:g} * Top1 count-weighted
      + {WEIGHTS['top4_count']:g} * Top4 count-weighted
      + {WEIGHTS['below_top1_count']:g} * BelowTop1 count-weighted
    )
  + confM * {WEIGHTS['win_rate']:g} * Win rate-adj (0-1)
  + {WEIGHTS['tournaments_played']:g} * Tournaments played

where "-adj" means the raw rate has been shrunk towards the league average
using Bayesian shrinkage with K={SHRINKAGE_K_TOURNAMENTS:g} phantom
tournaments (K={SHRINKAGE_K_MATCHES:g} phantom matches for win rate):

    adjusted_rate = (count + K * league_average_rate) / (n + K)

"count-weighted" means each Top1/Top4/BelowTop1 result is scaled by how
many rounds that particular tournament had, relative to a
{ROUND_REFERENCE:g}-round reference tournament:

    result_weight = rounds_in_that_tournament / {ROUND_REFERENCE:g}

so results from longer, harder-to-win tournaments count for more than
results from short ones.

"confT" / "confM" are CONFIDENCE factors that scale down every rate-derived
component (percentages, weighted counts, win rate) when there isn't much
evidence behind it yet. Confidence grows logarithmically and caps out
(reaches 1.0x) once a player has played {CONFIDENCE_CAP_FRACTION:g} (i.e.
{CONFIDENCE_CAP_FRACTION * 100:g}%) of a "full season"
({CONFIDENCE_REFERENCE_TOURNAMENTS:g} tournaments / {CONFIDENCE_REFERENCE_MATCHES:g} matches):

    threshold = {CONFIDENCE_CAP_FRACTION:g} * full_season_size
    confT / confM = min(1, log(1 + n) / log(1 + threshold))

Together these prevent a single lucky tournament (or a brand-new player
with no proven results at all) from producing an inflated score, while
still rewarding players who consistently perform well across many
tournaments - and without unfairly discounting players who already have a
solid (if not huge) sample backing up a genuinely strong rate.
"""

import math


def shrink_rate(count: float, n: float, league_average_rate: float, k: float) -> float:
    """Bayesian-shrink a rate (count/n) towards a league average, using k
    phantom observations as the prior strength. Returns a rate in the same
    scale as league_average_rate (e.g. 0-1 or 0-100)."""
    return (count + k * league_average_rate) / (n + k) if (n + k) > 0 else league_average_rate


def round_difficulty_weight(rounds: float, reference: float = ROUND_REFERENCE) -> float:
    """Weight applied to a single Top1/Top4/BelowTop1 result based on how
    many rounds that tournament had, relative to `reference` rounds (a
    `reference`-round tournament yields a weight of exactly 1.0; more rounds
    -> harder to win outright -> weight > 1; fewer rounds -> weight < 1)."""
    return rounds / reference if reference > 0 else 1.0


def confidence_factor(n: float, reference: float, cap_fraction: float = CONFIDENCE_CAP_FRACTION) -> float:
    """Logarithmic, capped confidence factor (0-1) reflecting how much
    evidence (n observations, e.g. tournaments or matches played) backs up
    a rate-derived score component, relative to a FIXED `reference` sample
    size representing "a full season" (see CONFIDENCE_REFERENCE_TOURNAMENTS
    / CONFIDENCE_REFERENCE_MATCHES) - NOT the league's running total, so the
    bar for "fully proven" doesn't keep moving as more tournaments get
    played over time. Confidence reaches its maximum of 1.0 once
    n >= cap_fraction * reference, and grows logarithmically (fast at
    first, flattening out) below that."""
    threshold = cap_fraction * reference
    if threshold <= 0 or n <= 0:
        return 0.0
    return min(1.0, math.log1p(n) / math.log1p(threshold))


def compute_score(metrics: dict) -> float:
    """metrics must contain: top1_pct, top4_pct, below_top1_pct (0-100),
    top1_count, top4_count, below_top1_count, win_rate (0-1),
    tournaments_played, total_matches. If present, the shrinkage-adjusted
    variants (top1_pct_adj, top4_pct_adj, below_top1_pct_adj, win_rate_adj),
    the round-weighted count variants (top1_count_weighted,
    top4_count_weighted, below_top1_count_weighted), and the precomputed
    confidence factors (conf_tournaments, conf_matches) are used instead of
    their raw/fallback counterparts."""
    top1_pct = metrics.get("top1_pct_adj", metrics["top1_pct"])
    top4_pct = metrics.get("top4_pct_adj", metrics["top4_pct"])
    below_top1_pct = metrics.get("below_top1_pct_adj", metrics["below_top1_pct"])
    win_rate = metrics.get("win_rate_adj", metrics["win_rate"])

    top1_count = metrics.get("top1_count_weighted", metrics["top1_count"])
    top4_count = metrics.get("top4_count_weighted", metrics["top4_count"])
    below_top1_count = metrics.get("below_top1_count_weighted", metrics["below_top1_count"])

    tournaments_played = metrics["tournaments_played"]
    total_matches = metrics.get(
        "total_matches",
        metrics.get("match_wins", 0) + metrics.get("match_losses", 0) + metrics.get("match_draws", 0),
    )

    # Confidence factors are normally precomputed by the stats engine using
    # the fixed CONFIDENCE_REFERENCE_* constants; fall back to computing
    # them here directly if not provided, e.g. when compute_score() is
    # called in isolation/tests.
    conf_tournaments = metrics.get(
        "conf_tournaments",
        confidence_factor(tournaments_played, CONFIDENCE_REFERENCE_TOURNAMENTS),
    )
    conf_matches = metrics.get(
        "conf_matches", confidence_factor(total_matches, CONFIDENCE_REFERENCE_MATCHES)
    )

    tournament_based_score = (
        WEIGHTS["top1_pct"] * (top1_pct / 100.0)
        + WEIGHTS["top4_pct"] * (top4_pct / 100.0)
        + WEIGHTS["below_top1_pct"] * (below_top1_pct / 100.0)
        + WEIGHTS["top1_count"] * top1_count
        + WEIGHTS["top4_count"] * top4_count
        + WEIGHTS["below_top1_count"] * below_top1_count
    )

    return (
        conf_tournaments * tournament_based_score
        + conf_matches * WEIGHTS["win_rate"] * win_rate
        + WEIGHTS["tournaments_played"] * tournaments_played
    )
