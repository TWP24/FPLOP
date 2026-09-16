"""Season plan: starting squad, chip calendar, and month-by-month targets.

Answers the operational questions rather than the analytical ones — what do I pick,
when does a chip come out, where do the points come from — and does it for the whole
season from today's data, so the plan can be refreshed daily and compared against
yesterday's.

**The objective is the season.** Win the season and the monthly prizes come with it:
the manager with the most points at the end is, by construction, the one who won or
came close in most months along the way. The reverse does not hold. Playing for a
monthly cheque means spending chips early to contest a month you would otherwise
coast, buying variance to spike a four-gameweek window, and picking a squad for the
fixtures in front of you rather than the ones that last — every one of which costs
season points to buy a lottery ticket.

Both objectives are still available, because the tool was built for a league that pays
monthly and that money is real:

    objective="season"  — the default. Squad picked for the rest of the season, chips
                          where they score most, risk appetite flat.
    objective="month"   — the old behaviour. Squad picked for the month in front of
                          you, chips spread to contest as many months as possible,
                          risk appetite chosen by simulated monthly win probability.

`monthly_weight` is the underlying dial and still overrides the objective's default:
1.0 values only the month ahead, 0.0 only the rest of the season.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import chips as chipmod
from . import monthly as mo
from . import optimise as opt
from . import ratings as rt
from . import xp as xpmod


@dataclass
class MonthPlan:
    month: mo.Month
    n_gws: int
    squad_xp: float
    field_target: float
    chips: list[chipmod.ChipValue] = field(default_factory=list)
    contest: bool = False
    doubles: list[str] = field(default_factory=list)
    blanks: list[str] = field(default_factory=list)

    @property
    def chip_value(self) -> float:
        return sum(c.value for c in self.chips)

    @property
    def projected(self) -> float:
        return self.squad_xp + self.chip_value


@dataclass
class SeasonPlan:
    generated: str
    next_gw: int
    squad: opt.Squad
    months: list[MonthPlan]
    tables: dict[str, dict[int, mo.PlayerMonth]]
    team_ratings: dict = field(default_factory=dict)
    sim_scores: object = None      # Monte Carlo month totals, for the distribution chart
    sim_target: float = 0.0        # score the month's winner is expected to post
    sim_p_win: float = 0.0
    provider_note: str = ""
    start_note: str = ""
    objective: str = "season"
    kept: set[int] = field(default_factory=set)
    # The transfer this plan is recommending right now, as (out, in) names. The
    # forward planner starts *from* the squad chosen here and skips transfers for its
    # first gameweek, so it never sees this move and cannot report it. The dashboard
    # once said "no transfer - roll it" beside a squad that had already sold Haaland.
    moves_now: list[tuple[str, str]] = field(default_factory=list)
    # Free text from overrides.json, so a manual correction is visible on the page
    # rather than silently in force.
    note: str = ""

    @property
    def contested(self) -> list[MonthPlan]:
        return [m for m in self.months if m.contest]

    @property
    def season_xp(self) -> float:
        """Projected points from here to GW38, chips included."""
        return sum(m.projected for m in self.months)

    @property
    def season_target(self) -> float:
        """What the season's winner is expected to post over the same gameweeks."""
        return self.season_xp * (1.0 + season_winner_edge(len(self.months)))


# How much of the squad's valuation comes from the month in front of you rather than
# the rest of the season. Not zero even when the season is the objective: the near
# month is the part of the estimate that is actually reliable — team news, price,
# who is starting — and the far horizon is a fixture list multiplied by last season's
# rates. The weight is a precision argument, not an objective one.
MONTHLY_WEIGHT = {"season": 0.2, "month": 0.75}

# A monthly-prize plan spreads chips so it can contest more months. A season plan
# spends them where they score most and lets the months fall where they fall.
CHIPS_PER_MONTH = {"season": None, "month": 2}

# How far above a good squad's own expectation the winner of a month lands. Calibrated
# from the three-season backtest.
MONTH_WINNER_EDGE = 0.15

# The same figure for a whole season, which is emphatically NOT the monthly one summed:
# nobody wins every month, and a manager who tops the table has usually won two or
# three and been solid in the rest. The month winner's edge is part being better, which
# persists, and part running hot, which does not — so the luck half averages out over
# the months while the skill half stays. Split 50/50 for want of a measurement.
#
# This is a PRIOR. It sets the bar the season chart draws, nothing that is decided on.
# It gets replaced the moment the backtest is pointed at the right question: what the
# winning manager's season total was, against a good squad's own expectation, in each
# of the four seasons already downloaded.
WINNER_SKILL_SHARE = 0.5


def season_winner_edge(n_months: int) -> float:
    """What the season's winner clears a good squad's own expectation by."""
    if n_months < 1:
        return MONTH_WINNER_EDGE
    luck = MONTH_WINNER_EDGE * (1.0 - WINNER_SKILL_SHARE) / n_months**0.5
    return MONTH_WINNER_EDGE * WINNER_SKILL_SHARE + luck


def _season_label(boot: dict) -> str:
    """FPL does not publish a season string, so derive it from the GW1 deadline."""
    ev = sorted(boot["events"], key=lambda e: e["id"])
    year = int(ev[0]["deadline_time"][:4]) if ev else 2026
    return f"{year}-{str(year + 1)[2:]}"


def build(
    boot: dict,
    fixtures: list[dict],
    prior_weight: float = 0.5,
    minutes_override: dict[int, float] | None = None,
    rivals: int = 19,
    objective: str = "season",
    monthly_weight: float | None = None,
    min_minutes: float = 25.0,
    budget: float = 100.0,
    current_squad: set[int] | None = None,
    free_transfers: int = 1,
    max_hits: int = 0,
    simulate: bool = True,
    start: str = "xp",
    model: str = "fplm",
    note: str = "",
    keep: set[int] | None = None,
    captain: int | None = None,
) -> SeasonPlan:
    """Build a whole-season plan from today's data."""
    if objective not in MONTHLY_WEIGHT:
        raise ValueError(f"objective must be one of {sorted(MONTHLY_WEIGHT)}")
    if monthly_weight is None:
        monthly_weight = MONTHLY_WEIGHT[objective]

    team_ratings = rt.build(boot, fixtures, prior_weight=prior_weight)
    rates = xpmod.build_rates(boot, minutes_override=minutes_override)
    months = mo.get_months(boot)

    next_gw = next((e["id"] for e in boot["events"] if e.get("is_next")), None)
    if next_gw is None:
        next_gw = next((e["id"] for e in boot["events"] if not e["finished"]), 1)

    tables = {
        m.name: mo.build_table(boot, fixtures, rates, team_ratings, m) for m in months
    }

    # A different provider replaces the xP values while leaving every other field —
    # price, ownership, fixtures, minutes — exactly as built, so the optimiser, the
    # chip planner and the dashboard are all indifferent to which model produced them.
    provider_note = ""
    if model != "fplm":
        from pathlib import Path as _P

        from . import providers as pv

        season = _season_label(boot)
        prov, provider_note = pv.resolve(model, season, next_gw)
        if prov.name != "fplm":
            cmap = pv.code_map_from(_P(__file__).resolve().parent.parent
                                    / "data" / f"players_raw_{season}.csv")
            for m in months:
                got = prov.predict(boot, fixtures, m, season=season, code_map=cmap)
                if not got.ok:
                    continue
                for pid, v in got.xp.items():
                    if pid in tables[m.name]:
                        tables[m.name][pid].xp = v

    # The starting squad is chosen for the month we are about to enter, but a squad
    # persists, so rest-of-season value is blended in according to `monthly_weight`.
    current_month = next((m for m in months if m.start_event <= next_gw <= m.stop_event),
                         months[0])
    # Every gameweek left, not a ten-week window. The window was a hedge against the
    # far fixtures being noise, but the blend already normalises per gameweek, so a
    # longer horizon does not shout louder — it just stops the valuation ending in
    # February. A season objective has to be able to see the end of the season.
    season_month = mo.Month(0, "rest-of-season", next_gw, 38)
    season_table = mo.build_table(boot, fixtures, rates, team_ratings, season_month)

    blended: dict[int, mo.PlayerMonth] = {}
    now_tbl = tables[current_month.name]
    for pid, p in now_tbl.items():
        import copy as _copy

        q = _copy.copy(p)
        soon = season_table.get(pid)
        # Normalise both to a per-gameweek rate before blending, otherwise the longer
        # horizon simply dominates by having more fixtures in it.
        a = p.xp / max(p.n_fixtures, 1)
        b = (soon.xp / max(soon.n_fixtures, 1)) if soon and soon.n_fixtures else a
        q.xp = (monthly_weight * a + (1 - monthly_weight) * b) * max(p.n_fixtures, 1)
        blended[pid] = q

    # FPL publishes no endpoint for how many free transfers you are holding, so it
    # has to be told. Defaulting to one is safe but wrong the week after you bank
    # one: the plan would consider a single move when two are available free.
    cons = opt.Constraints(
        budget=budget,
        min_expected_minutes=min_minutes,
        current_squad=current_squad or set(),
        free_transfers=max(1, min(free_transfers, opt.MAX_BANKED_TRANSFERS)),
        max_hits=max_hits,
        include=set(keep or ()),
    )

    # Forcing the most-owned fifteen is a pre-season device: before a ball is kicked
    # there is no squad to keep, and the measured result is that the crowd's fifteen
    # beats the model's. Once a real squad exists that reasoning no longer applies —
    # you cannot buy the template without paying for the transfers, and the plan has
    # to start from the team actually owned and recommend moves from there.
    if start == "template" and not current_squad:
        # The most-owned legal fifteen, solved rather than taken in ownership order —
        # picking greedily spends the budget on premiums and then cannot fill the last
        # slots, which is not what real managers do.
        #
        # This is the measured choice, not a hedge. Scored on actual points across four
        # seasons, weighting the pick toward ownership beats pure expected points
        # monotonically: 1790 at zero weight, 1928 at half, 1974 at full. The crowd can
        # see fitness, team news and manager preference; the model reads last season's
        # per-90 rates and a fixture list.
        own_view: dict[int, mo.PlayerMonth] = {}
        for pid, p in now_tbl.items():
            import copy as _copy2

            q = _copy2.copy(p)
            q.xp = p.selected_by
            own_view[pid] = q
        squad = opt.solve(own_view, lam=0.0,
                          cons=opt.Constraints(budget=budget, min_expected_minutes=0.0))
        if squad is not None:
            # The fifteen come from ownership, but the eleven must not. Solving on
            # ownership also picks the XI on ownership, which benched a 7.2 xP
            # midfielder for a 1.4 xP defender purely because more people owned the
            # defender. You always field your best eleven regardless of how the squad
            # was assembled, so re-solve the XI and the armband on expected points with
            # the fifteen held fixed.
            fifteen = {p.pid for p in squad.players}
            cost = squad.cost
            refield = opt.solve(
                {pid: v for pid, v in now_tbl.items() if pid in fifteen},
                lam=0.0,
                cons=opt.Constraints(budget=999.0, min_expected_minutes=0.0,
                                     include=fifteen),
            )
            if refield is not None:
                squad = opt.Squad(
                    players=[now_tbl[p.pid] for p in refield.players],
                    starters=refield.starters, captain=refield.captain,
                    vice=refield.vice, lam=0.0, cost=cost,
                )
            else:
                squad = opt.Squad(
                    players=[now_tbl[p.pid] for p in squad.players],
                    starters=squad.starters, captain=squad.captain, vice=squad.vice,
                    lam=0.0, cost=cost,
                )
    else:
        # A transfer is a decision about several gameweeks, not one. Solving a single
        # week greedily cannot express holding a transfer so that two moves land
        # together later, because there is no variable for the transfer you did not
        # make — which is why it once wanted to spend a free transfer for +0.88 xP.
        # Measured over four seasons, planning four gameweeks jointly is worth +22.5
        # points across twenty-one gameweeks, better in every season.
        squad = _solve_with_horizon(boot, fixtures, rates, team_ratings, next_gw,
                                    current_squad, cons, blended, budget, rivals,
                                    current_month, simulate, objective=objective)
        if squad is None and objective == "month":
            squad = _solve_for_win(boot, fixtures, tables[current_month.name], rates,
                                   team_ratings, current_month, blended, cons, rivals,
                                   simulate)
        if squad is None:
            # A season is long enough that the mean wins it. Spread only pays when you
            # need to leapfrog a field in a four-gameweek window, and the measured cost
            # of buying it is about 2 points of mean for 1 of spread — see the risk
            # table in the README. Over 38 gameweeks that is simply a worse squad.
            lam = 0.0 if objective == "season" else opt.suggested_lam(rivals)
            squad = opt.solve(blended, lam=lam, cons=cons)

    start_note = ("most-owned fifteen (no squad held yet)"
                  if start == "template" and not current_squad
                  else f"held squad of {len(current_squad)}, "
                       f"{cons.free_transfers} free transfer(s), max {cons.max_hits} hits"
                  if current_squad else "expected points")

    if squad is None and current_squad:
        # Relaxing to a free rebuild silently would show a fifteen that ignores the
        # transfer rules and the squad actually owned, which is worse than saying so.
        squad = opt.solve(blended, lam=0.0,
                          cons=opt.Constraints(budget=budget,
                                               current_squad=current_squad))
        start_note = ("could not find a legal move from the held squad — "
                      "showing it unchanged") if squad else start_note
    if squad is None:
        squad = opt.solve(blended, lam=0.0, cons=opt.Constraints(budget=budget))
        if current_squad:
            start_note = ("WARNING: no legal plan from your squad; "
                          "showing a free rebuild that ignores transfer limits")
    if squad is None:
        raise SystemExit("No feasible squad — check your constraints.")

    # --- Per-gameweek expected points, needed to price single-week chips ----
    per_gw = _per_gameweek_xp(boot, fixtures, rates, team_ratings)

    # --- Value every chip in every month -----------------------------------
    values: list[chipmod.ChipValue] = []
    for m in months:
        if m.stop_event < next_gw:
            continue
        tbl = tables[m.name]
        values.append(chipmod.triple_captain_value(squad, tbl, m, per_gw))
        values.append(chipmod.bench_boost_value(squad, m, per_gw))
        values.append(chipmod.free_hit_value(squad, tbl, m, per_gw, cons))
        values.append(chipmod.wildcard_value(squad, tbl, m, cons))

    live_windows = [w for w in chipmod.windows(boot) if w.stop_event >= next_gw]
    # Real fixture counts per gameweek, so the blank/double prior retires itself as
    # soon as the schedule actually shows one.
    real_counts: dict[int, int] = {}
    for f in fixtures:
        if f["event"]:
            real_counts[f["event"]] = real_counts.get(f["event"], 0) + 2
    allocation = chipmod.allocate(values, live_windows, months,
                                  max_per_month=CHIPS_PER_MONTH[objective],
                                  real_counts=real_counts)

    # --- Assemble the month-by-month view ----------------------------------
    counts_by_month = {m.name: mo.fixture_counts(fixtures, m) for m in months}
    short = {t["id"]: t["short_name"] for t in boot["teams"]}

    plans: list[MonthPlan] = []
    for m in months:
        if m.stop_event < next_gw:
            continue
        tbl = tables[m.name]
        sq_xp = sum(tbl[p.pid].xp for p in squad.xi if p.pid in tbl)
        cap = max((tbl[p.pid].xp for p in squad.xi if p.pid in tbl), default=0.0)
        sq_xp += cap

        counts = counts_by_month[m.name]
        plans.append(
            MonthPlan(
                month=m,
                n_gws=m.n_events,
                squad_xp=sq_xp,
                field_target=sq_xp * (1.0 + MONTH_WINNER_EDGE),
                chips=[c for c in allocation if c.month == m.name],
                doubles=[short[t] for t, c in counts.items() if c > m.n_events],
                blanks=[short[t] for t, c in counts.items() if c < m.n_events],
            )
        )

    # Under a monthly objective this is the plan's whole shape: these are the months
    # you go for and the rest you coast. Under a season objective nothing is being
    # coasted — the flag just marks where the chips land, which is where the month
    # totals jump.
    for p in plans:
        p.contest = bool(p.chips)

    # Simulate the month we are entering, so the dashboard can show the actual
    # distribution of outcomes rather than a mean with an error bar. This is the only
    # place the Monte Carlo runs for display; everything else uses it for decisions.
    sim_scores, sim_target, sim_p_win = None, 0.0, 0.0
    if simulate:
        try:
            from .simulate import MonthSimulator

            sim = MonthSimulator(boot, fixtures, tables[current_month.name], rates,
                                 team_ratings, current_month, n_sims=6000)
            field = sim.build_field(rivals, cons)
            res = sim.evaluate(squad, field)
            sim_scores, sim_target, sim_p_win = res.scores, res.target, res.p_win
        except Exception:  # noqa: BLE001 — a chart is never worth failing the build for
            pass

    # An armband you have already chosen. The optimiser's pick is a recommendation,
    # and once it has been declined the page should show the team you are actually
    # fielding rather than keep arguing for a different one.
    if captain and captain in {p.pid for p in squad.xi}:
        vice = squad.vice if squad.vice != captain else squad.captain
        squad = opt.Squad(players=squad.players, starters=squad.starters,
                          captain=captain, vice=vice, lam=squad.lam, cost=squad.cost)

    moves_now: list[tuple[str, str]] = []
    if current_squad:
        chosen = {p.pid for p in squad.players}
        gone = sorted(current_squad - chosen)
        came = sorted(chosen - current_squad)
        names = {pid: r.name for pid, r in rates.items()}
        for o, i in zip(gone, came):
            moves_now.append((names.get(o, str(o)), names.get(i, str(i))))

    return SeasonPlan(
        objective=objective,
        provider_note=provider_note,
        start_note=start_note,
        kept=set(keep or ()),
        moves_now=moves_now,
        note=note,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        next_gw=next_gw,
        squad=squad,
        months=plans,
        tables=tables,
        team_ratings=team_ratings,
        sim_scores=sim_scores,
        sim_target=sim_target,
        sim_p_win=sim_p_win,
    )


def _solve_with_horizon(boot, fixtures, rates, team_ratings, next_gw, current_squad,
                       cons, blended, budget: float, rivals: int = 19,
                       month=None, simulate: bool = True, span: int = 4,
                       objective: str = "season"):
    """Decide this week's transfer as the first move of a multi-gameweek plan.

    Two things have to be true of the answer at once. It has to spend transfers at
    the right time, which needs several gameweeks solved jointly — a single week
    cannot express holding one back. And it has to be a squad that wins a month,
    which is not the same as the squad with the most expected points: buy the
    template and you finish mid-table by construction, which loses a prize paid to
    whoever finishes top.

    So under a monthly objective the horizon is solved at several risk levels and the
    winner is chosen by simulated win probability, rather than by maximising expected
    points and hoping, or by looking the risk level up in a table.

    Under a season objective that second requirement is gone, and with it the reason
    to pay for spread: nothing has to be won inside a four-gameweek window, so the
    horizon is solved once at zero risk and the points are the answer. Which is also
    why the template regression that motivated the win-probability search is not a
    regression here — finishing mid-table in March is not a failure if the season
    total is the thing being maximised.

    Returns None when there is no squad to plan from, the horizon cannot be built, or
    nothing solves — the caller falls back to the single-week paths.
    """
    if not current_squad:
        return None
    try:
        from . import horizon as hzmod

        gws = [g for g in range(next_gw, next_gw + span) if g <= 38]
        tabs = {}
        for g in gws:
            tbl = mo.build_table(boot, fixtures, rates, team_ratings,
                                 mo.Month(0, f"gw{g}", g, g))
            if tbl:
                tabs[g] = tbl
        if next_gw not in tabs or len(tabs) < 2:
            return None

        held_cost = sum(blended[p].price for p in current_squad if p in blended)
        bank = max(budget - held_cost, 0.0)

        # Build the field before choosing anything, then price differential risk
        # against what it actually owns. Optimising against published ownership while
        # being scored against this field would leave the objective and the
        # evaluation measuring different things.
        sim = field = None
        if simulate:
            try:
                from .simulate import MonthSimulator

                sim = MonthSimulator(boot, fixtures, tabs[next_gw], rates,
                                     team_ratings,
                                     mo.Month(0, f"gw{next_gw}", next_gw, next_gw),
                                     n_sims=4000)
                field = sim.build_field(rivals, cons)
                tabs = {g: sim.apply_field_ownership(t) for g, t in tabs.items()}
            except Exception:  # noqa: BLE001
                sim = field = None

        if objective == "season":
            lams = [0.0]
        else:
            lams = [0.0, 0.1, 0.2, 0.3] if sim else [opt.suggested_lam(rivals)]
        candidates = []
        for lam in lams:
            plan = hzmod.solve(tabs, set(current_squad), bank, cons,
                               free_transfers=cons.free_transfers,
                               max_hits_per_gw=cons.max_hits, lam=lam,
                               time_limit=60)
            if plan is None or next_gw not in plan.squads:
                continue
            fifteen = plan.squads[next_gw]
            if not all(p in blended for p in fifteen):
                continue
            sq = _refield(fifteen, blended, lam)
            if sq is not None:
                candidates.append(sq)
        if not candidates:
            return None
        if sim is None or field is None or len(candidates) == 1:
            return candidates[0]
        # Every candidate is scored against the same field, so the comparison is
        # paired rather than four separate draws.
        return max(candidates, key=lambda sq: sim.evaluate(sq, field).p_win)
    except Exception:  # noqa: BLE001 — never fail a plan for want of a horizon
        return None


def _refield(fifteen, blended, lam):
    """Best legal eleven and armband from a fixed fifteen, on the blended view."""
    refield = opt.solve(
        {pid: v for pid, v in blended.items() if pid in fifteen},
        lam=lam,
        cons=opt.Constraints(budget=999.0, min_expected_minutes=0.0,
                             include=set(fifteen)),
    )
    if refield is None:
        return None
    return opt.Squad(players=[blended[p.pid] for p in refield.players],
                     starters=refield.starters, captain=refield.captain,
                     vice=refield.vice, lam=lam,
                     cost=sum(blended[p].price for p in fifteen))


def _solve_for_win(boot, fixtures, now_tbl, rates, team_ratings, month, blended,
                   cons, rivals: int, simulate: bool):
    """Choose the risk level by simulated win probability rather than by rule.

    `suggested_lam` maps a rival count to a risk appetite from a sweep run once,
    across simulated fields, for a squad built from scratch. None of those
    conditions necessarily hold now: the field is this league, the fixtures are
    this month, and the squad is usually one transfer away from what is already
    owned. Measuring beats interpolating when the machinery to measure is already
    here — the frontier command has done exactly this for months.

    Falls back to the rule when simulation is off or anything goes wrong, because
    a plan that fails to build is worse than one built from a heuristic.
    """
    if not simulate:
        return None
    try:
        from .simulate import MonthSimulator

        sim = MonthSimulator(boot, fixtures, now_tbl, rates, team_ratings, month,
                             n_sims=4000)
        field = sim.build_field(rivals, cons)
        # Price differential risk against what this field actually owns. Optimising
        # against published ownership while being scored against this field would
        # leave the objective and the evaluation measuring different things.
        priced = sim.apply_field_ownership(blended)
        lams = [0.0, 0.05, 0.1, 0.2, 0.3]
        squads = opt.frontier(priced, lams, cons)
        if not squads:
            return None
        best = max(squads, key=lambda s: sim.evaluate(s, field).p_win)
        return opt.Squad(players=[blended[p.pid] for p in best.players],
                         starters=best.starters, captain=best.captain,
                         vice=best.vice, lam=best.lam, cost=best.cost)
    except Exception:  # noqa: BLE001 — never fail a plan for want of a simulation
        return None


def _per_gameweek_xp(boot, fixtures, rates, team_ratings) -> dict[int, dict[int, float]]:
    """Expected points for every player in every individual gameweek."""
    avg_for, avg_against = xpmod.team_baseline_lambdas(team_ratings, fixtures)
    by_team_gw: dict[tuple[int, int], list[dict]] = {}
    for f in fixtures:
        if f["event"] is None:
            continue
        by_team_gw.setdefault((f["team_h"], f["event"]), []).append(f)
        by_team_gw.setdefault((f["team_a"], f["event"]), []).append(f)

    out: dict[int, dict[int, float]] = {}
    for (team, gw), fxs in by_team_gw.items():
        slot = out.setdefault(gw, {})
        for pid, r in rates.items():
            if r.team != team:
                continue
            slot[pid] = sum(
                xpmod.fixture_xp(r, f, team_ratings, avg_for, avg_against).xp for f in fxs
            )
    return out
