"""Gameweek-by-gameweek forward plan to the end of the season.

Rolls the squad forward from today under real FPL rules — one free transfer a week
bankable to five, four points a hit, chips fired in the gameweeks the chip planner
picked — and records what the squad looks like at every step.

This is a *projection*, not a prediction of what you should literally do in gameweek 31.
Its value is in the shape: where the transfers cluster, which weeks the chips land, and
which months the squad is actually built for. Re-running it daily is the point, because
every new injury and price change moves it.

Two honest limits. Prices are held flat, so team value never grows here — measured
separately as worth about 0.45 expected points per million, which is small against the
noise in everything else. And the further out a gameweek is, the more the projection is
really saying "a good squad for these fixtures" rather than "these fifteen players".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import chips as chipmod
from . import monthly as mo
from . import optimise as opt
from . import ratings as rt
from . import xp as xpmod

GK, DEF, MID, FWD = 1, 2, 3, 4
MAX_FREE_TRANSFERS = 5
HIT_COST = 4

CHIP_LABEL = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
}


@dataclass
class Move:
    out_name: str
    in_name: str
    out_price: float
    in_price: float


@dataclass
class GWPlan:
    gw: int
    month: str
    squad: list[int]
    xi: list[int]
    captain: int
    vice: int
    captain_name: str
    formation: str
    moves: list[Move] = field(default_factory=list)
    hits: int = 0
    free_transfers: int = 1
    bank: float = 0.0
    chip: str | None = None
    projected: float = 0.0

    @property
    def chip_label(self) -> str | None:
        return CHIP_LABEL.get(self.chip) if self.chip else None

    @property
    def net_projected(self) -> float:
        return self.projected - HIT_COST * self.hits


def _single_gw_month(gw: int) -> mo.Month:
    return mo.Month(0, f"GW{gw}", gw, gw)


def build(
    boot: dict,
    fixtures: list[dict],
    season_plan,
    horizon_weight: float = 0.8,
    hold_gws: int = 0,
    # Zero, and measured. Allowing hits scores +45 a season on average across four
    # seasons, but the average is one season: +19, -42, +214, -11. Two of four go
    # backwards, and dropping 2024-25 leaves -11.
    #
    # The control is what settles it. With perfect foresight, allowing hits is worth
    # +259 a season; with this model it is worth +30. Hits pay handsomely when your
    # predictions are good enough to justify a -4, and this model ranks players no
    # better than points-per-game. Revisit if the Actual-vs-predicted tracker ever
    # shows the model beating its own forecast over 8-10 gameweeks.
    max_hits: int = 0,
    min_minutes: float = 25.0,
    budget: float = 100.0,
) -> list[GWPlan]:
    """Roll the squad forward one gameweek at a time to the end of the season.

    `horizon_weight` blends each gameweek's own expected points with the following few
    gameweeks, so the planner does not churn the squad chasing a single good fixture and
    then immediately undo it. Zero is purely myopic. Swept across the season: 0.0 scores
    2196 over 67 transfers, 0.8 scores 2257 over 46. Looking ahead is better *and*
    cheaper, which is the same result the transfer-planning agent found independently.

    `hold_gws` would stop a player being sold within a few gameweeks of being bought.
    It defaults to off because it was measured and did not work: at 3 gameweeks it cost
    4 points and left re-buying essentially unchanged (31 against 32), and at 5 it was
    worse again. The re-buying turns out not to be flip-flopping — it is legitimate
    fixture rotation, selling a defender after a good run and buying him back for the
    next one. The horizon blend already removes the genuinely wasteful churn.
    """
    team_ratings = rt.build(boot, fixtures, prior_weight=0.5)
    rates = xpmod.build_rates(boot)
    names = {r.pid: r.name for r in rates.values()}
    prices = {r.pid: r.price for r in rates.values()}
    months = mo.get_months(boot)

    all_gws = sorted({f["event"] for f in fixtures if f["event"]})
    start = season_plan.next_gw
    gws = [g for g in all_gws if g >= start]

    # Chip allocation comes from the season plan: chip -> gameweek it fires in.
    chip_at: dict[int, str] = {}
    for m in season_plan.months:
        for c in m.chips:
            chip_at.setdefault(c.gw, c.chip)

    # Per-gameweek tables, built once and reused.
    tables: dict[int, dict[int, mo.PlayerMonth]] = {}
    for g in gws:
        tables[g] = mo.build_table(boot, fixtures, rates, team_ratings, _single_gw_month(g))

    def blended(g: int) -> dict[int, mo.PlayerMonth]:
        """This gameweek's points, nudged by the next few, to damp churn."""
        import copy as _copy

        ahead = [x for x in gws if g < x <= g + 3]
        base = tables[g]
        out: dict[int, mo.PlayerMonth] = {}
        for pid, p in base.items():
            q = _copy.copy(p)
            fut = [tables[x][pid].xp for x in ahead if pid in tables[x]]
            avg = sum(fut) / len(fut) if fut else p.xp
            q.xp = (1 - horizon_weight) * p.xp + horizon_weight * avg
            out[pid] = q
        return out

    squad = {p.pid for p in season_plan.squad.players}
    bank = round(budget - season_plan.squad.cost, 1)
    free = 1
    acquired: dict[int, int] = {p: start for p in squad}
    plans: list[GWPlan] = []

    for g in gws:
        chip = chip_at.get(g)
        table = tables[g]
        view = blended(g)

        moves: list[Move] = []
        hits = 0

        if g > start:
            # A wildcard or free hit lifts the transfer limit entirely for one week.
            unlimited = chip in ("wildcard", "freehit")
            # Anything bought in the last few gameweeks is locked in, unless a chip has
            # lifted the transfer limit anyway.
            locked = set()
            if not unlimited:
                locked = {p for p, bought in acquired.items()
                          if p in squad and g - bought < hold_gws}
            cons = opt.Constraints(
                budget=round(bank + sum(prices.get(p, 0.0) for p in squad), 1),
                current_squad=set() if unlimited else set(squad),
                include=locked,
                free_transfers=15 if unlimited else free,
                max_hits=0 if unlimited else max_hits,
                min_expected_minutes=min_minutes,
            )
            new = opt.solve(view, lam=0.0, cons=cons)
            if new is not None:
                chosen = {p.pid for p in new.players}
                out_ids = squad - chosen
                in_ids = chosen - squad
                n = len(out_ids)
                if n:
                    for o, i in zip(sorted(out_ids), sorted(in_ids)):
                        moves.append(Move(names.get(o, str(o)), names.get(i, str(i)),
                                          prices.get(o, 0.0), prices.get(i, 0.0)))
                    for i in in_ids:
                        acquired[i] = g
                    bank = round(
                        bank + sum(prices.get(p, 0.0) for p in out_ids)
                        - sum(prices.get(p, 0.0) for p in in_ids), 1
                    )
                    if not unlimited:
                        hits = max(0, n - free)
                        free = min(MAX_FREE_TRANSFERS, max(1, free - n + 1))
                    # A free hit reverts next week, so the squad does not persist.
                    if chip != "freehit":
                        squad = chosen
                    else:
                        free = min(MAX_FREE_TRANSFERS, free + 1)
                else:
                    free = min(MAX_FREE_TRANSFERS, free + 1)
            else:
                free = min(MAX_FREE_TRANSFERS, free + 1)

        # --- Field the best legal XI for this gameweek ----------------------
        scored = {p: table[p].xp if p in table else 0.0 for p in squad}
        xi = _best_xi(list(squad), scored, {p: table[p].pos for p in squad if p in table})
        cap = max(xi, key=lambda p: scored.get(p, 0.0)) if xi else None
        vice = max((p for p in xi if p != cap), key=lambda p: scored.get(p, 0.0), default=cap)

        projected = sum(scored.get(p, 0.0) for p in xi)
        if cap is not None:
            # Triple captain pays a third copy rather than the usual second.
            projected += scored.get(cap, 0.0) * (2 if chip == "3xc" else 1)
        if chip == "bboost":
            projected += sum(scored.get(p, 0.0) for p in squad if p not in set(xi))

        counts = {DEF: 0, MID: 0, FWD: 0}
        for p in xi:
            pos = table[p].pos if p in table else MID
            if pos in counts:
                counts[pos] += 1

        plans.append(GWPlan(
            gw=g,
            month=next((m.name for m in months if m.start_event <= g <= m.stop_event), "?"),
            squad=sorted(squad),
            xi=xi,
            captain=cap,
            vice=vice,
            captain_name=names.get(cap, "—"),
            formation=f"{counts[DEF]}-{counts[MID]}-{counts[FWD]}",
            moves=moves,
            hits=hits,
            free_transfers=free,
            bank=bank,
            chip=chip,
            projected=projected,
        ))

    return plans


def _best_xi(members: list[int], scored: dict[int, float], pos_of: dict[int, int]) -> list[int]:
    by_pos: dict[int, list[int]] = {}
    for p in members:
        by_pos.setdefault(pos_of.get(p, MID), []).append(p)
    for k in by_pos:
        by_pos[k].sort(key=lambda p: -scored.get(p, 0.0))

    xi = by_pos.get(GK, [])[:1] + by_pos.get(DEF, [])[:3] + by_pos.get(MID, [])[:2] + by_pos.get(FWD, [])[:1]
    chosen = set(xi)
    rest = sorted((p for p in members if p not in chosen and pos_of.get(p) != GK),
                  key=lambda p: -scored.get(p, 0.0))
    caps = {DEF: 5, MID: 5, FWD: 3}
    counts = {DEF: 3, MID: 2, FWD: 1}
    for p in rest:
        if len(xi) >= 11:
            break
        pos = pos_of.get(p, MID)
        if counts.get(pos, 0) < caps.get(pos, 0):
            xi.append(p)
            counts[pos] += 1
    return xi


def summarise(plans: list[GWPlan]) -> dict:
    """Headline totals for the whole forward plan."""
    return {
        "gameweeks": len(plans),
        "projected": sum(p.net_projected for p in plans),
        "transfers": sum(len(p.moves) for p in plans),
        "hits": sum(p.hits for p in plans),
        "chips": [(p.gw, p.chip_label) for p in plans if p.chip],
    }
