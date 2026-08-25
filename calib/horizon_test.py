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


def run_season(season, horizons=(1, 4), ft_value: float = 0.0) -> dict:
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
                            free_transfers=free, max_hits_per_gw=0,
                            ft_terminal_value=ft_value, time_limit=45)
            if plan is None:
                continue
            out_ids, in_ids = plan.transfers[g]
            n = len(in_ids)
            squad = plan.squads[g]
            free = min(hz.MAX_FREE, max(1, free - n + 1))
            total += bt._actual_squad_points(
                _as_squad(plan, g, tabs[g]), actual[g], {g: actual[g]}, {g: played[g]})
            hits_taken += plan.hits[g]
        results[H] = total
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
