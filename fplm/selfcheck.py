"""Invariants the model must satisfy, checked on every build.

This exists because of how the defects in this project have actually been found.
Not one was caught by the code noticing: start probabilities collapsing to a
thirty-eighth, positional means coming back as zero, the dashboard rendering a
freshly solved fifteen while a real squad was held, a plan proposing eleven
transfers against one free transfer. Every one produced plausible output and was
spotted by a person reading a number that looked wrong.

Rank correlation will not save you here — the means-collapse defect *improved*
rho, because shrinking every rate to a common value leaves a tidy ordering. What
catches these is not a better metric but a statement that cannot be true of a
working model.

Each check below is an identity or a rule, not a preference. A club plays 990
minutes; a plan may not exceed its transfer allowance; a squad you hold is the
squad you are shown. When one fails the build should stop rather than publish,
because a dashboard that is confidently wrong is worse than one that is missing.

    ./fplm.sh check
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

TEAM_MATCH_MINUTES = 990.0

# A club's expected minutes must sum to 990. Individual clubs legitimately drift —
# a promoted side whose entire squad has no Premier League history is inferred from
# price and lands low — so the median club is checked instead. That is robust to a
# few bad clubs and still catches a league-wide collapse, which is the failure mode
# that has actually happened twice.
CLUB_MINUTES_BAND = (700.0, 1300.0)

# A full eleven plus captain over one gameweek. The rollover defect produced 5.7.
SQUAD_XP_BAND = (25.0, 90.0)

# A squad chosen by an optimiser should not be a worse bet than the median rival in
# its own simulated field. That floor is 1/(rivals+1) by construction, so the check
# asks only that the plan clears the bar anyone gets for turning up.
#
# It exists because of a regression these checks did not catch. A horizon planner
# that maximised expected points bought the template, which finishes mid-table by
# construction; win probability fell from 9.4% to 0.2% while expected points barely
# moved, and every legality check passed, because the squad was perfectly legal and
# merely aimed at the wrong thing. Legality is not the same as fitness for purpose.
PWIN_FLOOR_MULTIPLE = 1.0


@dataclass
class Check:
    name: str
    ok: bool
    detail: str

    @property
    def line(self) -> str:
        return f"  {'PASS' if self.ok else 'FAIL'}  {self.name:34} {self.detail}"


def run(boot, plan, rates, held: set[int] | None = None,
        free_transfers: int = 1, max_hits: int = 0,
        rivals: int | None = None) -> list[Check]:
    """Every invariant, evaluated against one built plan."""
    out: list[Check] = []

    # --- minutes are an accounting identity ------------------------------
    by_team: dict[int, float] = {}
    for r in rates.values():
        by_team[r.team] = by_team.get(r.team, 0.0) + r.exp_minutes
    med = statistics.median(by_team.values()) if by_team else 0.0
    lo, hi = CLUB_MINUTES_BAND
    out.append(Check(
        "club minutes near 990", lo <= med <= hi,
        f"median club {med:.0f} of {TEAM_MATCH_MINUTES:.0f} (band {lo:.0f}-{hi:.0f})"))

    # --- the shrinkage target must exist ---------------------------------
    from . import xp as xpmod

    means = xpmod._positional_means(boot["elements"])
    dead = [p for p, m in means.items() if m["pp90"] <= 0.0]
    out.append(Check(
        "positional means non-zero", not dead,
        "all four positions" if not dead else f"zero for position(s) {dead}"))

    # --- the forecast must be on a human scale ---------------------------
    month = plan.months[0] if plan.months else None
    per_gw = (month.squad_xp / max(month.n_gws, 1)) if month else 0.0
    lo, hi = SQUAD_XP_BAND
    out.append(Check(
        "squad forecast plausible", lo <= per_gw <= hi,
        f"{per_gw:.1f} xP per gameweek (band {lo:.0f}-{hi:.0f})"))

    # --- the plan must be aimed at winning, not merely at scoring ----------
    # Skipped when nothing was simulated: an unsimulated plan reports zero, which is
    # not the same claim as a simulated plan reporting zero.
    if rivals and getattr(plan, "sim_scores", None) is not None:
        p_win = float(getattr(plan, "sim_p_win", 0.0) or 0.0)
        floor = PWIN_FLOOR_MULTIPLE / (rivals + 1)
        out.append(Check(
            "beats the median rival", p_win >= floor,
            f"P(win) {p_win * 100:.1f}% against a floor of {floor * 100:.1f}% "
            f"for {rivals} rivals"))

    # --- the plan must be reachable from the squad held -------------------
    if held:
        shown = {p.pid for p in plan.squad.players}
        moves = len(shown - held)
        allowed = free_transfers + max_hits
        out.append(Check(
            "transfers within allowance", moves <= allowed,
            f"{moves} transfer(s), {allowed} allowed"))
        # What the page tells you to do must match the squad it shows you. These are
        # produced by different code paths — the transfer comes from the plan, the
        # forward view from a separate planner — and they once disagreed in public,
        # with "no transfer, roll it" printed beside a squad that had sold Haaland.
        stated = len(getattr(plan, "moves_now", []) or [])
        out.append(Check(
            "advice matches the squad", stated == moves,
            f"panel states {stated} transfer(s), squad shows {moves}"))
        out.append(Check(
            "plan built on the squad held", moves <= allowed and len(shown & held) >= 15 - allowed,
            f"{len(shown & held)} of 15 held players retained"))

    # --- players you said to keep must actually be kept --------------------
    # A setting that silently fails to protect a player is worse than not offering
    # it: you would believe a decision had been made for you that had not.
    kept = set(getattr(plan, "kept", ()) or ())
    if kept:
        shown = {p.pid for p in plan.squad.players}
        missing = kept - shown
        out.append(Check(
            "kept players are still there", not missing,
            f"{len(kept)} kept, {len(missing)} sold" if missing
            else f"all {len(kept)} still in the squad"))

    # --- the squad itself must be legal ----------------------------------
    players = plan.squad.players
    per_club: dict[int, int] = {}
    for p in players:
        per_club[p.team] = per_club.get(p.team, 0) + 1
    worst = max(per_club.values()) if per_club else 0
    out.append(Check("squad is 15 players", len(players) == 15, f"{len(players)}"))
    out.append(Check("max 3 per club", worst <= 3, f"most from one club: {worst}"))
    out.append(Check("within budget", plan.squad.cost <= 100.01,
                     f"£{plan.squad.cost:.1f}m"))
    out.append(Check("eleven starters", len(plan.squad.xi) == 11,
                     f"{len(plan.squad.xi)}"))
    return out


def report(checks: list[Check]) -> bool:
    """Print the result. Returns True when everything passed."""
    for c in checks:
        print(c.line)
    bad = [c for c in checks if not c.ok]
    print(f"\n  {len(checks) - len(bad)}/{len(checks)} passed")
    return not bad
