"""Probability of winning a month, which is the thing the prize is paid on.

Every other harness here scores expected points. A monthly league does not pay for
expected points; it pays whoever finishes top of a field. Those objectives come
apart exactly where the money is — a squad that maximises the mean can be a worse
bet than one that trails it slightly and spreads wider, once you have to beat
forty-eight other people rather than an average.

Each month is simulated once, a field of rivals is solved under their own noisy
beliefs, and candidate squads are scored against the same universe so the
comparison is paired rather than two separate draws.

    ./.venv/bin/python -m calib.pwin
"""
from __future__ import annotations

import collections
import statistics
from pathlib import Path

from fplm import backtest as bt
from fplm import monthly as mo
from fplm import optimise as opt
from fplm import ratings as rt
from fplm import xp as xpmod

SEASONS = ("2023-24", "2024-25", "2025-26")
RIVALS = 48
N_SIMS = 3000


def month_contexts(season: str):
    """Everything needed to simulate one month, using only earlier gameweeks."""
    rows = bt.load_rows(Path(f"data/merged_gw_{season}.csv"))
    months = bt.month_buckets(rows)
    n2i = bt.team_ids(rows)
    for m in months[2:]:
        hist = [r for r in rows if r["gw"] < m.start_event]
        fut = [r for r in rows if m.start_event <= r["gw"] <= m.stop_event]
        if not hist or not fut:
            continue
        els = bt.elements_from_history(hist, m.start_event)
        for e in els:
            e["team"] = n2i.get(e["team_name"], 0)
        els = [e for e in els if e["team"]]
        if len(els) < 100:
            continue
        rates = xpmod.build_rates({"elements": els})
        tr = bt.ratings_from_results(hist, n2i)
        if not tr:
            continue
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
        boot = {"elements": els, "teams": [{"id": t, "short_name": str(t)} for t in tr]}
        table = mo.build_table(boot, fixtures, rates, tr, m)
        if len(table) < 200:
            continue
        yield season, m, boot, fixtures, table, rates, tr


def run(variants, label: str = "") -> None:
    from fplm.simulate import MonthSimulator

    res = collections.defaultdict(list)
    n = 0
    for season, m, boot, fixtures, table, rates, tr in (
            c for s in SEASONS for c in month_contexts(s)):
        sim = MonthSimulator(boot, fixtures, table, rates, tr, m, n_sims=N_SIMS)
        cons = opt.Constraints(min_expected_minutes=20)
        field = sim.build_field(RIVALS, cons)
        for name, apply in variants.items():
            apply()
            squad = opt.solve(table, lam=opt.suggested_lam(RIVALS), cons=cons)
            if squad is None:
                continue
            res[name].append(sim.evaluate(squad, field).p_win)
        n += 1

    print(f"{label}  {n} months, {RIVALS} rivals, {N_SIMS} sims each\n")
    print(f"  {'variant':22}{'mean P(win)':>13}")
    for name, v in res.items():
        if v:
            print(f"  {name:22}{statistics.mean(v) * 100:12.2f}%")
    keys = list(res)
    if len(keys) > 1 and all(len(res[k]) == len(res[keys[0]]) for k in keys):
        base = res[keys[0]]
        print("\n  paired against the first:")
        for k in keys[1:]:
            d = [b - a for a, b in zip(base, res[k])]
            se = statistics.stdev(d) / (len(d) ** 0.5) if len(d) > 1 else 0.0
            print(f"    {k:20}{statistics.mean(d) * 100:+7.2f}pp (se {se * 100:.2f}), "
                  f"better in {sum(1 for x in d if x > 0)}/{len(d)}")


def _set_mult(v):
    def apply():
        opt.CAPTAIN_DIFF_MULT = v
    return apply


if __name__ == "__main__":
    run({f"captain mult {v}": _set_mult(v) for v in (0.0, 1.0, 3.0)},
        "captain differential multiplier")
