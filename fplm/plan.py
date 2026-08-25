"""Season plan: starting squad, chip calendar, and month-by-month targets.

Answers the operational questions rather than the analytical ones — what do I pick,
which months do I contest, when does a chip come out — and does it for the whole season
from today's data, so the plan can be refreshed daily and compared against yesterday's.

Two objectives are in play and they pull in different directions. The monthly prize
rewards spikes; the overall title rewards consistency. `monthly_weight` sets the
balance: 1.0 plans purely for monthly prizes, 0.0 purely for the season.
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

    @property
    def contested(self) -> list[MonthPlan]:
        return [m for m in self.months if m.contest]


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
    monthly_weight: float = 0.75,
    min_minutes: float = 25.0,
    budget: float = 100.0,
    current_squad: set[int] | None = None,
    simulate: bool = True,
    start: str = "xp",
    model: str = "fplm",
) -> SeasonPlan:
    """Build a whole-season plan from today's data."""
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
    # persists, so long-month value is blended in according to `monthly_weight`.
    current_month = next((m for m in months if m.start_event <= next_gw <= m.stop_event),
                         months[0])
    season_month = mo.Month(0, "rest-of-season", next_gw, min(next_gw + 9, 38))
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

    cons = opt.Constraints(
        budget=budget,
        min_expected_minutes=min_minutes,
        current_squad=current_squad or set(),
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
                                    current_month, simulate)
        if squad is None:
            squad = _solve_for_win(boot, fixtures, tables[current_month.name], rates,
                                   team_ratings, current_month, blended, cons, rivals,
                                   simulate)
        if squad is None:
            squad = opt.solve(blended, lam=opt.suggested_lam(rivals), cons=cons)

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
    allocation = chipmod.allocate(values, live_windows, months, real_counts=real_counts)

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
                # A month's winner in a casual league runs roughly 15% above a good
                # squad's own expectation; calibrated from the three-season backtest.
                field_target=sq_xp * 1.15,
                chips=[c for c in allocation if c.month == m.name],
                doubles=[short[t] for t, c in counts.items() if c > m.n_events],
                blanks=[short[t] for t, c in counts.items() if c < m.n_events],
            )
        )

    # Contest the months where chips land — that is what "targeting" means.
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

    return SeasonPlan(
        provider_note=provider_note,
        start_note=start_note,
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
                       month=None, simulate: bool = True, span: int = 4):
    """Decide this week's transfer as the first move of a multi-gameweek plan.

    Two things have to be true of the answer at once. It has to spend transfers at
    the right time, which needs several gameweeks solved jointly — a single week
    cannot express holding one back. And it has to be a squad that wins a month,
    which is not the same as the squad with the most expected points: buy the
    template and you finish mid-table by construction, which loses a prize paid to
    whoever finishes top.

    So the horizon is solved at several risk levels and the winner is chosen by
    simulated win probability, rather than by maximising expected points and hoping,
    or by looking the risk level up in a table.

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
