"""How the model's level bias changes with how much of the season it has seen.

`calibrate` corrects a measured bias: over four seasons of player-months the model
runs hot, so the displayed number is shrunk. That fit pools every month, and almost
all of them are mid-season — which is fine until August, when FPL resets its per-90
statistics at GW1 and the model is running on one gameweek of heavily shrunk rates.
There it runs *cold*, and shrinking it again pushes an already-low number lower.

This measures the ratio of predicted to realised as a function of gameweeks played,
using the same quantity the calibration is fitted on, so the two are comparable.

The answer is that there is no early-season regime to correct. Top-60 predicted over
realised comes to 1.12 at three to five gameweeks played, 1.14 at six to nine, and
1.11 in the hardest case of all — predicting GW2 from GW1 alone, which is where the
model has least to work with. The existing calibration assumes about 1.13. It is
already right, in every regime that can be measured.

Worth recording why this was built, because the premise was wrong. `early_season.py`
reports a level ratio near 0.74 and that was read as the model running cold in
August. It does not measure the model's expected points: it uses `pp90` times the
minutes share, a proxy standing in for the whole component model. The proxy runs
cold; the model does not. Two harnesses, two different quantities, and the number
that looked like a bias was an artefact of comparing them.

Season-to-season spread at GW2 is 0.83, 1.44, 1.00, 1.16 — four observations with a
range wider than any correction worth making, so a regime-specific adjustment here
would be fitting noise.

    ./.venv/bin/python -m calib.regime
"""
from __future__ import annotations

import collections
import statistics
from pathlib import Path

from fplm import backtest as bt
from fplm import monthly as mo
from fplm import ratings as rt
from fplm import xp as xpmod

SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")


def measure() -> dict[int, list[float]]:
    """Predicted-over-realised for each month, keyed by gameweeks already played."""
    by_played: dict[int, list[float]] = collections.defaultdict(list)
    for season in SEASONS:
        rows = bt.load_rows(Path(f"data/merged_gw_{season}.csv"))
        months = bt.month_buckets(rows)
        n2i = bt.team_ids(rows)
        for m in months:
            hist = [r for r in rows if r["gw"] < m.start_event]
            fut = [r for r in rows if m.start_event <= r["gw"] <= m.stop_event]
            if not hist or not fut:
                continue
            played = m.start_event - 1
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
            boot = {"elements": els,
                    "teams": [{"id": t, "short_name": str(t)} for t in tr]}
            table = mo.build_table(boot, fixtures, rates, tr, m)
            if len(table) < 200:
                continue
            actual: dict[int, float] = collections.defaultdict(float)
            for r in fut:
                actual[r["pid"]] += r["points"]
            # The region a reader actually looks at: the top of the ranking.
            top = sorted(table, key=lambda p: -table[p].xp)[:60]
            pred = sum(table[p].xp for p in top)
            real = sum(actual.get(p, 0.0) for p in top)
            if real > 0:
                by_played[played].append(pred / real)
    return by_played


def run() -> None:
    by_played = measure()
    print("predicted / realised for the top 60, by gameweeks already played")
    print("above 1.00 the model runs hot and should be shrunk; below it runs cold\n")
    print(f"  {'GWs played':>11}{'months':>8}{'ratio':>8}")
    buckets = {"1-2": range(1, 3), "3-5": range(3, 6), "6-9": range(6, 10),
               "10-19": range(10, 20), "20+": range(20, 39)}
    for label, rng in buckets.items():
        vals = [v for k, vs in by_played.items() if k in rng for v in vs]
        if vals:
            print(f"  {label:>11}{len(vals):8}{statistics.mean(vals):8.2f}")
    allv = [v for vs in by_played.values() for v in vs]
    print(f"\n  pooled: {statistics.mean(allv):.2f} over {len(allv)} months")


if __name__ == "__main__":
    run()
