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
from fplm import forecast as fcmod
from fplm import horizon as hzmod
from fplm import optimise as opt
from fplm import plan as planmod
from fplm import tracking
from fplm import selfcheck
from fplm import xp as xpmod
from fplm.monthly import Month, PlayerMonth


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


def _pm(pid, pos, price, xp=4.0, team=None):
    """A PlayerMonth with nothing pathological in it."""
    team = team if team is not None else 1 + pid % 20
    return PlayerMonth(pid, f"P{pid}", team, f"T{team}", pos, price, 5.0, xp,
                       xp * 0.8, 1, 85.0)


def _pool(n_per_pos=(4, 10, 10, 6), price=4.5):
    """A legal pool: enough in every position, spread across twenty clubs."""
    table, pid = {}, 0
    for pos, n in zip((1, 2, 3, 4), n_per_pos):
        for _ in range(n):
            pid += 1
            table[pid] = _pm(pid, pos, price)
    return table


class SquadState(unittest.TestCase):
    """The squad, bank and selling prices the plan is solved against.

    The plan used to assume £100.0m and the last published picks every day. Once
    prices move that is the wrong purse, and once a transfer has been made for the
    coming deadline it is the wrong squad — and the wrong number of free transfers.
    """

    def _fake_api(self, picks_by_gw, transfers, chips=()):
        """Stand in for the three endpoints `squad_state` reads."""
        def fetch(endpoint, key=None, ttl=0):
            if endpoint.endswith("/history"):
                return {"current": [], "chips": list(chips)}
            if endpoint.endswith("/transfers"):
                return list(transfers)
            raise AssertionError(endpoint)

        def entry_picks(entry, gw, ttl=0):
            if gw not in picks_by_gw:
                raise RuntimeError("Not found")
            return {"picks": [{"element": p} for p in picks_by_gw[gw]],
                    "entry_history": {"bank": 12}}   # £1.2m
        return fetch, entry_picks

    def _boot(self, cost, change=None):
        change = change or {}
        return {"elements": [{"id": pid, "now_cost": c,
                              "cost_change_start": change.get(pid, 0)}
                             for pid, c in cost.items()]}

    def _run(self, next_gw, picks_by_gw, transfers, boot, chips=()):
        fetch, picks = self._fake_api(picks_by_gw, transfers, chips)
        orig = tracking.api.fetch, tracking.api.entry_picks
        tracking.api.fetch, tracking.api.entry_picks = fetch, picks
        try:
            return tracking.squad_state(1, next_gw, boot)
        finally:
            tracking.api.fetch, tracking.api.entry_picks = orig

    def test_selling_price_is_purchase_plus_half_the_rise_rounded_down(self):
        self.assertAlmostEqual(tracking.sell_price(5.0, 5.3), 5.1)   # 0.3 rise -> +0.1
        self.assertAlmostEqual(tracking.sell_price(5.0, 5.4), 5.2)
        self.assertAlmostEqual(tracking.sell_price(5.0, 5.1), 5.0)   # half of 0.1 rounds down
        self.assertAlmostEqual(tracking.sell_price(5.0, 4.7), 4.7)   # a fall is passed on in full

    def test_the_purse_is_bank_plus_what_the_fifteen_would_sell_for(self):
        held = list(range(1, 16))
        cost = {p: 50 for p in held}
        # Player 1 has risen 0.4 since the season opened: bought at 4.6, listed 5.0,
        # sells for 4.8. The other fourteen are unchanged.
        boot = self._boot(cost, change={1: 4})
        st = self._run(5, {4: held}, [], boot)
        self.assertIsNotNone(st)
        self.assertAlmostEqual(st.sell[1], 4.8)
        self.assertAlmostEqual(st.sell[2], 5.0)
        self.assertAlmostEqual(st.bank, 1.2)
        self.assertAlmostEqual(st.budget, 1.2 + 4.8 + 14 * 5.0)

    def test_a_transfer_already_made_this_week_is_applied(self):
        held = list(range(1, 16))
        cost = {p: 50 for p in held}
        cost[99] = 60
        boot = self._boot(cost)
        # Sold 15 for 5.0, bought 99 for 6.0, for the coming GW5.
        transfers = [{"event": 5, "time": "t", "element_in": 99, "element_in_cost": 60,
                      "element_out": 15, "element_out_cost": 50}]
        st = self._run(5, {4: held}, transfers, boot)
        self.assertIn(99, st.players)
        self.assertNotIn(15, st.players)
        self.assertEqual(st.pending, 1)
        self.assertAlmostEqual(st.bank, 1.2 - 1.0)       # bank moved with the trade
        self.assertAlmostEqual(st.sell[99], 6.0)          # bought at the listed price
        self.assertEqual(len(st.players), 15)

    def test_a_player_bought_by_transfer_sells_from_what_was_paid(self):
        held = list(range(1, 16))
        cost = {p: 50 for p in held}
        cost[1] = 56   # listed 5.6 now; bought for 5.0 in GW3
        boot = self._boot(cost, change={1: 10})   # up 1.0 since GW1, but that is not his purchase
        transfers = [{"event": 3, "time": "t", "element_in": 1, "element_in_cost": 50,
                      "element_out": 77, "element_out_cost": 45}]
        st = self._run(5, {4: held}, transfers, boot)
        self.assertAlmostEqual(st.sell[1], 5.3)           # 5.0 + half of 0.6

    def test_after_a_free_hit_the_real_squad_is_the_week_before(self):
        real = list(range(1, 16))
        one_week = list(range(101, 116))
        cost = {p: 50 for p in real + one_week}
        boot = self._boot(cost)
        # Free hit played in GW4: the GW4 picks are the one-week team.
        st = self._run(5, {4: one_week, 3: real}, [], boot,
                       chips=[{"name": "freehit", "event": 4}])
        self.assertEqual(st.players, set(real))

    def test_unreadable_picks_mean_no_state_not_a_guess(self):
        boot = self._boot({p: 50 for p in range(1, 16)})
        self.assertIsNone(self._run(5, {}, [], boot))

    def test_before_gw1_there_is_nothing_to_read(self):
        boot = self._boot({p: 50 for p in range(1, 16)})
        self.assertIsNone(self._run(1, {}, [], boot))


class BudgetLine(unittest.TestCase):
    """The optimiser must afford exactly what FPL would let you afford."""

    def test_a_squad_over_a_flat_hundred_is_still_legal_when_it_is_yours(self):
        # Fifteen held players listed at a combined 100.5 after price rises. The purse
        # is bank plus selling value; a flat 100.0 would force a sale nobody asked for.
        table = _pool(price=6.7)                      # 30 x 6.7 = 201 listed
        held = set(list(range(1, 3)) + list(range(5, 10)) + list(range(15, 20))
                   + list(range(25, 28)))
        self.assertEqual(len(held), 15)
        for p in held:
            table[p].xp = 4.1                         # keeping them is strictly best
        sell = {p: 6.6 for p in held}                 # each sells 0.1 under listed
        purse = round(sum(sell.values()) + 0.5, 1)    # 99.5 + 0.5 in the bank
        cons = opt.Constraints(budget=purse, current_squad=held, free_transfers=1,
                               sell_price=sell)
        sq = opt.solve(table, lam=0.0, cons=cons)
        self.assertIsNotNone(sq, "the squad you hold must always be a legal answer")
        self.assertEqual({p.pid for p in sq.players}, held)
        # And the same fifteen against a flat 100.0 at listed prices is *not* legal,
        # which is the forced sale the old purse produced.
        flat = opt.solve(table, lam=0.0, cons=opt.Constraints(
            budget=100.0, current_squad=held, free_transfers=1))
        self.assertTrue(flat is None or {p.pid for p in flat.players} != held)

    def test_a_swap_is_affordable_only_when_bank_plus_selling_price_covers_it(self):
        table = _pool(price=6.0)
        held = set(list(range(1, 3)) + list(range(5, 10)) + list(range(15, 20))
                   + list(range(25, 28)))
        target = 3                                    # a keeper worth buying
        table[target].xp = 30.0
        table[target].price = 6.4
        sell = {p: 6.0 for p in held}
        for bank in (0.3, 0.4):
            cons = opt.Constraints(budget=round(90.0 + bank, 1), current_squad=held,
                                   free_transfers=1, sell_price=sell)
            sq = opt.solve(table, lam=0.0, cons=cons)
            bought = target in {p.pid for p in sq.players}
            # 6.4 in for 6.0 out needs 0.4 in the bank, not 0.3.
            self.assertEqual(bought, bank >= 0.4, f"bank {bank}")

    def test_zero_free_transfers_means_no_move(self):
        table = _pool(price=5.0)
        held = set(list(range(1, 3)) + list(range(5, 10)) + list(range(15, 20))
                   + list(range(25, 28)))
        table[3].xp = 40.0                            # very tempting
        cons = opt.Constraints(budget=100.0, current_squad=held, free_transfers=0,
                               max_hits=0)
        sq = opt.solve(table, lam=0.0, cons=cons)
        self.assertEqual({p.pid for p in sq.players}, held)

    def test_the_horizon_planner_accepts_zero_free_transfers(self):
        table = _pool(price=5.0)
        held = set(list(range(1, 3)) + list(range(5, 10)) + list(range(15, 20))
                   + list(range(25, 28)))
        tables = {g: table for g in (5, 6, 7)}
        cons = opt.Constraints(budget=100.0, current_squad=held)
        plan = hzmod.solve(tables, held, cons, free_transfers=0, time_limit=20)
        self.assertIsNotNone(plan, "a week with nothing free used to be infeasible")
        self.assertEqual(plan.squads[5], held)
        self.assertEqual(plan.free[6], 1)


class ForwardPlan(unittest.TestCase):
    """The gameweek-by-gameweek projection must play the chips it shows."""

    def _plan(self, next_gw, chips):
        boot = {"elements": make_elements(),
                "teams": [{"id": t, "short_name": f"T{t}", "name": f"Team{t}",
                           "strength_overall_home": 3, "strength_overall_away": 3}
                          for t in range(1, 21)],
                "events": [{"id": g, "finished": g < next_gw, "is_next": g == next_gw,
                            "deadline_time": "2026-10-03T10:00:00Z"} for g in range(1, 39)],
                "phases": [{"id": 1, "name": "Overall", "start_event": 1, "stop_event": 38},
                           {"id": 2, "name": "October", "start_event": 1, "stop_event": 38}]}
        fixtures, fid = [], 0
        for g in range(1, 39):
            for i in range(0, 20, 2):
                fid += 1
                fixtures.append({"id": fid, "event": g, "team_h": i + 1, "team_a": i + 2,
                                 "team_h_difficulty": 3, "team_a_difficulty": 3})
        p = planmod.build(boot, fixtures, simulate=False, start="template")
        p.months[0].chips = [chipmod.ChipValue(c, "October", gw, 5.0) for gw, c in chips]
        return boot, fixtures, p

    def test_a_free_hit_week_scores_the_free_hit_squad_and_then_reverts(self):
        boot, fixtures, p = self._plan(5, [(7, "freehit")])
        gws = fcmod.build(boot, fixtures, p, use_horizon=False, min_minutes=0.0)
        by = {g.gw: g for g in gws}
        self.assertEqual(by[7].chip, "freehit")
        # The week after, the only differences from before the free hit are that
        # week's own transfers: everything the free hit changed has come back.
        changed = set(by[8].squad) ^ set(by[6].squad)
        self.assertEqual(len(changed), 2 * len(by[8].moves),
                         "the squad must come back after a free hit")
        self.assertAlmostEqual(by[7].bank, by[6].bank, places=1,
                               msg="a free hit must not move the bank")
        self.assertEqual(by[7].hits, 0)
        if by[7].moves:
            self.assertNotEqual(set(by[7].squad), set(by[6].squad),
                                "the week is scored on the one-week team, not the old one")

    def test_a_chip_week_does_not_spend_the_free_transfer(self):
        boot, fixtures, p = self._plan(5, [(7, "wildcard")])
        gws = fcmod.build(boot, fixtures, p, use_horizon=False, min_minutes=0.0)
        by = {g.gw: g for g in gws}
        self.assertEqual(by[7].hits, 0)
        self.assertEqual(by[7].free_transfers, min(5, by[6].free_transfers + 1))


if __name__ == "__main__":
    unittest.main()
