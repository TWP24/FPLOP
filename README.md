# fplm — an FPL team builder for monthly prizes

A statistical squad builder for Fantasy Premier League leagues where **each month pays
a cash prize**. That objective is different from season-long FPL in ways that change
what you should actually pick, so the tool optimises for the month and then measures
how often the squad it picked would actually *win* one.

Everything below that sounds like a claim was measured. Where the evidence was thin or
contradicted what I expected, that is said plainly.

```bash
./fplm.sh months                    # the monthly buckets and how uneven they are
./fplm.sh players -m August         # ranked player outlook for a month
./fplm.sh build -m August           # optimise a squad
./fplm.sh frontier -m August        # sweep risk appetite, rank by P(win month)
./fplm.sh backtest                  # walk-forward validation on 2025/26
```

---

## The three things that actually matter

### 1. Months are wildly uneven, and they are fixed in advance

FPL publishes the month boundaries itself, and the 2026/27 season looks like this:

| Month | GWs | # |
|---|---|---|
| August | 1–2 | **2** |
| September | 3–5 | 3 |
| October | 6–9 | 4 |
| November | 10–12 | 3 |
| December | 13–18 | **6** |
| January | 19–23 | 5 |
| February | 24–27 | 4 |
| March | 28–30 | 3 |
| April | 31–33 | 3 |
| May | 34–38 | 5 |

Every month pays the same prize, but August is two gameweeks and December is six. A
two-gameweek month is close to a coin toss — one captain haul decides it. A six-gameweek
month rewards the better squad far more reliably.

The practical consequence: **your chips and your transfer budget are worth most in the
short months**, because that is where a single decision swings the whole prize. Run
`./fplm.sh months` for the live picture.

### 2. Expected points is not the objective — winning is

A conventional FPL optimiser maximises expected points. To win a month you have to beat
the *best* of N rivals, which is a question about the tail of your distribution, not its
mean. So the tool simulates the whole month 10,000+ times, builds a field of rival
managers, and scores everyone **in the same simulated universe**.

That last part matters more than it sounds. If you and every rival own the same captain,
that captain hauling does not help you win. Simulating rivals separately would destroy
this correlation and make template picks look far better than they are.

### 3. Why chasing differentials usually loses

This is where the tool told me I was wrong.

The folk theory is sound as far as it goes: if your expected score sits below the score
needed to win, extra variance helps you. Formally, with `P(win) ≈ Φ((μ − T)/σ)` and
`μ < T`, increasing `σ` raises your chances.

The catch is what variance *costs*. In August the optimiser's squad has μ ≈ 117 against
a best-rival target T ≈ 130, with σ ≈ 21. Working through the derivative, an extra point
of σ is worth having only if it costs less than **0.56 points of mean**. Buying variance
by degrading the squad actually costs about **2 points of mean per point of σ**. It is a
bad trade, and it is a bad trade by a factor of four.

Buying variance the *other* way — owning players the field does not — is much cheaper,
because only the part of a player's variance the field is not also exposed to can move
you up the table. With the field owning a player with probability `o`, your differential
exposure is `(1 − o)` and the variance of your lead scales with `(1 − o)²`. A 60%-owned
premium contributes only 16% of his raw variance to your chances; a 3%-owned punt
contributes 94%. The optimiser prices risk on that quantity, not on raw variance.

Even then, measured across 8 independent simulated fields:

| risk λ | P(win), 19 rivals | beat λ=0 in |
|---|---|---|
| 0 | **18.8%** | — |
| 0.1 | 18.4% | 4 of 8 |
| 0.3 | 11.1% | 0 of 8 |
| 1.0 | 7.9% | 0 of 8 |

**In a 20-manager league, maximise expected points.** Deliberate differential-chasing is
a losing strategy. The edge comes from being better, not different.

That flips with league size, and the crossover is around 40 rivals:

| rivals | λ=0 | λ=0.1 | λ=0.3 | best |
|---|---|---|---|---|
| 5 | **36.9%** | 31.7 | 22.4 | λ=0 |
| 9 | **28.3%** | 25.1 | 15.8 | λ=0 |
| 19 | **17.1%** | 16.5 | 11.0 | λ=0 |
| 49 | 8.7 | **9.8%** | 6.7 | λ=0.1 |
| 99 | 5.5 | **7.7%** | 5.4 | λ=0.1 |

Skill and difference are substitutes. In a small league a good squad already wins about
one month in five against a 1-in-20 baseline, so just be good. Across a hundred rivals
someone gets lucky regardless of how good you are, and the only way into that tail is
owning players they do not. `build` picks λ from `--rivals` automatically.

---

## Does the model actually work?

`./fplm.sh backtest` rebuilds the model from scratch at the start of every month of
2025/26 using **only** gameweeks already played, then scores it against what happened.
29,757 player-gameweeks, no leakage across the month boundary.

```
                       rho  PPG rho    MAE   optimiser  template  median
2023/24  MEAN        0.450    0.469   5.18         231       205     152
2024/25  MEAN        0.462    0.454   5.10         240       208     162
2025/26  MEAN        0.420    0.419   5.51         229       204     171
pooled (24 months)   0.444    0.447   5.27         233       206     162
```

- `rho` — rank correlation of predicted vs actual monthly points.
- `optimiser / template / median` — points a squad built each way *actually* scored.

**The optimiser's squad scored 233 points per month against 162 for a median legal
squad.** That is the number that matters; rank correlation
is only a means to it.

Two honest caveats:

- On pure ranking the model is **level with points-per-game to date** (0.420 vs 0.419),
  not ahead of it. It wins the early months, when PPG has little data, and loses the late
  ones. The squad-level gap comes from combining that ranking with fixtures, budget and
  the squad constraints — not from ranking players better.
- FPL's own published `xP` is excluded from the table above. It is only populated in
  scattered gameweeks in this archive (GW7, 10, 11, 12 are entirely empty), so scoring a
  partial month against a full-month actual flattered it to a meaningless rho of 0.90.
  The backtest now reports it only where a month has >80% coverage.

### What the backtest changed

Two real bugs, both found only by running it:

1. **The minutes model was the whole problem.** The original version shrank observed
   start rates toward a price-percentile prior weighted by minutes played. Expected
   minutes is the single largest input to expected points, and the price prior was
   swamping real data. Anchoring on realised minutes per game took rho from **0.314 to
   0.415** in one change.
2. **The analytic model and the simulator disagreed by 8 points a month** — meaning the
   ILP was optimising something the simulator did not score. Three causes: clean sheets
   used plain Poisson while the simulator's overdispersed match multiplier makes shut-outs
   ~19% likelier (Jensen's inequality — the model was systematically undervaluing
   defenders); defensive contribution was discounted by `p_start` twice; and saves and
   goals-conceded ignored that FPL *floors* rather than pays pro rata. They now agree to
   **0.2%**.

The blend between the structural model and realised points per 90 survives as a tunable
(`--empirical-weight`) but, once minutes were fixed, the backtest could no longer tell
the settings apart — rho 0.412 to 0.421 across the entire range, inside the noise for
eight months. The default sits at the flat top of that curve. It is not a tuned constant
and is not presented as one.

---

## How the model works

**Team ratings** (`ratings.py`). FPL zeroes `strength_attack_*` and `strength_defence_*`
pre-season, so ratings are derived from three signals and blended: squad xG, squad xGC,
and FPL's own `strength_overall` plus the difficulty it assigns to teams facing that
opponent. Promoted clubs have no Premier League history, so they fall back entirely to
FPL's prior — visible as `prior wt` ≈ 1.0 in `./fplm.sh teams`.

Goals are negative binomial, not Poisson: a Gamma(4, ¼) multiplier per team per match.
Real football is overdispersed, and this is also what correlates teammates, so tripling
up on one attack is correctly priced as riskier than three players from three clubs.

**Player points** (`xp.py`). Per-90 rates from last season, shrunk toward positional
means by sample size, then priced against the FPL scoring table: appearance, goals,
assists, clean sheets, defensive contribution, saves, bonus, cards, goals conceded. The
structural model is run twice — once for the real fixture, once against a neutral
opponent — and their ratio gives fixture sensitivity, which is trustworthy even when the
absolute level is not.

**Optimiser** (`optimise.py`). An integer program over the full squad: 15 players, £100m,
max 3 per club, legal formation, captain, with bench points discounted to 12%. Supports
transfer planning from your current squad with hits costed at −4.

**Simulator** (`simulate.py`). 10,000+ months, correlated within teams, with automatic
substitutions and vice-captaincy. Rivals are built by solving the same optimisation under
*their own* noisy beliefs, so the field is competitive rather than random — modelling
rivals as noise made every squad look like a winner (P(win) fell from 34% to 20% when
this was fixed, and 5% is the chance baseline).

---

## Known weaknesses

These are real, and they are where the model will hurt you:

- **Pre-season minutes are guesswork.** 164 of 564 players have no Premier League
  history, and their role is inferred from price alone. They are flagged `*` in
  `players` output. This is the weakest part of the model and the reason
  `--minutes-csv` exists — feed it what you know about confirmed signings and pre-season
  friendlies:
  ```
  # name,minutes_per_start
  Rashford,80
  ```
- **Penalty duty is not modelled.** A player newly on penalties will be underrated;
  `pens-1st` is surfaced as a flag but carries no points adjustment.
- **Doubles and blanks do not exist yet.** All 380 fixtures currently sit one-per-team
  per gameweek. They appear later from cup postponements and matter enormously in a
  monthly league. `months` will flag them once they exist.
- **P(win) has real sampling error.** It depends on which 19 rivals get drawn — estimates
  moved between 14% and 22% across field draws. Treat the ranking between squads as
  meaningful and the absolute percentage as approximate.
- **Automatic substitutions are applied per month, not per gameweek.** The simulator
  only subs a player out if they miss the *entire* month, whereas FPL subs per gameweek.
  In a six-gameweek month this understates simulated scores by roughly 3% against the
  analytic figure — which is why `build` reports a simulated mean below its own xP. It
  affects you and every rival identically, so P(win) is largely unharmed, but the
  absolute simulated totals are a slight underestimate.
- **The backtest is one season, eight months.** Differences below about 0.02 in rho are
  noise. It was used to find bugs, not to tune constants finely, and the tuning it did
  inform is documented as such.

---

## Setup

```bash
cd ~/fpl
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./fplm.sh months
```

Backtest data (already downloaded to `data/`) comes from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League):

```bash
curl -L -o data/merged_gw_2025-26.csv \
  https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/2025-26/gws/merged_gw.csv
```

### Useful flags

```bash
./fplm.sh build -m August --rivals 19 --budget 100 --include Haaland --exclude Saka
./fplm.sh build -m September --entry 1234567 --free-transfers 2 --max-hits 1
./fplm.sh players -m December --position DEF --sort value --limit 40
./fplm.sh frontier -m August --rivals 19 --sims 20000
```

`--entry` is your FPL team id (the number in your team's URL), used to plan transfers
from your actual squad rather than building from scratch.

---

## Running it without your Mac

`refresh.sh` plus the launchd agent keeps the plan current on your own machine, and
copies it into iCloud Drive so it reaches your phone. That needs the Mac to be on at
some point each day, which is no good if you are away.

`.github/workflows/refresh.yml` removes that dependency. It rebuilds the plan on
GitHub's runners every morning and publishes it to GitHub Pages, so the Mac can be shut
and the URL still updates.

To turn it on:

1. Push this repo to GitHub (private is fine — Pages works on private repos on paid
   plans; on a free plan the repo needs to be public for Pages, and there is nothing
   sensitive in here beyond an FPL entry id).
2. **Settings → Pages → Source: GitHub Actions**.
3. **Settings → Secrets and variables → Actions → Variables**, add:
   - `FPL_ENTRY` — your entry id, so the plan starts from your real squad
   - `FPL_LEAGUE` — your mini-league id, to fill the League tab
   - `FPL_RIVALS` — league size minus you (defaults to 19)
4. **Actions → Refresh FPL plan → Run workflow** to check it before trusting the schedule.

The page then lives at `https://<user>.github.io/fplm/`, which you can bookmark or add
to your phone's home screen.

Two things worth knowing. GitHub schedules run in UTC and ignore daylight saving, so
06:50 UTC is 07:50 Irish summer time and 06:50 in winter. And GitHub disables scheduled
workflows in repositories with no activity for 60 days — a daily commit is not required,
but the repo cannot go completely untouched for two months.
