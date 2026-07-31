"""Your mini-league: what your rivals actually own, and what it is worth.

Everywhere else in this tool the opposition is *simulated* — `simulate.py` builds a
field of plausible managers because, before a season starts, that is the only field
there is. This module replaces the simulation with the real thing: it reads your
league's standings, pulls each rival's actual fifteen, and prices them through the same
model that prices yours.

That upgrade matters most for one number. The whole differential argument rests on
effective ownership — a player owned by most of your league cannot win you anything,
because his haul lifts everyone. Until now that was estimated from FPL's global
ownership, which is the wrong population: what decides a twenty-person work league is
what those nineteen specific people own, not what six million strangers do.

Timing constraint, not a limitation of the code: FPL does not expose any manager's
picks until that gameweek's deadline has passed. Before the season starts every request
returns "Not found", for your own entry as much as anyone else's. This module reports
that state plainly rather than guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import api
from .monthly import PlayerMonth

GK, DEF, MID, FWD = 1, 2, 3, 4


@dataclass
class Rival:
    entry: int
    team_name: str
    manager: str
    rank: int
    total_points: int
    squad: list[int] = field(default_factory=list)
    xi: list[int] = field(default_factory=list)
    captain: int | None = None
    chip: str | None = None
    xp: float = 0.0

    @property
    def has_picks(self) -> bool:
        return bool(self.squad)


@dataclass
class LeagueView:
    league_id: int
    league_name: str
    gameweek: int
    rivals: list[Rival]
    ownership: dict[int, float]        # pid -> share of the league starting him
    available: bool = True
    note: str = ""

    @property
    def with_picks(self) -> list[Rival]:
        return [r for r in self.rivals if r.has_picks]


def fetch_standings(league_id: int, ttl: int = 900) -> dict:
    return api.fetch(f"leagues-classic/{league_id}/standings",
                     key=f"league_{league_id}", ttl=ttl)


def fetch_picks(entry: int, gw: int, ttl: int = 900) -> dict | None:
    """A manager's squad for a gameweek, or None if FPL will not serve it yet."""
    try:
        return api.fetch(f"entry/{entry}/event/{gw}/picks",
                         key=f"picks_{entry}_{gw}", ttl=ttl)
    except Exception:  # noqa: BLE001 — 404 before the deadline is the normal case
        return None


def build(
    league_id: int,
    gw: int,
    table: dict[int, PlayerMonth],
    my_entry: int | None = None,
    limit: int = 30,
) -> LeagueView:
    """Read a league, price every rival's squad, and measure real ownership."""
    try:
        data = fetch_standings(league_id)
    except Exception as exc:  # noqa: BLE001
        return LeagueView(league_id, f"league {league_id}", gw, [], {},
                          available=False, note=f"could not read league: {exc}")

    league_name = data.get("league", {}).get("name", f"league {league_id}")
    results = data.get("standings", {}).get("results", [])
    if not results:
        return LeagueView(league_id, league_name, gw, [], {}, available=False,
                          note="league standings are empty — nothing scored yet this season")

    rivals: list[Rival] = []
    for row in results[:limit]:
        if my_entry and row["entry"] == my_entry:
            continue
        rivals.append(Rival(
            entry=row["entry"],
            team_name=row.get("entry_name", "?"),
            manager=row.get("player_name", "?"),
            rank=row.get("rank", 0),
            total_points=row.get("total", 0),
        ))

    # --- Pull each squad and price it -------------------------------------
    starts: dict[int, int] = {}
    fielded = 0
    for r in rivals:
        picks = fetch_picks(r.entry, gw)
        if not picks:
            continue
        r.chip = picks.get("active_chip")
        for p in picks.get("picks", []):
            pid = p["element"]
            r.squad.append(pid)
            # multiplier 0 means benched; 2 or 3 means captain or triple captain.
            if p.get("multiplier", 0) > 0:
                r.xi.append(pid)
                starts[pid] = starts.get(pid, 0) + 1
            if p.get("is_captain"):
                r.captain = pid
        r.xp = sum(table[p].xp for p in r.xi if p in table)
        if r.captain in table:
            r.xp += table[r.captain].xp
        fielded += 1

    if not fielded:
        return LeagueView(
            league_id, league_name, gw, rivals, {}, available=False,
            note=("squads are not readable yet — FPL only publishes picks once a "
                  f"gameweek deadline has passed, and GW{gw} has not started"),
        )

    ownership = {pid: n / fielded for pid, n in starts.items()}
    rivals.sort(key=lambda r: -r.xp)
    return LeagueView(league_id, league_name, gw, rivals, ownership)


def differentials(view: LeagueView, my_squad: list[int],
                  table: dict[int, PlayerMonth]) -> tuple[list, list]:
    """Split your squad into players the league mostly does not own, and template.

    Returned as (differentials, template), each a list of (PlayerMonth, ownership).
    Ownership here is the share of your league starting the player — the figure the
    differential maths actually needs.
    """
    mine, theirs = [], []
    for pid in my_squad:
        p = table.get(pid)
        if p is None:
            continue
        own = view.ownership.get(pid, 0.0)
        (mine if own < 0.34 else theirs).append((p, own))
    mine.sort(key=lambda x: -x[0].xp)
    theirs.sort(key=lambda x: -x[1])
    return mine, theirs


def threats(view: LeagueView, my_squad: list[int],
            table: dict[int, PlayerMonth], top: int = 8) -> list:
    """Highest-xP players your rivals own that you do not — what can beat you."""
    mine = set(my_squad)
    out = []
    for pid, own in view.ownership.items():
        if pid in mine or pid not in table:
            continue
        out.append((table[pid], own))
    out.sort(key=lambda x: -x[0].xp)
    return out[:top]
