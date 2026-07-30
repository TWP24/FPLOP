"""Automatic substitutions, applied the way FPL actually applies them.

Three separate places used to have their own version of this and all three were
wrong in a different way, so the rule now lives once.

What FPL does, per gameweek:

  * a starter who played no minutes is replaced by the first bench player, in bench
    order, who did play *and* whose position leaves the XI legal;
  * the bench goalkeeper only ever replaces the starting goalkeeper, and vice versa;
  * legal means exactly 1 GK, at least 3 DEF, at least 2 MID and at least 1 FWD.

The formation check is not a detail. Measured over 24 backtest months, 6.8% of
blanking starters cannot legally be replaced — a 3-4-3 losing a defender cannot bring
on a midfielder — so a substitution routine without it over-credits the bench.

The per-gameweek part is not a detail either. `simulate.py` used to sub only players
who missed the *whole month*, which is why the simulated mean sat about 3% below the
analytic expected points it was supposed to agree with.
"""
from __future__ import annotations

GK, DEF, MID, FWD = 1, 2, 3, 4
XI_MIN = {GK: 1, DEF: 3, MID: 2, FWD: 1}


def legal_swap(counts: dict[int, int], out_pos: int, in_pos: int) -> bool:
    """Would replacing a starter at `out_pos` with a bench player at `in_pos` be legal?"""
    if (out_pos == GK) != (in_pos == GK):
        return False
    if out_pos == in_pos:
        return True
    c = dict(counts)
    c[out_pos] = c.get(out_pos, 0) - 1
    c[in_pos] = c.get(in_pos, 0) + 1
    return all(c.get(p, 0) >= XI_MIN[p] for p in (GK, DEF, MID, FWD))


def apply(
    xi: list[int],
    bench_order: list[int],
    pos: dict[int, int],
    played: dict[int, bool],
) -> list[int]:
    """Return the players who actually score this gameweek, after substitutions.

    `bench_order` is the manager's chosen order; the goalkeeper's place in it is
    irrelevant because keepers only swap with keepers.
    """
    counts: dict[int, int] = {}
    for p in xi:
        counts[pos[p]] = counts.get(pos[p], 0) + 1

    avail_out = [b for b in bench_order if pos.get(b) != GK]
    avail_gk = [b for b in bench_order if pos.get(b) == GK]

    scoring = []
    for p in xi:
        if played.get(p, False):
            scoring.append(p)
            continue
        pool = avail_gk if pos[p] == GK else avail_out
        for b in pool:
            if not played.get(b, False):
                continue
            if not legal_swap(counts, pos[p], pos[b]):
                continue
            counts[pos[p]] -= 1
            counts[pos[b]] = counts.get(pos[b], 0) + 1
            pool.remove(b)
            scoring.append(b)
            break
    return scoring
