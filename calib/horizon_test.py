"""Does planning several gameweeks at once beat planning one at a time?

Receding horizon: at each gameweek the model optimises the next H weeks jointly but
only executes the first week's decision, then re-solves. H=1 is the current greedy
planner. Everything is scored on points that actually happened, under real transfer
rules, so the comparison is of decisions rather than of forecasts.

    ./.venv/bin/python -m calib.horizon_test
"""
from __future__ import annotations

import collections
import statistics
from pathlib import Path

from fplm import backtest as bt
from fplm import horizon as hz
from fplm import monthly as mo
from fplm import optimise as opt
from fplm import ratings as rt
from fplm import xp as xpmod

SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")
FIRST, LAST = 6, 26
BUDGET = 100.0


def _tables(rows, n2i, upto, gws):
    """Per-gameweek expected points tables built from history before `upto`."""
    hist = [r for r in rows if r["gw"] < upto]
    if not hist:
        return None
    els = bt.elements_from_history(hist, upto)
    for e in els:
        e["team"] = n2i.get(e["team_name"], 0)
    els = [e for e in els if e["team"]]
    if len(els) < 100:
        return None
    rates = xpmod.build_rates({"elements": els})
    tr = bt.ratings_from_results(hist, n2i)
    if not tr:
        return None
    by_gw = collections.defaultdict(list)
    for r in rows:
        if r["gw"] in gws:
            by_gw[r["gw"]].append(r)

    out = {}
    for g in gws:
        fixtures, seen = [], set()
        for r in by_gw.get(g, []):
            tid = n2i.get(r["team_name"])
            if tid is None:
                continue
            hh, aa = (tid, r["opponent"]) if r["home"] else (r["opponent"], tid)
            if (hh, aa) in seen:
                continue
            seen.add((hh, aa))
            fixtures.append({"event": g, "team_h": hh, "team_a": aa,
                             "team_h_difficulty": 3, "team_a_difficulty": 3})
        trg = dict(tr)
        for t in ({f["team_h"] for f in fixtures} | {f["team_a"] for f in fixtures}) - set(trg):
            trg[t] = rt.TeamRating(t, "", "", 1.0, 1.0, 1.0)
        boot = {"elements": els, "teams": [{"id": t, "short_name": str(t)} for t in trg]}
        tbl = mo.build_table(boot, fixtures, rates, trg, mo.Month(0, f"gw{g}", g, g))
        if tbl:
            out[g] = tbl
    return out or None


def run_season(season, horizons=(1, 4), ft_value: float = 0.0,
               max_hits: int = 0, shuffle_seed: int | None = None) -> dict:
    rows = bt.load_rows(Path(f"data/merged_gw_{season}.csv"))
    n2i = bt.team_ids(rows)
    actual = collections.defaultdict(dict)
    played = collections.defaultdict(dict)
    for r in rows:
        actual[r["gw"]][r["pid"]] = r["points"]
        played[r["gw"]][r["pid"]] = r["minutes"] > 0

    results = {}
    for H in horizons:
        squad, free, bank, total, hits_taken = None, 1, 0.0, 0.0, 0
        for g in range(FIRST, LAST + 1):
            gws = [x for x in range(g, min(g + H, LAST) + 1)]
            tabs = _tables(rows, n2i, g, gws)
            if not tabs or g not in tabs:
                continue
            if squad is None:
                seed = opt.solve(tabs[g], lam=0.0,
                                 cons=opt.Constraints(budget=BUDGET,
                                                      min_expected_minutes=20))
                if seed is None:
                    continue
                squad = {p.pid for p in seed.players}
                bank = round(BUDGET - seed.cost, 1)

            plan = hz.solve(tabs, squad, bank,
                            opt.Constraints(budget=BUDGET, min_expected_minutes=20),
                            free_transfers=free, max_hits_per_gw=max_hits,
                            ft_terminal_value=ft_value, time_limit=45,
                            shuffle_seed=shuffle_seed)
            if plan is None:
                continue
            out_ids, in_ids = plan.transfers[g]
            n = len(in_ids)
            squad = plan.squads[g]
            free = min(hz.MAX_FREE, max(1, free - n + 1))
            total += bt._actual_squad_points(
                _as_squad(plan, g, tabs[g]), actual[g], {g: actual[g]}, {g: played[g]})
            # Charge the hits. Counting them without subtracting them is how a
            # previous version of this project flattered aggressive strategies.
            total -= 4 * plan.hits[g]
            hits_taken += plan.hits[g]
        results[H] = total
        results[f'hits{H}'] = hits_taken
    return results


def run(horizons=(1, 4)) -> None:
    import statistics as st
    print(f"receding horizon, GW{FIRST}-{LAST}, scored on actual points\n")
    print(f"  {'season':10}" + "".join(f"{'H='+str(H):>9}" for H in horizons)
          + f"{'delta':>9}")
    deltas = []
    for season in SEASONS:
        try:
            r = run_season(season, horizons)
        except Exception as exc:  # noqa: BLE001
            print(f"  {season:10} failed: {exc}")
            continue
        if len(r) < len(horizons):
            continue
        d = r[horizons[-1]] - r[horizons[0]]
        deltas.append(d)
        print(f"  {season:10}" + "".join(f"{r[H]:9.0f}" for H in horizons)
              + f"{d:+9.0f}", flush=True)
    if deltas:
        se = st.stdev(deltas)/(len(deltas)**0.5) if len(deltas) > 1 else 0.0
        print(f"\n  mean {st.mean(deltas):+.1f} points over {LAST-FIRST+1} gameweeks "
              f"(se {se:.1f}), better in {sum(1 for x in deltas if x>0)}/{len(deltas)} seasons")


def _as_squad(plan, g, table):
    players = [table[p] for p in plan.squads[g] if p in table]
    starters = [p for p in plan.starters[g] if p in table]
    return opt.Squad(players=players, starters=starters,
                     captain=plan.captains[g], vice=plan.captains[g],
                     lam=0.0, cost=0.0)


if __name__ == "__main__":
    run()


def run_ft(values=(0.0, 0.75, 1.5, 2.5), H: int = 4) -> None:
    """What is it worth to end the horizon still holding a free transfer?

    A finite horizon has an edge, and at that edge the model has no reason to keep
    anything: a transfer unspent in the last modelled week is worth nothing to it,
    so it spends everything by then. A terminal value is the correction for that,
    and it is the same number the public solver carries as `ft_value`.

    This is the question that was asked once before against a single-week solver,
    where it could only be answered wrongly.
    """
    import statistics as st

    print(f"terminal value on free transfers held, H={H}, GW{FIRST}-{LAST}\n")
    print(f"  {'season':10}" + "".join(f"{'v='+str(v):>9}" for v in values))
    rows_out = {v: [] for v in values}
    for season in SEASONS:
        line = f"  {season:10}"
        for v in values:
            try:
                r = run_season(season, (H,), ft_value=v)
                pts = r.get(H, float("nan"))
            except Exception:  # noqa: BLE001
                pts = float("nan")
            rows_out[v].append(pts)
            line += f"{pts:9.0f}"
        print(line, flush=True)

    base = rows_out[values[0]]
    print("\n  paired against v=0:")
    for v in values[1:]:
        d = [b - a for a, b in zip(base, rows_out[v])
             if a == a and b == b]
        if not d:
            continue
        se = st.stdev(d) / (len(d) ** 0.5) if len(d) > 1 else 0.0
        print(f"    v={v:<5}{st.mean(d):+7.1f} points over {LAST-FIRST+1} gameweeks "
              f"(se {se:.1f}), better in {sum(1 for x in d if x > 0)}/{len(d)}")


def run_hits(levels=(0, 1, 2), H: int = 4) -> None:
    """Do points hits pay once the model can plan several gameweeks ahead?

    The recorded verdict is that they do not: +45 points a season on average, one
    season carrying the whole result, and an oracle control showing +259 with perfect
    foresight against +30 with this model. That was measured against a planner that
    solved one gameweek at a time, and a hit is a bet that pays back over several —
    the same reason banking a transfer measured as worthless until the horizon model
    could express it.

    Hits are charged at four points here, which the earlier version of this harness
    did not do — counting them without subtracting them is how this project once
    flattered aggressive strategies.

    Measured over four seasons, GW6-26, H=4:

        season      max 0     max 1      max 2
        2022-23      966      875/4h     815/6h
        2023-24     1082     1082/0h    1082/0h
        2024-25     1158     1135/0h    1158/0h
        2025-26     1181     1181/0h    1181/0h

        max 1: -28.5 points (se 21.5), better in 0/4
        max 2: -37.8 points (se 37.8), better in 0/4

    The shape says more than the total. Given the option, the model declines to take
    a single hit in three seasons of four; where it did take them it lost 91 points
    and then 151. Four gameweeks of foresight do not make a -4 easier to justify,
    which is what the oracle control said years of evidence ago: hits pay when your
    predictions are good enough to warrant one, and these are not.

    2024-25 differs by 23 points between the first two columns while taking no hits
    in either, which is not noise. Allowing hits lets the model *plan* one in the
    second, third or fourth week of its window; that changes what it does this week,
    and then the window slides and the hit is never taken. The option is not free
    even when unused. Solver tie-breaking was ruled out: every solve returns Optimal,
    and perturbing the objective by one part in a million leaves the answer identical.
    """
    import statistics as st

    print(f"points hits inside a {H}-gameweek horizon, GW{FIRST}-{LAST}\n")
    print(f"  {'season':10}" + "".join(f"{'max '+str(v):>10}" for v in levels))
    got = {v: [] for v in levels}
    for season in SEASONS:
        line = f"  {season:10}"
        for v in levels:
            try:
                r = run_season(season, (H,), max_hits=v)
                pts, hits = r.get(H, float("nan")), r.get(f"hits{H}", 0)
            except Exception:  # noqa: BLE001
                pts, hits = float("nan"), 0
            got[v].append(pts)
            line += f"{pts:8.0f}/{hits:<2}"
        print(line, flush=True)
    print("  (points after hits / hits taken)")

    base = got[levels[0]]
    print("\n  paired against no hits:")
    for v in levels[1:]:
        d = [b - a for a, b in zip(base, got[v]) if a == a and b == b]
        if not d:
            continue
        se = st.stdev(d) / (len(d) ** 0.5) if len(d) > 1 else 0.0
        print(f"    max {v}: {st.mean(d):+7.1f} points over {LAST-FIRST+1} gameweeks "
              f"(se {se:.1f}), better in {sum(1 for x in d if x > 0)}/{len(d)}")
