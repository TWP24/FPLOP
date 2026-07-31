"""Team attack / defence ratings.

FPL zeroes out `strength_attack_*` and `strength_defence_*` during pre-season,
so we derive our own ratings from three independent signals and blend them:

  1. Squad xG        — minutes-weighted sum of each player's xG90 from last season.
                       Transfers carry their output from their old club, which is
                       exactly what we want as a squad-quality proxy.
  2. Squad xGC       — minutes-weighted mean of defenders'/keepers' xGC90.
  3. FPL's own prior — `strength_overall_home/away` (1-5, hand-set by FPL) plus the
                       difficulty FPL assigns to teams that face this opponent.
                       This is the only signal that covers promoted clubs, so it
                       carries full weight where there is no Premier League history.

Output is a multiplicative rating centred on 1.0 feeding a Poisson goals model:

    lambda_home = BASE_HOME * attack[home] * defence[away]
    lambda_away = BASE_AWAY * attack[away] * defence[home]
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Premier League long-run baselines: ~2.85 goals/game split by home advantage.
BASE_HOME = 1.55
BASE_AWAY = 1.30

# How far one standard deviation of team quality moves the goal rate.
# 0.30 => a +2sd attack scores exp(0.6) = 1.8x the league average.
K_ATTACK = 0.30
K_DEFENCE = 0.28

# Gamma shape for the per-match team multiplier. Real football is overdispersed
# relative to a plain Poisson: blowouts and shut-outs both happen more often than
# Poisson predicts. Mixing Poisson over Gamma(k, 1/k) gives a negative binomial,
# which fits far better. Shared by the analytic model and the simulator so the two
# cannot disagree about how likely a clean sheet is.
MATCH_SHAPE = 4.0

# Minimum minutes of Premier League history before squad data is trusted at all.
MIN_SQUAD_MINUTES = 6000


@dataclass
class TeamRating:
    team_id: int
    short_name: str
    name: str
    attack: float
    defence: float  # <1.0 means concedes fewer than average
    prior_weight: float  # how much of the rating came from FPL's prior vs squad data

    @property
    def net(self) -> float:
        """Single-number strength, handy for sorting and display."""
        return self.attack / self.defence


def _zscore(values: dict[int, float]) -> dict[int, float]:
    xs = list(values.values())
    mu = sum(xs) / len(xs)
    var = sum((x - mu) ** 2 for x in xs) / len(xs)
    sd = math.sqrt(var) if var > 0 else 1.0
    return {k: (v - mu) / sd for k, v in values.items()}


def _squad_signals(boot: dict) -> tuple[dict[int, float], dict[int, float], dict[int, float]]:
    """Return (xg_per_match, xgc_per_match, pl_minutes) keyed by team id."""
    xg: dict[int, float] = {}
    xgc_num: dict[int, float] = {}
    xgc_den: dict[int, float] = {}
    mins: dict[int, float] = {}

    for t in boot["teams"]:
        xg[t["id"]] = 0.0
        xgc_num[t["id"]] = 0.0
        xgc_den[t["id"]] = 0.0
        mins[t["id"]] = 0.0

    for e in boot["elements"]:
        tid = e["team"]
        m = e["minutes"]
        if m <= 0:
            continue
        mins[tid] += m
        # Season xG contributed by this player = xG90 * (minutes / 90), spread over 38 games.
        xg[tid] += float(e["expected_goals_per_90"]) * (m / 90.0) / 38.0
        # xGC90 is already a team-level rate; weight defenders and keepers by minutes.
        if e["element_type"] in (1, 2):
            xgc_num[tid] += float(e["expected_goals_conceded_per_90"]) * m
            xgc_den[tid] += m

    xgc = {
        tid: (xgc_num[tid] / xgc_den[tid]) if xgc_den[tid] > 0 else 0.0
        for tid in xgc_num
    }
    return xg, xgc, mins


def _fdr_signal(boot: dict, fixtures: list[dict]) -> dict[int, float]:
    """How hard FPL thinks it is to face each team, averaged over all 38 fixtures."""
    total: dict[int, float] = {t["id"]: 0.0 for t in boot["teams"]}
    count: dict[int, int] = {t["id"]: 0 for t in boot["teams"]}
    for f in fixtures:
        # The difficulty the home team is given reflects how hard the away team is.
        total[f["team_a"]] += f["team_h_difficulty"]
        count[f["team_a"]] += 1
        total[f["team_h"]] += f["team_a_difficulty"]
        count[f["team_h"]] += 1
    return {tid: total[tid] / max(count[tid], 1) for tid in total}


def build(boot: dict, fixtures: list[dict], prior_weight: float = 0.5) -> dict[int, TeamRating]:
    """Blend squad data with FPL's prior into per-team attack/defence multipliers.

    KNOWN ISSUE, unhandled by choice (July 2026). Two things change the moment the
    season starts, and neither raises an error:

      * `strength_overall_home/away` changes *units*, not just values. Pre-season it is
        a 1-5 scale (Arsenal 4 and 5); in-season it is roughly 1000-1400 (Arsenal 1305
        and 1355, per the 2025/26 end-of-season snapshot). This function z-scores it, so
        nothing breaks loudly — the signal simply starts being measured on a different
        scale from the squad xG it is blended with.
      * `strength_attack_home/away` and `strength_defence_home/away` are all zero
        pre-season and populate once games are played. They are separate attack and
        defence figures split by venue, which is exactly what the Poisson model wants,
        and are strictly better than the proxy derived here. This function ignores them.

    Both were left alone deliberately: they cannot be tested before real values exist,
    and the existing pipeline is what has been backtested. Revisit after GW1, when the
    live values can actually be inspected.

    `prior_weight` is the floor weight given to FPL's own ratings. Teams without
    enough Premier League history (promoted clubs) are pushed to weight 1.0.
    """
    xg, xgc, pl_minutes = _squad_signals(boot)
    fdr = _fdr_signal(boot, fixtures)
    overall = {
        t["id"]: (t["strength_overall_home"] + t["strength_overall_away"]) / 2.0
        for t in boot["teams"]
    }

    # FPL's prior: high strength_overall and high faced-difficulty both mean "good team".
    # KNOWN ISSUE, deliberately not handled — see the note above `build`.
    z_overall = _zscore(overall)
    z_fdr = _zscore(fdr)
    z_prior = {tid: 0.5 * z_overall[tid] + 0.5 * z_fdr[tid] for tid in z_overall}

    z_xg = _zscore(xg)
    # Conceding fewer xG is better, so flip the sign to make "high = good defence".
    z_xgc = _zscore({tid: -v for tid, v in xgc.items()})

    ratings: dict[int, TeamRating] = {}
    for t in boot["teams"]:
        tid = t["id"]
        # Teams with thin PL history lean entirely on FPL's prior.
        coverage = min(pl_minutes[tid] / MIN_SQUAD_MINUTES, 1.0)
        w = prior_weight + (1.0 - prior_weight) * (1.0 - coverage)
        w = min(max(w, 0.0), 1.0)

        z_att = w * z_prior[tid] + (1 - w) * z_xg[tid]
        z_def = w * z_prior[tid] + (1 - w) * z_xgc[tid]

        ratings[tid] = TeamRating(
            team_id=tid,
            short_name=t["short_name"],
            name=t["name"],
            attack=math.exp(K_ATTACK * z_att),
            defence=math.exp(-K_DEFENCE * z_def),
            prior_weight=w,
        )

    # Renormalise so the league average multiplier is exactly 1.0 in both directions.
    n = len(ratings)
    mean_att = sum(r.attack for r in ratings.values()) / n
    mean_def = sum(r.defence for r in ratings.values()) / n
    for r in ratings.values():
        r.attack /= mean_att
        r.defence /= mean_def

    return ratings


def match_lambdas(
    ratings: dict[int, TeamRating], home_id: int, away_id: int
) -> tuple[float, float]:
    """Expected goals for (home, away) in a single fixture."""
    lam_h = BASE_HOME * ratings[home_id].attack * ratings[away_id].defence
    lam_a = BASE_AWAY * ratings[away_id].attack * ratings[home_id].defence
    return lam_h, lam_a


def nb_pmf(lam: float, n: int, k: float = MATCH_SHAPE) -> float:
    """P(X = n) for goals X ~ NegBinomial with mean `lam` and Gamma shape `k`."""
    if lam <= 0:
        return 1.0 if n == 0 else 0.0
    p = k / (k + lam)
    coef = 1.0
    for i in range(n):
        coef *= (k + i) / (i + 1)
    return coef * (p**k) * ((1 - p) ** n)


def clean_sheet_prob(lam_against: float, k: float = MATCH_SHAPE) -> float:
    """P(opponent fails to score).

    Uses the negative binomial rather than exp(-lambda). Because P(0 goals) is convex
    in the goal rate, mixing over match-to-match variation *raises* the shut-out
    probability — around 0.32 rather than 0.27 at a rate of 1.3. Using plain Poisson
    here systematically undervalues defenders and keepers.
    """
    return (1.0 + lam_against / k) ** (-k)
