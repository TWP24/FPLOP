"""Per-player, per-fixture expected points.

The model decomposes a player's score into independent scoring events, prices each
one against the FPL scoring table, and scales the attacking and defensive rates by
how the fixture itself is expected to go (via the Poisson team model in `ratings`).

Pre-season caveat that shapes every choice below: FPL has published the 2026/27
player list but every current-season counter reads zero. Every rate here therefore
comes from *last* season's per-90 numbers, shrunk toward a positional mean by
sample size. For the 164 players with no Premier League minutes at all, price
percentile within position is the only role signal available. That is the weakest
part of the model and the reason `--minutes-csv` exists.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import ratings as rt

GK, DEF, MID, FWD = 1, 2, 3, 4

GOAL_POINTS = {GK: 6, DEF: 6, MID: 5, FWD: 4}
CS_POINTS = {GK: 4, DEF: 4, MID: 1, FWD: 0}
ASSIST_POINTS = 3
# Defensive contribution: defenders need 10 CBIT, everyone else 12 CBIRT, for 2 points.
DEFCON_THRESHOLD = {DEF: 10, MID: 12, FWD: 12}
DEFCON_POINTS = 2

# Shrinkage strength, in minutes. A player with exactly this many minutes lands
# halfway between their own rate and the positional mean.
SHRINK_MINUTES = 900
SHRINK_MINUTES_BONUS = 1200

# Minutes assumed for a start that ends before the hour, and for a bench cameo.
SHORT_START_MINUTES = 40.0
CAMEO_MINUTES = 18.0

# How much of the points level comes from realised points per 90 rather than from the
# component model, expressed as a half-way point in minutes played: a player with
# exactly this many minutes is trusted 50/50, and the weight rises with sample size.
#
# Honest note on this constant. It originally mattered a great deal, because a broken
# minutes model was crippling the structural side. With minutes fixed, the backtest
# spread across the entire range — pure empirical to pure structural — is rho 0.412
# to 0.421 over eight months, which is inside the noise. 5000 sits at the flat top of
# that curve and still leaves a real empirical anchor (~0.37 weight after a full
# season), which matters pre-season: a transferred player's realised scoring rate
# travels with them, while their structural components are still attributed to last
# season's club. Override with --empirical-weight if you disagree.
EMPIRICAL_SHRINK_MINUTES = 5000.0

# Games of observation before the price-implied start-rate prior is outweighed.
START_SHRINK_GAMES = 5.0

# How much of the way to pull each team's player rates toward the team model's own
# expected goals. 0.0 leaves them inconsistent, 1.0 forces exact agreement.
#
# Measured and left OFF. The sweep looked promising — optimiser points peak at +4.04 a
# month at 0.5, and calibration improves monotonically with it (level ratio 0.944 to
# 0.968, slope 0.881 to 0.901). The paired per-month test kills it: t = 1.30 over 24
# months, only 8 improved against 5 worsened, and the whole effect is one season
# (2023/24 +11.12, then +0.88 and +0.12). Removing the two largest months leaves +0.50.
#
# Pre-season it changes two players out of fifteen and moves no-Premier-League-history
# rates from 0.1630 to 0.1616. The promoted-club players it was supposed to rescue are
# already excluded on expected minutes rather than on expected goals, so the correction
# never reaches them.
#
# Adding 2022/23 to the harness later took the pooled result to t = 2.27, nominally
# significant — and then showed exactly why it should still be off. The effect is
# entirely in the two older seasons and absent from the two recent ones:
#
#     2022/23  +13.00      2024/25  +0.88
#     2023/24  +11.12      2025/26  +0.12
#
# That is a regime, not noise. Expected-goals data entered FPL in 2022/23, and while it
# was young the player-level rates were poor enough that borrowing strength from the
# team model genuinely helped. It has since stopped helping. 2026/27 resembles the
# recent regime, so the pooled figure is evidence from a world that no longer exists.
RECONCILE = 0.0

# Goals conceded by an average team against an average opponent, used as the neutral
# reference fixture when measuring how good or bad a real fixture is.
NEUTRAL_GOALS_AGAINST = 1.42

# How much of the fixture-specific clean-sheet probability to keep, the rest being
# pulled to the league average. 1.0 is no shrinkage.
#
# Left at 1.0 after measurement. Shrinking it genuinely fixes the calibration defect —
# defenders in the top 20 by prediction go from realising 0.79 of their expected points
# to 0.85 at CS_SHRINK=0.4 — but it costs optimiser points monotonically all the way
# down (221.8, 218.8, 219.4, 218.6, 217.9 at 1.0/0.85/0.7/0.55/0.4). The optimiser only
# ever compares players against each other inside a budget, and those defenders were
# still worth buying relative to the alternatives even while realising less than
# advertised. Calibration is therefore corrected for *display* instead — see
# `calibrate` — and the optimiser keeps the raw ranking it does better on.
CS_SHRINK = 1.0

# Realised = INTERCEPT + SLOPE x predicted, fitted over 8,392 player-months across
# three seasons. Slope below 1 means the model over-spreads: too optimistic about the
# players at the top, too pessimistic about those at the bottom. Per season the slope
# is 0.880 / 0.913 / 0.838 and the overall level ratio 0.913 / 0.948 / 0.969.
#
# Used only to present honest numbers. Applying it inside the optimiser would change
# nothing anyway: a positive affine transform of every player's xP leaves the ranking
# and the constrained argmax identical.
CALIBRATION_SLOPE = 0.881
CALIBRATION_INTERCEPT = 0.56

# Expected goals a first-choice penalty taker earns per match from spot kicks alone:
# roughly 0.13 penalties per team per game at about 0.79 conversion.
PENALTY_XG_PER_GAME = 0.10
# ...but a taker who already had the job last season has that value baked into their
# historical xG, so adding it all again would double-count. This is the share assumed
# to represent a *change* of duty rather than continuation. Half is a deliberate
# compromise: the API exposes who takes them now but not who took them before.
PENALTY_NEW_ROLE_SHARE = 0.5

FULL_SEASON_MINUTES = 38 * 90


@dataclass
class PlayerRates:
    """Per-90 rates for one player, already shrunk and availability-adjusted."""

    pid: int
    name: str
    team: int
    pos: int
    price: float  # in millions
    status: str
    selected_by: float

    p_start: float
    p_cameo: float
    exp_minutes: float
    p60: float

    xg90: float
    xa90: float
    defcon90: float
    saves90: float
    bonus90: float
    yellow90: float
    xgc90: float
    # Realised FPL points per 90. Backtesting says this single number out-predicts the
    # whole component model, because it silently contains set pieces, penalty duty,
    # bonus propensity and defensive work that the components estimate badly.
    pp90: float = 0.0
    # How far to trust pp90 over the structural model, from this player's sample size.
    emp_weight: float = 0.0

    # Minutes played when a start is completed, and P(reaching 60 | started).
    # Held explicitly so the analytic model and the simulator cannot drift apart.
    mins_per_start: float = 85.0
    p60_given_start: float = 1.0

    penalties_order: int | None = None
    freekicks_order: int | None = None
    corners_order: int | None = None
    news: str = ""
    flags: list[str] = field(default_factory=list)

    @property
    def set_piece_load(self) -> str:
        """Compact summary of dead-ball duty, e.g. "P1 F1 C2"."""
        bits = []
        for tag, val in (("P", self.penalties_order), ("F", self.freekicks_order),
                         ("C", self.corners_order)):
            if val:
                bits.append(f"{tag}{val}")
        return " ".join(bits)

    @property
    def available(self) -> bool:
        return self.exp_minutes > 1.0


@dataclass
class FixtureXP:
    """Expected points and variance for one player in one fixture."""

    pid: int
    event: int
    opponent: int
    home: bool
    fdr: int
    xp: float
    var: float
    components: dict[str, float]


def _positional_means(elements: list[dict]) -> dict[int, dict[str, float]]:
    """Minutes-weighted mean per-90 rates by position, used as the shrinkage target."""
    acc: dict[int, dict[str, float]] = {}
    for pos in (GK, DEF, MID, FWD):
        acc[pos] = {
            k: 0.0
            for k in ("xg90", "xa90", "defcon90", "saves90", "bonus90",
                      "yellow90", "xgc90", "pp90", "w")
        }

    for e in elements:
        m = e["minutes"]
        if m < 450:  # too few minutes to inform a league-wide mean
            continue
        a = acc[e["element_type"]]
        a["w"] += m
        a["xg90"] += float(e["expected_goals_per_90"]) * m
        a["xa90"] += float(e["expected_assists_per_90"]) * m
        a["defcon90"] += float(e["defensive_contribution_per_90"]) * m
        a["saves90"] += float(e["saves_per_90"]) * m
        a["bonus90"] += (e["bonus"] / (m / 90.0)) * m
        a["yellow90"] += (e["yellow_cards"] / (m / 90.0)) * m
        a["xgc90"] += float(e["expected_goals_conceded_per_90"]) * m
        a["pp90"] += (e.get("total_points", 0) / (m / 90.0)) * m

    out = {}
    for pos, a in acc.items():
        w = a["w"] or 1.0
        out[pos] = {k: v / w for k, v in a.items() if k != "w"}
    return out


def _price_percentile(elements: list[dict]) -> dict[int, float]:
    """Rank of each player's price within their position, in [0, 1].

    For players with no Premier League history this is the only signal we have about
    whether they are a first-choice starter — FPL prices new arrivals by expected role.
    """
    by_pos: dict[int, list[dict]] = {}
    for e in elements:
        by_pos.setdefault(e["element_type"], []).append(e)
    out: dict[int, float] = {}
    for pos, group in by_pos.items():
        group = sorted(group, key=lambda e: e["now_cost"])
        n = len(group)
        for i, e in enumerate(group):
            out[e["id"]] = i / max(n - 1, 1)
    return out


def _availability(e: dict) -> float:
    """Multiplier in [0, 1] from injury/suspension status."""
    chance = e.get("chance_of_playing_next_round")
    if chance is not None:
        return chance / 100.0
    return {"a": 1.0, "d": 0.75, "i": 0.0, "s": 0.0, "u": 0.0, "n": 0.0}.get(e["status"], 1.0)


def build_rates(boot: dict, minutes_override: dict[int, float] | None = None) -> dict[int, PlayerRates]:
    """Turn raw bootstrap elements into shrunk, availability-adjusted per-90 rates.

    `minutes_override` maps player id -> expected minutes per start, letting you inject
    what you actually know about pre-season and confirmed signings.
    """
    elements = boot["elements"]
    means = _positional_means(elements)
    pctl = _price_percentile(elements)
    minutes_override = minutes_override or {}

    rates: dict[int, PlayerRates] = {}
    for e in elements:
        pid = e["id"]
        pos = e["element_type"]
        m = float(e["minutes"])
        pm = means[pos]
        flags: list[str] = []

        def shrink(value: float, target: float, k: float = SHRINK_MINUTES) -> float:
            return (m * value + k * target) / (m + k)

        # --- Minutes model -------------------------------------------------
        # Backtesting is unambiguous here: realised minutes per game predicts future
        # minutes far better than anything reconstructed from price (rho 0.42 vs 0.37),
        # and expected minutes is the single most important input to expected points.
        # So the observed rate leads, and the price-implied prior only fills the gap
        # for players with no Premier League history.
        games = float(e.get("games_available", 38) or 38)
        prior_start = 1.0 / (1.0 + math.exp(-(pctl[pid] - 0.72) * 9.0))

        if m > 0 and e["starts"] > 0:
            raw_start_rate = min(e["starts"] / games, 1.0)
            mins_per_start = min(max(m / e["starts"], 30.0), 90.0)
            # Weight by games actually observed, not minutes. A regular seen over ten
            # gameweeks is already well measured; shrinking them halfway to a price
            # percentile throws away exactly the signal that matters.
            w_own = games / (games + START_SHRINK_GAMES)
        else:
            raw_start_rate = prior_start
            mins_per_start = 70.0 + 20.0 * pctl[pid]
            w_own = 0.0
            flags.append("no-PL-history")

        start_rate = w_own * raw_start_rate + (1 - w_own) * prior_start
        p_start = start_rate * _availability(e)

        if pid in minutes_override:
            mins_per_start = minutes_override[pid]
            flags.append("minutes-override")

        # P(reaching 60 minutes | started) rises with typical minutes per start.
        # A start that does not reach 60 (early sub, injury) is treated as ~40 minutes,
        # so expected minutes stays consistent with the simulator's own draw.
        p60_given_start = min(max((mins_per_start - 40.0) / 35.0, 0.0), 1.0)
        p_cameo = max(0.0, (1.0 - p_start)) * min(raw_start_rate + 0.15, 0.55) * _availability(e)
        mins_given_start = p60_given_start * mins_per_start + (1 - p60_given_start) * SHORT_START_MINUTES
        exp_minutes = p_start * mins_given_start + p_cameo * CAMEO_MINUTES
        p60 = p_start * p60_given_start

        if e["status"] != "a":
            flags.append(f"status:{e['status']}")
        if e.get("penalties_order") == 1:
            flags.append("pens-1st")

        rates[pid] = PlayerRates(
            pid=pid,
            name=e["web_name"],
            team=e["team"],
            pos=pos,
            price=e["now_cost"] / 10.0,
            status=e["status"],
            selected_by=float(e["selected_by_percent"]),
            p_start=p_start,
            p_cameo=p_cameo,
            exp_minutes=exp_minutes,
            p60=p60,
            mins_per_start=mins_per_start,
            p60_given_start=p60_given_start,
            xg90=shrink(float(e["expected_goals_per_90"]), pm["xg90"]),
            xa90=shrink(float(e["expected_assists_per_90"]), pm["xa90"]),
            defcon90=shrink(float(e["defensive_contribution_per_90"]), pm["defcon90"]),
            saves90=shrink(float(e["saves_per_90"]), pm["saves90"]),
            bonus90=shrink(
                e["bonus"] / (m / 90.0) if m > 0 else 0.0, pm["bonus90"], k=SHRINK_MINUTES_BONUS
            ),
            yellow90=shrink(e["yellow_cards"] / (m / 90.0) if m > 0 else 0.0, pm["yellow90"]),
            xgc90=shrink(float(e["expected_goals_conceded_per_90"]), pm["xgc90"]),
            pp90=shrink(
                e.get("total_points", 0) / (m / 90.0) if m > 0 else 0.0, pm["pp90"]
            ),
            emp_weight=m / (m + EMPIRICAL_SHRINK_MINUTES),
            penalties_order=e.get("penalties_order"),
            freekicks_order=e.get("direct_freekicks_order"),
            corners_order=e.get("corners_and_indirect_freekicks_order"),
            news=e.get("news", ""),
            flags=flags,
        )
    return rates


def team_baseline_lambdas(
    team_ratings: dict[int, rt.TeamRating], fixtures: list[dict]
) -> tuple[dict[int, float], dict[int, float]]:
    """Season-average expected goals for and against, per team.

    Used to express a single fixture as a multiplier on the team's own norm, so a
    player's rates scale with how good this particular fixture is rather than being
    double-counted against their historical baseline.
    """
    for_tot: dict[int, float] = {t: 0.0 for t in team_ratings}
    ag_tot: dict[int, float] = {t: 0.0 for t in team_ratings}
    n: dict[int, int] = {t: 0 for t in team_ratings}

    for f in fixtures:
        h, a = f["team_h"], f["team_a"]
        lh, la = rt.match_lambdas(team_ratings, h, a)
        for_tot[h] += lh
        ag_tot[h] += la
        n[h] += 1
        for_tot[a] += la
        ag_tot[a] += lh
        n[a] += 1

    return (
        {t: for_tot[t] / max(n[t], 1) for t in for_tot},
        {t: ag_tot[t] / max(n[t], 1) for t in ag_tot},
    )


def _poisson_at_least(lam: float, k: int) -> float:
    """P(X >= k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 0.0
    cum = 0.0
    term = math.exp(-lam)
    for i in range(k):
        cum += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cum)


def _expected_concede_penalty(lam_against: float, minutes_share: float) -> float:
    """E[-floor(goals_conceded / 2)] for keepers and defenders, negative binomial."""
    lam = lam_against * minutes_share
    if lam <= 0:
        return 0.0
    return -sum(rt.nb_pmf(lam, n) * (n // 2) for n in range(0, 15))


def _expected_floor_div(lam: float, divisor: int, terms: int = 25) -> float:
    """E[floor(X / divisor)] for X ~ Poisson(lam).

    FPL floors saves (1 point per 3) rather than paying pro rata, and floor() is worth
    materially less than lam/divisor — about a third of a point per keeper per match.
    """
    if lam <= 0:
        return 0.0
    total = 0.0
    term = math.exp(-lam)
    for n in range(terms):
        total += term * (n // divisor)
        term *= lam / (n + 1)
    return total


def _raw_components(
    r: PlayerRates, att_mult: float, def_mult: float, lam_against: float
) -> tuple[float, float, dict[str, float]]:
    """The structural model: build points up from individual scoring events."""
    mshare = r.exp_minutes / 90.0
    c: dict[str, float] = {}
    var = 0.0

    # Appearance: 1 point for turning up, 2 for reaching 60 minutes.
    c["appearance"] = r.p_start + r.p_cameo + r.p60
    p_any = min(r.p_start + r.p_cameo, 1.0)
    var += p_any * (1 - p_any) * 1.0 + r.p60 * (1 - r.p60) * 1.0

    # Goals. First-choice penalty takers get an explicit uplift, because a change of
    # dead-ball duty is invisible to historical per-90 rates: a player who took none
    # last season and takes them all this season looks identical in the data. Only the
    # portion NOT already reflected in their own history is added — see
    # PENALTY_XG_PER_GAME for how that is split.
    lam_g = r.xg90 * mshare * att_mult
    if r.penalties_order == 1:
        lam_g += PENALTY_XG_PER_GAME * PENALTY_NEW_ROLE_SHARE * mshare * att_mult
    gp = GOAL_POINTS[r.pos]
    c["goals"] = lam_g * gp
    var += lam_g * gp**2

    # Assists.
    lam_a_pl = r.xa90 * mshare * att_mult
    c["assists"] = lam_a_pl * ASSIST_POINTS
    var += lam_a_pl * ASSIST_POINTS**2

    # Clean sheet — needs 60 minutes and a shut-out.
    #
    # The raw probability is shrunk toward the league average shut-out rate. Clean
    # sheets are the component that dominates defender scoring and also the one that
    # regresses hardest: a team's shut-out rate over a handful of games is a noisy
    # estimate of its true rate, and the teams at the top of the ranking are there
    # partly because they got lucky. Left unshrunk, defenders in the top 20 by
    # prediction realise only 0.78-0.80 of their expected points — stable across all
    # three backtested seasons, and across the 2025/26 scoring change, so this is a
    # property of the estimator rather than of a particular rules regime.
    if CS_POINTS[r.pos] > 0:
        raw_cs = rt.clean_sheet_prob(lam_against)
        league_cs = rt.clean_sheet_prob(NEUTRAL_GOALS_AGAINST)
        shrunk_cs = CS_SHRINK * raw_cs + (1 - CS_SHRINK) * league_cs
        p_cs = r.p60 * shrunk_cs
        csp = CS_POINTS[r.pos]
        c["clean_sheet"] = p_cs * csp
        var += p_cs * (1 - p_cs) * csp**2

    # Goals conceded penalty for keepers and defenders. Unlike the clean sheet this
    # carries no 60-minute requirement, so it is gated on appearing at all.
    if r.pos in (GK, DEF):
        p_any_app = min(r.p_start + r.p_cameo, 1.0)
        c["conceded"] = p_any_app * _expected_concede_penalty(lam_against, 1.0)
        var += abs(c["conceded"]) * 1.0

    # Saves — scale with how much shooting the opponent is expected to do.
    # Points are awarded per completed set of three, so floor rather than divide.
    if r.pos == GK:
        lam_saves = r.saves90 * mshare * def_mult
        c["saves"] = _expected_floor_div(lam_saves, 3)
        var += lam_saves / 9.0

    # Defensive contribution: a threshold event, so genuinely binary. The count must
    # be conditioned on actually starting — averaging minutes in first would smear the
    # rate below the threshold and wipe out the points entirely.
    if r.pos in DEFCON_THRESHOLD:
        lam_dc = r.defcon90 * (r.mins_per_start / 90.0)
        p_dc = _poisson_at_least(lam_dc, DEFCON_THRESHOLD[r.pos]) * r.p_start
        c["defcon"] = p_dc * DEFCON_POINTS
        var += p_dc * (1 - p_dc) * DEFCON_POINTS**2

    # Bonus — taken from last season's realised rate rather than modelling BPS,
    # nudged by fixture quality.
    exp_bonus = r.bonus90 * mshare * (0.5 + 0.5 * att_mult)
    c["bonus"] = exp_bonus
    var += exp_bonus * 1.6  # bonus is lumpy: 3/2/1 or nothing

    # Cards.
    c["cards"] = -r.yellow90 * mshare
    var += abs(c["cards"]) * 1.0

    return sum(c.values()), var, c


def fixture_xp(
    r: PlayerRates,
    fixture: dict,
    team_ratings: dict[int, rt.TeamRating],
    avg_for: dict[int, float],
    avg_against: dict[int, float],
    empirical_weight: float | None = None,
) -> FixtureXP:
    """Expected points and variance for one player in one fixture.

    The structural model is run twice: once for this fixture and once against a neutral
    opponent. Their ratio is the fixture sensitivity — how much better or worse than
    usual this particular match is. That ratio is trustworthy even when the absolute
    level is not.

    The level itself is then blended toward the player's realised points per 90.
    Walk-forward testing on 2025/26 showed the component model alone ranking players
    *worse* than raw points per game (rho 0.33 vs 0.43): estimating goals, assists,
    bonus and defensive contribution separately compounds four lots of estimation
    error, while realised points already contain all four plus set pieces and penalty
    duty. Anchoring the level empirically and keeping the model only for fixture
    adjustment recovers the lost signal.
    """
    home = fixture["team_h"] == r.team
    opponent = fixture["team_a"] if home else fixture["team_h"]
    fdr = fixture["team_h_difficulty"] if home else fixture["team_a_difficulty"]

    lam_h, lam_a = rt.match_lambdas(team_ratings, fixture["team_h"], fixture["team_a"])
    lam_for, lam_against = (lam_h, lam_a) if home else (lam_a, lam_h)

    # Express this fixture relative to the team's own season average, so we scale the
    # player's historical rate rather than replacing it.
    att_mult = lam_for / max(avg_for[r.team], 1e-6)
    def_mult = lam_against / max(avg_against[r.team], 1e-6)

    if r.exp_minutes / 90.0 <= 0.01:
        return FixtureXP(r.pid, fixture["event"], opponent, home, fdr, 0.0, 0.0, {})

    xp_fix, var_fix, comps = _raw_components(r, att_mult, def_mult, lam_against)
    # The neutral reference stays a league constant rather than the team's own average
    # goals against. Using the team's own figure is arguably cleaner — goals already
    # scale relative to the team's own average — and it was tried, on the theory that
    # defenders at good defensive sides were getting a fixture factor above 1.0 in every
    # match. It is not what is wrong: it moved defender realisation from 0.79 to 0.80
    # and cost 5.2 optimiser points a month. The two errors were cancelling, because a
    # league-constant neutral also understates those same defenders' baseline.
    xp_neutral, _, _ = _raw_components(r, 1.0, 1.0, NEUTRAL_GOALS_AGAINST)

    if xp_neutral <= 1e-6:
        return FixtureXP(r.pid, fixture["event"], opponent, home, fdr, 0.0, 0.0, comps)

    w = r.emp_weight if empirical_weight is None else empirical_weight
    fixture_factor = xp_fix / xp_neutral
    xp_empirical = r.pp90 * (r.exp_minutes / 90.0)
    level = w * xp_empirical + (1 - w) * xp_neutral
    xp = fixture_factor * level

    # Rescale variance with the level so the two stay proportional.
    scale = xp / xp_fix if xp_fix > 1e-6 else 1.0
    comps = {k: v * scale for k, v in comps.items()}

    return FixtureXP(r.pid, fixture["event"], opponent, home, fdr, xp, var_fix * scale, comps)


def calibrate(xp: float, n_fixtures: int = 1, pos: int | None = None) -> float:
    """Convert a raw model xP into what it is actually expected to realise.

    Still a forecast, not an outcome — it is the prediction with a measured bias taken
    out of it, not anything that has happened. The raw number is what the optimiser
    ranks on and is deliberately left alone; this is the one a human should read. A
    player projected at 13.4 has historically returned about 12.3.

    The intercept is per player-month, so it is spread across the fixtures in the
    period rather than applied once per gameweek. Defenders at the very top of the
    ranking are additionally optimistic — they realise about 0.79 against midfielders'
    1.00 — and `pos` applies that on top where it is known.
    """
    base = CALIBRATION_INTERCEPT * min(n_fixtures, 1) + CALIBRATION_SLOPE * xp
    if pos in (GK, DEF):
        # Measured at 0.87 (GK) and 0.79 (DEF) in the top 20 by prediction, stable
        # across all three seasons including the 2025/26 scoring change. Applied at
        # half strength: the full figure is conditional on being top-20, and most
        # players being displayed are not.
        base *= 0.94
    return max(base, 0.0)


def reconcile_to_team_rates(
    rates: dict[int, PlayerRates],
    avg_for: dict[int, float],
    strength: float | None = None,
) -> None:
    """Force each team's player rates to agree with the team-level goals model.

    Adapted from AIrsenal (Alan Turing Institute), whose architecture makes this
    impossible to get wrong: a Bayesian Dixon-Coles model produces the probability of
    every scoreline, and player points are then computed *conditional* on the team's
    goals. Players necessarily share out exactly what the team is expected to score.

    This model estimates the two halves independently and they disagree badly. Summing
    each squad's minutes-weighted xG per 90 against the team model's own expected goals
    gives ratios from 0.23 to 1.18 across the twenty clubs. Promoted sides are the worst
    case by far: their players have no Premier League history, so their individual rates
    collapse toward zero while the team model correctly expects them to score about 0.89
    a game. Nothing else in the model notices, and every one of their players is
    therefore priced as if they will never score.

    Modifies `rates` in place. `strength` blends between leaving rates alone and
    imposing exact agreement.
    """
    strength = RECONCILE if strength is None else strength
    if strength <= 0:
        return

    implied: dict[int, float] = {}
    for r in rates.values():
        implied[r.team] = implied.get(r.team, 0.0) + r.xg90 * (r.exp_minutes / 90.0)

    for r in rates.values():
        target = avg_for.get(r.team)
        got = implied.get(r.team, 0.0)
        if not target or got <= 1e-6:
            continue
        # Geometric blend, so a partial correction is symmetric in over- and
        # under-estimation rather than favouring one direction.
        factor = (target / got) ** strength
        r.xg90 *= factor
        r.xa90 *= factor
