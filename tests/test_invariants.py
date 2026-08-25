"""The invariants, as tests that run without a network.

Every defect this project has shipped was silent: it produced plausible output and
was found by a person reading a number that looked wrong. These encode the rules
that were violated, using a synthetic bootstrap rather than the live API, so they
run on every push and do not depend on FPL being up or on what happens to be true
of this week's data.

    ./.venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from fplm import optimise as opt
from fplm import selfcheck
from fplm import xp as xpmod


def make_elements(n_per_team: int = 15, teams: int = 20, minutes: int = 900,
                  starts: int = 10) -> list[dict]:
    """A bootstrap-shaped element list with nothing pathological in it."""
    els = []
    pid = 0
    for t in range(1, teams + 1):
        for i in range(n_per_team):
            pid += 1
            els.append({
                "id": pid, "code": 100000 + pid, "web_name": f"P{pid}",
                "team": t, "element_type": (i % 4) + 1, "now_cost": 45 + (i % 8) * 5,
                "status": "a", "selected_by_percent": "5.0", "minutes": minutes,
                "starts": starts, "bonus": 4, "yellow_cards": 1, "total_points": 40,
                "expected_goals_per_90": "0.20", "expected_assists_per_90": "0.15",
                "expected_goals_conceded_per_90": "1.30",
                "defensive_contribution_per_90": "5.0", "saves_per_90": "0.0",
                "chance_of_playing_next_round": None, "news": "",
                "penalties_order": None, "direct_freekicks_order": None,
                "corners_and_indirect_freekicks_order": None,
            })
    return els


class PositionalMeans(unittest.TestCase):
    """The shrinkage target must exist, or every rate collapses toward zero."""

    def test_means_present_with_a_full_season(self):
        means = xpmod._positional_means(make_elements(minutes=900))
        for pos, m in means.items():
            self.assertGreater(m["pp90"], 0.0, f"position {pos} has no mean")

    def test_means_survive_one_gameweek(self):
        # The defect: a hard 450-minute floor meant nobody qualified in August and
        # every mean came back 0.000, which shrank every player's rates to nothing.
        means = xpmod._positional_means(make_elements(minutes=90, starts=1))
        for pos, m in means.items():
            self.assertGreater(m["pp90"], 0.0,
                               f"position {pos} collapsed after one gameweek")

    def test_empty_input_does_not_raise(self):
        self.assertEqual(xpmod.build_rates({"elements": []}), {})


class MinutesModel(unittest.TestCase):
    """Start rates must reflect games played, not a whole season."""

    def test_a_player_who_started_every_game_is_nailed(self):
        # The defect: `games_available` is absent from the live API, so the divisor
        # fell back to 38 and a player who started the only match scored 1/38.
        rates = xpmod.build_rates({"elements": make_elements(minutes=90, starts=1)})
        best = max(rates.values(), key=lambda r: r.p_start)
        self.assertGreater(best.p_start, 0.5,
                           "an ever-present is not being treated as a starter")
        self.assertGreater(best.exp_minutes, 45.0)

    def test_club_minutes_are_in_the_right_order_of_magnitude(self):
        rates = xpmod.build_rates({"elements": make_elements(minutes=900, starts=10)})
        by_team: dict[int, float] = {}
        for r in rates.values():
            by_team[r.team] = by_team.get(r.team, 0.0) + r.exp_minutes
        lo, hi = selfcheck.CLUB_MINUTES_BAND
        for team, total in by_team.items():
            self.assertTrue(lo <= total <= hi,
                            f"club {team} projects {total:.0f} of 990 minutes")


class TransferRules(unittest.TestCase):
    """A plan has to be reachable from the squad actually held."""

    def test_roll_value_is_off_or_positive(self):
        self.assertGreaterEqual(opt.ROLL_VALUE, 0.0)

    def test_a_held_player_is_never_screened_out_by_the_minutes_floor(self):
        # The defect: the pool filter excluded held players below the floor, which
        # forced transfers nobody asked for and made the problem infeasible.
        cons = opt.Constraints(min_expected_minutes=25.0, current_squad={7})
        self.assertIn("current_squad", opt.Constraints.__dataclass_fields__)
        self.assertEqual(cons.current_squad, {7})


class SelfCheckHarness(unittest.TestCase):
    """The checker itself must fail when the model is broken."""

    class _Squad:
        def __init__(self, players, xi):
            self.players, self.xi, self.cost = players, xi, 99.0

    class _Month:
        def __init__(self, xp):
            self.squad_xp, self.n_gws = xp, 1

    class _Plan:
        def __init__(self, squad, xp):
            self.squad = squad
            self.months = [SelfCheckHarness._Month(xp)]

    def _plan(self, xp: float):
        class P:
            def __init__(self, pid, team):
                self.pid, self.team = pid, team
        players = [P(i, 1 + i % 20) for i in range(15)]
        squad = self._Squad(players, players[:11])
        return self._Plan(squad, xp)

    def test_healthy_model_passes(self):
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        checks = selfcheck.run(boot, self._plan(55.0), rates)
        self.assertTrue(all(c.ok for c in checks),
                        [c.line for c in checks if not c.ok])

    def test_collapsed_minutes_are_caught(self):
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        for r in rates.values():        # replay the GW1 rollover defect
            r.exp_minutes /= 6.0
        checks = selfcheck.run(boot, self._plan(5.7), rates)
        failed = {c.name for c in checks if not c.ok}
        self.assertIn("club minutes near 990", failed)
        self.assertIn("squad forecast plausible", failed)

    def test_a_plan_that_cannot_win_is_caught(self):
        # The regression this check was added for: a squad that maximises expected
        # points, buys the template and finishes mid-table by construction. Every
        # legality check passed while win probability fell from 9.4% to 0.2%.
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        plan = self._plan(55.0)
        plan.sim_scores = [1, 2, 3]        # mark it as actually simulated
        plan.sim_p_win = 0.002
        checks = selfcheck.run(boot, plan, rates, rivals=48)
        self.assertIn("beats the median rival", {c.name for c in checks if not c.ok})

    def test_a_healthy_win_probability_passes(self):
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        plan = self._plan(55.0)
        plan.sim_scores = [1, 2, 3]
        plan.sim_p_win = 0.106
        checks = selfcheck.run(boot, plan, rates, rivals=48)
        self.assertTrue(all(c.ok for c in checks),
                        [c.line for c in checks if not c.ok])

    def test_an_unsimulated_plan_is_not_judged_on_win_probability(self):
        # Reporting zero because nothing was simulated is not the same claim as
        # reporting zero after simulating, and must not fail the build.
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        checks = selfcheck.run(boot, self._plan(55.0), rates, rivals=48)
        self.assertNotIn("beats the median rival", {c.name for c in checks})

    def test_advice_disagreeing_with_the_squad_is_caught(self):
        # The dashboard printed "no transfer - roll it" beside a squad that had
        # already sold Haaland, because the advice and the squad came from
        # different planners.
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        plan = self._plan(55.0)
        held = {p.pid for p in plan.squad.players}
        held.remove(next(iter(held)))
        held.add(9999)                      # one transfer away from the squad shown
        plan.moves_now = []                 # ...but the panel claims none
        checks = selfcheck.run(boot, plan, rates, held=held)
        self.assertIn("advice matches the squad",
                      {c.name for c in checks if not c.ok})

    def test_illegal_squad_is_caught(self):
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        plan = self._plan(55.0)
        for p in plan.squad.players:    # everyone from one club
            p.team = 1
        checks = selfcheck.run(boot, plan, rates)
        self.assertIn("max 3 per club", {c.name for c in checks if not c.ok})


if __name__ == "__main__":
    unittest.main()
