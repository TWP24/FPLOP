"""Early-season regime check: predict from GW1 alone, score against GW2-6.

`calib/measure.py` starts three months into a season and therefore cannot see the
first weeks at all. That blind spot hid a real defect: FPL serves per-90 statistics
for the current season only, so at the GW1 rollover every rate resets, and
`_positional_means` needed 450 minutes per player before it would report anything.
For the first weeks it reported zero and the model shrank every rate to nothing,
forecasting 0.50 points per match for players who went on to score 3.59.

This once predicted with `pp90` times the minutes share, a stand-in for the model
rather than its expected points. The stand-in runs cold where the model does not,
and reading its level ratio as the model's calibration produced a confident claim
that August needs a correction it does not need. It now builds the same table the
tool builds, through fixtures and team ratings, so a ratio here means what it says.

Run this in August. Rank correlation will not catch it — the broken arm scores a
*higher* rho, because collapsing every rate to a common mean leaves a tidy ordering
by position and minutes. Watch the level ratio and MAE instead.

    ./.venv/bin/python -m calib.early_season
"""
import collections
import statistics
from pathlib import Path

from fplm import backtest as bt
from fplm import monthly as mo
from fplm import ratings as rt
from fplm import xp as xpmod

SEASON = "2025-26"
SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")
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


def _table_for(els, rows, n2i, gws):
    """The model's own expected points over `gws`, from GW1 data only."""
    rates = xpmod.build_rates({"elements": els})
    hist = [r for r in rows if r["gw"] == 1]
    tr = bt.ratings_from_results(hist, n2i)
    if not tr:
        return None
    fixtures, seen = [], set()
    for r in rows:
        if r["gw"] not in gws:
            continue
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
    return mo.build_table(boot, fixtures, rates, tr,
                          mo.Month(0, "early", min(gws), max(gws)))


def run(season: str = SEASON) -> None:
    rows = bt.load_rows(Path(f"data/merged_gw_{season}.csv"))
    n2i = bt.team_ids(rows)
    els = bt.elements_from_history([r for r in rows if r["gw"] == 1], 1)
    for e in els:
        e["team"] = n2i.get(e["team_name"], 0)
    els = [e for e in els if e["team"]]
    gws = set(range(2, 7))

    actual = collections.defaultdict(float)
    for r in rows:
        if r["gw"] in gws:
            actual[r["pid"]] += r["points"]

    print(f"{season}: predicting GW2-6 from GW1, on the model's own expected points\n")
    for label, patched in (("BROKEN: hard 450 floor", _means_hard_floor),
                           ("shipped: floor falls back", None)):
        original = xpmod._positional_means
        if patched:
            xpmod._positional_means = patched
        try:
            table = _table_for(els, rows, n2i, gws)
        finally:
            xpmod._positional_means = original
        if table is None:
            print(f"  {label:26} could not build a table")
            continue

        pids = [p for p in table if p in actual]
        xs = [table[p].xp for p in pids]
        ys = [actual[p] for p in pids]
        top = sorted(range(len(xs)), key=lambda i: -xs[i])[:60]
        tp = sum(xs[i] for i in top)
        ta = sum(ys[i] for i in top)
        print(f"  {label:26} n={len(xs):4}  rho {_spearman(xs, ys):.4f}  "
              f"MAE {statistics.mean(abs(x - y) for x, y in zip(xs, ys)):5.2f}")
        print(f"  {'':26} top-60 predicted {tp:6.0f} vs realised {ta:6.0f}"
              f"   ratio {tp / ta if ta else 0:.2f}")


def run_all() -> None:
    for season in SEASONS:
        try:
            run(season)
        except Exception as exc:  # noqa: BLE001
            print(f"{season}: failed — {exc}\n")


if __name__ == "__main__":
    run_all()
