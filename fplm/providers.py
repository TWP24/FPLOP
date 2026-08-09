"""Pluggable expected-points providers, so the model is a runtime choice.

There are two credible sources of xP for this tool and no way to pick between them from
the armchair. Measured on 17,622 identical player-gameweeks, Dastan is better on the
players that matter — starters rho 0.414 against this project's 0.356, MAE 0.919
against 1.272. But every lesson from this codebase says a ranking gain need not convert
into squad points: an audit once moved pooled rho by +0.10 and bought nothing, because
the region an ILP actually shops in barely changed.

So neither is hardcoded. A provider supplies a per-player expected-points map, the
optimiser and everything downstream stay identical, and `predictions.json` records which
provider produced each gameweek's forecast. After a couple of months the Actual-vs-xP
tracker answers the question with data instead of argument.

Availability differs, and the code says so rather than pretending:

* `fplm` runs anywhere the FPL API is reachable, including before a season starts.
* `dastan` needs its feature frame, which currently ends at 2025-26. It cannot predict
  2026/27 until either their pipeline gains a forward path or they publish a frame that
  includes it. `available_for` reports that honestly instead of returning silence.
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASTAN_DIR = ROOT / "vendor" / "dastan"


@dataclass
class Prediction:
    """Expected points per player id, plus where it came from."""

    xp: dict[int, float]
    provider: str
    note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.xp)


class FplmProvider:
    """This project's own model. Always available."""

    name = "fplm"
    label = "fplm (built in)"

    def available_for(self, season: str, gw: int) -> tuple[bool, str]:
        return True, "runs from the live FPL API"

    def predict(self, boot, fixtures, month, rates=None, team_ratings=None) -> Prediction:
        from . import monthly as mo
        from . import ratings as rt
        from . import xp as xpmod

        tr = team_ratings or rt.build(boot, fixtures, prior_weight=0.5)
        rr = rates or xpmod.build_rates(boot)
        table = mo.build_table(boot, fixtures, rr, tr, month)
        return Prediction({pid: p.xp for pid, p in table.items()}, self.name)


class DastanProvider:
    """The open-source SmartPlayFPL model, vendored under `vendor/dastan`.

    Two caveats are baked in rather than discovered later. The released weights predict
    at roughly 0.53 of the scale of the authors' published walk-forward numbers, which
    leaves squad selection untouched — an ILP only ranks — but corrupts anything reading
    absolute points, so `SCALE` restores them. And the frame stops at 2025-26.
    """

    name = "dastan"
    label = "Dastan (SmartPlayFPL)"
    SCALE = 1.9   # measured: my run sits at 0.528 of their published scale

    def __init__(self, repo: Path | str = DASTAN_DIR):
        self.repo = Path(repo)

    def _load(self):
        if not (self.repo / "dastan").is_dir():
            return None, None
        if str(self.repo) not in sys.path:
            sys.path.insert(0, str(self.repo))
        try:
            from dastan import data, predictor  # type: ignore

            return data.load(), predictor.Dastan()
        except Exception:  # noqa: BLE001 — missing weights or deps, reported below
            return None, None

    def available_for(self, season: str, gw: int) -> tuple[bool, str]:
        if not (self.repo / "dastan").is_dir():
            return False, f"not vendored — clone the repo into {self.repo}"
        frame, _ = self._load()
        if frame is None:
            return False, "vendored but would not import (check xgboost, scikit-learn)"
        if season not in set(frame["season"].unique()):
            newest = max(frame["season"].unique())
            return False, (f"feature frame ends at {newest}; it has no rows for "
                           f"{season}, so it cannot predict this season yet")
        if gw not in set(frame[frame.season == season]["gameweek"].unique()):
            return False, f"no rows for {season} GW{gw}"
        return True, f"{season} GW{gw} present in the feature frame"

    def predict(self, boot, fixtures, month, rates=None, team_ratings=None,
                season: str = "", code_map: dict[int, int] | None = None) -> Prediction:
        frame, model = self._load()
        if frame is None:
            return Prediction({}, self.name, "not available")

        gws = list(month.events)
        sub = frame[(frame.season == season) & (frame.gameweek.isin(gws))].copy()
        if sub.empty:
            return Prediction({}, self.name, f"no rows for {season} GW{gws}")

        out = model.predict_frame(sub)
        # One row per fixture, so a double gameweek contributes twice — summing is
        # what the authors' own evaluation does.
        agg = out.groupby("fpl_code", as_index=False)["xpts"].sum()

        cmap = code_map or {}
        xp = {}
        for _, r in agg.iterrows():
            pid = cmap.get(int(r["fpl_code"]))
            if pid is not None:
                xp[pid] = float(r["xpts"]) * self.SCALE
        return Prediction(xp, self.name, f"{len(xp)} players, scale x{self.SCALE}")


PROVIDERS = {p.name: p for p in (FplmProvider(), DastanProvider())}


def code_map_from(path: Path) -> dict[int, int]:
    """FPL's stable player `code` to this season's `element` id."""
    if not path.exists():
        return {}
    return {int(x["code"]): int(x["id"]) for x in csv.DictReader(open(path))}


def resolve(name: str, season: str, gw: int):
    """Pick a provider, falling back to the built-in one with the reason stated."""
    prov = PROVIDERS.get(name, PROVIDERS["fplm"])
    ok, why = prov.available_for(season, gw)
    if ok:
        return prov, why
    fallback = PROVIDERS["fplm"]
    return fallback, f"{prov.name} unavailable ({why}); using {fallback.name}"
