"""Monthly aggregation.

FPL ships the month boundaries itself in `bootstrap-static["phases"]`, and those are
the exact buckets a monthly-prize league scores on. They are wildly uneven — the
2026/27 season runs August over 2 gameweeks and December over 6 — which is the single
biggest strategic fact in a monthly league and the reason this tool exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ratings as rt
from . import xp as xpmod


@dataclass
class Month:
    phase_id: int
    name: str
    start_event: int
    stop_event: int

    @property
    def events(self) -> list[int]:
        return list(range(self.start_event, self.stop_event + 1))

    @property
    def n_events(self) -> int:
        return self.stop_event - self.start_event + 1

    def __str__(self) -> str:
        return f"{self.name} (GW{self.start_event}-{self.stop_event}, {self.n_events} GWs)"


@dataclass
class PlayerMonth:
    """One player's outlook across a whole month."""

    pid: int
    name: str
    team: int
    team_name: str
    pos: int
    price: float
    selected_by: float
    xp: float
    var: float
    n_fixtures: int
    exp_minutes: float
    fixtures: list[xpmod.FixtureXP] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def sd(self) -> float:
        return self.var**0.5

    @property
    def differential_var(self) -> float:
        """Variance that actually moves you up the table.

        Only the part of a player's variance that the field is *not* also exposed to
        can win a month. If a rival owns the same player, his haul lifts both scores
        and changes nothing between you. With the field owning him with probability o,
        your differential exposure is (1 - o), and the variance of your lead scales
        with the square of that.

        The practical consequence: a 60%-owned premium contributes only 16% of his raw
        variance to your chances, while a 3%-owned punt contributes 94% of his.
        """
        o = min(max(self.selected_by / 100.0, 0.0), 1.0)
        return self.var * (1.0 - o) ** 2

    @property
    def xp_per_million(self) -> float:
        return self.xp / self.price if self.price else 0.0

    @property
    def fdr_string(self) -> str:
        parts = []
        for f in sorted(self.fixtures, key=lambda x: x.event):
            parts.append(f"{f.fdr}{'H' if f.home else 'A'}")
        return "/".join(parts) if parts else "-"


def get_months(boot: dict) -> list[Month]:
    """Every scoring month, skipping the 'Overall' phase."""
    return [
        Month(p["id"], p["name"], p["start_event"], p["stop_event"])
        for p in boot["phases"]
        if p["name"].lower() != "overall"
    ]


def resolve_month(boot: dict, name: str | None) -> Month:
    """Look up a month by name, or fall back to the one containing the next gameweek."""
    months = get_months(boot)
    if name:
        want = name.strip().lower()
        for m in months:
            if m.name.lower() == want or m.name.lower().startswith(want):
                return m
        raise SystemExit(f"Unknown month {name!r}. Options: {', '.join(m.name for m in months)}")

    next_ev = next((e["id"] for e in boot["events"] if e.get("is_next")), None)
    if next_ev is None:
        next_ev = next((e["id"] for e in boot["events"] if not e["finished"]), 1)
    for m in months:
        if m.start_event <= next_ev <= m.stop_event:
            return m
    return months[0]


def build_table(
    boot: dict,
    fixtures: list[dict],
    rates: dict[int, xpmod.PlayerRates],
    team_ratings: dict[int, rt.TeamRating],
    month: Month,
) -> dict[int, PlayerMonth]:
    """Expected points and variance for every player across the whole month."""
    avg_for, avg_against = xpmod.team_baseline_lambdas(team_ratings, fixtures)
    team_names = {t["id"]: t["short_name"] for t in boot["teams"]}

    events = set(month.events)
    by_team: dict[int, list[dict]] = {}
    for f in fixtures:
        if f["event"] in events:
            by_team.setdefault(f["team_h"], []).append(f)
            by_team.setdefault(f["team_a"], []).append(f)

    table: dict[int, PlayerMonth] = {}
    for pid, r in rates.items():
        fxs = [
            xpmod.fixture_xp(r, f, team_ratings, avg_for, avg_against)
            for f in by_team.get(r.team, [])
        ]
        table[pid] = PlayerMonth(
            pid=pid,
            name=r.name,
            team=r.team,
            team_name=team_names[r.team],
            pos=r.pos,
            price=r.price,
            selected_by=r.selected_by,
            xp=sum(f.xp for f in fxs),
            var=sum(f.var for f in fxs),
            n_fixtures=len(fxs),
            exp_minutes=r.exp_minutes,
            fixtures=fxs,
            flags=r.flags,
        )
    return table


def fixture_counts(fixtures: list[dict], month: Month) -> dict[int, int]:
    """How many fixtures each team has in the month — catches doubles and blanks."""
    events = set(month.events)
    counts: dict[int, int] = {}
    for f in fixtures:
        if f["event"] in events:
            counts[f["team_h"]] = counts.get(f["team_h"], 0) + 1
            counts[f["team_a"]] = counts.get(f["team_a"], 0) + 1
    return counts
