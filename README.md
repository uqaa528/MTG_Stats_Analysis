# MTG Stats Analysis

Tools to turn screenshots of MTG tournament standings into a queryable
SQLite database, and a Streamlit app to analyze player performance over
time.

## Project structure

```
.
├── app.py                       # Streamlit app entrypoint (run from repo root)
├── requirements.txt
├── mtg_stats.db                  # created automatically, git-ignored
├── data/
│   ├── screenshots/               # your raw tournament screenshots (git-ignored contents)
│   ├── tournament_data/           # extracted/normalized CSVs (git-ignored contents)
│   ├── name_mapping.json          # real name corrections (git-ignored, contains PII)
│   └── name_mapping.example.json  # tracked template for name_mapping.json
├── scripts/                        # non-Streamlit CLI commands
│   ├── import_csv.py
│   └── recalculate_stats.py
└── src/                              # application package
    ├── db.py                          # SQLite connection + schema
    ├── data_access.py                  # all SQL queries used by app/scripts
    ├── scoring.py                       # score weights & shrinkage formula
    ├── stats_engine.py                   # per-player measure computation
    └── ocr/                                # screenshot -> CSV extraction pipeline
        ├── extract_tournament_data.py
        ├── validate_tournament_data.py
        ├── fix_tournament_data.py
        ├── analyze_names.py
        ├── name_mapping.py
        └── apply_name_mapping.py
```

All raw/generated tournament data lives under a single `data/` folder:
`data/screenshots/` for source images and `data/tournament_data/` for the
extracted CSVs. Both folders themselves **are** tracked in the repo (via
`.gitkeep`), but their file *contents* are git-ignored — so a fresh clone
shows the expected folder structure without any of the actual tournament
images/data.

## Pipeline overview

```
data/screenshots/*.png,*.jpg
        │  (OCR - optional, only if you're starting from screenshots)
        ▼
src/ocr/extract_tournament_data.py  ──►  data/tournament_data/*.csv  (Rank, Name, Points, W-L-D)
        │
        ├─ src/ocr/validate_tournament_data.py  (sanity-check CSV format & Points = 3*W + D)
        ├─ src/ocr/fix_tournament_data.py        (recompute Points from W-L-D, clean Name artifacts)
        ├─ src/ocr/analyze_names.py               (find likely-duplicate name spellings)
        └─ src/ocr/apply_name_mapping.py          (apply confirmed data/name_mapping.json corrections)
        │
        ▼
scripts/import_csv.py        ──►  mtg_stats.db  (tournaments, results tables)
        │
        ▼
scripts/recalculate_stats.py ──►  mtg_stats.db  (player_stats_history table)
        │
        ▼
streamlit run app.py ──►  interactive analysis app
```

## Installation

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If you plan to use the OCR pipeline (extracting data from screenshots),
you also need the [tesseract](https://github.com/tesseract-ocr/tesseract)
OCR engine installed as a system package:

```bash
# macOS
brew install tesseract

# Debian/Ubuntu
sudo apt-get install tesseract-ocr
```

## File naming rules

These conventions are relied on by the scripts, so please follow them:

- **Screenshots** (`data/screenshots/`): name each file `YYYY_MM_DD.png` or
  `YYYY_MM_DD.jpg`, one per tournament date. If there are multiple events on
  the same date, append a suffix, e.g. `YYYY_MM_DD_2.png` — the date is
  parsed from the first `YYYY_MM_DD` pattern found in the filename, so the
  suffix doesn't interfere.
- **CSVs** (`data/tournament_data/`): must have the **same base filename**
  as the screenshot it was extracted from (or, if you're supplying your own
  data directly, still follow the `YYYY_MM_DD.csv` pattern), with header
  exactly:
  ```
  Rank,Name,Points,W-L-D
  ```
  where `W-L-D` is formatted like `3-0-1` (3 wins / 0 losses / 1 draw).

## Bringing your own data (fresh clone / new setup)

`data/screenshots/` and `data/tournament_data/` folder *contents*, and
`mtg_stats.db`, are all git-ignored — so a fresh clone of this repo will not
include any tournament data.

To set this up yourself:

1. Add your CSV files to `data/tournament_data/` following the naming rules
   above. You can produce these yourself from screenshots using the OCR
   pipeline below, or write/export them directly if you already have the
   data in another format.
2. Run `python scripts/import_csv.py` — **no manual database setup is
   required**. `mtg_stats.db` and its schema (`tournaments`, `results`,
   `player_stats_history` tables) are created automatically on first run
   (see `src/db.py`'s `init_db`), then your CSVs are imported into it.
3. Run `python scripts/recalculate_stats.py` to compute all measures/scores.
4. Run the Streamlit app (see below).

This whole flow was verified by deleting `mtg_stats.db` and re-running
`scripts/import_csv.py` + `scripts/recalculate_stats.py` from scratch — it
recreates the database and schema with no errors.

### Setup prompt

If you'd rather have an AI coding agent set everything up for you (e.g. in
a fresh clone, or in a new environment), you can hand it this prompt:

> Set up this repository: create/activate a Python virtual environment,
> install dependencies from `requirements.txt`, then check whether
> `data/tournament_data/` contains any CSV files. If it does, run
> `python scripts/import_csv.py` followed by
> `python scripts/recalculate_stats.py` to build/refresh `mtg_stats.db`.
> If `data/tournament_data/` is empty but `data/screenshots/` contains
> images, first run the OCR pipeline (`python -m src.ocr.extract_tournament_data`,
> then `python -m src.ocr.validate_tournament_data` and
> `python -m src.ocr.fix_tournament_data`) to produce the CSVs, then
> continue with the import/recalculate steps above. Finally, start the
> Streamlit app with `streamlit run app.py` (or, if the `streamlit` command
> isn't on PATH, `python -m streamlit run app.py` using the active
> environment's Python interpreter) and confirm it serves successfully.

## 1. Extract data from screenshots (optional — only if starting from screenshots)

```bash
python -m src.ocr.extract_tournament_data
```

Reads every file in `data/screenshots/` and writes a matching CSV (same
base filename) into `data/tournament_data/`, with columns
`Rank, Name, Points, W-L-D`.

### Validate & fix extracted CSVs

```bash
python -m src.ocr.validate_tournament_data   # reports any format/Points mismatches
python -m src.ocr.fix_tournament_data        # recomputes Points = 3*Wins + Draws, cleans Name artifacts
```

### Normalize player names

OCR often produces several spelling variants of the same person's name.

```bash
python -m src.ocr.analyze_names        # lists all unique name strings + suggested duplicate groups
```

Since the mapping contains real participant names, it is **not** stored in
git-tracked source code. Instead:

1. Copy the tracked template to create your own (gitignored) mapping file:
   ```bash
   cp data/name_mapping.example.json data/name_mapping.json
   ```
2. Edit `data/name_mapping.json` with confirmed `"raw string": "canonical name"`
   entries based on the suggestions from `analyze_names`.
3. Apply the mapping to all CSVs:
   ```bash
   python -m src.ocr.apply_name_mapping
   ```

`src/ocr/name_mapping.py` simply loads `data/name_mapping.json` at import
time (falling back to an empty mapping with a warning if the file doesn't
exist yet). `apply_name_mapping.py` also reports any raw name string it
finds that is **not yet** covered by the mapping, so nothing silently slips
through unnormalized.

## 2. Load CSVs into the SQLite database

```bash
python scripts/import_csv.py
```

- Creates `mtg_stats.db` (if it doesn't exist) with tables `tournaments` and
  `results` (see `src/db.py` for the schema).
- Scans `data/tournament_data/*.csv`. The tournament **date is parsed from
  the filename** (`YYYY_MM_DD.csv`).
- Each CSV's `W-L-D` column is split into separate `wins`, `losses`, `draws`
  integer columns in the `results` table.
- **Already-imported files are skipped** (matched by filename), so it's safe
  to re-run this after adding new CSVs — only new files get imported.

## 3. Recalculate player statistics

```bash
python scripts/recalculate_stats.py
```

Rebuilds the `player_stats_history` table from scratch based on whatever is
currently in `tournaments`/`results`. Run this after every
`scripts/import_csv.py` run that added new tournaments, **and after any
change to the measure/score calculation logic** (see "Customizing measure
calculations" below).

This table stores, **per player per tournament date**, their cumulative
stats up to and including that date — this is what powers the "measure over
time" chart in the app.

## 4. Run the Streamlit app

```bash
streamlit run app.py
```

If the `streamlit` command isn't recognized in your shell (`command not
found: streamlit`), it usually means Streamlit was installed into a Python
environment whose `bin/` directory isn't on your shell's `PATH`. You have
two options:

**Option A — run it as a module with the active environment's Python
interpreter** (always works, no PATH setup needed):

```bash
python -m streamlit run app.py
```

**Option B — activate the environment first, then use `streamlit`
directly.** If you're using a `venv`/`virtualenv` at `.venv/`:

```bash
source .venv/bin/activate   # NOT `.venv/bin/activate` alone — it must be sourced
streamlit run app.py
```

(Running `.venv/bin/activate` directly, without `source`, gives a
`permission denied` error — it's a script meant to be sourced into your
current shell, not executed.)

Once running, Streamlit prints a local URL (default
`http://localhost:8501`) — open it in your browser. On first run in a new
environment, Streamlit may prompt for an email address in the terminal;
just press Enter to skip it.

Features:
- **Date range filter** (sidebar) — restricts both the leaderboard and the
  time-series chart to a window of tournaments.
- **Leaderboard** — recomputed live for exactly the selected date range
  (not just a filtered snapshot), showing Score, Tournaments played, TOP1 /
  TOP4 / BelowTOP1 counts and percentages, and win rate.
- **Measure over time chart** — one line per selected player, showing how
  their chosen measure (Score, TOP1 %, TOP4 %, BelowTOP1 %, raw counts, win
  rate, tournaments played) evolved tournament-by-tournament. **Defaults to
  the top 8 scorers in the currently selected measure** (re-picked whenever
  you change the measure dropdown), and can be freely adjusted via the
  multiselect.
- **Win rate over time** — always shown as an additional chart below the
  main measure chart (for the same selected players), even if you've picked
  a different measure above, so win rate trends are never more than one
  scroll away. (If you select "Win rate" as the main measure, this second
  chart is hidden to avoid showing the same chart twice.)
- **Custom SQL query panel** — run any read-only `SELECT` statement against
  the database directly from the app, for ad-hoc exploration.
- **Measure explanations panel** — hidden by default, toggle via the sidebar
  checkbox "Show measure explanations". Explains TOP1 / TOP4 / BelowTOP1 /
  win rate / percentages and shows the exact Score formula and weights.

## Measure definitions

- **TOP1** — player's Points total equals the *highest* Points total in that
  tournament (ties all count).
- **TOP4** — player finished in the top 4 of the tournament's official Rank
  standings.
- **BelowTOP1** — player didn't reach TOP1, but their Points total equals
  the *second-highest distinct* Points total in that tournament. This
  avoids under-crediting players who, due to pairing randomness, ended up a
  tier below the winner(s) even though several players share that near-miss
  result (e.g. two players at 2-1-0 and one at 1-1-1 — if 1-1-1 is the next
  distinct tier down, that player also counts as BelowTOP1).
- **Tournament presence** — number of tournaments a player appears in
  (within the selected range).
- **Win rate** — `(match wins + 0.5 × match draws) / total matches`. Draws
  count as half a win.
- **% measures** — TOP1/TOP4/BelowTOP1 counts divided by tournaments played,
  × 100.

## Score formula

Defined in `src/scoring.py`, shown live in the app's explanation panel:

```
Score =
    40 * (TOP1 %-adj / 100)
  + 20 * (TOP4 %-adj / 100)
  + 15 * (BelowTOP1 %-adj / 100)
  +  5 * TOP1 count
  +  3 * TOP4 count
  +  2 * BelowTOP1 count
  + 10 * Win rate-adj (0-1)
  + 0.5 * Tournaments played
```

Percentages carry the most weight, raw counts add a smaller boost, win rate
contributes moderately, and simply attending more tournaments contributes
very little on its own — as requested.

### Preventing "one-hit-wonders" from dominating the leaderboard

Raw percentages are unreliable with a small sample: a player with **1**
tournament and **1** win has a "perfect" 100% TOP1 rate, which would
otherwise score almost as well as a player with 10 tournaments and 5 wins
(50%) — rewarding luck over consistency.

To fix this, every `%-adj` value above is **Bayesian-shrunk** towards the
league-wide average rate before being used in the Score:

```
adjusted_rate = (count + K * league_average_rate) / (n + K)
```

where `K` is a number of "phantom average tournaments" assumed as a prior
(`K=4` for TOP1/TOP4/BelowTOP1 %, `K=10` "phantom matches" for win rate,
configurable in `src/scoring.py`). With a small sample (`n` small), the
result is pulled strongly toward the league average — so a single lucky win
can't inflate the score. As a player accumulates more tournaments (`n >>
K`), the adjusted rate converges to their true raw rate, rewarding proven,
repeated consistency.

Raw (unadjusted) percentages are still shown in the leaderboard for
transparency — check the "Show score-adjusted (shrunk) % columns" checkbox
above the leaderboard table to see both side-by-side.

## Customizing measure calculations

All measure/score logic lives in two files, kept deliberately separate from
data access and the UI:

- **`src/scoring.py`** — the Score weights (`WEIGHTS` dict), the shrinkage
  strength constants (`SHRINKAGE_K_TOURNAMENTS`, `SHRINKAGE_K_MATCHES`), the
  `shrink_rate()` helper, and `compute_score()`. Edit this file to:
  - change how much each measure contributes to Score (adjust `WEIGHTS`),
  - change how aggressively small samples get shrunk towards the league
    average (adjust the `SHRINKAGE_K_*` constants — higher = more
    skepticism towards players with few tournaments/matches),
  - change the Score formula itself (edit `compute_score()`).
  `FORMULA_TEXT` in this file is auto-generated from `WEIGHTS` and is what's
  displayed in the app's explanation panel, so it stays in sync
  automatically — no need to update it by hand.

- **`src/stats_engine.py`** — `compute_core_stats()` defines what counts as
  TOP1 / TOP4 / BelowTOP1 and computes win rate, tournaments played, and the
  league-wide averages used for shrinkage. Edit this file to:
  - change the TOP1/TOP4/BelowTOP1 tier logic itself (e.g. use a different
    rule for "near miss" instead of the second-highest-distinct-points
    tier),
  - add an entirely new measure (add it to the per-player dict here, wire
    it into `compute_score()` in `scoring.py`, add a column for it to the
    `player_stats_history` table schema in `src/db.py`, and add it to
    `MEASURE_LABELS` in `app.py` so it's selectable in the chart dropdown).

**After making any change here, always re-run**
`python scripts/recalculate_stats.py` to rebuild `player_stats_history`
with the new logic — the Streamlit app's leaderboard is computed live so it
picks up changes immediately, but the "measure over time" chart reads from
the precomputed history table, which only updates when you re-run this
script.

## File reference

| File | Purpose |
|---|---|
| `src/ocr/extract_tournament_data.py` | OCR screenshots → CSV |
| `src/ocr/validate_tournament_data.py` | Validate CSV format / Points formula |
| `src/ocr/fix_tournament_data.py` | Auto-fix Points & clean Name artifacts |
| `src/ocr/analyze_names.py` | Suggest duplicate-name groups |
| `src/ocr/name_mapping.py` | Loads `data/name_mapping.json` into `NAME_MAP` |
| `data/name_mapping.json` | Gitignored raw-name → canonical-name mapping (real names) |
| `data/name_mapping.example.json` | Tracked template for `name_mapping.json` |
| `src/ocr/apply_name_mapping.py` | Apply the name mapping to all CSVs |
| `src/db.py` | SQLite connection + schema |
| `src/data_access.py` | All SQL queries used by the app/CLI scripts |
| `src/scoring.py` | Score weights, shrinkage & formula |
| `src/stats_engine.py` | Per-player measure computation + history builder |
| `scripts/import_csv.py` | CLI: import new CSVs into the DB |
| `scripts/recalculate_stats.py` | CLI: rebuild `player_stats_history` |
| `app.py` | Streamlit app |
| `requirements.txt` | Python dependencies |
