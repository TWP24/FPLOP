"""Two terms taken from a public FPL solver, measured against this model.

The solver at solioanalytics/open-fpl-solver prices things this optimiser does not:
a vice-captaincy, and bench places weighted by how often each substitute actually
comes on. Neither is exotic and both are cheap to test, so they are tested rather
than adopted or dismissed.

    ./.venv/bin/python -m calib.objective_terms
"""
from __future__ import annotations

import statistics

from fplm import optimise as opt
from calib import measure

# Keeper first, then the three outfield substitutes in listed order.
SOLVER_BENCH = [0.03, 0.21, 0.06, 0.002]


def _reset():
    opt.VICE_WEIGHT = 0.0
    opt.BENCH_SLOT_WEIGHTS = None


def run() -> None:
    arms = {"baseline": lambda: None}
    for w in (0.05, 0.1, 0.2):
        arms[f"vice {w}"] = (lambda w=w: setattr(opt, "VICE_WEIGHT", w))
    arms["bench slots"] = lambda: setattr(opt, "BENCH_SLOT_WEIGHTS", list(SOLVER_BENCH))
    arms["vice 0.1 + slots"] = lambda: (setattr(opt, "VICE_WEIGHT", 0.1),
                                        setattr(opt, "BENCH_SLOT_WEIGHTS",
                                                list(SOLVER_BENCH)))

    results = {}
    print(f"  {'arm':20}{'opt pts/mo':>12}{'top60 rho':>11}{'rho':>8}{'slope':>8}")
    for name, apply in arms.items():
        _reset()
        apply()
        try:
            r = measure.run()
        finally:
            _reset()
        results[name] = r
        print(f"  {name:20}{r['optimiser']:12.2f}{r['top60_rho']:11.4f}"
              f"{r['rho']:8.4f}{r['slope']:8.3f}")

    base = results["baseline"]["optimiser_list"]
    print("\n  paired against baseline, per month:")
    for name in arms:
        if name == "baseline":
            continue
        arm = results[name]["optimiser_list"]
        if len(arm) != len(base):
            continue
        d = [b - a for a, b in zip(base, arm)]
        se = statistics.stdev(d) / (len(d) ** 0.5) if len(d) > 1 else 0.0
        print(f"    {name:18}{statistics.mean(d):+7.2f} pts/month (se {se:.2f}), "
              f"better in {sum(1 for x in d if x > 0)}/{len(d)}")


if __name__ == "__main__":
    run()
