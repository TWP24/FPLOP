"""Does weighting recent gameweeks more heavily improve the model?

Every rate here is a season-to-date average: a gameweek from August counts exactly
as much as last weekend. Other public models weight recency explicitly — one
published approach splits its goal and assist rates 30% last season, 30% this
season, 40% the last six gameweeks — and form is the intuition most managers
actually run on.

The test weights each historical gameweek before it is aggregated into per-90
rates, which is the honest place to put it: recency is a claim about how to read
history, not a separate term to bolt on. Total minutes are held constant while the
weights are applied, so a player's confidence weight is unchanged and only the
composition of his rates moves — otherwise leaning on recent form would quietly
also claim more certainty about it.

`share` is the fraction of total weight placed on the last six gameweeks. At 0 the
model is unchanged; the published blend above corresponds to roughly 0.4.

Measured and rejected. Over 24 months:

    share  opt pts/mo  top60 rho     rho  ratio
      0.0      200.72     0.1382  0.4193  1.008
      0.5      203.41     0.1311  0.4361  1.032
      0.6      201.84     0.1406  0.4464  1.047
      0.7      200.50     0.1398  0.4516  1.061
      0.8      199.84     0.1173  0.4528  1.082

Paired against the current model the deltas are +2.69, +1.12, -0.22 and -0.88
points a month, every one inside a standard error, better in 13 to 15 months of
32. A coin flip.

The shape is the familiar one and worth reading carefully. Pooled rank correlation
improves monotonically and substantially, 0.4193 to 0.4528, while rho inside the
top sixty does not and squad points do not, and calibration drifts from 1.008 to
1.082. Recency sharpens the ordering of the whole pool — mostly among players the
optimiser never buys — and leaves the region it does buy from untouched. That is
the same diagnosis this project has recorded repeatedly, now reproduced against an
idea taken from someone else's published model.

A first version of this harness reported +5.09 points a month at share 0.6 and was
wrong: it scaled `starts` along with the rate fields, and games played is taken from
the most-started player, so the weighting was quietly moving the minutes model
rather than the rates. The gain was that artefact. Hence the note on SCALED below.

Nothing to run early in a season, incidentally: with fewer than six gameweeks
played there is no older history to weight against, and the wrapper falls through.

    ./.venv/bin/python -m calib.recency
"""
from __future__ import annotations

import statistics

from fplm import backtest as bt
from calib import measure

WINDOW = 6
# `starts` is deliberately absent. It feeds the minutes model, where games played is
# taken from the most-started player, so scaling it would distort start rates as a
# side effect and confound the thing being measured. Minutes are scaled because they
# are the per-90 denominator and must move with the numerators, and the normalisation
# below puts the season total back exactly where it was.
SCALED = ("minutes", "xg", "xa", "xgc", "defcon",
          "saves", "bonus", "points", "yellow")

_original = bt.elements_from_history


def weighted(share: float):
    """Wrap the aggregator so recent gameweeks carry `share` of the weight.

    A share of 1 would divide by zero and mean "discard everything older", which
    is a different model rather than a weighting of this one, so it falls through
    to the unweighted aggregator.
    """
    def wrapper(history, upto_gw):
        if share <= 0 or share >= 1.0:
            return _original(history, upto_gw)
        latest = max((r["gw"] for r in history), default=0)
        cut = latest - WINDOW + 1
        recent = [r for r in history if r["gw"] >= cut]
        older = [r for r in history if r["gw"] < cut]
        mr = sum(r["minutes"] for r in recent)
        mo = sum(r["minutes"] for r in older)
        if not recent or not older or mr <= 0 or mo <= 0:
            return _original(history, upto_gw)

        # Weight recent rows so they hold `share` of the minutes-weighted mass,
        # then rescale everything so total minutes are exactly as they were.
        w_recent = (share * mo) / ((1.0 - share) * mr)
        norm = (mr + mo) / (w_recent * mr + mo)
        out = []
        for r in history:
            w = (w_recent if r["gw"] >= cut else 1.0) * norm
            q = dict(r)
            for k in SCALED:
                if k in q and isinstance(q[k], (int, float)):
                    q[k] = q[k] * w
            out.append(q)
        return _original(out, upto_gw)
    return wrapper


def run() -> None:
    print("share = weight on the last six gameweeks; 0.0 is the current model\n")
    print(f"  {'share':>6}{'opt pts/mo':>12}{'top60 rho':>11}{'rho':>8}"
          f"{'ratio':>7}{'slope':>7}")
    results = {}
    for share in (0.0, 0.5, 0.6, 0.7, 0.85):
        bt.elements_from_history = weighted(share)
        try:
            r = measure.run()
        finally:
            bt.elements_from_history = _original
        results[share] = r
        print(f"  {share:6.1f}{r['optimiser']:12.2f}{r['top60_rho']:11.4f}"
              f"{r['rho']:8.4f}{r['ratio']:7.3f}{r['slope']:7.3f}")

    base = results[0.0]["optimiser_list"]
    print("\n  paired against the current model, per month:")
    for share in (0.5, 0.6, 0.7, 0.85):
        arm = results[share]["optimiser_list"]
        if len(arm) != len(base):
            continue
        d = [b - a for a, b in zip(base, arm)]
        se = statistics.stdev(d) / (len(d) ** 0.5) if len(d) > 1 else 0.0
        print(f"    share {share:.1f}: {statistics.mean(d):+7.2f} pts/month "
              f"(se {se:.2f}), better in {sum(1 for x in d if x > 0)}/{len(d)}")


if __name__ == "__main__":
    run()
