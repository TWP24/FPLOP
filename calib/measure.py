"""Pre-registered calibration harness.

Reports, on every change, the four numbers the audit said matter — and the one that
matters most is not overall rho.

  1. optimiser points/month, paired per month across 24 months (PRIMARY)
  2. rho restricted to the top 60 by predicted xP — the only region the ILP shops in
  3. calibration slope and realisation ratio, overall and by position at the top
  4. pooled rho, reported but demoted: two agents moved it by +0.10 and bought nothing

Usage:
    python calib/measure.py              # measure current working tree
    python calib/measure.py --placebo 6  # information-free control, N seeds
"""
from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplm import backtest as bt  # noqa: E402
from fplm import optimise as opt  # noqa: E402
from fplm import ratings as rt  # noqa: E402
from fplm import xp as xpmod  # noqa: E402
from fplm.monthly import PlayerMonth  # noqa: E402

SEASONS = ["2023-24", "2024-25", "2025-26"]
POS_NAME = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _month_context(rows, months, n2i, m):
    """Everything needed to predict one month, using only earlier gameweeks."""
    hist = [r for r in rows if r["gw"] < m.start_event]
    fut = [r for r in rows if m.start_event <= r["gw"] <= m.stop_event]
    if not hist or not fut:
        return None

    els = bt.elements_from_history(hist, m.start_event)
    for e in els:
        e["team"] = n2i.get(e["team_name"], 0)
    els = [e for e in els if e["team"]]
    if len(els) < 100:
        return None

    tr = bt.ratings_from_results(hist, n2i)
    if not tr:
        return None
    rates = xpmod.build_rates({"elements": els})

    fixtures, seen = [], set()
    for r in fut:
        tid = n2i.get(r["team_name"])
        if tid is None:
            continue
        h, a = (tid, r["opponent"]) if r["home"] else (r["opponent"], tid)
        if (r["gw"], h, a) in seen:
            continue
        seen.add((r["gw"], h, a))
        fixtures.append({"event": r["gw"], "team_h": h, "team_a": a,
                         "team_h_difficulty": 3, "team_a_difficulty": 3})
    for t in ({f["team_h"] for f in fixtures} | {f["team_a"] for f in fixtures}) - set(tr):
        tr[t] = rt.TeamRating(t, "", "", 1.0, 1.0, 1.0)

    allfx, s2 = [], set()
    for r in rows:
        tid = n2i.get(r["team_name"])
        if tid is None:
            continue
        h, a = (tid, r["opponent"]) if r["home"] else (r["opponent"], tid)
        if (r["gw"], h, a) in s2:
            continue
        s2.add((r["gw"], h, a))
        allfx.append({"event": r["gw"], "team_h": h, "team_a": a,
                      "team_h_difficulty": 3, "team_a_difficulty": 3})
    af, ag = xpmod.team_baseline_lambdas(tr, allfx)

    fbt = defaultdict(list)
    for f in fixtures:
        fbt[f["team_h"]].append(f)
        fbt[f["team_a"]].append(f)

    actual, pmin = defaultdict(float), defaultdict(float)
    for r in fut:
        actual[r["pid"]] += r["points"]
    for r in hist:
        pmin[r["pid"]] += r["minutes"]

    # Per-gameweek ledger so the scorer can apply real automatic substitutions.
    gw_pts: dict[int, dict[int, float]] = defaultdict(dict)
    gw_played: dict[int, dict[int, bool]] = defaultdict(dict)
    for r in fut:
        gw_pts[r["gw"]][r["pid"]] = r["points"]
        gw_played[r["gw"]][r["pid"]] = r["minutes"] > 0

    return rates, tr, af, ag, fbt, actual, pmin, dict(gw_pts), dict(gw_played)


def run(jitter: float = 0.0, seed: int = 0) -> dict:
    """Measure the current model. `jitter` injects information-free noise as a control."""
    rnd = random.Random(seed)
    rows_by_month = []

    for season in SEASONS:
        rows = bt.load_rows(Path(f"data/merged_gw_{season}.csv"))
        months = bt.month_buckets(rows)
        n2i = bt.team_ids(rows)
        for m in months[2:]:
            ctx = _month_context(rows, months, n2i, m)
            if ctx is None:
                continue
            rates, tr, af, ag, fbt, actual, pmin, gwp, gwpl = ctx

            table: dict[int, PlayerMonth] = {}
            for pid, r in rates.items():
                if r.team not in tr or pmin[pid] < 270:
                    continue
                fxs = [xpmod.fixture_xp(r, f, tr, af, ag) for f in fbt.get(r.team, [])]
                if not fxs:
                    continue
                pred = sum(f.xp for f in fxs)
                if jitter:
                    pred *= math.exp(rnd.gauss(0, jitter) - 0.5 * jitter**2)
                table[pid] = PlayerMonth(
                    pid=pid, name=r.name, team=r.team, team_name=str(r.team), pos=r.pos,
                    price=r.price, selected_by=r.selected_by, xp=pred,
                    var=sum(f.var for f in fxs), n_fixtures=len(fxs),
                    exp_minutes=r.exp_minutes, fixtures=fxs, flags=r.flags,
                )
            if len(table) < 60:
                continue
            rows_by_month.append((table, actual, gwp, gwpl))

    return _score(rows_by_month)


def _score(months) -> dict:
    allp, alla, allpos = [], [], []
    rhos, top_rhos, opt_pts = [], [], []
    pos_top = defaultdict(lambda: [0.0, 0.0])
    pos_all = defaultdict(lambda: [0.0, 0.0])

    for table, actual, gwp, gwpl in months:
        pids = list(table)
        pred = [table[p].xp for p in pids]
        act = [actual.get(p, 0.0) for p in pids]
        allp.extend(pred)
        alla.extend(act)
        allpos.extend(table[p].pos for p in pids)
        rhos.append(bt.spearman(pred, act))

        # Top 60 by prediction — the region the optimiser actually buys from.
        top = sorted(pids, key=lambda p: -table[p].xp)[:60]
        if len(top) >= 20:
            top_rhos.append(bt.spearman([table[p].xp for p in top],
                                        [actual.get(p, 0.0) for p in top]))
        for p in top[:20]:
            pos_top[table[p].pos][0] += table[p].xp
            pos_top[table[p].pos][1] += actual.get(p, 0.0)
        # Whole-pool realisation separates a genuine positional bias from simple
        # regression to the mean at the top of the ranking.
        for p in pids:
            pos_all[table[p].pos][0] += table[p].xp
            pos_all[table[p].pos][1] += actual.get(p, 0.0)

        squad = opt.solve(table, lam=0.0, cons=opt.Constraints(min_expected_minutes=20))
        if squad:
            opt_pts.append(bt._actual_squad_points(squad, actual, gwp, gwpl))

    n = len(allp)
    mp, ma = sum(allp) / n, sum(alla) / n
    b = (sum((allp[i] - mp) * (alla[i] - ma) for i in range(n))
         / sum((x - mp) ** 2 for x in allp))

    return {
        "n_months": len(months),
        "optimiser": statistics.mean(opt_pts) if opt_pts else float("nan"),
        "optimiser_list": opt_pts,
        "top60_rho": statistics.mean(top_rhos) if top_rhos else float("nan"),
        "rho": statistics.mean(rhos),
        "ratio": ma / mp,
        "slope": b,
        "pos_ratio": {POS_NAME[k]: (v[1] / v[0] if v[0] else float("nan"))
                      for k, v in sorted(pos_top.items())},
        "pos_all": {POS_NAME[k]: (v[1] / v[0] if v[0] else float("nan"))
                    for k, v in sorted(pos_all.items())},
    }


def report(tag: str, r: dict) -> None:
    pr = "  ".join(f"{k} {v:.2f}" for k, v in r["pos_ratio"].items())
    print(f"{tag:<22} opt {r['optimiser']:7.2f} | top60rho {r['top60_rho']:.4f} | "
          f"rho {r['rho']:.4f} | ratio {r['ratio']:.3f} | slope {r['slope']:.3f}")
    print(f"{'':<22} top-20 realisation:  {pr}")
    pa = "  ".join(f"{k} {v:.2f}" for k, v in r["pos_all"].items())
    print(f"{'':<22} full-pool realisation:  {pa}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--placebo", type=int, default=0,
                    help="Run N information-free jitter seeds as a noise control.")
    ap.add_argument("--jitter", type=float, default=0.24)
    ap.add_argument("--tag", default="current")
    a = ap.parse_args()

    base = run()
    report(a.tag, base)

    if a.placebo:
        print()
        vals = []
        for s in range(1, a.placebo + 1):
            p = run(jitter=a.jitter, seed=s)
            vals.append(p["optimiser"])
            print(f"  placebo seed {s}: opt {p['optimiser']:.2f} "
                  f"({p['optimiser'] - base['optimiser']:+.2f})")
        d = [v - base["optimiser"] for v in vals]
        print(f"\n  placebo mean {statistics.mean(d):+.2f}  sd {statistics.pstdev(d):.2f}"
              f"  -> any real gain must clearly beat this")
