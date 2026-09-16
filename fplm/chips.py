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

import heapq
from dataclasses import dataclass, field

from .monthly import Month, PlayerMonth, fixture_counts
from .optimise import Constraints, Squad, solve

GK, DEF, MID, FWD = 1, 2, 3, 4

CHIP_LABEL = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
}


# Blank and double gameweeks do not exist in the fixture list yet — all 380 fixtures
# currently sit one-per-team-per-gameweek — but they are close to certain to appear, and
# the chip planner is otherwise allocating against a fiction.
#
# The mechanism is structural rather than random. Premier League fixtures get postponed
# when they clash with FA Cup rounds, and the postponed games return later as doubles.
# The historical pattern is consistent: one or two blanks in late February and March
# around the fifth round and quarter-finals, a larger blank on FA Cup semi-final weekend
# (usually GW32-34), and the rescheduled games landing as doubles in the run-in
# (GW34-37).
#
# These are PRIORS, not measurements. They are here so the planner holds its second set
# of chips back for the window where they are worth most, instead of spending a Bench
# Boost in February on a normal gameweek. Every one is re-derived from the real fixture
# list the moment the postponements are actually published, at which point these
# multipliers stop mattering.
# Narrowed using Ben Crellin's published 2026/27 fixture calendar (a public Google
# Sheet, produced with Fantasy Football Hub). Its date-to-gameweek mapping was checked
# against the live fixture list and matches exactly: Apr 10 = GW31, Apr 17 = GW32,
# Apr 24 = GW33, May 1 = GW34.
#
# What that calendar shows for this season in particular:
#   * FA Cup 3rd, 4th and 5th rounds fall on Jan 9, Feb 13 and Mar 6 — all weekends
#     with NO gameweek scheduled. FPL has deliberately routed around them, so the usual
#     late-February and March blanks do not appear this season.
#   * The semi-finals (Apr 20/27) collide with GW33, which is the one real blank.
#   * Crellin marks GW32 "Fairly Likely DGW".
#
# One caution learned the hard way: that sheet also carries a note reading "GW18 Blank:
# MCI vs BRE", which is stale — City and Brentford meet in GW14 and GW34 this season and
# GW18 has its full ten fixtures. Published calendars carry over between seasons, so
# check any specific claim against the live fixture list before encoding it.
BLANK_WINDOW = range(33, 34)        # GW33 — FA Cup semi-final weekend
DOUBLE_WINDOW = list(range(34, 38)) + [32]  # GW32 flagged likely; rescheduled games return GW34-37

# A bench boost in a double gameweek pays four bench players across two fixtures rather
# than one, so it roughly doubles. A triple captain likewise. A free hit is worth most
# in a blank, when your own squad cannot field eleven players and a fresh one can.
# Discounted for the chance the window lands elsewhere.
DGW_UPLIFT = {"bboost": 1.75, "3xc": 1.70, "wildcard": 1.15}
BGW_UPLIFT = {"freehit": 2.60, "wildcard": 1.20}


def window_uplift(chip: str, gw: int, real_counts: dict[int, int] | None = None) -> float:
    """Prior multiplier on a chip's value for landing in a likely blank or double.

    Self-cancelling by design. `real_counts` maps gameweek to the number of fixtures
    actually scheduled that week; once a genuine blank or double appears there, the
    prior for that gameweek switches off. Without this the two would compound: a real
    double already raises the chip's computed value because the bench plays twice, and
    multiplying that by the prior as well would count the same fixture twice over.
    """
    if real_counts is not None:
        n = real_counts.get(gw)
        # 20 fixtures in a gameweek means every club plays once. Anything else means
        # the schedule already knows about the blank or double, so the prior retires.
        if n is not None and n != 20:
            return 1.0

    factor = 1.0
    if gw in DOUBLE_WINDOW:
        factor = max(factor, DGW_UPLIFT.get(chip, 1.0))
    if gw in BLANK_WINDOW:
        factor = max(factor, BGW_UPLIFT.get(chip, 1.0))
    return factor


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
    # What the chip is worth in *every* week of the month, not only its best one.
    # The allocator needs the alternatives: FPL allows one chip per gameweek, so when
    # two chips want the same Saturday the loser has to move, not go unplayed.
    by_gw: dict[int, float] = field(default_factory=dict)
    note_by_gw: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A value built without the per-week breakdown still has one option: its own.
        if not self.by_gw:
            self.by_gw = {self.gw: self.value}

    def at(self, gw: int, value: float) -> "ChipValue":
        """The same chip, priced in a different week of the same month."""
        return ChipValue(self.chip, self.month, gw, value,
                         self.note_by_gw.get(gw, self.note),
                         dict(self.by_gw), dict(self.note_by_gw))


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
    Every week of the month is priced, not just the best one, because the best one is
    often also the week the bench boost wants and only one of them can have it.
    """
    by_gw: dict[int, float] = {}
    notes: dict[int, str] = {}
    for gw in month.events:
        gw_xp = per_gw.get(gw, {})
        cands = [(gw_xp.get(p.pid, 0.0), p.name) for p in squad.xi]
        if not cands:
            continue
        v, nm = max(cands)
        by_gw[gw] = v
        notes[gw] = f"on {nm}"

    best_gw, best_val = month.start_event, 0.0
    for gw, v in by_gw.items():
        if v > best_val:
            best_gw, best_val = gw, v
    return ChipValue("3xc", month.name, best_gw, best_val,
                     notes.get(best_gw, "") if best_val else "", by_gw, notes)


def bench_boost_value(squad: Squad, month: Month,
                      per_gw: dict[int, dict[int, float]]) -> ChipValue:
    """Bench boost pays your four bench players for one gameweek."""
    by_gw = {
        gw: sum(per_gw.get(gw, {}).get(p.pid, 0.0) for p in squad.bench)
        for gw in month.events
    }
    best_gw, best_val = month.start_event, 0.0
    for gw, v in by_gw.items():
        if v > best_val:
            best_gw, best_val = gw, v
    return ChipValue("bboost", month.name, best_gw, best_val,
                     f"{len(squad.bench)}-man bench", by_gw)


def free_hit_value(squad: Squad, table: dict[int, PlayerMonth], month: Month,
                   per_gw: dict[int, dict[int, float]], cons: Constraints) -> ChipValue:
    """Free hit buys one gameweek's unlimited transfers, reverting afterwards.

    Worth the difference between the best possible eleven for that single gameweek and
    what your actual squad would have scored. Most valuable in a blank gameweek, when
    your own squad cannot field a full team.
    """
    by_gw: dict[int, float] = {}
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
        by_gw[gw] = max(gain, 0.0)
        if gain > best_val:
            best_gw, best_val = gw, gain
    return ChipValue("freehit", month.name, best_gw, max(best_val, 0.0), "", by_gw)


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
    gain = max((ideal.xp - current) * (1.0 - reachable), 0.0)

    # A wildcard only improves the weeks that come after it, so played later in the
    # month it is worth pro-rata less. Pricing that decay gives the allocator somewhere
    # to put the chip when the first week of the month is already spoken for, instead
    # of leaving it unplayed.
    by_gw = {gw: gain * (month.stop_event - gw + 1) / month.n_events
             for gw in month.events}
    return ChipValue("wildcard", month.name, month.start_event, gain,
                     f"{month.n_events} GWs", by_gw)


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
    max_per_month: int | None = None,
    real_counts: dict[int, int] | None = None,
    first_gw: int | None = None,
) -> list[ChipValue]:
    """Assign each available chip to the month, and the week, where it is worth most.

    Greedy on value, respecting each chip's gameweek window, FPL's one-chip-a-week
    rule and an optional cap on how many chips one month can absorb. Greedy is optimal
    enough here: chip values are close to independent across months, and the binding
    constraints are the windows rather than interactions between chips.

    `max_per_month` is a monthly-prize device: spreading chips over more months buys
    more chances at a monthly cheque even where the points are worth less. Left unset
    the chips simply go where they score most, which is what a season objective wants,
    and FPL's one-chip-a-week rule is the only spreading force left.

    When two chips want the same Saturday the loser moves to its next-best week. It
    used to be dropped instead, and the chip it was dropped for was almost always the
    Triple Captain — the cheapest of the four, so it lost every tie — which is how a
    season plan ended up showing one Triple Captain when the game gives you two.

    `first_gw` is the next gameweek you can still play a chip in. Without it the
    valuation happily picks the best week of a month that is already half gone, and a
    month keeps its best week long after that week has been played — a live plan
    advised a Triple Captain in GW3 with GW5 the next deadline, which is not advice.
    A chip you have not spent has to find the best week *left*.
    """
    by_key = {(v.chip, v.month): v for v in values}
    month_of = {m.name: m for m in months}

    chosen: list[ChipValue] = []
    used_per_month: dict[str, int] = {}

    # One entry per physical chip, so both halves of the season are allocated.
    candidates = []
    for w in chip_windows:
        for m in months:
            # A chip can go in any month it *overlaps*. Requiring the month to sit
            # wholly inside the window is what the rule looks like, but it is not the
            # rule: the two halves split at GW19/20 and FPL's month boundaries do not
            # respect that, so this season January runs GW19-23 and used to be barred
            # from every chip in the game. Only the week the chip is played in has to
            # be inside the window, which `price` enforces.
            if m.stop_event < w.start_event or m.start_event > w.stop_event:
                continue
            v = by_key.get((w.name, m.name))
            if v:
                candidates.append((w, v))

    def price(v: ChipValue, w: ChipWindow, taken: set[int]) -> tuple[float, int] | None:
        """Best value and week for this chip in its month, avoiding the taken weeks.

        The blank/double prior is priced in here, per gameweek rather than once on the
        month's best week, so that the second set of chips is held back for the window
        where it is worth most and a chip that has to move is re-judged on where it
        actually lands.
        """
        opts = [(val * window_uplift(v.chip, gw, real_counts), -gw)
                for gw, val in v.by_gw.items()
                if gw not in taken and w.start_event <= gw <= w.stop_event
                and (first_gw is None or gw >= first_gw)]
        if not opts:
            return None
        val, neg_gw = max(opts)    # ties go to the earlier week
        return val, -neg_gw

    spent: set[int] = set()
    used_gws: set[int] = set()

    # Lazy greedy. Taking a chip removes a week from every other chip's options, so a
    # candidate's price can only fall as the queue drains: re-price the head before
    # trusting it, and push it back if it has slipped below the runner-up. Each
    # push-back strictly lowers that candidate's price and a month has finitely many
    # weeks, so this terminates.
    heap: list[tuple[float, int]] = []
    for i, (w, v) in enumerate(candidates):
        p = price(v, w, set())
        if p is not None:
            heapq.heappush(heap, (-p[0], i))

    while heap:
        _neg, i = heapq.heappop(heap)
        w, v = candidates[i]
        if id(w) in spent:
            continue
        if max_per_month is not None and used_per_month.get(v.month, 0) >= max_per_month:
            continue
        # Never play the same chip type twice in one month.
        if any(c.month == v.month and c.chip == v.chip for c in chosen):
            continue
        # FPL allows exactly one chip per gameweek. Two chips can share a month, but
        # not a week — without this the planner happily stacked a bench boost and a
        # triple captain on the same Saturday and counted both.
        p = price(v, w, used_gws)
        if p is None:
            continue
        val, gw = p
        if heap and val < -heap[0][0] - 1e-9:
            heapq.heappush(heap, (-val, i))
            continue

        chosen.append(v.at(gw, val))
        spent.add(id(w))
        used_gws.add(gw)
        used_per_month[v.month] = used_per_month.get(v.month, 0) + 1

    return sorted(chosen, key=lambda v: (month_of[v.month].start_event, -v.value))
