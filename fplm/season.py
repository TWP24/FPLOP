"""Full-season simulation under real FPL transfer rules.

The month-by-month backtest in `backtest.py` quietly handed the optimiser a free
wildcard every month: it rebuilt a fifteen from scratch at each month boundary. That
is not the game. This module runs a season the way it is actually played —

  * one free transfer per gameweek, bankable up to five;
  * every transfer beyond that costs four points;
  * a squad persists across month boundaries, so a bad August is still in your team
    in September;
  * selling a player returns their purchase price plus half of any profit, rounded
    down to the nearest 0.1;
  * prices move each gameweek, so team value drifts.

Everyone — you and every simulated rival — starts from the same gameweek 1 squad and
is scored on what players *really* did. The only thing that differs between strategies
is when and how they diverge from the template, which is exactly the question worth
answering.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import backtest as bt
from . import optimise as opt
from . import ratings as rt
from . import xp as xpmod
from .monthly import Month, PlayerMonth

GK, DEF, MID, FWD = 1, 2, 3, 4
SQUAD_QUOTA = {GK: 2, DEF: 5, MID: 5, FWD: 3}
MAX_FREE_TRANSFERS = 5
HIT_COST = 4
BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"


@dataclass
class Squad15:
    """A live squad: who you own, what you paid, and what is left in the bank."""

    players: set[int] = field(default_factory=set)
    purchase: dict[int, float] = field(default_factory=dict)
    bank: float = 0.0
    free_transfers: int = 1

    def value(self, price_now: dict[int, float]) -> float:
        return sum(sell_price(self.purchase[p], price_now.get(p, self.purchase[p]))
                   for p in self.players) + self.bank


def sell_price(purchase: float, current: float) -> float:
    """FPL returns your purchase price plus half the profit, rounded down to 0.1."""
    if current <= purchase:
        return current
    profit = current - purchase
    return purchase + math.floor(profit * 10 / 2) / 10


# --------------------------------------------------------------------- #
# Strategies


@dataclass
class Strategy:
    """How a manager decides what to do each gameweek.

    `lam_for_gw` returns the differential-risk appetite for a given gameweek, which is
    what lets us express "hold the template early, diverge later" as a single knob
    moving over time.
    """

    name: str
    lam_for_gw: object  # callable: (gw, month) -> float
    max_hits: int = 1
    hold_until_gw: int = 0  # make no transfers at all before this gameweek
    # "xp" chases expected points; "ownership" chases whatever the crowd owns; a
    # callable returning either lets a strategy switch objective partway through.
    objective: object = "xp"

    def objective_for_gw(self, gw: int) -> str:
        return self.objective(gw) if callable(self.objective) else self.objective


def follow_template() -> Strategy:
    """Chase the crowd every week: always converge on the most-owned squad."""
    return Strategy("follow-template", lambda gw, m: 0.0, max_hits=0, objective="ownership")


def hold_forever() -> Strategy:
    """Pick the template at GW1 and never transfer again."""
    return Strategy("set-and-forget", lambda gw, m: 0.0, max_hits=0, hold_until_gw=999)


def ev_strategy(max_hits: int = 1) -> Strategy:
    """Pure expected points every week."""
    return Strategy(f"expected-points(hits<={max_hits})", lambda gw, m: 0.0, max_hits=max_hits)


def differential_strategy(lam: float = 0.3) -> Strategy:
    """Chase differentials from the first whistle."""
    return Strategy(f"differential(lam={lam})", lambda gw, m: lam, max_hits=1)


def template_then_differentiate(switch_gw: int = 4, lam: float = 0.3) -> Strategy:
    """Hold the crowd's squad early, then diverge — the plan under test.

    Before `switch_gw` this genuinely follows ownership rather than expected points,
    so the early phase really is "the team everyone chooses" and not a model squad
    that happens to resemble it.
    """
    return Strategy(
        f"template->diff(GW{switch_gw},lam={lam})",
        lambda gw, m, s=switch_gw, l=lam: 0.0 if gw < s else l,
        max_hits=1,
        objective=lambda gw, s=switch_gw: "ownership" if gw < s else "xp",
    )


def form_chaser(max_hits: int = 2) -> Strategy:
    """The casual manager: buys whoever hauled last week, takes hits doing it.

    This is what most work-league opponents actually look like. They are not noisy
    optimisers — they are strongly template-correlated (everyone watches the same
    content and buys the same viral pick) and they pay for it in hits. Modelling the
    field this way rather than as competent optimisers changes the answer, because
    differentiation only pays when the field clusters.
    """
    return Strategy(
        f"form-chaser(hits<={max_hits})",
        lambda gw, m: 0.0,
        max_hits=max_hits,
        objective="form",
    )


def template_then_ev(switch_gw: int = 4) -> Strategy:
    """Hold the crowd's squad early, then optimise expected points without tilting."""
    return Strategy(
        f"template->EV(GW{switch_gw})",
        lambda gw, m: 0.0,
        max_hits=1,
        objective=lambda gw, s=switch_gw: "ownership" if gw < s else "xp",
    )


# --------------------------------------------------------------------- #


class SeasonRunner:
    """Precomputes per-gameweek model predictions once, then runs many strategies."""

    def __init__(self, csv_path: Path, min_history_gw: int = 4):
        self.rows = bt.load_rows(csv_path)
        self.months = bt.month_buckets(self.rows)
        self.name_to_id = bt.team_ids(self.rows)
        self.min_history_gw = min_history_gw

        self.by_gw: dict[int, list[dict]] = defaultdict(list)
        for r in self.rows:
            self.by_gw[r["gw"]].append(r)
        self.gws = sorted(self.by_gw)

        self.actual: dict[int, dict[int, float]] = {}   # gw -> pid -> points
        self.price: dict[int, dict[int, float]] = {}    # gw -> pid -> price
        self.owned: dict[int, dict[int, float]] = {}    # gw -> pid -> ownership share
        self.pos: dict[int, int] = {}
        self.team: dict[int, int] = {}
        self.pname: dict[int, str] = {}

        for gw in self.gws:
            a, pr, ow = {}, {}, {}
            total = max((int(r.get("selected", 0) or 0) for r in self.by_gw[gw]), default=1)
            for r in self.by_gw[gw]:
                a[r["pid"]] = r["points"]
                pr[r["pid"]] = r["price"]
                ow[r["pid"]] = (r.get("selected", 0) or 0) / max(total, 1)
                self.pos[r["pid"]] = r["pos"]
                self.pname[r["pid"]] = r["name"]
                tid = self.name_to_id.get(r["team_name"])
                if tid:
                    self.team[r["pid"]] = tid
            self.actual[gw], self.price[gw], self.owned[gw] = a, pr, ow

        self._tables: dict[int, dict[int, PlayerMonth]] = {}

    # ------------------------------------------------------------------ #

    def table_for_gw(self, gw: int) -> dict[int, PlayerMonth]:
        """Model predictions for a single gameweek, using only earlier gameweeks."""
        if gw in self._tables:
            return self._tables[gw]

        history = [r for r in self.rows if r["gw"] < gw]
        future = self.by_gw[gw]
        els = bt.elements_from_history(history, gw)
        for e in els:
            e["team"] = self.name_to_id.get(e["team_name"], 0)
        els = [e for e in els if e["team"]]

        team_ratings = bt.ratings_from_results(history, self.name_to_id)
        rates = xpmod.build_rates({"elements": els})

        fixtures, seen = [], set()
        for r in future:
            tid = self.name_to_id.get(r["team_name"])
            if tid is None:
                continue
            h, a = (tid, r["opponent"]) if r["home"] else (r["opponent"], tid)
            if (h, a) in seen:
                continue
            seen.add((h, a))
            fixtures.append({"event": gw, "team_h": h, "team_a": a,
                             "team_h_difficulty": 3, "team_a_difficulty": 3})

        for t in ({f["team_h"] for f in fixtures} | {f["team_a"] for f in fixtures}) - set(team_ratings):
            team_ratings[t] = rt.TeamRating(t, "", "", 1.0, 1.0, 1.0)

        all_fx, s2 = [], set()
        for r in self.rows:
            tid = self.name_to_id.get(r["team_name"])
            if tid is None:
                continue
            h, a = (tid, r["opponent"]) if r["home"] else (r["opponent"], tid)
            if (r["gw"], h, a) in s2:
                continue
            s2.add((r["gw"], h, a))
            all_fx.append({"event": r["gw"], "team_h": h, "team_a": a,
                           "team_h_difficulty": 3, "team_a_difficulty": 3})
        avg_for, avg_against = xpmod.team_baseline_lambdas(team_ratings, all_fx)

        fx_by_team: dict[int, list[dict]] = defaultdict(list)
        for f in fixtures:
            fx_by_team[f["team_h"]].append(f)
            fx_by_team[f["team_a"]].append(f)

        own = self.owned[gw]
        table: dict[int, PlayerMonth] = {}
        for pid, r in rates.items():
            if r.team not in team_ratings:
                continue
            fxs = [xpmod.fixture_xp(r, f, team_ratings, avg_for, avg_against)
                   for f in fx_by_team.get(r.team, [])]
            table[pid] = PlayerMonth(
                pid=pid, name=r.name, team=r.team, team_name=str(r.team), pos=r.pos,
                price=self.price[gw].get(pid, r.price),
                selected_by=own.get(pid, 0.0) * 100.0,
                xp=sum(f.xp for f in fxs), var=sum(f.var for f in fxs),
                n_fixtures=len(fxs), exp_minutes=r.exp_minutes, fixtures=fxs, flags=r.flags,
            )
        self._tables[gw] = table
        return table

    # ------------------------------------------------------------------ #

    def template_squad(self, gw: int) -> Squad15 | None:
        """The most-owned legal fifteen — literally the team everyone chooses.

        Solved rather than picked greedily. Taking players in pure ownership order
        spends the budget on premiums and then cannot fill the last few slots, which
        is not what real managers do: they pair the premiums with cheap enablers and
        the whole thing fits. Maximising total ownership subject to the real squad
        rules reproduces that trade-off properly.
        """
        own = self.owned[gw]
        price = self.price[gw]
        table: dict[int, PlayerMonth] = {}
        for p, o in own.items():
            if p not in self.pos or p not in self.team or p not in price:
                continue
            table[p] = PlayerMonth(
                pid=p, name=self.pname.get(p, str(p)), team=self.team[p],
                team_name=str(self.team[p]), pos=self.pos[p], price=price[p],
                selected_by=o * 100.0, xp=o, var=0.0, n_fixtures=1,
                exp_minutes=90.0, fixtures=[], flags=[],
            )
        if len(table) < 60:
            return None

        squad = opt.solve(table, lam=0.0, cons=opt.Constraints(budget=100.0))
        if squad is None:
            return None
        picked = {p.pid for p in squad.players}
        spend = sum(price[p] for p in picked)
        return Squad15(
            players=picked,
            purchase={p: price[p] for p in picked},
            bank=round(100.0 - spend, 1),
            free_transfers=1,
        )

    # ------------------------------------------------------------------ #

    def run(self, strategy: Strategy, seed: int = 0, noise: float = 0.0) -> dict:
        """Play a full season under one strategy. Returns per-month points."""
        import copy as _copy
        import random

        rnd = random.Random(seed)
        start_gw = self.gws[0]
        squad = self.template_squad(start_gw)
        if squad is None:
            raise SystemExit("Could not build a legal template squad.")

        monthly: dict[str, float] = defaultdict(float)
        gw_points: dict[int, float] = {}
        total_hits = 0
        total_transfers = 0

        for gw in self.gws:
            table = self.table_for_gw(gw)
            price = self.price[gw]
            lam = strategy.lam_for_gw(gw, None)
            hits_this_gw = 0

            # --- Transfers -------------------------------------------------
            if gw > start_gw and gw >= strategy.hold_until_gw and gw >= self.min_history_gw:
                # Chasing ownership just means swapping the objective the ILP
                # maximises; every squad rule and transfer cost stays identical.
                obj = strategy.objective_for_gw(gw)
                if obj == "ownership":
                    own_now = self.owned[gw]
                    view = {}
                    for pid, p in table.items():
                        q = _copy.copy(p)
                        q.xp = own_now.get(pid, 0.0)
                        view[pid] = q
                elif obj == "oracle":
                    # Perfect foresight: the "prediction" is what actually happened.
                    # Still bound by one free transfer a week, the budget, and every
                    # other squad rule — so this is the ceiling for *prediction*, not
                    # the ceiling for the game. The gap between a real model and this
                    # is all the headroom any amount of modelling could ever recover.
                    truth = self.actual.get(gw, {})
                    view = {}
                    for pid, p in table.items():
                        q = _copy.copy(p)
                        q.xp = truth.get(pid, 0.0)
                        view[pid] = q
                elif obj == "form":
                    # Rank by what happened last gameweek, with a nod to ownership —
                    # the casual manager's actual decision rule.
                    last = self.actual.get(gw - 1, {})
                    own_now = self.owned[gw]
                    view = {}
                    for pid, p in table.items():
                        q = _copy.copy(p)
                        q.xp = last.get(pid, 0.0) + 4.0 * own_now.get(pid, 0.0)
                        view[pid] = q
                else:
                    view = table
                if noise:
                    noisy = {}
                    for pid, p in view.items():
                        q = _copy.copy(p)
                        q.xp = p.xp * math.exp(rnd.gauss(0, noise) - 0.5 * noise**2)
                        noisy[pid] = q
                    view = noisy

                budget = squad.bank + sum(
                    sell_price(squad.purchase[p], price.get(p, squad.purchase[p]))
                    for p in squad.players
                )
                cons = opt.Constraints(
                    budget=budget,
                    current_squad=set(squad.players),
                    free_transfers=squad.free_transfers,
                    max_hits=strategy.max_hits,
                    min_expected_minutes=20.0,
                )
                # Only consider players we can actually price this week.
                pool = {p: v for p, v in view.items() if p in price}
                new = opt.solve(pool, lam=lam, cons=cons)
                if new is not None:
                    chosen = {p.pid for p in new.players}
                    out = squad.players - chosen
                    inn = chosen - squad.players
                    n = len(out)
                    if n:
                        proceeds = sum(
                            sell_price(squad.purchase[p], price.get(p, squad.purchase[p]))
                            for p in out
                        )
                        cost = sum(price[p] for p in inn)
                        squad.bank = round(squad.bank + proceeds - cost, 1)
                        for p in out:
                            squad.purchase.pop(p, None)
                        for p in inn:
                            squad.purchase[p] = price[p]
                        squad.players = chosen

                        hits = max(0, n - squad.free_transfers)
                        total_hits += hits
                        hits_this_gw = hits
                        total_transfers += n
                        squad.free_transfers = min(
                            MAX_FREE_TRANSFERS, max(1, squad.free_transfers - n + 1)
                        )
                    else:
                        squad.free_transfers = min(MAX_FREE_TRANSFERS, squad.free_transfers + 1)
                else:
                    squad.free_transfers = min(MAX_FREE_TRANSFERS, squad.free_transfers + 1)
            elif gw > start_gw:
                squad.free_transfers = min(MAX_FREE_TRANSFERS, squad.free_transfers + 1)

            # --- Pick an XI and captain from predictions, score on reality --
            # Hits are charged to the month they were taken in. Leaving them out of the
            # monthly figures hands a free pass to any strategy that transfers
            # aggressively, which is exactly what the casual field does.
            pts = self._score_gw(squad, table, gw) - HIT_COST * hits_this_gw
            gw_points[gw] = pts
            monthly[self._month_of(gw)] += pts

        return {
            "strategy": strategy.name,
            "monthly": dict(monthly),
            "gw_points": gw_points,
            "total": sum(monthly.values()),
            "hits": total_hits,
            "transfers": total_transfers,
        }

    def _month_of(self, gw: int) -> str:
        for m in self.months:
            if m.start_event <= gw <= m.stop_event:
                return m.name
        return "?"

    def _score_gw(self, squad: Squad15, table: dict[int, PlayerMonth], gw: int) -> float:
        """Best XI on predictions, captain on predictions, points from reality."""
        actual = self.actual[gw]
        played = {p: (r["minutes"] > 0) for r in self.by_gw[gw] for p in [r["pid"]]}

        members = [p for p in squad.players]
        pred = {p: (table[p].xp if p in table else 0.0) for p in members}
        xi = self._best_xi(members, pred)
        cap = max(xi, key=lambda p: pred[p]) if xi else None

        total = sum(actual.get(p, 0.0) for p in xi)

        # Automatic substitutions, in predicted order.
        bench = [p for p in members if p not in set(xi)]
        bench.sort(key=lambda p: (self.pos.get(p) == GK, -pred.get(p, 0)))
        missing = [p for p in xi if not played.get(p, False)]
        for m in missing:
            for b in list(bench):
                if not played.get(b, False):
                    continue
                if self.pos.get(m) == GK and self.pos.get(b) != GK:
                    continue
                if self.pos.get(m) != GK and self.pos.get(b) == GK:
                    continue
                total += actual.get(b, 0.0)
                bench.remove(b)
                break

        if cap is not None:
            if played.get(cap, False):
                total += actual.get(cap, 0.0)
            else:
                vice = max((p for p in xi if p != cap), key=lambda p: pred[p], default=None)
                if vice is not None and played.get(vice, False):
                    total += actual.get(vice, 0.0)
        return total

    def _best_xi(self, members: list[int], pred: dict[int, float]) -> list[int]:
        by_pos: dict[int, list[int]] = defaultdict(list)
        for p in members:
            by_pos[self.pos.get(p, MID)].append(p)
        for k in by_pos:
            by_pos[k].sort(key=lambda p: -pred.get(p, 0))
        xi = by_pos[GK][:1] + by_pos[DEF][:3] + by_pos[MID][:2] + by_pos[FWD][:1]
        chosen = set(xi)
        rest = sorted((p for p in members if p not in chosen and self.pos.get(p) != GK),
                      key=lambda p: -pred.get(p, 0))
        caps = {DEF: 5, MID: 5, FWD: 3}
        counts = {DEF: 3, MID: 2, FWD: 1}
        for p in rest:
            if len(xi) >= 11:
                break
            pos = self.pos.get(p, MID)
            if counts.get(pos, 0) < caps.get(pos, 0):
                xi.append(p)
                counts[pos] += 1
        return xi
