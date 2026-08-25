"""Head-to-head against other public FPL models, on identical rows.

Everything else in `calib/` measures this model against itself. That answers whether
a change helped, never whether the thing is any good — and the honest answer to
"is it good" has to be relative to what an FPL manager could use instead.

Two references are available without a subscription:

* **FPL's own `ep_next`**, the number the official site shows every manager.
* **OpenFPL**, an open model whose published predictions are vendored in the
  SmartPlayFPL repository together with `ep_next` and realised points, on 18,173
  player-gameweeks from 2025-26 GW1-24.

Protocol follows the one those predictions were published under, so the numbers are
comparable rather than merely adjacent: metrics are computed inside each gameweek
and then averaged, and every method is restricted to exactly the same eligible
rows. This model is rebuilt walk-forward at each gameweek from earlier gameweeks
only, so it never sees the week it is predicting.

    ./.venv/bin/python -m calib.benchmark
"""
from __future__ import annotations

import collections
import csv
import statistics
from pathlib import Path

from fplm import backtest as bt
from fplm import monthly as mo
from fplm import ratings as rt
from fplm import xp as xpmod

SEASON = "2025-26"
OPENFPL = Path("/tmp/openfpl.csv")
FIRST_GW, LAST_GW = 2, 24     # GW1 has no history for a walk-forward model


def _spearman(xs, ys):
    def rank(v):
        rk = [0.0] * len(v)
        for pos, i in enumerate(sorted(range(len(v)), key=lambda i: v[i])):
            rk[i] = pos
        return rk
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def load_reference(path: Path) -> dict:
    """(element, gw) -> {openfpl, ep_next, actual}."""
    out = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            out[(int(r["element"]), int(r["gw"]))] = {
                "openfpl": float(r["openfpl_xpts"]),
                "ep_next": float(r["ep_next"] or 0.0),
                "actual": float(r["actual_points"]),
                "minutes": float(r["minutes"] or 0.0),
            }
    return out


def run() -> None:
    ref = load_reference(OPENFPL)
    rows = bt.load_rows(Path(f"data/merged_gw_{SEASON}.csv"))
    n2i = bt.team_ids(rows)
    by_gw = collections.defaultdict(list)
    for r in rows:
        by_gw[r["gw"]].append(r)

    per_gw = collections.defaultdict(list)     # model -> [rho per gameweek]
    errs = collections.defaultdict(list)       # model -> [abs error]
    covered = 0

    for gw in range(FIRST_GW, LAST_GW + 1):
        hist = [r for r in rows if r["gw"] < gw]
        fut = by_gw.get(gw, [])
        if not hist or not fut:
            continue

        els = bt.elements_from_history(hist, gw)
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
            if (h, a) in seen:
                continue
            seen.add((h, a))
            fixtures.append({"event": gw, "team_h": h, "team_a": a,
                             "team_h_difficulty": 3, "team_a_difficulty": 3})
        for t in ({f["team_h"] for f in fixtures} | {f["team_a"] for f in fixtures}) - set(tr):
            tr[t] = rt.TeamRating(t, "", "", 1.0, 1.0, 1.0)

        month = mo.Month(0, f"gw{gw}", gw, gw)
        fake_boot = {"elements": els,
                     "teams": [{"id": t, "short_name": str(t)} for t in tr]}
        table = mo.build_table(fake_boot, fixtures, rates, tr, month)

        # Split by whether the player actually started. A model that is merely
        # better at spotting who will not play wins both metrics without being
        # better at rating the players who do.
        cols = {c: {"fplm": [], "openfpl": [], "ep_next": [], "act": []}
                for c in ("all", "starters")}
        for pid, p in table.items():
            key = (pid, gw)
            if key not in ref:
                continue
            groups = ["all"] + (["starters"] if ref[key]["minutes"] >= 60 else [])
            for c in groups:
                cols[c]["fplm"].append(p.xp)
                cols[c]["openfpl"].append(ref[key]["openfpl"])
                cols[c]["ep_next"].append(ref[key]["ep_next"])
                cols[c]["act"].append(ref[key]["actual"])
        if len(cols["all"]["fplm"]) < 20:
            continue
        covered += len(cols["all"]["fplm"])

        for c, d in cols.items():
            if len(d["fplm"]) < 20:
                continue
            for name in ("fplm", "openfpl", "ep_next"):
                rho = _spearman(d[name], d["act"])
                if rho is not None:
                    per_gw[f"{name}|{c}"].append(rho)
                errs[f"{name}|{c}"].extend(
                    abs(x - a) for x, a in zip(d[name], d["act"]))

    print(f"{SEASON} GW{FIRST_GW}-{LAST_GW}, {covered} player-gameweeks on identical rows")
    print("metrics computed within each gameweek, then averaged\n")
    for c, label in (("all", "every eligible row"),
                     ("starters", "players who reached 60 minutes")):
        print(f"  {label}")
        print(f"    {'model':10}{'Spearman':>11}{'MAE':>8}")
        for name in ("fplm", "openfpl", "ep_next"):
            k = f"{name}|{c}"
            if not per_gw[k]:
                continue
            print(f"    {name:10}{statistics.mean(per_gw[k]):11.4f}"
                  f"{statistics.mean(errs[k]):8.3f}")
        print("    paired by gameweek:")
        for other in ("openfpl", "ep_next"):
            a, b = per_gw[f"fplm|{c}"], per_gw[f"{other}|{c}"]
            if not a or not b:
                continue
            d = [x - y for x, y in zip(a, b)]
            se = statistics.stdev(d) / (len(d) ** 0.5) if len(d) > 1 else 0.0
            print(f"      fplm - {other:8} {statistics.mean(d):+.4f} rho "
                  f"(se {se:.4f}), ahead in {sum(1 for x in d if x > 0)}/{len(d)}")
        print()


if __name__ == "__main__":
    run()
