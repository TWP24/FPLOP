"""Squad optimisation as an integer linear program.

Standard FPL optimisers maximise expected points. That is the wrong objective for a
monthly-prize league, so the objective here is

    E[points]  +  lam * Var[points]

`lam` is a risk-appetite knob. At lam = 0 this is a conventional EV optimiser. Above
zero it deliberately buys variance. Section "Why variance" in the README derives why
that is correct when only first place pays; `simulate.py` then scores the resulting
candidates on the objective you actually care about, P(winning the month).

Variance enters linearly (variance is additive across independent players), which
keeps the whole thing a genuine ILP rather than a quadratic program.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pulp

from .monthly import PlayerMonth

GK, DEF, MID, FWD = 1, 2, 3, 4
SQUAD_QUOTA = {GK: 2, DEF: 5, MID: 5, FWD: 3}
XI_MIN = {GK: 1, DEF: 3, MID: 2, FWD: 1}
XI_MAX = {GK: 1, DEF: 5, MID: 5, FWD: 3}
POS_NAME = {GK: "GKP", DEF: "DEF", MID: "MID", FWD: "FWD"}

# Bench players only score through automatic substitutions, so their expected points
# are heavily discounted rather than ignored — enough to break ties toward a bench
# that can actually cover a blank.
#
# This was a guess until it was swept. Across 24 backtest months, scored with real
# per-gameweek autosubs, the curve is a wide flat plateau:
#
#     0.00   224.5      0.12   233.4      0.30   230.0
#     0.06   231.2      0.16   234.0      0.50   229.1
#     0.09   233.0      0.20   233.4      1.00   216.9   (points/month)
#
# Everything from 0.09 to 0.20 is one number inside the noise; only the ends are
# real. Dropping to zero costs 8.9 points a month (2.5 se) because the optimiser
# then fills the bench with players who never appear — 21.7% of blanks go
# uncovered, against 7.6% at 0.12. Pushing it past 0.4 costs XI quality faster
# than it buys bench cover.
#
# Two more principled variants were tried and both lost. Weighting bench slots by
# their measured firing rates (0.65 / 0.31 / 0.11 per gameweek, keeper 0.07) scored
# 2 to 7 points a month *worse*: concentrating the budget on one good bench player
# leaves the other two unable to appear, and bench value turns out to be about
# positional coverage rather than slot order. Scaling the weight with each squad's
# own rotation risk also failed, because that risk barely varies — P(some starter
# blanks) ran 0.21 to 0.54 across the 24 months with sd 0.08, over a response
# surface that is flat anyway.
BENCH_WEIGHT = 0.12


@dataclass
class Squad:
    """A solved 15-player squad with its chosen XI and captain."""

    players: list[PlayerMonth]
    starters: list[int]
    captain: int
    vice: int
    lam: float
    cost: float
    transfers: int = 0
    hits: int = 0

    @property
    def xi(self) -> list[PlayerMonth]:
        order = {GK: 0, DEF: 1, MID: 2, FWD: 3}
        return sorted(
            [p for p in self.players if p.pid in self.starters],
            key=lambda p: (order[p.pos], -p.xp),
        )

    @property
    def bench(self) -> list[PlayerMonth]:
        return sorted(
            [p for p in self.players if p.pid not in self.starters],
            key=lambda p: (p.pos != GK, -p.xp),
        )

    @property
    def formation(self) -> str:
        c = {DEF: 0, MID: 0, FWD: 0}
        for p in self.xi:
            if p.pos in c:
                c[p.pos] += 1
        return f"{c[DEF]}-{c[MID]}-{c[FWD]}"

    @property
    def xp(self) -> float:
        """Expected points for the month, counting the captain twice, minus hits."""
        cap = next(p for p in self.players if p.pid == self.captain)
        return sum(p.xp for p in self.xi) + cap.xp - 4 * self.hits

    @property
    def var(self) -> float:
        """Variance treating players as independent — a floor, not the true figure.

        `simulate.py` computes the real number with same-team correlation included.
        """
        cap = next(p for p in self.players if p.pid == self.captain)
        return sum(p.var for p in self.xi) + 3 * cap.var

    @property
    def sd(self) -> float:
        return self.var**0.5

    def signature(self) -> tuple:
        return tuple(sorted(p.pid for p in self.players)) + (self.captain,)


def suggested_lam(n_rivals: int) -> float:
    """Risk appetite that maximised win probability at this league size.

    Measured, not assumed. Sweeping lam against simulated fields of varying size gives
    a clean crossover: below roughly forty rivals the expected-points squad wins most
    often, and a deliberate differential tilt only starts paying above that.

    The reason is that skill and difference are substitutes. In a twenty-person league
    a well-optimised squad already wins about one month in five against a baseline of
    one in twenty, so the edge is simply being better. Across a hundred rivals, someone
    is going to get lucky no matter how good you are, and the only way into that tail
    is owning players the rest of them do not.
    """
    if n_rivals <= 29:
        return 0.0
    if n_rivals <= 79:
        return 0.1
    return 0.15


@dataclass
class Constraints:
    budget: float = 100.0
    max_per_team: int = 3
    exclude: set[int] = field(default_factory=set)
    include: set[int] = field(default_factory=set)
    current_squad: set[int] = field(default_factory=set)
    free_transfers: int = 1
    max_hits: int = 0
    min_expected_minutes: float = 0.0


def solve(
    table: dict[int, PlayerMonth],
    lam: float = 0.0,
    cons: Constraints | None = None,
    seed_exclude: set[tuple] | None = None,
) -> Squad | None:
    """Solve for one squad at risk appetite `lam`. Returns None if infeasible."""
    cons = cons or Constraints()
    pool = [
        p
        for p in table.values()
        if p.pid not in cons.exclude
        and (p.exp_minutes >= cons.min_expected_minutes or p.pid in cons.include)
    ]
    if not pool:
        return None

    prob = pulp.LpProblem("fpl_month", pulp.LpMaximize)
    ids = [p.pid for p in pool]
    P = {p.pid: p for p in pool}

    squad = pulp.LpVariable.dicts("squad", ids, cat="Binary")
    start = pulp.LpVariable.dicts("start", ids, cat="Binary")
    cap = pulp.LpVariable.dicts("cap", ids, cat="Binary")

    # --- Objective ---------------------------------------------------------
    obj = []
    for i in ids:
        p = P[i]
        # Risk is priced on *differential* variance, not raw variance. Buying raw
        # variance by degrading the squad turned out to be a losing trade — it costs
        # about two points of mean per point of extra spread, against a break-even of
        # roughly half a point. Differential variance is the cheap kind: it comes from
        # who the field does *not* own, so it barely costs expected points at all.
        dv = p.differential_var
        obj.append(start[i] * (p.xp + lam * dv))
        obj.append(cap[i] * (p.xp + 3 * lam * dv))
        obj.append((squad[i] - start[i]) * (BENCH_WEIGHT * p.xp))

    hits = None
    if cons.current_squad:
        # transfers = players leaving the current squad; hits = transfers beyond free.
        kept = pulp.lpSum(squad[i] for i in ids if i in cons.current_squad)
        n_transfers = 15 - kept
        hits = pulp.LpVariable("hits", lowBound=0, upBound=cons.max_hits, cat="Integer")
        prob += hits >= n_transfers - cons.free_transfers
        prob += n_transfers <= cons.free_transfers + cons.max_hits
        obj.append(-4 * hits)

    prob += pulp.lpSum(obj)

    # --- Squad structure ---------------------------------------------------
    prob += pulp.lpSum(squad[i] for i in ids) == 15
    for pos, n in SQUAD_QUOTA.items():
        prob += pulp.lpSum(squad[i] for i in ids if P[i].pos == pos) == n

    prob += pulp.lpSum(squad[i] * P[i].price for i in ids) <= cons.budget

    teams = {P[i].team for i in ids}
    for t in teams:
        prob += pulp.lpSum(squad[i] for i in ids if P[i].team == t) <= cons.max_per_team

    for i in cons.include:
        if i in squad:
            prob += squad[i] == 1

    # --- Starting XI -------------------------------------------------------
    prob += pulp.lpSum(start[i] for i in ids) == 11
    for i in ids:
        prob += start[i] <= squad[i]
    for pos in (GK, DEF, MID, FWD):
        n = pulp.lpSum(start[i] for i in ids if P[i].pos == pos)
        prob += n >= XI_MIN[pos]
        prob += n <= XI_MAX[pos]

    # --- Captain -----------------------------------------------------------
    prob += pulp.lpSum(cap[i] for i in ids) == 1
    for i in ids:
        prob += cap[i] <= start[i]

    # Forbid squads we have already produced, so the lam sweep returns distinct teams.
    for sig in seed_exclude or set():
        members = [i for i in sig[:-1] if i in squad]
        if len(members) == 15:
            prob += pulp.lpSum(squad[i] for i in members) <= 14

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        return None

    chosen = [P[i] for i in ids if squad[i].value() > 0.5]
    starters = [i for i in ids if start[i].value() > 0.5]
    captain = next(i for i in ids if cap[i].value() > 0.5)
    vice = max(
        (i for i in starters if i != captain), key=lambda i: P[i].xp, default=captain
    )

    n_hits = int(hits.value()) if hits is not None else 0
    n_transfers = 0
    if cons.current_squad:
        n_transfers = 15 - len({p.pid for p in chosen} & cons.current_squad)

    return Squad(
        players=chosen,
        starters=starters,
        captain=captain,
        vice=vice,
        lam=lam,
        cost=sum(p.price for p in chosen),
        transfers=n_transfers,
        hits=n_hits,
    )


def frontier(
    table: dict[int, PlayerMonth],
    lams: list[float],
    cons: Constraints | None = None,
) -> list[Squad]:
    """Solve across a range of risk appetites, returning the distinct squads found."""
    out: list[Squad] = []
    seen: set[tuple] = set()
    for lam in lams:
        s = solve(table, lam=lam, cons=cons)
        if s is None:
            continue
        sig = s.signature()
        if sig in seen:
            continue
        seen.add(sig)
        out.append(s)
    return out
