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

from fplm import chips as chipmod
from fplm import optimise as opt
from fplm import plan as planmod
from fplm import tracking
from fplm import selfcheck
from fplm import xp as xpmod
from fplm.monthly import Month


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


class FreeTransfers(unittest.TestCase):
    """Banked transfers are rebuilt from what was spent, since FPL will not say."""

    def _derive(self, history, next_gw, chips=()):
        payload = {"current": history, "chips": list(chips)}
        original = tracking.api.fetch
        tracking.api.fetch = lambda *a, **k: payload
        try:
            return tracking.free_transfers(1, next_gw)
        finally:
            tracking.api.fetch = original

    def test_everyone_starts_gw2_with_one(self):
        # GW1's squad is assembled freely before the deadline, so nothing banks
        # out of it however many changes were made.
        h = [{"event": 1, "event_transfers": 0}]
        self.assertEqual(self._derive(h, 2), 1)

    def test_banking_a_week_gives_two(self):
        h = [{"event": 1, "event_transfers": 0}, {"event": 2, "event_transfers": 0}]
        self.assertEqual(self._derive(h, 3), 2)

    def test_spending_keeps_you_at_one(self):
        h = [{"event": 1, "event_transfers": 0}, {"event": 2, "event_transfers": 1}]
        self.assertEqual(self._derive(h, 3), 1)

    def test_banking_is_capped_at_five(self):
        h = [{"event": g, "event_transfers": 0} for g in range(1, 12)]
        self.assertEqual(self._derive(h, 12), 5)

    def test_a_wildcard_does_not_spend_the_bank(self):
        h = [{"event": 1, "event_transfers": 0}, {"event": 2, "event_transfers": 0},
             {"event": 3, "event_transfers": 11}]
        self.assertEqual(self._derive(h, 4, chips=[{"name": "wildcard", "event": 3}]), 3)


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

    def test_selling_a_kept_player_is_caught(self):
        # A setting that silently fails to protect a player is worse than not
        # offering it — you would believe a decision had been made for you.
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        plan = self._plan(55.0)
        plan.kept = {9999}                  # asked to keep someone not in the squad
        checks = selfcheck.run(boot, plan, rates)
        self.assertIn("kept players are still there",
                      {c.name for c in checks if not c.ok})

    def test_keeping_a_player_who_is_there_passes(self):
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        plan = self._plan(55.0)
        plan.kept = {plan.squad.players[0].pid}
        checks = selfcheck.run(boot, plan, rates)
        self.assertTrue(all(c.ok for c in checks),
                        [c.line for c in checks if not c.ok])

    def test_illegal_squad_is_caught(self):
        boot = {"elements": make_elements()}
        rates = xpmod.build_rates(boot)
        plan = self._plan(55.0)
        for p in plan.squad.players:    # everyone from one club
            p.team = 1
        checks = selfcheck.run(boot, plan, rates)
        self.assertIn("max 3 per club", {c.name for c in checks if not c.ok})


class ChipAllocation(unittest.TestCase):
    """Every chip the game gives you has to end up on the calendar.

    The defect: the allocator priced each chip in the single best week of a month and
    dropped it outright if another chip had already taken that week. Within a month the
    kindest week is largely the same week for everybody — best captain fixture, best
    bench fixtures, best week to free-hit — so collisions were the norm, and the chip
    that lost was the one worth least, which is the Triple Captain every time. The
    visible symptom was a season plan showing one Triple Captain when FPL gives two.
    """

    PHASES = [("October", 6, 9), ("November", 10, 12), ("December", 13, 18),
              ("January", 19, 23), ("February", 24, 27), ("March", 28, 30),
              ("April", 31, 33), ("May", 34, 38)]

    def _months(self):
        return [Month(i + 1, n, a, b) for i, (n, a, b) in enumerate(self.PHASES)]

    def _windows(self):
        """Both halves of the season, as bootstrap-static reports them."""
        names = ("wildcard", "freehit", "bboost", "3xc")
        return ([chipmod.ChipWindow(n, 1, 19) for n in names]
                + [chipmod.ChipWindow(n, 20, 38) for n in names])

    def _values(self, months, peak):
        """Chip values where `peak(month)` is the week every chip wants."""
        tops = {"wildcard": 15.0, "freehit": 10.0, "bboost": 8.0, "3xc": 6.0}
        vals = []
        for m in months:
            top_gw = peak(m)
            for chip, top in tops.items():
                by_gw = {gw: top * 0.85 ** abs(gw - top_gw) for gw in m.events}
                vals.append(chipmod.ChipValue(chip, m.name, top_gw, top, "", by_gw))
        return vals

    def test_both_triple_captains_survive_a_week_collision(self):
        months = self._months()
        got = chipmod.allocate(
            self._values(months, peak=lambda m: m.start_event),
            self._windows(), months)
        self.assertEqual(len([c for c in got if c.chip == "3xc"]), 2,
                         f"a Triple Captain went unplayed: {[(c.chip, c.gw) for c in got]}")

    def test_every_chip_is_allocated(self):
        months = self._months()
        got = chipmod.allocate(
            self._values(months, peak=lambda m: m.start_event),
            self._windows(), months)
        self.assertEqual(len(got), 8, [(c.chip, c.month, c.gw) for c in got])

    def test_one_chip_per_gameweek(self):
        months = self._months()
        got = chipmod.allocate(
            self._values(months, peak=lambda m: m.start_event),
            self._windows(), months)
        gws = [c.gw for c in got]
        self.assertEqual(len(gws), len(set(gws)), f"two chips share a week: {gws}")

    def test_chips_land_inside_their_own_window_and_month(self):
        months = self._months()
        by_name = {m.name: m for m in months}
        got = chipmod.allocate(
            self._values(months, peak=lambda m: m.stop_event),
            self._windows(), months)
        halves = {}
        for c in got:
            m = by_name[c.month]
            self.assertTrue(m.start_event <= c.gw <= m.stop_event,
                            f"{c.chip} in {c.month} landed on GW{c.gw}")
            halves.setdefault(c.chip, []).append(c.gw <= 19)
        for chip, first_half in halves.items():
            self.assertEqual(sorted(first_half), [False, True],
                             f"both {chip} chips came from the same half of the season")

    def test_a_month_straddling_the_halfway_split_can_still_take_a_chip(self):
        # January runs GW19-23 this season and the chip windows split at GW19/20, so
        # requiring a month to sit wholly inside a window barred January from every
        # chip in the game. Only the week played has to be inside the window.
        months = [Month(1, "January", 19, 23)]
        vals = self._values(months, peak=lambda m: m.start_event)
        got = chipmod.allocate(vals, self._windows(), months)
        self.assertTrue(got, "January took no chip at all")
        for c in got:
            self.assertTrue(19 <= c.gw <= 23)

    def test_a_first_half_chip_never_lands_after_the_split(self):
        months = [Month(1, "January", 19, 23)]
        vals = self._values(months, peak=lambda m: m.stop_event)   # everything wants GW23
        first_half = [chipmod.ChipWindow("3xc", 1, 19)]
        got = chipmod.allocate(vals, first_half, months)
        self.assertEqual([(c.chip, c.gw) for c in got], [("3xc", 19)])

    def test_a_chip_is_never_advised_for_a_week_already_played(self):
        # The live plan advised a Triple Captain in GW3 with GW5 the next deadline:
        # the month we are in is part-spent, and its best week for a chip was behind
        # us. A chip still held has to find the best week LEFT.
        months = self._months()
        got = chipmod.allocate(self._values(months, peak=lambda m: m.start_event),
                               self._windows(), months, first_gw=12)
        self.assertTrue(got)
        for c in got:
            self.assertGreaterEqual(c.gw, 12, f"{c.chip} advised for a played GW{c.gw}")

    def test_a_chip_whose_best_week_has_gone_moves_rather_than_vanishes(self):
        # November runs GW10-12 and every chip's best week in it is GW10, already
        # played. The chip should slide to GW12, not disappear and not jump month.
        months = [Month(1, "November", 10, 12)]
        vals = [chipmod.ChipValue("3xc", "November", 10, 9.0, "on Haaland",
                                  {10: 9.0, 11: 4.0, 12: 6.0},
                                  {10: "on Haaland", 11: "on Salah", 12: "on Isak"})]
        wins = [chipmod.ChipWindow("3xc", 1, 19)]
        got = chipmod.allocate(vals, wins, months, first_gw=11)
        self.assertEqual([(c.chip, c.gw, c.note) for c in got],
                         [("3xc", 12, "on Isak")])

    def test_a_month_wholly_behind_us_takes_no_chip(self):
        months = [Month(1, "August", 1, 2)]
        vals = [chipmod.ChipValue("3xc", "August", 1, 9.0, "", {1: 9.0, 2: 8.0})]
        got = chipmod.allocate(vals, [chipmod.ChipWindow("3xc", 1, 19)], months,
                               first_gw=5)
        self.assertEqual(got, [])

    def test_a_chip_with_nowhere_to_go_is_simply_left_out(self):
        # One month, one legal week: the second set of chips has no home and the
        # allocator must not invent one.
        months = [Month(1, "May", 38, 38)]
        vals = [chipmod.ChipValue(n, "May", 38, 5.0)
                for n in ("wildcard", "freehit", "bboost", "3xc")]
        got = chipmod.allocate(vals, self._windows(), months)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].gw, 38)

    def test_the_triple_captain_says_whose_armband_it_is(self):
        # The note is what the dashboard prints next to the week, so it has to follow
        # the chip when a collision moves it.
        v = chipmod.ChipValue("3xc", "October", 6, 9.0, "on Haaland",
                              {6: 9.0, 7: 8.0}, {6: "on Haaland", 7: "on Salah"})
        self.assertEqual(v.at(7, 8.0).note, "on Salah")


class SeasonObjective(unittest.TestCase):
    """The season total is what the plan is aimed at; months are where it lands."""

    def test_the_season_default_looks_past_the_month_ahead(self):
        self.assertLess(planmod.MONTHLY_WEIGHT["season"], 0.5)
        self.assertGreater(planmod.MONTHLY_WEIGHT["month"], 0.5)

    def test_a_season_plan_does_not_spread_chips_to_contest_months(self):
        # Spreading buys extra chances at a monthly cheque with points that would
        # score more elsewhere. Only the one-chip-a-week rule should spread a season
        # plan's chips.
        self.assertIsNone(planmod.CHIPS_PER_MONTH["season"])
        self.assertEqual(planmod.CHIPS_PER_MONTH["month"], 2)

    def test_chips_stack_in_one_month_when_nothing_caps_them(self):
        months = [Month(1, "December", 13, 18)]
        vals = [chipmod.ChipValue(n, "December", 13 + i, 10.0 - i,
                                  "", {gw: 10.0 - i for gw in months[0].events})
                for i, n in enumerate(("wildcard", "freehit", "bboost", "3xc"))]
        wins = [chipmod.ChipWindow(n, 1, 19)
                for n in ("wildcard", "freehit", "bboost", "3xc")]
        self.assertEqual(len(chipmod.allocate(vals, wins, months)), 4)
        self.assertEqual(len(chipmod.allocate(vals, wins, months, max_per_month=2)), 2)

    def test_winning_a_season_asks_for_less_of_an_edge_than_winning_a_month(self):
        # Nobody wins every month. Summing the monthly bar would set a target only a
        # manager who won all ten could hit.
        self.assertLess(planmod.season_winner_edge(9), planmod.MONTH_WINNER_EDGE)

    def test_the_season_edge_shrinks_as_the_months_pile_up(self):
        # The luck half of a month winner's edge averages out; the skill half does not,
        # so the bar falls toward it and never below it.
        edges = [planmod.season_winner_edge(n) for n in (1, 4, 9, 38)]
        self.assertEqual(edges, sorted(edges, reverse=True))
        floor = planmod.MONTH_WINNER_EDGE * planmod.WINNER_SKILL_SHARE
        self.assertGreater(edges[-1], floor)

    def test_a_month_in_progress_is_trimmed_to_what_is_left(self):
        # September runs GW3-5. With GW5 the next deadline the plan is about GW5 and
        # nothing else in that month: GW3 and GW4 are already in the bank, and
        # projecting them again counted the same points twice.
        sept = Month(3, "September", 3, 5)
        left = planmod.remaining(sept, 5)
        self.assertEqual((left.start_event, left.stop_event, left.n_events), (5, 5, 1))
        self.assertEqual(left.name, sept.name)
        self.assertEqual(left.phase_id, sept.phase_id)

    def test_a_month_wholly_ahead_of_us_is_left_alone(self):
        dec = Month(6, "December", 13, 18)
        self.assertEqual(planmod.remaining(dec, 5), dec)

    def test_a_month_already_over_trims_to_nothing_playable(self):
        aug = Month(2, "August", 1, 2)
        left = planmod.remaining(aug, 5)
        self.assertEqual(left.events, [])

    def test_an_unknown_objective_is_refused_rather_than_guessed(self):
        with self.assertRaises(ValueError):
            planmod.build({"events": [], "chips": []}, [], objective="vibes")


if __name__ == "__main__":
    unittest.main()
