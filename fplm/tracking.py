"""Actual points against predicted, gameweek by gameweek.

Nothing else in this tool keeps a record. Every run rebuilds the plan from scratch, so
by the time a gameweek has been played the prediction that preceded it is gone and
there is nothing to score the model against.

This writes predictions down before the deadline, then joins them to what actually
happened afterwards. That gives two things the backtest cannot: whether the model is
working *now*, on this season under these rules, and whether it is drifting — a model
that was well calibrated in August and 15% optimistic by November is telling you
something a static backtest never will.

The log is append-only JSON in the repo root. A prediction is written once per gameweek
and never revised, because a prediction you are allowed to edit after the fact is not a
prediction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import api

LOG = Path(__file__).resolve().parent.parent / "predictions.json"


@dataclass
class GWRecord:
    gw: int
    predicted: float
    actual: float | None = None
    rank: int | None = None
    captain: str = ""
    chip: str | None = None

    @property
    def played(self) -> bool:
        return self.actual is not None

    @property
    def error(self) -> float | None:
        return None if self.actual is None else self.actual - self.predicted


def load() -> dict[int, GWRecord]:
    if not LOG.exists():
        return {}
    try:
        raw = json.loads(LOG.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {int(k): GWRecord(**v) for k, v in raw.items()}


def save(records: dict[int, GWRecord]) -> None:
    LOG.write_text(json.dumps(
        {str(k): v.__dict__ for k, v in sorted(records.items())}, indent=1))


def record_prediction(gw: int, predicted: float, captain: str = "",
                      chip: str | None = None) -> dict[int, GWRecord]:
    """Write down what we expect, before the gameweek is played.

    Existing predictions are never overwritten. Re-running the tool the day before a
    deadline must not quietly restate what it expected a week earlier — the whole
    point is to be held to the first answer.
    """
    recs = load()
    if gw not in recs:
        recs[gw] = GWRecord(gw=gw, predicted=round(predicted, 1), captain=captain, chip=chip)
        save(recs)
    return recs


def fill_actuals(entry_id: int, records: dict[int, GWRecord] | None = None) -> dict[int, GWRecord]:
    """Pull real gameweek scores from the manager's history and join them on."""
    recs = records if records is not None else load()
    try:
        hist = api.fetch(f"entry/{entry_id}/history", key=f"hist_{entry_id}", ttl=900)
    except Exception:  # noqa: BLE001
        return recs

    changed = False
    for row in hist.get("current", []):
        gw = row.get("event")
        if gw is None:
            continue
        pts = row.get("points")
        if gw in recs and recs[gw].actual != pts:
            recs[gw].actual = pts
            recs[gw].rank = row.get("overall_rank")
            changed = True
        elif gw not in recs and pts is not None:
            # A gameweek played before tracking started: keep the actual, but leave
            # predicted empty rather than inventing one after the fact.
            recs[gw] = GWRecord(gw=gw, predicted=0.0, actual=pts,
                                rank=row.get("overall_rank"))
            changed = True
    if changed:
        save(recs)
    return recs


def summary(records: dict[int, GWRecord]) -> dict:
    """Headline accuracy over the gameweeks that have actually been played."""
    played = [r for r in records.values() if r.played and r.predicted > 0]
    if not played:
        return {"n": 0}
    pred = sum(r.predicted for r in played)
    act = sum(r.actual for r in played)
    errs = [abs(r.error) for r in played]
    return {
        "n": len(played),
        "predicted": pred,
        "actual": act,
        "ratio": act / pred if pred else 0.0,
        "mae": sum(errs) / len(errs),
        "beat": sum(1 for r in played if r.error > 0),
    }
