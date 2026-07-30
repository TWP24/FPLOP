"""Monte Carlo month simulation and win probability.

Expected points alone cannot tell you which squad wins a month. Winning requires
beating the best of N rivals, which is a question about the *tail* of your score
distribution and about how correlated you are with the field.

Design decisions that matter:

* **Shared match multipliers.** Each team gets a Gamma(k, 1/k) attacking multiplier
  per match (mean 1). Teammates' returns then rise and fall together — the standard
  negative-binomial construction, and the reason tripling up on one attack is riskier
  than three players from three clubs. Independent-player models miss this entirely.

* **One shared universe.** Rivals are scored on the *same* simulated gameweeks as you.
  Correlation between your squad and the field is what actually decides a monthly
  prize: if you and everyone else own the same captain, that captain hauling does not
  help you win. Simulating rivals separately would destroy this and badly overstate
  the value of template picks.

* **Rivals sampled by ownership.** Rival squads are drawn from the ownership
  distribution in `selected_by_percent`, so the field clusters on the template and
  differentials are rewarded correctly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import ratings as rt
from .monthly import Month, PlayerMonth
from .optimise import Squad
from .xp import CAMEO_MINUTES, SHORT_START_MINUTES, PlayerRates, team_baseline_lambdas

GK, DEF, MID, FWD = 1, 2, 3, 4
GOAL_POINTS = {GK: 6, DEF: 6, MID: 5, FWD: 4}
CS_POINTS = {GK: 4, DEF: 4, MID: 1, FWD: 0}
DEFCON_THRESHOLD = {DEF: 10, MID: 12, FWD: 12}

# Gamma shape for the per-match team multiplier. Lower = more volatile matches.
MATCH_SHAPE = 4.0


@dataclass
class SimResult:
    mean: float
    sd: float
    p10: float
    p50: float
    p90: float
    p_win: float
    p_top3: float
    target: float
    field_mean: float
    field_sd: float
    scores: np.ndarray


class MonthSimulator:
    """Simulates every player's month once, then scores any squad against it."""

    def __init__(
        self,
        boot: dict,
        fixtures: list[dict],
        table: dict[int, PlayerMonth],
        rates: dict[int, PlayerRates],
        team_ratings: dict[int, rt.TeamRating],
        month: Month,
        n_sims: int = 10000,
        seed: int = 7,
    ):
        self.table = table
        self.rates = rates
        self.month = month
        self.n_sims = n_sims
        self.rng = np.random.default_rng(seed)

        self.pids = sorted(table.keys())
        self.index = {pid: i for i, pid in enumerate(self.pids)}
        self.n = len(self.pids)

        self.points = np.zeros((n_sims, self.n), dtype=np.float32)
        self.played = np.zeros((n_sims, self.n), dtype=bool)

        # Populated by build_field, then read back by field_ownership().
        self.field_starts: dict[int, int] = {}
        self.field_caps: dict[int, int] = {}
        self.field_size = 0

        self._run(fixtures, team_ratings)

    # ------------------------------------------------------------------ #

    def _run(self, fixtures: list[dict], team_ratings: dict) -> None:
        avg_for, avg_against = team_baseline_lambdas(team_ratings, fixtures)
        events = set(self.month.events)
        month_fixtures = [f for f in fixtures if f["event"] in events]

        by_team: dict[int, list[int]] = {}
        for pid in self.pids:
            by_team.setdefault(self.table[pid].team, []).append(self.index[pid])

        S = self.n_sims
        rng = self.rng

        for f in month_fixtures:
            lam_h, lam_a = rt.match_lambdas(team_ratings, f["team_h"], f["team_a"])

            # One attacking multiplier per team per match, shared by all its players.
            m_h = rng.gamma(MATCH_SHAPE, 1.0 / MATCH_SHAPE, size=S).astype(np.float32)
            m_a = rng.gamma(MATCH_SHAPE, 1.0 / MATCH_SHAPE, size=S).astype(np.float32)

            goals_h = rng.poisson(lam_h * m_h).astype(np.float32)
            goals_a = rng.poisson(lam_a * m_a).astype(np.float32)

            for team, mult, conceded in (
                (f["team_h"], m_h, goals_a),
                (f["team_a"], m_a, goals_h),
            ):
                idx = by_team.get(team)
                if idx:
                    self._score_side(idx, mult, conceded, team, f, avg_for, avg_against, team_ratings)

    def _score_side(
        self,
        idx: list[int],
        mult: np.ndarray,
        conceded: np.ndarray,
        team: int,
        fixture: dict,
        avg_for: dict,
        avg_against: dict,
        team_ratings: dict,
    ) -> None:
        """Simulate every player on one side of one fixture."""
        S = self.n_sims
        rng = self.rng
        n = len(idx)

        home = fixture["team_h"] == team
        lam_h, lam_a = rt.match_lambdas(team_ratings, fixture["team_h"], fixture["team_a"])
        lam_for, lam_against = (lam_h, lam_a) if home else (lam_a, lam_h)
        att_mult = lam_for / max(avg_for[team], 1e-6)
        def_mult = lam_against / max(avg_against[team], 1e-6)

        rr = [self.rates[self.pids[i]] for i in idx]
        f32 = lambda fn: np.array([fn(r) for r in rr], dtype=np.float32)  # noqa: E731

        p_start = f32(lambda r: r.p_start)
        p_cameo = f32(lambda r: r.p_cameo)
        mps = f32(lambda r: r.mins_per_start)
        p60_gs = f32(lambda r: r.p60_given_start)

        # --- Minutes -------------------------------------------------------
        # Uses exactly the rates the analytic model uses, so the two agree.
        u = rng.random((S, n), dtype=np.float32)
        started = u < p_start[None, :]
        cameo = (~started) & (u < (p_start + p_cameo)[None, :])
        appeared = started | cameo

        # A start either goes the distance or is cut short before the hour.
        long_start = rng.random((S, n), dtype=np.float32) < p60_gs[None, :]
        minutes = np.where(
            started,
            np.where(long_start, mps[None, :], SHORT_START_MINUTES),
            0.0,
        ).astype(np.float32)
        minutes = np.where(cameo, CAMEO_MINUTES, minutes)
        played60 = minutes >= 60.0
        share = minutes / 90.0

        pts = appeared.astype(np.float32) + played60.astype(np.float32)

        # --- Goals and assists, scaled by the shared match multiplier ------
        gp = f32(lambda r: GOAL_POINTS[r.pos])
        lam_g = f32(lambda r: r.xg90)[None, :] * share * mult[:, None] * att_mult
        lam_as = f32(lambda r: r.xa90)[None, :] * share * mult[:, None] * att_mult

        goals = rng.poisson(np.clip(lam_g, 0, 8)).astype(np.float32)
        assists = rng.poisson(np.clip(lam_as, 0, 8)).astype(np.float32)
        pts += goals * gp[None, :] + assists * 3.0

        # --- Clean sheets: everyone on the side shares one conceded draw ---
        csp = f32(lambda r: CS_POINTS[r.pos])
        pts += ((conceded[:, None] == 0) & played60).astype(np.float32) * csp[None, :]

        # --- Goals conceded penalty for keepers and defenders --------------
        # No 60-minute requirement on this one, unlike the clean sheet.
        is_back = np.array([r.pos in (GK, DEF) for r in rr], dtype=bool)
        pts -= (
            np.floor(conceded[:, None] / 2.0) * is_back[None, :] * appeared
        ).astype(np.float32)

        # --- Saves ---------------------------------------------------------
        is_gk = np.array([r.pos == GK for r in rr], dtype=bool)
        if is_gk.any():
            lam_sv = f32(lambda r: r.saves90)[None, :] * share * def_mult * is_gk[None, :]
            saves = rng.poisson(np.clip(lam_sv, 0, 15)).astype(np.float32)
            pts += np.floor(saves / 3.0)

        # --- Defensive contribution ----------------------------------------
        thresh = f32(lambda r: DEFCON_THRESHOLD.get(r.pos, 9999))
        lam_dc = f32(lambda r: r.defcon90)[None, :] * share
        dc = rng.poisson(np.clip(lam_dc, 0, 60)).astype(np.float32)
        pts += (dc >= thresh[None, :]).astype(np.float32) * 2.0

        # --- Bonus: lumpy 3/2/1, far likelier when the player returned -----
        # The split pays 1.85 points per bonus-winning event on average, and the
        # "returned" boost is renormalised by each player's own return probability,
        # so expected bonus still matches the analytic rate exactly. Only the shape
        # of the distribution changes, which is the whole point of simulating it.
        returned = (goals + assists) > 0
        rate = f32(lambda r: r.bonus90)[None, :] * share * (0.5 + 0.5 * att_mult)
        p_ret = 1.0 - np.exp(-(lam_g + lam_as))
        modulate = (0.55 + 1.6 * returned) / (0.55 + 1.6 * p_ret)
        p_bonus = np.clip(rate * modulate / 1.85, 0.0, 1.0)

        b = rng.random((S, n), dtype=np.float32)
        pts += np.where(b < p_bonus * 0.25, 3.0, 0.0)
        pts += np.where((b >= p_bonus * 0.25) & (b < p_bonus * 0.60), 2.0, 0.0)
        pts += np.where((b >= p_bonus * 0.60) & (b < p_bonus), 1.0, 0.0)

        # --- Cards ---------------------------------------------------------
        yc = rng.random((S, n), dtype=np.float32) < np.clip(
            f32(lambda r: r.yellow90)[None, :] * share, 0, 0.6
        )
        pts -= yc.astype(np.float32)

        pts *= appeared  # no appearance, no points

        cols = np.array(idx)
        self.points[:, cols] += pts
        self.played[:, cols] |= appeared

    # ------------------------------------------------------------------ #

    def squad_scores(self, squad: Squad) -> np.ndarray:
        """Score one squad across every simulation, with autosubs and captaincy."""
        base = self.score_picks(
            [p.pid for p in squad.players], squad.starters, squad.captain, squad.vice
        )
        return base - 4 * squad.hits

    def score_picks(
        self, squad_ids: list[int], starters: list[int], captain: int, vice: int
    ) -> np.ndarray:
        cols = {pid: self.index[pid] for pid in squad_ids}
        start_set = set(starters)
        bench_ids = [p for p in squad_ids if p not in start_set]

        s_idx = np.array([cols[p] for p in starters])
        total = (self.points[:, s_idx] * self.played[:, s_idx]).sum(axis=1)

        # --- Automatic substitutions ---------------------------------------
        pos_of = {pid: self.table[pid].pos for pid in squad_ids}
        bench_gk = [p for p in bench_ids if pos_of[p] == GK]
        bench_out = [p for p in bench_ids if pos_of[p] != GK]
        start_gk = [p for p in starters if pos_of[p] == GK]

        if bench_gk and start_gk:
            gi, bi = cols[start_gk[0]], cols[bench_gk[0]]
            swap = (~self.played[:, gi]) & self.played[:, bi]
            total += swap * self.points[:, bi]

        out_start = [p for p in starters if pos_of[p] != GK]
        if bench_out and out_start:
            o_idx = np.array([cols[p] for p in out_start])
            missing = (~self.played[:, o_idx]).sum(axis=1)

            b_idx = np.array([cols[p] for p in bench_out])
            b_played = self.played[:, b_idx]
            b_pts = self.points[:, b_idx]
            # Rank of each available bench player in bench order.
            rank = np.cumsum(b_played, axis=1)
            for k in range(1, len(bench_out) + 1):
                kth = ((rank == k) & b_played).astype(np.float32)
                total += (missing >= k) * (b_pts * kth).sum(axis=1)

        # --- Captain, with the vice taking over if the captain does not play
        ci, vi = cols[captain], cols[vice]
        total += np.where(
            self.played[:, ci],
            self.points[:, ci],
            np.where(self.played[:, vi], self.points[:, vi], 0.0),
        )
        return total

    # ------------------------------------------------------------------ #

    def build_field(
        self,
        n_rivals: int,
        cons=None,
        belief_noise: float = 0.22,
        ownership_pull: float = 0.20,
        rival_lam: float = 0.15,
    ) -> np.ndarray:
        """Build a competitive field and score it in this universe.

        Rivals are not random ownership draws — a monthly league is full of people who
        also pick well, and modelling them as noise makes any squad look like a winner.
        Each rival instead solves the same optimisation under *their own* noisy beliefs
        about expected points, nudged toward popular players. That yields legal,
        budget-constrained, genuinely competitive squads that still disagree with each
        other, which is what a real mini-league looks like.

        `belief_noise` is the spread of rival estimates around the model's own xP;
        `ownership_pull` is how strongly they drift to the template.
        """
        import copy as _copy

        from . import optimise as opt

        rng = self.rng
        base_cons = cons or opt.Constraints()

        own = np.array([self.table[p].selected_by for p in self.pids], dtype=np.float64)
        own_z = (own - own.mean()) / (own.std() or 1.0)

        scores = np.zeros((n_rivals, self.n_sims), dtype=np.float32)
        built = 0
        for r in range(n_rivals):
            noisy: dict[int, PlayerMonth] = {}
            for i, pid in enumerate(self.pids):
                p = self.table[pid]
                shock = float(rng.normal(0.0, belief_noise))
                mult = float(np.exp(shock - 0.5 * belief_noise**2))
                q = _copy.copy(p)
                q.xp = p.xp * mult * (1.0 + ownership_pull * own_z[i])
                noisy[pid] = q

            # Rivals differ in risk appetite as well as in belief.
            lam = max(0.0, float(rng.normal(rival_lam, rival_lam)))
            squad = opt.solve(noisy, lam=lam, cons=base_cons)
            if squad is None:
                continue

            # They field and captain according to their own beliefs, not the truth.
            xi = squad.starters
            cap = max(xi, key=lambda p: noisy[p].xp)
            vice = max((p for p in xi if p != cap), key=lambda p: noisy[p].xp, default=cap)
            scores[built] = self.score_picks([p.pid for p in squad.players], xi, cap, vice)
            built += 1
            for pid in xi:
                self.field_starts[pid] = self.field_starts.get(pid, 0) + 1
            self.field_caps[cap] = self.field_caps.get(cap, 0) + 1
            self.field_size += 1

        return scores[:built] if built else scores

    def field_ownership(self) -> dict[int, float]:
        """Share of the simulated field starting each player.

        Measured from the field that was actually built rather than taken from FPL's
        published `selected_by_percent`, because those are different quantities: the
        published figure is global ownership across millions of managers, while what
        decides a twenty-person cash league is what those nineteen specific rivals
        own. Feeding this back into the optimiser is what makes the differential term
        and the win-probability estimate consistent with each other.
        """
        if not self.field_size:
            return {}
        return {pid: n / self.field_size for pid, n in self.field_starts.items()}

    def apply_field_ownership(self, table: dict[int, PlayerMonth]) -> dict[int, PlayerMonth]:
        """Copy of the table with `selected_by` replaced by realised field ownership."""
        import copy as _copy

        own = self.field_ownership()
        out = {}
        for pid, p in table.items():
            q = _copy.copy(p)
            q.selected_by = own.get(pid, 0.0) * 100.0
            out[pid] = q
        return out

    def evaluate(self, squad: Squad, field: np.ndarray) -> SimResult:
        """Full distributional summary of a squad against a simulated field."""
        mine = self.squad_scores(squad)
        best_rival = field.max(axis=0)
        rank = (field > mine[None, :]).sum(axis=0) + 1

        return SimResult(
            mean=float(mine.mean()),
            sd=float(mine.std()),
            p10=float(np.percentile(mine, 10)),
            p50=float(np.percentile(mine, 50)),
            p90=float(np.percentile(mine, 90)),
            p_win=float((mine > best_rival).mean()),
            p_top3=float((rank <= 3).mean()),
            target=float(best_rival.mean()),
            field_mean=float(field.mean()),
            field_sd=float(field.std()),
            scores=mine,
        )


def _best_xi(picks: list[int], table: dict[int, PlayerMonth]) -> list[int]:
    """Pick a legal, expected-points-maximising XI from a 15."""
    by_pos: dict[int, list[int]] = {}
    for p in picks:
        by_pos.setdefault(table[p].pos, []).append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: -table[p].xp)

    xi = (
        by_pos.get(GK, [])[:1]
        + by_pos.get(DEF, [])[:3]
        + by_pos.get(MID, [])[:2]
        + by_pos.get(FWD, [])[:1]
    )
    chosen = set(xi)
    rest = sorted(
        (p for p in picks if p not in chosen and table[p].pos != GK),
        key=lambda p: -table[p].xp,
    )

    caps = {DEF: 5, MID: 5, FWD: 3}
    counts = {DEF: 3, MID: 2, FWD: 1}
    for p in rest:
        if len(xi) >= 11:
            break
        pos = table[p].pos
        if counts.get(pos, 0) < caps.get(pos, 0):
            xi.append(p)
            counts[pos] += 1
    return xi
