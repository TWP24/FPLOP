"""Chip valuation and season-long allocation.

Chips are the largest lever in a monthly-prize league and were the biggest gap in the
model. The arithmetic that makes them decisive: across three backtested seasons the
gap between a well-played squad (~198 pts/month) and the month's winner (~216-231) was
roughly twenty points. A well-timed chip is worth about that much on its own.

You get eight chips and there are ten months, so you cannot contest every month. You
*can* be chip-boosted in five or six of them. This module prices each chip in each
month and then solves the allocation, which turns "win every month" into the question
that can actually be answered: which months do I contest, and with what.

Chip rules taken live from the API (`bootstrap-static["chips"]`): two sets, one usable
GW1-19 and one GW20-38, each set containing a wildcard, a free hit, a bench boost and
a triple captain.
"""
from __future__ import annotations

from dataclasses import dataclass

from .monthly import Month, PlayerMonth, fixture_counts
from .optimise import Constraints, Squad, solve

GK, DEF, MID, FWD = 1, 2, 3, 4

CHIP_LABEL = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
}


@dataclass
class ChipWindow:
    name: str
    start_event: int
    stop_event: int

    @property
    def label(self) -> str:
        return CHIP_LABEL.get(self.name, self.name)


@dataclass
class ChipValue:
    """What one chip is worth in one month, in expected points."""

    chip: str
    month: str
    gw: int          # best single gameweek to play it, where that matters
    value: float
    note: str = ""


def windows(boot: dict) -> list[ChipWindow]:
    """Every chip the game currently offers, with its usable gameweek range."""
    return [
        ChipWindow(c["name"], c["start_event"], c["stop_event"])
        for c in boot.get("chips", [])
    ]


# --------------------------------------------------------------------- #
# Valuing individual chips


def triple_captain_value(squad: Squad, table: dict[int, PlayerMonth], month: Month,
                         per_gw: dict[int, dict[int, float]]) -> ChipValue:
    """Triple captain pays one extra copy of your captain's score in a single week.

    Best played in the single gameweek where your best captain has the highest
    expected return — a double gameweek if one exists, otherwise the kindest fixture.
    """
    best_gw, best_val, best_name = month.start_event, 0.0, ""
    for gw in month.events:
        gw_xp = per_gw.get(gw, {})
        cands = [(gw_xp.get(p.pid, 0.0), p.name) for p in squad.xi]
        if not cands:
            continue
        v, nm = max(cands)
        if v > best_val:
            best_gw, best_val, best_name = gw, v, nm
    return ChipValue("3xc", month.name, best_gw, best_val,
                     f"on {best_name}" if best_name else "")


def bench_boost_value(squad: Squad, month: Month,
                      per_gw: dict[int, dict[int, float]]) -> ChipValue:
    """Bench boost pays your four bench players for one gameweek."""
    best_gw, best_val = month.start_event, 0.0
    for gw in month.events:
        gw_xp = per_gw.get(gw, {})
        v = sum(gw_xp.get(p.pid, 0.0) for p in squad.bench)
        if v > best_val:
            best_gw, best_val = gw, v
    return ChipValue("bboost", month.name, best_gw, best_val,
                     f"{len(squad.bench)}-man bench")


def free_hit_value(squad: Squad, table: dict[int, PlayerMonth], month: Month,
                   per_gw: dict[int, dict[int, float]], cons: Constraints) -> ChipValue:
    """Free hit buys one gameweek's unlimited transfers, reverting afterwards.

    Worth the difference between the best possible eleven for that single gameweek and
    what your actual squad would have scored. Most valuable in a blank gameweek, when
    your own squad cannot field a full team.
    """
    best_gw, best_val = month.start_event, 0.0
    for gw in month.events:
        gw_xp = per_gw.get(gw, {})
        single = {
            pid: _as_single_gw(p, gw_xp.get(pid, 0.0)) for pid, p in table.items()
        }
        ideal = solve(single, lam=0.0, cons=Constraints(
            budget=cons.budget, max_per_team=cons.max_per_team,
            min_expected_minutes=cons.min_expected_minutes))
        if ideal is None:
            continue
        mine = _best_xi_score(squad, gw_xp)
        gain = sum(gw_xp.get(p.pid, 0.0) for p in ideal.xi) - mine
        if gain > best_val:
            best_gw, best_val = gw, gain
    return ChipValue("freehit", month.name, best_gw, max(best_val, 0.0))


def wildcard_value(squad: Squad, table: dict[int, PlayerMonth], month: Month,
                   cons: Constraints) -> ChipValue:
    """Wildcard rebuilds the squad permanently, so its value is a whole month of gain.

    Compared against what the current squad would score over the same month using only
    normal transfers, which is why it is worth most before a long month.
    """
    ideal = solve(table, lam=0.0, cons=Constraints(
        budget=cons.budget, max_per_team=cons.max_per_team,
        min_expected_minutes=cons.min_expected_minutes))
    if ideal is None:
        return ChipValue("wildcard", month.name, month.start_event, 0.0)

    # Both sides must be measured in the *same* month's table. Scoring the ideal
    # December squad against a squad valued over August's two gameweeks compares six
    # gameweeks with two and inflates the wildcard enormously.
    mine = [table[p.pid].xp for p in squad.xi if p.pid in table]
    current = sum(mine) + max(mine, default=0.0)

    # A wildcard is only worth what normal transfers could not have achieved anyway.
    # With one free transfer a week you can reach much of the ideal squad unaided, so
    # credit the chip with the shortfall rather than the full gap.
    reachable = min(month.n_events, 5) / 15.0
    gain = (ideal.xp - current) * (1.0 - reachable)
    return ChipValue("wildcard", month.name, month.start_event, max(gain, 0.0),
                     f"{month.n_events} GWs")


def _as_single_gw(p: PlayerMonth, xp: float) -> PlayerMonth:
    import copy as _copy

    q = _copy.copy(p)
    q.xp = xp
    q.var = p.var / max(p.n_fixtures, 1)
    q.n_fixtures = 1
    return q


def _best_xi_score(squad: Squad, gw_xp: dict[int, float]) -> float:
    """What the current squad's best legal eleven scores in one gameweek."""
    members = [(gw_xp.get(p.pid, 0.0), p.pos, p.pid) for p in squad.players]
    by_pos: dict[int, list[float]] = {}
    for v, pos, _ in members:
        by_pos.setdefault(pos, []).append(v)
    for k in by_pos:
        by_pos[k].sort(reverse=True)
    xi = by_pos.get(GK, [0])[:1] + by_pos.get(DEF, [])[:3] + by_pos.get(MID, [])[:2] + by_pos.get(FWD, [])[:1]
    rest = sorted(
        by_pos.get(DEF, [])[3:5] + by_pos.get(MID, [])[2:5] + by_pos.get(FWD, [])[1:3],
        reverse=True,
    )
    return sum(xi) + sum(rest[: 11 - len(xi)])


# --------------------------------------------------------------------- #
# Allocation


def allocate(
    values: list[ChipValue],
    chip_windows: list[ChipWindow],
    months: list[Month],
    max_per_month: int = 2,
) -> list[ChipValue]:
    """Assign each available chip to the month where it is worth most.

    Greedy on value, respecting each chip's gameweek window and a cap on how many
    chips one month can absorb. Greedy is optimal enough here: chip values are close
    to independent across months, and the binding constraints are the windows rather
    than interactions between chips.
    """
    by_key = {(v.chip, v.month): v for v in values}
    month_of = {m.name: m for m in months}

    chosen: list[ChipValue] = []
    used_per_month: dict[str, int] = {}

    # One entry per physical chip, so both halves of the season are allocated.
    candidates = []
    for w in chip_windows:
        for m in months:
            # A chip can only go in a month it can legally cover.
            if m.start_event < w.start_event or m.stop_event > w.stop_event:
                continue
            v = by_key.get((w.name, m.name))
            if v:
                candidates.append((w, v))

    candidates.sort(key=lambda wv: -wv[1].value)
    spent: set[int] = set()
    used_gws: set[int] = set()
    for i, (w, v) in enumerate(candidates):
        wid = id(w)
        if wid in spent:
            continue
        if used_per_month.get(v.month, 0) >= max_per_month:
            continue
        # FPL allows exactly one chip per gameweek. Two chips can share a month, but
        # not a week — without this the planner happily stacked a bench boost and a
        # triple captain on the same Saturday and counted both.
        if v.gw in used_gws:
            continue
        # Never play the same chip type twice in one month.
        if any(c.month == v.month and c.chip == v.chip for c in chosen):
            continue
        chosen.append(v)
        spent.add(wid)
        used_gws.add(v.gw)
        used_per_month[v.month] = used_per_month.get(v.month, 0) + 1

    return sorted(chosen, key=lambda v: (month_of[v.month].start_event, -v.value))
