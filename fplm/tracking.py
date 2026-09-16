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
class SquadState:
    """What you actually hold going into the next deadline, and what it is worth.

    Everything the optimiser needs to make a legal transfer and nothing it has to
    be told: the fifteen (with any transfer already made this week applied), the
    bank, and what each held player would fetch. FPL does not return your selling
    prices on any public endpoint, so they are rebuilt from the transfer history
    the way FPL computes them — purchase price plus half of any rise, rounded down
    to the nearest 0.1 — and a player never transferred in was bought at his
    season-opening price, which `cost_change_start` recovers.
    """

    players: set[int]
    bank: float                     # millions, after any transfers already made
    sell: dict[int, float]          # pid -> what selling him now would return
    pending: int = 0                # transfers already made for the next deadline
    note: str = ""

    @property
    def budget(self) -> float:
        """Bank plus the selling value of the fifteen: the most a squad can cost."""
        return round(self.bank + sum(self.sell.get(p, 0.0) for p in self.players), 1)


def sell_price(purchase: float, current: float) -> float:
    """FPL returns your purchase price plus half the profit, rounded down to 0.1."""
    if current <= purchase:
        return current
    profit = round(current - purchase, 1)
    return round(purchase + int(profit * 10 // 2) / 10, 1)


def squad_state(entry_id: int, next_gw: int, boot: dict) -> SquadState | None:
    """Rebuild the live squad, bank and selling prices from the public API.

    The fifteen are the last published picks — FPL only serves a gameweek's picks
    once its deadline has passed — with this week's transfers, which the transfers
    endpoint does publish as they are made, applied on top. Without that step the
    plan spends a transfer you have already spent, on a squad you no longer hold.

    A free hit in the last gameweek is the one case where the last published picks
    are not the squad you hold: they are the one-week team, and the real fifteen
    are the picks from the week before. Handled, because a plan built on a free-hit
    squad would sell eleven players nobody owns.

    Returns None if any of it cannot be read; the caller decides whether that is
    fatal. Before GW1 there are no picks to read and that is not an error.
    """
    if next_gw <= 1:
        return None
    try:
        hist = api.fetch(f"entry/{entry_id}/history", key=f"hist_{entry_id}", ttl=900)
        transfers = api.fetch(f"entry/{entry_id}/transfers",
                              key=f"transfers_{entry_id}", ttl=600)
    except Exception:  # noqa: BLE001
        return None

    chips = {c.get("event"): c.get("name") for c in hist.get("chips", [])}
    last = next_gw - 1
    base_gw = last - 1 if chips.get(last) == "freehit" and last > 1 else last
    try:
        picks = api.entry_picks(entry_id, base_gw)
    except Exception:  # noqa: BLE001
        return None
    players = {p["element"] for p in picks.get("picks", [])}
    if len(players) != 15:
        return None
    bank = float(picks.get("entry_history", {}).get("bank") or 0) / 10.0

    now_cost = {e["id"]: e["now_cost"] for e in boot["elements"]}
    change = {e["id"]: e.get("cost_change_start") or 0 for e in boot["elements"]}

    # Purchase price is the last price paid for a player still held. Walk the
    # transfers in time order so a player sold and bought back carries the later
    # price. Transfers made under a free hit are reverted by FPL, so they neither
    # move the squad nor set a purchase price.
    bought: dict[int, int] = {}
    pending = 0
    for t in sorted(transfers, key=lambda t: (t.get("event", 0), t.get("time", ""))):
        ev = t.get("event")
        if chips.get(ev) == "freehit":
            continue
        if ev is not None and ev > base_gw:
            # Made since the last published picks, so apply it to the squad. The
            # bank has already moved in FPL's ledger for these, but the picks were
            # taken before they happened, so it is moved here too.
            players.discard(t["element_out"])
            players.add(t["element_in"])
            bank += (t.get("element_out_cost", 0) - t.get("element_in_cost", 0)) / 10.0
            if ev == next_gw:
                pending += 1
        bought[t["element_in"]] = t.get("element_in_cost") or now_cost.get(t["element_in"], 0)

    sell: dict[int, float] = {}
    for pid in players:
        now = now_cost.get(pid)
        if now is None:
            continue
        paid = bought.get(pid, now - change.get(pid, 0))
        sell[pid] = sell_price(paid / 10.0, now / 10.0)

    if len(players) != 15:
        return None
    note = f"{pending} transfer(s) already made for GW{next_gw}" if pending else ""
    return SquadState(players=players, bank=round(bank, 1), sell=sell,
                      pending=pending, note=note)


@dataclass
class GWRecord:
    gw: int
    predicted: float
    actual: float | None = None
    rank: int | None = None
    captain: str = ""
    chip: str | None = None
    model: str = "fplm"   # which provider produced this forecast
    note: str = ""        # why this entry was corrected, if it ever was

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
                      chip: str | None = None, model: str = "fplm") -> dict[int, GWRecord]:
    """Write down what we expect, before the gameweek is played.

    Existing predictions are never overwritten. Re-running the tool the day before a
    deadline must not quietly restate what it expected a week earlier — the whole
    point is to be held to the first answer.
    """
    recs = load()
    if gw not in recs:
        recs[gw] = GWRecord(gw=gw, predicted=round(predicted, 1), captain=captain,
                            chip=chip, model=model)
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


def free_transfers(entry_id: int, next_gw: int) -> int | None:
    """Work out how many free transfers are banked, from what was actually spent.

    FPL publishes no endpoint for this, and the plan's advice depends on it — at one
    the recommendation is a single move, at two it reshapes the squad. Rather than
    leaving it as a number to remember, it is rebuilt from the transfer history: one
    a week, bankable to five, spent as they are made.

    A wildcard or free hit lifts the limit for its week without consuming the bank,
    so those gameweeks are skipped. Returns None if the history cannot be read, and
    the caller keeps its default rather than guessing.
    """
    try:
        hist = api.fetch(f"entry/{entry_id}/history", key=f"hist_{entry_id}", ttl=900)
    except Exception:  # noqa: BLE001
        return None

    unlimited = {c.get("event") for c in hist.get("chips", [])
                 if c.get("name") in ("wildcard", "freehit")}
    # Counting starts at GW2. The first gameweek's squad is assembled freely before
    # its deadline, so nothing is banked out of it and everyone begins GW2 with one.
    free = 1
    for row in sorted(hist.get("current", []), key=lambda r: r.get("event", 0)):
        gw = row.get("event")
        if gw is None or gw < 2 or gw >= next_gw:
            continue
        if gw in unlimited:
            free = min(5, free + 1)
            continue
        used = min(int(row.get("event_transfers") or 0), free)
        free = min(5, max(1, free - used + 1))
    return free


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
