"""Plan several gameweeks at once instead of one at a time.

`forecast.build` walks the season a gameweek at a time and approximates foresight by
blending the next few gameweeks' expected points into today's ratings. That stops the
squad churning after one good fixture, but it is a rating tweak rather than a plan:
nothing in it can represent "hold this transfer, because in three weeks two moves are
worth more than one is now". A greedy solver cannot bank anything, because banking
only pays in a future it does not model.

This solves the whole horizon jointly. Squad membership, transfers, hits and the free
transfer balance are decision variables in every gameweek at once, so the model can
spend a transfer early, hold one, or take a hit, on the merits of the whole run.

The free-transfer rule linearises without any extra binaries. Writing `t` for
transfers made, `u` for free ones used and `h` for hits, `t = u + h` with `u <= f` is
an identity rather than an approximation, and since hits cost four points the solver
will always prefer a free transfer where one exists. The balance then rolls forward as
`f_next <= min(5, f - u + 1)`; more free transfers are never worse, so the upper bound
binds on its own.

Prices are held flat, as they are in `forecast`, and chips are left to `chips.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pulp

from .optimise import BENCH_WEIGHT, Constraints
from .monthly import PlayerMonth

GK, DEF, MID, FWD = 1, 2, 3, 4
SQUAD_BY_POS = {GK: 2, DEF: 5, MID: 5, FWD: 3}
XI_MIN = {GK: 1, DEF: 3, MID: 2, FWD: 1}
XI_MAX = {GK: 1, DEF: 5, MID: 5, FWD: 3}
MAX_FREE = 5
HIT_COST = 4

# Later gameweeks are discounted: the plan for gameweek eight is a sketch, and letting
# it trade against a decision being taken this week overstates what it knows.
DECAY = 0.9

# Pool size per position. A joint model over eight gameweeks has a binary for every
# player in every week, so the pool has to be cut to something a solver can chew.
POOL_PER_POS = {GK: 12, DEF: 45, MID: 55, FWD: 30}


@dataclass
class HorizonPlan:
    gameweeks: list[int]
    squads: dict[int, set[int]] = field(default_factory=dict)
    starters: dict[int, set[int]] = field(default_factory=dict)
    captains: dict[int, int] = field(default_factory=dict)
    transfers: dict[int, tuple[set[int], set[int]]] = field(default_factory=dict)
    hits: dict[int, int] = field(default_factory=dict)
    free: dict[int, int] = field(default_factory=dict)
    objective: float = 0.0


def _prune(tables: dict[int, dict[int, PlayerMonth]], held: set[int]) -> list[int]:
    """Players worth considering across the horizon, plus everyone already owned."""
    total: dict[int, float] = {}
    pos: dict[int, int] = {}
    for tbl in tables.values():
        for pid, p in tbl.items():
            total[pid] = total.get(pid, 0.0) + p.xp
            pos[pid] = p.pos
    keep = set(held)
    for want_pos, n in POOL_PER_POS.items():
        ranked = sorted((pid for pid in total if pos.get(pid) == want_pos),
                        key=lambda pid: -total[pid])
        keep.update(ranked[:n])
    return [pid for pid in keep if pid in total]


def solve(
    tables: dict[int, dict[int, PlayerMonth]],
    held: set[int],
    bank: float,
    cons: Constraints,
    free_transfers: int = 1,
    max_hits_per_gw: int = 0,
    decay: float = DECAY,
    ft_terminal_value: float = 0.0,
    time_limit: int = 120,
) -> HorizonPlan | None:
    """Optimise squad and transfers jointly across every gameweek in `tables`."""
    gws = sorted(tables)
    if not gws:
        return None
    ids = _prune(tables, held)
    if len(ids) < 30:
        return None

    any_tbl = tables[gws[0]]
    ref = {pid: next((tables[g][pid] for g in gws if pid in tables[g]), None)
           for pid in ids}
    ids = [pid for pid in ids if ref[pid] is not None]
    price = {pid: ref[pid].price for pid in ids}
    pos = {pid: ref[pid].pos for pid in ids}
    team = {pid: ref[pid].team for pid in ids}
    xp = {(pid, g): (tables[g][pid].xp if pid in tables[g] else 0.0)
          for pid in ids for g in gws}

    prob = pulp.LpProblem("fpl_horizon", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("x", (ids, gws), cat="Binary")       # in squad
    s = pulp.LpVariable.dicts("s", (ids, gws), cat="Binary")       # starting
    c = pulp.LpVariable.dicts("c", (ids, gws), cat="Binary")       # captain
    buy = pulp.LpVariable.dicts("buy", (ids, gws), cat="Binary")
    sell = pulp.LpVariable.dicts("sell", (ids, gws), cat="Binary")
    f = pulp.LpVariable.dicts("f", gws, lowBound=1, upBound=MAX_FREE, cat="Integer")
    u = pulp.LpVariable.dicts("u", gws, lowBound=0, upBound=MAX_FREE, cat="Integer")
    h = pulp.LpVariable.dicts("h", gws, lowBound=0, upBound=max_hits_per_gw,
                              cat="Integer")

    obj = []
    for gi, g in enumerate(gws):
        w = decay ** gi
        for pid in ids:
            obj.append(w * s[pid][g] * xp[(pid, g)])
            obj.append(w * c[pid][g] * xp[(pid, g)])
            obj.append(w * (x[pid][g] - s[pid][g]) * (BENCH_WEIGHT * xp[(pid, g)]))
        obj.append(-w * HIT_COST * h[g])
    if ft_terminal_value:
        obj.append(ft_terminal_value * f[gws[-1]])
    prob += pulp.lpSum(obj)

    for g in gws:
        prob += pulp.lpSum(x[pid][g] for pid in ids) == 15
        prob += pulp.lpSum(s[pid][g] for pid in ids) == 11
        prob += pulp.lpSum(c[pid][g] for pid in ids) == 1
        prob += pulp.lpSum(price[pid] * x[pid][g] for pid in ids) <= cons.budget
        for want_pos, n in SQUAD_BY_POS.items():
            prob += pulp.lpSum(x[pid][g] for pid in ids if pos[pid] == want_pos) == n
        for want_pos in (GK, DEF, MID, FWD):
            inpos = [pid for pid in ids if pos[pid] == want_pos]
            prob += pulp.lpSum(s[pid][g] for pid in inpos) >= XI_MIN[want_pos]
            prob += pulp.lpSum(s[pid][g] for pid in inpos) <= XI_MAX[want_pos]
        for t in set(team.values()):
            prob += pulp.lpSum(x[pid][g] for pid in ids if team[pid] == t) <= 3
        for pid in ids:
            prob += s[pid][g] <= x[pid][g]
            prob += c[pid][g] <= s[pid][g]

    # --- squad continuity and the transfer ledger --------------------------
    for gi, g in enumerate(gws):
        for pid in ids:
            prev = (x[pid][gws[gi - 1]] if gi else (1 if pid in held else 0))
            prob += x[pid][g] == prev + buy[pid][g] - sell[pid][g]
            prob += buy[pid][g] + sell[pid][g] <= 1
        moves = pulp.lpSum(buy[pid][g] for pid in ids)
        prob += moves == u[g] + h[g]
        prob += u[g] <= f[g]
        if gi == 0:
            prob += f[g] == free_transfers
        else:
            prob += f[g] <= f[gws[gi - 1]] - u[gws[gi - 1]] + 1
            prob += f[g] <= MAX_FREE

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    if pulp.LpStatus[status] not in ("Optimal", "Not Solved") or x[ids[0]][gws[0]].value() is None:
        return None

    plan = HorizonPlan(gameweeks=gws, objective=float(pulp.value(prob.objective) or 0.0))
    for g in gws:
        plan.squads[g] = {pid for pid in ids if x[pid][g].value() > 0.5}
        plan.starters[g] = {pid for pid in ids if s[pid][g].value() > 0.5}
        plan.captains[g] = next((pid for pid in ids if c[pid][g].value() > 0.5), 0)
        plan.transfers[g] = ({pid for pid in ids if sell[pid][g].value() > 0.5},
                             {pid for pid in ids if buy[pid][g].value() > 0.5})
        plan.hits[g] = int(round(h[g].value() or 0))
        plan.free[g] = int(round(f[g].value() or 1))
    return plan
