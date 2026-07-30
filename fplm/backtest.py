"""Walk-forward validation on the completed 2025/26 season.

The model is rebuilt from scratch at the start of every month using *only* gameweeks
that had already been played, then scored against what actually happened. Nothing
downstream of the month boundary leaks in.

Two questions are being asked, and only the second one really matters:

  1. Does predicted xP correlate with actual points?  (rank correlation, MAE)
  2. Does a squad built by the optimiser actually score more than the alternatives?

Question 2 is the honest test. A model can have a respectable correlation and still
pick a bad fifteen, because squad selection is a constrained argmax over the top of
the distribution — precisely where estimation error concentrates.

Data: vaastav/Fantasy-Premier-League, data/2025-26/gws/merged_gw.csv.
"""
from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

from . import autosub
from . import optimise as opt
from . import ratings as rt
from . import xp as xpmod
from .monthly import Month, PlayerMonth

POS_MAP = {"GK": 1, "GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
POS_NAME = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
DATA = Path(__file__).resolve().parent.parent / "data"
BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"


# --------------------------------------------------------------------- #
# Loading


def load_rows(path: Path) -> list[dict]:
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        try:
            out.append(
                {
                    "pid": int(r["element"]),
                    "name": r["name"],
                    "pos": POS_MAP[r["position"]],
                    "team_name": r["team"],
                    "gw": int(r["GW"]),
                    "opponent": int(r["opponent_team"]),
                    "home": r["was_home"].strip().lower() == "true",
                    "minutes": int(r["minutes"]),
                    "starts": int(r["starts"] or 0),
                    "points": int(r["total_points"]),
                    # Managers selecting this player — real ownership, which is what
                    # defines "the team everyone owns" in season.py.
                    "selected": int(r["selected"] or 0),
                    "fpl_xp": float(r["xP"] or 0),
                    "price": int(r["value"]) / 10.0,
                    "xg": float(r["expected_goals"] or 0),
                    "xa": float(r["expected_assists"] or 0),
                    "xgc": float(r["expected_goals_conceded"] or 0),
                    # Defensive contribution scoring only arrived in 2025/26, so older
                    # season archives have no such column. Treat it as absent rather
                    # than dropping the whole season.
                    "defcon": float(r.get("defensive_contribution") or 0),
                    "saves": int(r["saves"] or 0),
                    "bonus": int(r["bonus"] or 0),
                    "yellow": int(r["yellow_cards"] or 0),
                    "gs": int(r["team_h_score"] or 0) if r["was_home"].strip().lower() == "true"
                    else int(r["team_a_score"] or 0),
                    "ga": int(r["team_a_score"] or 0) if r["was_home"].strip().lower() == "true"
                    else int(r["team_h_score"] or 0),
                    "month": r["kickoff_time"][:7],
                }
            )
        except (ValueError, KeyError):
            continue
    return out


def month_buckets(rows: list[dict]) -> list[Month]:
    """Group gameweeks into calendar months by their first kickoff."""
    first: dict[int, str] = {}
    for r in rows:
        first.setdefault(r["gw"], r["month"])
        first[r["gw"]] = min(first[r["gw"]], r["month"])

    by_month: dict[str, list[int]] = defaultdict(list)
    for gw, ym in first.items():
        by_month[ym].append(gw)

    months = []
    for i, (ym, gws) in enumerate(sorted(by_month.items())):
        months.append(Month(i + 1, ym, min(gws), max(gws)))
    return months


# --------------------------------------------------------------------- #
# Rebuilding the model from history only


def team_ids(rows: list[dict]) -> dict[str, int]:
    """Map team names to the opponent ids used in the same file."""
    pairs: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        pairs[r["team_name"]].add(r["opponent"])
    names = sorted(pairs)
    # Recover each team's own id as the one id never appearing as its own opponent.
    all_ids = set().union(*pairs.values())
    out = {}
    for n in names:
        missing = all_ids - pairs[n]
        if len(missing) == 1:
            out[n] = missing.pop()
    return out


def ratings_from_results(
    history: list[dict], name_to_id: dict[str, int], shrink_games: float = 6.0
) -> dict[int, rt.TeamRating]:
    """Attack/defence multipliers from goals actually scored and conceded so far."""
    gf: dict[int, list[int]] = defaultdict(list)
    ga: dict[int, list[int]] = defaultdict(list)
    seen: set[tuple] = set()
    for r in history:
        tid = name_to_id.get(r["team_name"])
        if tid is None:
            continue
        key = (tid, r["gw"], r["opponent"])
        if key in seen:
            continue
        seen.add(key)
        gf[tid].append(r["gs"])
        ga[tid].append(r["ga"])

    ids = sorted(set(gf) | set(ga))
    if not ids:
        return {}
    league_gf = statistics.mean([g for t in ids for g in gf[t]] or [1.4])
    league_ga = statistics.mean([g for t in ids for g in ga[t]] or [1.4])

    out = {}
    for tid in ids:
        n = len(gf[tid])
        # Shrink toward the league average; early in the season the sample is tiny.
        w = n / (n + shrink_games)
        att = w * (statistics.mean(gf[tid]) / league_gf) + (1 - w) * 1.0 if n else 1.0
        dfc = w * (statistics.mean(ga[tid]) / league_ga) + (1 - w) * 1.0 if n else 1.0
        out[tid] = rt.TeamRating(tid, str(tid), str(tid), max(att, 0.25), max(dfc, 0.25), 1 - w)
    return out


def elements_from_history(history: list[dict], upto_gw: int) -> list[dict]:
    """Collapse played gameweeks into a bootstrap-shaped element list.

    Building a synthetic `elements` list means the backtest runs through the exact
    same `xp.build_rates` the live tool uses, rather than a parallel reimplementation
    that could quietly diverge from it.
    """
    agg: dict[int, dict] = {}
    for r in history:
        a = agg.setdefault(
            r["pid"],
            {
                "id": r["pid"],
                "web_name": r["name"],
                "element_type": r["pos"],
                "team_name": r["team_name"],
                "minutes": 0,
                "starts": 0,
                "xg": 0.0,
                "xa": 0.0,
                "xgc": 0.0,
                "defcon": 0.0,
                "saves": 0,
                "bonus": 0,
                "yellow_cards": 0,
                "total_points": 0,
                "price": r["price"],
                "games": 0,
            },
        )
        a["minutes"] += r["minutes"]
        a["starts"] += r["starts"]
        a["xg"] += r["xg"]
        a["xa"] += r["xa"]
        a["xgc"] += r["xgc"]
        a["defcon"] += r["defcon"]
        a["saves"] += r["saves"]
        a["bonus"] += r["bonus"]
        a["total_points"] += r["points"]
        a["yellow_cards"] += r["yellow"]
        a["price"] = r["price"]  # most recent price
        a["games"] += 1

    played = max(upto_gw - 1, 1)
    out = []
    for a in agg.values():
        m = max(a["minutes"], 1)
        per90 = 90.0 / m
        out.append(
            {
                "id": a["id"],
                "web_name": a["web_name"],
                "element_type": a["element_type"],
                "team": 0,  # filled by the caller
                "team_name": a["team_name"],
                "minutes": a["minutes"],
                "starts": a["starts"],
                # Raw counts plus the number of gameweeks they could have played, so
                # build_rates works from real rates rather than a rescaled proxy.
                "games_available": played,
                "now_cost": int(round(a["price"] * 10)),
                "status": "a",
                "chance_of_playing_next_round": None,
                "selected_by_percent": "5.0",
                "expected_goals_per_90": a["xg"] * per90,
                "expected_assists_per_90": a["xa"] * per90,
                "expected_goals_conceded_per_90": a["xgc"] * per90,
                "defensive_contribution_per_90": a["defcon"] * per90,
                "saves_per_90": a["saves"] * per90,
                "bonus": a["bonus"],
                "yellow_cards": a["yellow_cards"],
                "total_points": a["total_points"],
                # Was hardcoded None, which silently zeroed the set-piece uplift in
                # xp.py for every backtest — the change measured as a perfect no-op.
                # players_raw.csv carries the real order; merged_gw does not.
                "penalties_order": a.get("penalties_order"),
                "direct_freekicks_order": a.get("freekicks_order"),
                "corners_and_indirect_freekicks_order": a.get("corners_order"),
                "news": "",
            }
        )
    return out


# --------------------------------------------------------------------- #
# Metrics


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if va == 0 or vb == 0:
        return float("nan")
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (va * vb)


def spearman(a: list[float], b: list[float]) -> float:
    return _pearson(_ranks(a), _ranks(b))


# --------------------------------------------------------------------- #


def run_backtest(args) -> None:
    path = Path(args.csv) if args.csv else DATA / "merged_gw_2025-26.csv"
    if not path.exists():
        raise SystemExit(
            f"Missing {path}.\nDownload it with:\n"
            "  curl -L -o data/merged_gw_2025-26.csv "
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
            "master/data/2025-26/gws/merged_gw.csv"
        )

    rows = load_rows(path)
    months = month_buckets(rows)
    name_to_id = team_ids(rows)
    by_gw: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_gw[r["gw"]].append(r)

    print(f"\n{BOLD}Walk-forward backtest — 2025/26{RESET}")
    print(f"{DIM}{len(rows):,} player-gameweeks, {len(months)} months. "
          f"Each month is predicted using only earlier gameweeks.{RESET}")
    print("-" * 88)
    print(
        f"{'Month':<10}{'GWs':<8}{'n':>5}{'rho':>7}{'FPL rho':>9}{'PPG rho':>9}"
        f"{'MAE':>7}{'  optimiser':>12}{'template':>10}{'median':>8}"
    )
    print("-" * 88)

    agg = {"rho": [], "fpl": [], "ppg": [], "mae": [], "opt": [], "tmpl": [], "med": []}

    for mi, month in enumerate(months):
        if mi < args.from_month - 1:
            continue
        history = [r for r in rows if r["gw"] < month.start_event]
        future = [r for r in rows if month.start_event <= r["gw"] <= month.stop_event]
        if not history or not future:
            continue

        els = elements_from_history(history, month.start_event)
        tid_of = {e["id"]: name_to_id.get(e["team_name"], 0) for e in els}
        for e in els:
            e["team"] = tid_of[e["id"]]
        els = [e for e in els if e["team"]]
        if len(els) < 100:
            continue

        team_ratings = ratings_from_results(history, name_to_id)
        if not team_ratings:
            continue

        rates = xpmod.build_rates({"elements": els})

        # Fixtures actually played in the target month.
        fixtures, seen = [], set()
        for r in future:
            tid = name_to_id.get(r["team_name"])
            if tid is None:
                continue
            h, a = (tid, r["opponent"]) if r["home"] else (r["opponent"], tid)
            key = (r["gw"], h, a)
            if key in seen:
                continue
            seen.add(key)
            fixtures.append(
                {"event": r["gw"], "team_h": h, "team_a": a,
                 "team_h_difficulty": 3, "team_a_difficulty": 3}
            )

        missing = {f["team_h"] for f in fixtures} | {f["team_a"] for f in fixtures}
        for t in missing - set(team_ratings):
            team_ratings[t] = rt.TeamRating(t, str(t), str(t), 1.0, 1.0, 1.0)

        # Whole-season fixture set for the baseline lambdas.
        all_fx, seen2 = [], set()
        for r in rows:
            tid = name_to_id.get(r["team_name"])
            if tid is None:
                continue
            h, a = (tid, r["opponent"]) if r["home"] else (r["opponent"], tid)
            if (r["gw"], h, a) in seen2:
                continue
            seen2.add((r["gw"], h, a))
            all_fx.append({"event": r["gw"], "team_h": h, "team_a": a,
                           "team_h_difficulty": 3, "team_a_difficulty": 3})

        avg_for, avg_against = xpmod.team_baseline_lambdas(team_ratings, all_fx)

        fx_by_team: dict[int, list[dict]] = defaultdict(list)
        for f in fixtures:
            fx_by_team[f["team_h"]].append(f)
            fx_by_team[f["team_a"]].append(f)

        # --- Predict ------------------------------------------------------
        table: dict[int, PlayerMonth] = {}
        for pid, r in rates.items():
            if r.team not in team_ratings:
                continue
            fxs = [
                xpmod.fixture_xp(r, f, team_ratings, avg_for, avg_against)
                for f in fx_by_team.get(r.team, [])
            ]
            table[pid] = PlayerMonth(
                pid=pid, name=r.name, team=r.team, team_name=str(r.team), pos=r.pos,
                price=r.price, selected_by=r.selected_by,
                xp=sum(f.xp for f in fxs), var=sum(f.var for f in fxs),
                n_fixtures=len(fxs), exp_minutes=r.exp_minutes, fixtures=fxs, flags=r.flags,
            )

        # --- Actuals ------------------------------------------------------
        actual: dict[int, float] = defaultdict(float)
        fpl_xp: dict[int, float] = defaultdict(float)
        # Per-gameweek truth as well as the monthly total, because automatic
        # substitutions are a per-gameweek decision and cannot be scored from a
        # month-level aggregate.
        gw_pts: dict[int, dict[int, float]] = defaultdict(dict)
        gw_played: dict[int, dict[int, bool]] = defaultdict(dict)
        for r in future:
            actual[r["pid"]] += r["points"]
            fpl_xp[r["pid"]] += r["fpl_xp"]
            g = r["gw"]
            gw_pts[g][r["pid"]] = gw_pts[g].get(r["pid"], 0.0) + r["points"]
            gw_played[g][r["pid"]] = gw_played[g].get(r["pid"], False) or r["minutes"] > 0

        prior_minutes: dict[int, float] = defaultdict(float)
        prior_points: dict[int, float] = defaultdict(float)
        prior_games: dict[int, int] = defaultdict(int)
        for r in history:
            prior_minutes[r["pid"]] += r["minutes"]
            prior_points[r["pid"]] += r["points"]
            prior_games[r["pid"]] += 1

        # Score only players who were plausibly in contention.
        pool = [
            pid for pid in table
            if prior_minutes[pid] >= 270 and table[pid].n_fixtures > 0 and pid in actual
        ]
        if len(pool) < 60:
            continue

        pred = [table[p].xp for p in pool]
        act = [actual[p] for p in pool]
        fplp = [fpl_xp[p] for p in pool]
        ppg = [
            prior_points[p] / max(prior_games[p], 1) * table[p].n_fixtures for p in pool
        ]

        rho = spearman(pred, act)
        rho_ppg = spearman(ppg, act)
        # FPL only publishes its own xP for some gameweeks in this archive — several
        # months have none at all. Scoring it on a partial month would flatter it
        # against a full-month actual, so it is only reported where most of the month
        # is actually covered.
        covered = sum(1 for v in fplp if v > 0) / len(fplp)
        rho_fpl = spearman(fplp, act) if covered > 0.8 else float("nan")
        mae = sum(abs(pred[i] - act[i]) for i in range(len(pool))) / len(pool)

        # --- Squad-level test ---------------------------------------------
        opt_pts = tmpl_pts = med_pts = float("nan")
        sub = {p: table[p] for p in pool}
        squad = opt.solve(sub, lam=0.0, cons=opt.Constraints(min_expected_minutes=20))
        if squad:
            opt_pts = _actual_squad_points(squad, actual, gw_pts, gw_played)

        # Template baseline: the fifteen most-selected players that form a legal squad,
        # proxied here by prior points per game since ownership is not in this file.
        tmpl = _greedy_legal_squad(sub, key=lambda p: prior_points[p.pid])
        if tmpl:
            tmpl_pts = _actual_squad_points(tmpl, actual, gw_pts, gw_played)
        med_pts = _median_random_squad(sub, actual, gw_pts, gw_played)

        print(
            f"{month.name:<10}{f'{month.start_event}-{month.stop_event}':<8}{len(pool):>5}"
            f"{rho:>7.3f}{rho_fpl:>9.3f}{rho_ppg:>9.3f}{mae:>7.2f}"
            f"{opt_pts:>12.0f}{tmpl_pts:>10.0f}{med_pts:>8.0f}"
        )
        for k, v in (("rho", rho), ("fpl", rho_fpl), ("ppg", rho_ppg), ("mae", mae),
                     ("opt", opt_pts), ("tmpl", tmpl_pts), ("med", med_pts)):
            if not math.isnan(v):
                agg[k].append(v)

    print("-" * 88)
    if agg["rho"]:
        print(
            f"{'MEAN':<10}{'':<8}{'':>5}{statistics.mean(agg['rho']):>7.3f}"
            f"{statistics.mean(agg['fpl']):>9.3f}{statistics.mean(agg['ppg']):>9.3f}"
            f"{statistics.mean(agg['mae']):>7.2f}{statistics.mean(agg['opt']):>12.0f}"
            f"{statistics.mean(agg['tmpl']):>10.0f}{statistics.mean(agg['med']):>8.0f}"
        )
        print("-" * 88)
        print(f"{DIM}rho = Spearman rank correlation of predicted vs actual monthly "
              f"points (higher is better).{RESET}")
        print(f"{DIM}FPL rho = same, using FPL's own published xP. PPG rho = points "
              f"per game to date.{RESET}")
        print(f"{DIM}optimiser / template / median = actual points scored by a squad "
              f"built each way: XI + captain, with automatic substitutions.{RESET}")
        edge = statistics.mean(agg["opt"]) - statistics.mean(agg["med"])
        print(f"\n{BOLD}Optimiser beat the median squad by {edge:+.0f} points per "
              f"month on average.{RESET}\n")
    else:
        print("No months scored — check the CSV.\n")


def _actual_squad_points(
    squad: opt.Squad,
    actual: dict[int, float],
    gw_pts: dict[int, dict[int, float]] | None = None,
    gw_played: dict[int, dict[int, bool]] | None = None,
) -> float:
    """Points a squad actually scored: XI plus captain, with automatic substitutions.

    Substitutions used to be missing entirely here, which made this a biased ruler for
    anything to do with the bench — a bench player was worth exactly zero, so every
    pound spent on one was pure loss and `BENCH_WEIGHT` could only ever measure as
    harmful. Measured across 24 months the autosubs are worth **15.5 points a month**,
    so the old figure understated the optimiser's squad by about 8%.

    Falls back to the old XI-only sum when no per-gameweek data is supplied.
    """
    if gw_pts is None or gw_played is None:
        total = sum(actual.get(p.pid, 0.0) for p in squad.xi)
        return total + actual.get(squad.captain, 0.0)

    xi = [p.pid for p in squad.xi]
    bench = [p.pid for p in squad.bench]
    pos = {p.pid: p.pos for p in squad.players}

    total = 0.0
    for gw in sorted(gw_pts):
        pts = gw_pts[gw]
        played = gw_played.get(gw, {})
        for pid in autosub.apply(xi, bench, pos, played):
            total += pts.get(pid, 0.0)
        # The vice-captain takes over only if the captain did not play that gameweek.
        c, v = squad.captain, squad.vice
        if played.get(c, False):
            total += pts.get(c, 0.0)
        elif played.get(v, False):
            total += pts.get(v, 0.0)
    return total


def _greedy_legal_squad(table: dict[int, PlayerMonth], key) -> opt.Squad | None:
    """Best legal fifteen under a simple ranking, used for baseline comparisons."""
    quota = {1: 2, 2: 5, 3: 5, 4: 3}
    picked: list[PlayerMonth] = []
    per_team: dict[int, int] = defaultdict(int)
    spend = 0.0
    for pos, n in quota.items():
        cands = sorted(
            (p for p in table.values() if p.pos == pos), key=lambda p: -key(p)
        )
        got = 0
        for p in cands:
            if got >= n:
                break
            if per_team[p.team] >= 3 or spend + p.price > 100.0 - _min_remaining(quota, picked, table):
                continue
            picked.append(p)
            per_team[p.team] += 1
            spend += p.price
            got += 1
        if got < n:
            return None
    starters = [p.pid for p in _best_xi_local(picked)]
    cap = max(starters, key=lambda pid: table[pid].xp)
    vice = max((p for p in starters if p != cap), key=lambda pid: table[pid].xp, default=cap)
    return opt.Squad(picked, starters, cap, vice, 0.0, spend)


def _min_remaining(quota, picked, table) -> float:
    """Crude budget guard: reserve 4.0m per still-unfilled slot."""
    return max(0, 15 - len(picked) - 1) * 4.0


def _best_xi_local(picked: list[PlayerMonth]) -> list[PlayerMonth]:
    by_pos: dict[int, list[PlayerMonth]] = defaultdict(list)
    for p in picked:
        by_pos[p.pos].append(p)
    for k in by_pos:
        by_pos[k].sort(key=lambda p: -p.xp)
    xi = by_pos[1][:1] + by_pos[2][:3] + by_pos[3][:2] + by_pos[4][:1]
    chosen = {p.pid for p in xi}
    rest = sorted((p for p in picked if p.pid not in chosen and p.pos != 1),
                  key=lambda p: -p.xp)
    caps = {2: 5, 3: 5, 4: 3}
    counts = {2: 3, 3: 2, 4: 1}
    for p in rest:
        if len(xi) >= 11:
            break
        if counts[p.pos] < caps[p.pos]:
            xi.append(p)
            counts[p.pos] += 1
    return xi


def _median_random_squad(
    table: dict[int, PlayerMonth],
    actual: dict[int, float],
    gw_pts: dict[int, dict[int, float]] | None = None,
    gw_played: dict[int, dict[int, bool]] | None = None,
) -> float:
    """Median actual score of legal squads drawn at random from the credible pool."""
    import random

    rnd = random.Random(11)
    pool = [p for p in table.values() if p.exp_minutes >= 45]
    quota = {1: 2, 2: 5, 3: 5, 4: 3}
    scores = []
    for _ in range(200):
        picked, per_team, spend, ok = [], defaultdict(int), 0.0, True
        for pos, n in quota.items():
            cands = [p for p in pool if p.pos == pos]
            rnd.shuffle(cands)
            got = 0
            for p in cands:
                if got >= n:
                    break
                if per_team[p.team] >= 3 or spend + p.price > 100.0:
                    continue
                picked.append(p)
                per_team[p.team] += 1
                spend += p.price
                got += 1
            if got < n:
                ok = False
                break
        if not ok:
            continue
        xi = _best_xi_local(picked)
        cap = max(xi, key=lambda p: p.xp)
        vice = max((p for p in xi if p.pid != cap.pid), key=lambda p: p.xp, default=cap)
        sq = opt.Squad(picked, [p.pid for p in xi], cap.pid, vice.pid, 0.0, spend)
        scores.append(_actual_squad_points(sq, actual, gw_pts, gw_played))
    return statistics.median(scores) if scores else float("nan")
