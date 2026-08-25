"""Early-season regime check: predict from GW1 alone, score against GW2-6.

`calib/measure.py` starts three months into a season and therefore cannot see the
first weeks at all. That blind spot hid a real defect: FPL serves per-90 statistics
for the current season only, so at the GW1 rollover every rate resets, and
`_positional_means` needed 450 minutes per player before it would report anything.
For the first weeks it reported zero and the model shrank every rate to nothing,
forecasting 0.50 points per match for players who went on to score 3.59.

Note what this does and does not measure. The prediction here is `pp90` times the
minutes share, a proxy for the model rather than its expected points, so the level
ratio it reports is not the model's calibration and must not be read as one. Doing
exactly that produced a confident claim that the model runs cold in August; measured
properly in `regime.py`, on the model's own xP, it runs slightly hot like everywhere
else. Use this for detecting collapse, not for judging level.

Run this in August. Rank correlation will not catch it — the broken arm scores a
*higher* rho, because collapsing every rate to a common mean leaves a tidy ordering
by position and minutes. Watch the level ratio and MAE instead.

    ./.venv/bin/python -m calib.early_season
"""
import collections
import statistics
from pathlib import Path

from fplm import backtest as bt
from fplm import xp as xpmod

SEASON = "2025-26"
POSITIONS = (1, 2, 3, 4)
RATE_KEYS = ("xg90", "xa90", "defcon90", "saves90", "bonus90",
             "yellow90", "xgc90", "pp90", "w")


def _means_hard_floor(elements):
    """The pre-fix behaviour: a hard 450-minute floor with no fallback."""
    acc = {pos: dict.fromkeys(RATE_KEYS, 0.0) for pos in POSITIONS}
    for e in elements:
        m = e["minutes"]
        if m < 450:
            continue
        a = acc[e["element_type"]]
        a["w"] += m
        a["xg90"] += float(e["expected_goals_per_90"]) * m
        a["xa90"] += float(e["expected_assists_per_90"]) * m
        a["defcon90"] += float(e["defensive_contribution_per_90"]) * m
        a["saves90"] += float(e["saves_per_90"]) * m
        a["bonus90"] += (e["bonus"] / (m / 90.0)) * m
        a["yellow90"] += (e["yellow_cards"] / (m / 90.0)) * m
        a["xgc90"] += float(e["expected_goals_conceded_per_90"]) * m
        a["pp90"] += (e.get("total_points", 0) / (m / 90.0)) * m
    return {pos: {k: v / (a["w"] or 1.0) for k, v in a.items() if k != "w"}
            for pos, a in acc.items()}


def _spearman(xs, ys):
    def rank(v):
        rk = [0.0] * len(v)
        for pos, i in enumerate(sorted(range(len(v)), key=lambda i: v[i])):
            rk[i] = pos
        return rk
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def run(season: str = SEASON) -> None:
    rows = bt.load_rows(Path(f"data/merged_gw_{season}.csv"))
    els = bt.elements_from_history([r for r in rows if r["gw"] == 1], 1)

    actual = collections.defaultdict(lambda: [0.0, 0])
    for r in rows:
        if 2 <= r["gw"] <= 6 and r["minutes"] > 0:
            a = actual[r["pid"]]
            a[0] += r["points"]
            a[1] += 1

    print(f"{season}: predicting from GW1, scoring on GW2-6\n")
    for label, patched in (("BROKEN: hard 450 floor", _means_hard_floor),
                           ("shipped: floor falls back", None)):
        original = xpmod._positional_means
        if patched:
            xpmod._positional_means = patched
        try:
            rates = xpmod.build_rates({"elements": els})
        finally:
            xpmod._positional_means = original

        xs, ys = [], []
        for pid, r in rates.items():
            a = actual.get(pid)
            if not a or a[1] < 2:
                continue
            xs.append(r.pp90 * (r.exp_minutes / 90.0))
            ys.append(a[0] / a[1])

        top = sorted(range(len(xs)), key=lambda i: -xs[i])[:60]
        print(f"  {label:26} n={len(xs):4}  rho {_spearman(xs, ys):.4f}  "
              f"level {sum(xs) / sum(ys):5.2f}x  "
              f"MAE {statistics.mean(abs(x - y) for x, y in zip(xs, ys)):5.2f}")
        print(f"  {'':26} top-60 predicted "
              f"{statistics.mean(xs[i] for i in top):.2f} vs actual "
              f"{statistics.mean(ys[i] for i in top):.2f} per match")


if __name__ == "__main__":
    run()
