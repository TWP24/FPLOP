# fplm — an FPL tool for monthly-prize leagues

A squad builder, chip planner and dashboard for Fantasy Premier League leagues where
**each month pays a cash prize**. That objective is different from season-long FPL in
ways that change what you should pick, so the tool optimises for the month and then
measures how often the squad it picked would actually *win* one.

**Live: [twp24.github.io/FPLOP](https://twp24.github.io/FPLOP/)** — rebuilt every
morning on GitHub's runners, no local machine involved.

Everything below that sounds like a claim was measured. Where the evidence contradicted
what I expected — which was most of the time — that is what is written down.

```bash
./fplm.sh plan                      # squad, chips, week-by-week plan, dashboard
./fplm.sh months                    # the monthly buckets and how uneven they are
./fplm.sh template                  # the most-owned legal fifteen, vs the model's
./fplm.sh players -m August         # ranked player outlook
./fplm.sh backtest                  # walk-forward validation, four seasons
```

---

## The finding that matters most: the crowd beats the model

Scored on **actual points** across four seasons, tilting squad selection toward what
everyone else owns beats pure expected points, monotonically:

| ownership weight | season total |
|---|---|
| 0.0 — pure model | 1,790 |
| 0.5 | 1,928 |
| **1.0 — pure template** | **1,974** |

**+184 points a season, winning 3 of 4 seasons.** Not a hedge — the better strategy.

The reason is information, not cleverness. The crowd sees fitness, team news, who the
manager rates and who has quietly been dropped. This model reads last season's per-90
rates and a fixture list. Six million people reading team news beat it, and they beat it
*even though* the ownership squad starts obvious dead weight.

So `plan` defaults to `--start template`. The fifteen come from ownership; the eleven and
the armband are then chosen on expected points, because ownership is a reason to buy a
player and never a reason to start him.

## Months are uneven, and fixed in advance

FPL publishes the boundaries itself. August is **2 gameweeks**, December is **6** — same
prize. A two-gameweek month is close to a coin toss; one captain haul decides it.

Your chips and transfers are worth most where a single decision swings a whole prize.
`./fplm.sh months` shows the live picture.

## Chasing differentials loses

The folk theory — behind on the mean, so buy variance — is sound until you price it. An
extra point of spread is worth having only if it costs less than **0.56** points of mean;
degrading the squad to get it costs about **2**. Measured across 8 simulated fields:

| risk λ | P(win), 19 rivals | beat λ=0 |
|---|---|---|
| 0 | **18.8%** | — |
| 0.3 | 11.1% | 0 of 8 |

It only starts paying above ~40 rivals. `suggested_lam` picks from `--rivals`, and for a
20-person league returns 0 — ownership has no effect on your squad at all.

## Hits do not pay

| max hits | season total | vs never |
|---|---|---|
| **0** | 1,790 | — |
| 3 | 1,834 | +45 |

+45 looks like a win until the per-season split: **+19, −42, +214, −11**. One season is
the whole result and two of four go backwards.

The control settles it: with **perfect foresight**, allowing hits is worth **+259** a
season; with this model, **+30**. Hits pay handsomely when your predictions justify a −4.
These don't. Default is 0, and the condition for revisiting is written into the source.

---

## Does the model work?

`./fplm.sh backtest` rebuilds from scratch at every month boundary using **only**
gameweeks already played.

```
                       rho  PPG rho    MAE   optimiser  template  median
2023/24  MEAN        0.450    0.469   5.18         231       205     152
2024/25  MEAN        0.462    0.454   5.10         240       208     162
2025/26  MEAN        0.420    0.419   5.51         229       204     171
pooled (24 months)   0.444    0.447   5.27         233       206     162
```

**The optimiser's squad scored 233 points a month against 162 for a median legal squad.**
That is the number that matters.

But on pure ranking the model is **level with points-per-game to date** (0.444 vs 0.447)
— fractionally behind, in fact. The squad-level gap comes from combining that ranking
with fixtures, budget and squad constraints, not from ranking players better.

### 14 changes tested, zero net gain

A ten-agent audit plus follow-up work tested fourteen model changes. **None survived.**
Everything that ever worked was structural — a missing autosub scorer, a minutes model
shrinking to a price prior, clean sheets using the wrong distribution, hits not charged
to months. Bugs, not insights.

The diagnostic that explains it: **rho within the top 60 by prediction — the only region
the optimiser shops in — is ~0.17 and barely moves.** Agents produced pooled rho gains of
+0.10 that bought nothing, because they improved separation among players already
excluded.

The project is instrument-limited, not idea-limited: expected-goals data starts in
2022/23, so four seasons is the ceiling, and the optimiser metric's standard error is
4–5 points a month.

## Two models, one switch

```bash
./fplm.sh plan --model fplm      # built in, runs anywhere
./fplm.sh plan --model dastan    # SmartPlayFPL's open model
```

On 17,622 identical player-gameweeks, [Dastan](https://github.com/qazybekb/smartplayfpl-dastan)
is better where its data reaches — **starters rho 0.414 against 0.356**, MAE 0.919
against 1.272 — and beats FPL's own `ep_next` too. Blending was tested and rejected: the
best blend beats pure Dastan by +0.002 rho against seed noise of 0.0106. This model
contributes no independent signal.

Its feature frame currently ends at 2025-26, so for 2026/27 it falls back and says why.
`predictions.json` records which model made each forecast, so the tracker settles it with
data. `./fetch_dastan.sh` vendors it. See [DASTAN_INTEGRATION.md](DASTAN_INTEGRATION.md).

---

## What's on the dashboard

Five tabs, plus a **before the deadline** panel that leads with team news on your own
squad — 55 players currently carry injury text the model reads and would otherwise never
show.

**Squad** · **Season** (chips, months to contest, simulated outcome distribution) ·
**Gameweeks** (every week to GW38 with transfers, captain, chips) · **League** (rivals'
real squads and ownership measured in *your* league) · **Charts**.

Both `xP` and `xP adj` are shown. Both are forecasts — the second has the model's
measured bias removed (realised = 0.56 + 0.881 × predicted over 8,392 player-months).
Actual outcomes appear from GW1 via the tracker, which writes each prediction down
**before** the deadline and never revises it.

## Running it

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./fplm.sh plan
```

Three independent delivery paths, which fail for different reasons:

| | updates | needs |
|---|---|---|
| GitHub Pages | daily 06:50 UTC | nothing of yours |
| launchd → iCloud Drive | daily 07:50 local | the Mac powered on |
| `./refresh.sh` | on demand | you |

Repository variables `FPL_ENTRY`, `FPL_LEAGUE` (space-separated for several),
`FPL_RIVALS`, `FPL_START` configure the cloud build.

## Known weaknesses

- **Pre-season minutes are guesswork.** 164 of 564 players have no Premier League
  history and their role is inferred from **price**. Flagged `?` on the dashboard. This
  is the weakest part of the model and the reason `--minutes-csv` exists — it is also the
  one place a human beats it outright.
- **Team strength fields change units at GW1** (1–5 pre-season, ~1000–1400 after) and the
  granular attack/defence fields go from zero to populated. Documented in
  `ratings.build`, deliberately unhandled until real values exist.
- **Blanks and doubles do not exist yet.** Chip values use a documented prior for where
  they historically land, which retires itself as soon as the real fixtures show one.
- **P(win) has real sampling error** — it depends which 19 rivals get drawn. Treat the
  ranking between squads as meaningful and the percentage as approximate.
- **Automatic substitutions are per gameweek in the backtest but per month in the Monte
  Carlo**, understating simulated totals ~3%. Affects you and every rival identically.

Backtest data comes from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League);
`data/README.md` has the fetch commands.
