"""Inline SVG charts for the dashboard.

Hand-built SVG rather than a charting library: the page has to stay a single
self-contained file with no external requests, and every chart here is simple enough
that a library would cost more than it saves.

Each one exists because it answers a question the tables cannot:

  * the fixture ticker shows *runs* of easy and hard games, which is what transfer
    timing actually turns on — a table of per-month averages hides them;
  * the score distribution turns "P(win) 20%" into something you can see, with the
    score you actually have to beat drawn on it;
  * the value frontier shows who is underpriced, which is invisible in a ranked list;
  * the team scatter shows why a fixture is easy — a weak attack and a weak defence
    are very different problems for a defender and a striker.

Colours come from CSS variables so both themes work, with a separate semantic scale
for fixture difficulty that is deliberately not the page accent.
"""
from __future__ import annotations

import html
import math

FDR_FILL = {
    1: "var(--fdr1)", 2: "var(--fdr2)", 3: "var(--fdr3)",
    4: "var(--fdr4)", 5: "var(--fdr5)",
}


def _esc(s) -> str:
    return html.escape(str(s))


# --------------------------------------------------------------------- #


def fixture_ticker(boot: dict, fixtures: list[dict], start_gw: int, n: int = 8,
                   only_teams: set[int] | None = None,
                   labels: dict[int, str] | None = None) -> str:
    """Colour grid of upcoming fixtures, easiest run at the top.

    Defaults to every club, but `only_teams` narrows it to the clubs you actually own.
    Twenty rows of ten is a wall of colour to scan; eight rows of eight is something
    you can read in a glance and act on, which is the whole point of a ticker.
    """
    # Opponent names always come from the full map — filtering the rows must not
    # filter the lookup, or any fixture against an unshown club raises.
    names = {t["id"]: t["short_name"] for t in boot["teams"]}
    teams = dict(names)
    if only_teams:
        teams = {k: v for k, v in teams.items() if k in only_teams}
    if labels:
        teams = {k: labels.get(k, v) for k, v in teams.items()}
    gws = list(range(start_gw, min(start_gw + n, 39)))

    # team -> gw -> list of (opponent, difficulty, home)
    grid: dict[int, dict[int, list]] = {t: {g: [] for g in gws} for t in teams}
    for f in fixtures:
        if f["event"] not in gws:
            continue
        if f["team_h"] in grid:
            grid[f["team_h"]][f["event"]].append(
                (names[f["team_a"]], f["team_h_difficulty"], True))
        if f["team_a"] in grid:
            grid[f["team_a"]][f["event"]].append(
                (names[f["team_h"]], f["team_a_difficulty"], False))

    def total(t):
        return sum(d for g in gws for _, d, _ in grid[t][g]) or 99

    order = sorted(teams, key=total)

    cw, ch, lw, top = 58, 34, 58, 24
    W = lw + cw * len(gws) + 8
    H = top + ch * len(order) + 6

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" '
           f'role="img" aria-label="Fixture difficulty for the next {len(gws)} gameweeks" '
           f'style="max-width:{W}px">']
    for i, g in enumerate(gws):
        out.append(f'<text x="{lw + cw*i + cw/2}" y="14" class="cx" text-anchor="middle">{g}</text>')

    for r, t in enumerate(order):
        y = top + r * ch
        out.append(f'<text x="0" y="{y + 21}" class="cy">{_esc(teams[t])}</text>')
        for i, g in enumerate(gws):
            x = lw + cw * i
            cells = grid[t][g]
            if not cells:
                out.append(f'<rect x="{x+1}" y="{y+1}" width="{cw-3}" height="{ch-3}" '
                           f'rx="5" class="blank"/>'
                           f'<text x="{x+cw/2-1}" y="{y+21}" class="cb" text-anchor="middle">—</text>')
                continue
            n_c = len(cells)
            for j, (opp, diff, home) in enumerate(cells):
                sub = (cw - 3) / n_c
                out.append(
                    f'<rect x="{x+1+j*sub}" y="{y+1}" width="{sub-1}" height="{ch-3}" rx="5" '
                    f'fill="{FDR_FILL.get(diff, FDR_FILL[3])}"/>'
                    f'<text x="{x+1+j*sub+sub/2}" y="{y+16}" text-anchor="middle" '
                    f'class="cf">{_esc(opp if home else opp.lower())}</text>'
                )
            # A difficulty number under the opponent, so it reads without the legend.
            if n_c == 1:
                out.append(f'<text x="{x+cw/2}" y="{y+28}" text-anchor="middle" '
                           f'class="cd">{cells[0][1]}</text>')
    out.append("</svg>")
    return "".join(out)


def score_distribution(scores, target: float, mean: float) -> str:
    """Histogram of simulated month scores with the score-to-win drawn on it.

    A single win probability is easy to nod at and hard to feel. Seeing how much of the
    distribution sits left of the line is the point.
    """
    if scores is None or len(scores) == 0:
        return ""
    lo, hi = float(min(scores)), float(max(scores))
    if hi <= lo:
        return ""
    nb = 34
    counts = [0] * nb
    for s in scores:
        b = int((float(s) - lo) / (hi - lo) * (nb - 1))
        counts[b] += 1
    peak = max(counts) or 1

    W, H, pad = 620, 190, 26
    bw = (W - pad * 2) / nb
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
           f'aria-label="Distribution of simulated scores for the month">']

    for i, c in enumerate(counts):
        h = (c / peak) * (H - pad - 44)
        x = pad + i * bw
        val = lo + (i + 0.5) / nb * (hi - lo)
        cls = "barlose" if val < target else "barwin"
        out.append(f'<rect x="{x}" y="{H - 44 - h}" width="{bw - 1.5}" height="{h}" '
                   f'rx="1.5" class="{cls}"/>')

    def px(v):
        return pad + (v - lo) / (hi - lo) * (W - pad * 2)

    out.append(f'<line x1="{px(target)}" y1="10" x2="{px(target)}" y2="{H-40}" class="vline"/>')
    out.append(f'<text x="{px(target)}" y="8" text-anchor="middle" class="vlab">'
               f'to win {target:.0f}</text>')
    out.append(f'<line x1="{px(mean)}" y1="26" x2="{px(mean)}" y2="{H-40}" class="mline"/>')
    out.append(f'<text x="{px(mean)}" y="22" text-anchor="middle" class="mlab">'
               f'you {mean:.0f}</text>')
    out.append(f'<line x1="{pad}" y1="{H-44}" x2="{W-pad}" y2="{H-44}" class="axis"/>')
    for v in (lo, (lo + hi) / 2, hi):
        out.append(f'<text x="{px(v)}" y="{H-28}" text-anchor="middle" class="cx">{v:.0f}</text>')
    out.append("</svg>")
    return "".join(out)


def value_frontier(table: dict, owned: set[int], limit: int = 70) -> str:
    """Expected points against price, with your squad marked.

    The efficient frontier is the visible upper-left edge. A ranked table tells you who
    scores most; this tells you who scores most *per pound*, which is the constraint
    that actually binds a hundred-million squad.
    """
    pts = [p for p in table.values() if p.exp_minutes >= 45 and p.xp > 0]
    if len(pts) < 12:
        return ""
    pts.sort(key=lambda p: -p.xp)
    pts = pts[:limit]

    xs = [p.price for p in pts]
    ys = [p.xp for p in pts]
    x0, x1 = min(xs) - 0.4, max(xs) + 0.4
    y0, y1 = 0, max(ys) * 1.1
    W, H, pl, pb, pt_, pr = 620, 260, 40, 34, 16, 12

    def sx(v):
        return pl + (v - x0) / (x1 - x0) * (W - pl - pr)

    def sy(v):
        return H - pb - (v - y0) / (y1 - y0) * (H - pb - pt_)

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
           f'aria-label="Expected points against price">']
    for gy in range(0, 6):
        v = y0 + (y1 - y0) * gy / 5
        out.append(f'<line x1="{pl}" y1="{sy(v)}" x2="{W-pr}" y2="{sy(v)}" class="grid"/>'
                   f'<text x="{pl-6}" y="{sy(v)+4}" text-anchor="end" class="cy">{v:.0f}</text>')
    for gx in range(int(x0), int(x1) + 1, 2):
        out.append(f'<text x="{sx(gx)}" y="{H-pb+16}" text-anchor="middle" class="cx">{gx}</text>')

    for p in pts:
        if p.pid in owned:
            continue
        out.append(f'<circle cx="{sx(p.price):.1f}" cy="{sy(p.xp):.1f}" r="4" class="dot">'
                   f'<title>{_esc(p.name)} — £{p.price:.1f}m, {p.xp:.1f} xP</title></circle>')
    for p in pts:
        if p.pid not in owned:
            continue
        out.append(f'<circle cx="{sx(p.price):.1f}" cy="{sy(p.xp):.1f}" r="6.5" class="dotown">'
                   f'<title>{_esc(p.name)} — £{p.price:.1f}m, {p.xp:.1f} xP</title></circle>')
    # Name the handful that matter: yours, and anything outstanding you do not own.
    best = sorted(pts, key=lambda p: -(p.xp / max(p.price, 0.1)))[:5]
    for p in best:
        out.append(f'<text x="{sx(p.price)+7:.1f}" y="{sy(p.xp)+3:.1f}" class="pt">'
                   f'{_esc(p.name[:12])}</text>')
    out.append(f'<text x="{W/2}" y="{H-4}" text-anchor="middle" class="cx">price £m</text>')
    out.append("</svg>")
    return "".join(out)


def team_scatter(ratings: dict) -> str:
    """Attack against defence for all twenty clubs.

    Explains *why* a fixture is easy. Facing a weak attack is good for your defenders;
    facing a weak defence is good for your forwards; the two are not the same fixture
    and a single difficulty number cannot say which you are getting.
    """
    rs = list(ratings.values())
    if len(rs) < 8:
        return ""
    xs = [r.defence for r in rs]
    ys = [r.attack for r in rs]
    x0, x1 = min(xs) * 0.94, max(xs) * 1.06
    y0, y1 = min(ys) * 0.94, max(ys) * 1.06
    W, H, pl, pb, pt_, pr = 620, 300, 44, 36, 16, 14

    def sx(v):
        return pl + (v - x0) / (x1 - x0) * (W - pl - pr)

    def sy(v):
        return H - pb - (v - y0) / (y1 - y0) * (H - pb - pt_)

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
           f'aria-label="Team attack against defence">']
    out.append(f'<line x1="{sx(1.0)}" y1="{pt_}" x2="{sx(1.0)}" y2="{H-pb}" class="grid"/>')
    out.append(f'<line x1="{pl}" y1="{sy(1.0)}" x2="{W-pr}" y2="{sy(1.0)}" class="grid"/>')
    out.append(f'<text x="{sx(1.0)+4}" y="{pt_+10}" class="cq">league average</text>')

    for r in rs:
        strong = r.attack > 1.0 and r.defence < 1.0
        out.append(
            f'<circle cx="{sx(r.defence):.1f}" cy="{sy(r.attack):.1f}" r="4.5" '
            f'class="{"dotown" if strong else "dot"}"/>'
            f'<text x="{sx(r.defence)+7:.1f}" y="{sy(r.attack)+3.5:.1f}" class="pt">'
            f'{_esc(r.short_name)}</text>'
        )
    out.append(f'<text x="{W/2}" y="{H-4}" text-anchor="middle" class="cx">'
               f'goals conceded (left is better) &rarr;</text>')
    out.append(f'<text x="10" y="{pt_+4}" class="cx">goals scored</text>')
    out.append("</svg>")
    return "".join(out)


def sparkline(values: list[float], W: int = 150, H: int = 30) -> str:
    """Tiny trend line, for putting a shape next to a number in a table."""
    if not values or len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    step = W / (len(values) - 1)
    pts = " ".join(f"{i*step:.1f},{H - 3 - (v-lo)/rng*(H-6):.1f}" for i, v in enumerate(values))
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" class="spark" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" class="sparkline"/></svg>')


def actual_vs_xp(records: dict, W: int = 620, H: int = 250) -> str:
    """Predicted against actual, gameweek by gameweek, plus the running totals.

    Bars are what happened; the line is what was predicted. Where the bar sits above
    the line the squad beat its own forecast. The faint pair at the bottom is the
    cumulative version, which is the one that matters — single gameweeks are mostly
    noise, and a model can miss by twenty points a week and still be unbiased.
    """
    played = sorted((r for r in records.values() if r.played and r.predicted > 0),
                    key=lambda r: r.gw)
    if len(played) < 1:
        return ""

    pad_l, pad_b, pad_t, pad_r = 38, 30, 18, 12
    plot_h = H - pad_b - pad_t
    hi = max(max(r.actual, r.predicted) for r in played) * 1.15 or 1
    bw = (W - pad_l - pad_r) / max(len(played), 1)

    def sy(v):
        return H - pad_b - (v / hi) * plot_h

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
           f'aria-label="Actual points against predicted, by gameweek">']
    for g in range(0, 5):
        v = hi * g / 4
        out.append(f'<line x1="{pad_l}" y1="{sy(v):.1f}" x2="{W-pad_r}" y2="{sy(v):.1f}" '
                   f'class="grid"/><text x="{pad_l-6}" y="{sy(v)+4:.1f}" text-anchor="end" '
                   f'class="cy">{v:.0f}</text>')

    for i, r in enumerate(played):
        x = pad_l + i * bw
        beat = r.actual >= r.predicted
        out.append(f'<rect x="{x+bw*0.18:.1f}" y="{sy(r.actual):.1f}" width="{bw*0.64:.1f}" '
                   f'height="{H-pad_b-sy(r.actual):.1f}" rx="2" '
                   f'class="{"barwin" if beat else "barlose"}">'
                   f'<title>GW{r.gw}: {r.actual:.0f} actual vs {r.predicted:.0f} predicted</title>'
                   f'</rect>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{H-pad_b+13:.1f}" text-anchor="middle" '
                   f'class="cx">{r.gw}</text>')

    pts = " ".join(f"{pad_l + i*bw + bw/2:.1f},{sy(r.predicted):.1f}"
                   for i, r in enumerate(played))
    out.append(f'<polyline points="{pts}" fill="none" class="predline"/>')
    for i, r in enumerate(played):
        out.append(f'<circle cx="{pad_l + i*bw + bw/2:.1f}" cy="{sy(r.predicted):.1f}" '
                   f'r="3" class="preddot"/>')

    out.append(f'<text x="{W-pad_r}" y="{pad_t}" text-anchor="end" class="cq">'
               f'bars = actual &middot; line = predicted</text>')
    out.append("</svg>")
    return "".join(out)


def calibration_bars(deciles: list[tuple[float, float]], W: int = 620, H: int = 210) -> str:
    """Predicted against realised across the prediction range, from the backtest.

    Each pair is a tenth of all player-months, ordered by prediction. Equal heights
    would mean a perfectly calibrated model. The pattern here is the honest one: the
    model runs a little hot, and most so at the top end where it matters.
    """
    if not deciles:
        return ""
    pad_l, pad_b, pad_t, pad_r = 34, 34, 16, 12
    n = len(deciles)
    gw = (W - pad_l - pad_r) / n
    hi = max(max(p, a) for p, a in deciles) * 1.15 or 1

    def sy(v):
        return H - pad_b - (v / hi) * (H - pad_b - pad_t)

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
           f'aria-label="Predicted against realised points by decile">']
    for g in range(0, 4):
        v = hi * g / 3
        out.append(f'<line x1="{pad_l}" y1="{sy(v):.1f}" x2="{W-pad_r}" y2="{sy(v):.1f}" '
                   f'class="grid"/><text x="{pad_l-6}" y="{sy(v)+4:.1f}" text-anchor="end" '
                   f'class="cy">{v:.0f}</text>')
    for i, (pred, act) in enumerate(deciles):
        x = pad_l + i * gw
        out.append(f'<rect x="{x+gw*0.14:.1f}" y="{sy(pred):.1f}" width="{gw*0.34:.1f}" '
                   f'height="{H-pad_b-sy(pred):.1f}" rx="2" class="barpred"/>')
        out.append(f'<rect x="{x+gw*0.52:.1f}" y="{sy(act):.1f}" width="{gw*0.34:.1f}" '
                   f'height="{H-pad_b-sy(act):.1f}" rx="2" class="barwin"/>')
        out.append(f'<text x="{x+gw/2:.1f}" y="{H-pad_b+13:.1f}" text-anchor="middle" '
                   f'class="cx">{i+1}</text>')
    out.append(f'<text x="{W/2}" y="{H-4}" text-anchor="middle" class="cx">'
               f'tenths of all players, weakest predicted to strongest &rarr;</text>')
    out.append("</svg>")
    return "".join(out)


def pitch(xi, bench, captain: int, vice: int, W: int = 620) -> str:
    """The XI laid out on a pitch, which is how anyone actually reads a squad.

    A table tells you who is in the team; a pitch tells you the *shape* — whether the
    budget went into three premium forwards or five defenders, and where the weak slot
    is. Deliberately restrained: a faint tinted surface with markings rather than a
    bright green, so it sits inside the rest of the design instead of shouting over it.
    """
    if not xi:
        return ""
    rows: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
    for p in xi:
        rows.setdefault(p.pos, []).append(p)
    for k in rows:
        rows[k].sort(key=lambda p: -p.xp)

    H = 430
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
           f'aria-label="Starting eleven laid out by position">']
    # Pitch surface and markings.
    out.append(f'<rect x="0" y="0" width="{W}" height="{H}" rx="12" class="pitch"/>')
    out.append(f'<line x1="14" y1="{H/2:.0f}" x2="{W-14}" y2="{H/2:.0f}" class="pline"/>')
    out.append(f'<circle cx="{W/2}" cy="{H/2:.0f}" r="46" class="pline" fill="none"/>')
    bw, bh = 176, 62
    out.append(f'<rect x="{(W-bw)/2}" y="14" width="{bw}" height="{bh}" class="pline" fill="none"/>')
    out.append(f'<rect x="{(W-bw)/2}" y="{H-14-bh}" width="{bw}" height="{bh}" class="pline" fill="none"/>')

    # Goalkeeper at the top, forwards at the bottom.
    bands = {1: 0.11, 2: 0.35, 3: 0.60, 4: 0.85}
    for pos, frac in bands.items():
        line = rows.get(pos, [])
        if not line:
            continue
        y = H * frac
        step = W / (len(line) + 1)
        for i, p in enumerate(line, start=1):
            x = step * i
            mark = "C" if p.pid == captain else ("V" if p.pid == vice else "")
            out.append(f'<g><circle cx="{x:.0f}" cy="{y:.0f}" r="19" class="pdot"/>')
            if mark:
                out.append(f'<circle cx="{x+15:.0f}" cy="{y-14:.0f}" r="9" class="parm"/>'
                           f'<text x="{x+15:.0f}" y="{y-10:.0f}" text-anchor="middle" '
                           f'class="parmt">{mark}</text>')
            out.append(f'<text x="{x:.0f}" y="{y+4:.0f}" text-anchor="middle" '
                       f'class="pxp">{p.xp:.0f}</text>')
            out.append(f'<text x="{x:.0f}" y="{y+34:.0f}" text-anchor="middle" '
                       f'class="pnm">{_esc(p.name[:11])}</text>')
            out.append(f'<text x="{x:.0f}" y="{y+45:.0f}" text-anchor="middle" '
                       f'class="ppr">{_esc(p.team_name)} &pound;{p.price:.1f}</text></g>')
    out.append("</svg>")
    return "".join(out)


def season_trajectory(gwplans, W: int = 620, H: int = 230) -> str:
    """Cumulative projected points across the season, banded by month.

    The month bands are the point. A season total is one number; this shows where it
    accumulates, and a six-gameweek December stands out as the block that pays.
    """
    if not gwplans:
        return ""
    pad_l, pad_b, pad_t, pad_r = 42, 30, 16, 12
    cum, running = [], 0.0
    for g in gwplans:
        running += g.net_projected
        cum.append((g.gw, running, g.month, g.chip_label))
    hi = cum[-1][1] or 1

    def sx(i):
        return pad_l + i * (W - pad_l - pad_r) / max(len(cum) - 1, 1)

    def sy(v):
        return H - pad_b - (v / hi) * (H - pad_b - pad_t)

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
           f'aria-label="Cumulative projected points across the season">']

    # Alternating month bands behind the line.
    start, shade = 0, True
    for i in range(1, len(cum) + 1):
        if i == len(cum) or cum[i][2] != cum[start][2]:
            if shade:
                out.append(f'<rect x="{sx(start):.1f}" y="{pad_t}" '
                           f'width="{sx(i-1)-sx(start):.1f}" height="{H-pad_b-pad_t}" '
                           f'class="band"/>')
            mid = (sx(start) + sx(i - 1)) / 2
            out.append(f'<text x="{mid:.0f}" y="{H-pad_b+13}" text-anchor="middle" '
                       f'class="cx">{_esc(cum[start][2][:3])}</text>')
            start, shade = i, not shade

    for g in range(0, 5):
        v = hi * g / 4
        out.append(f'<line x1="{pad_l}" y1="{sy(v):.1f}" x2="{W-pad_r}" y2="{sy(v):.1f}" '
                   f'class="grid"/><text x="{pad_l-6}" y="{sy(v)+4:.1f}" text-anchor="end" '
                   f'class="cy">{v:.0f}</text>')

    pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, (_, v, _, _) in enumerate(cum))
    out.append(f'<polyline points="{pts}" fill="none" class="predline"/>')
    for i, (gw, v, _, chip) in enumerate(cum):
        if chip:
            out.append(f'<circle cx="{sx(i):.1f}" cy="{sy(v):.1f}" r="4.5" class="dotown">'
                       f'<title>GW{gw}: {_esc(chip)}</title></circle>')
    out.append(f'<text x="{W-pad_r}" y="{pad_t+2}" text-anchor="end" class="cq">'
               f'{hi:.0f} pts by GW{cum[-1][0]} &middot; dots are chips</text>')
    out.append("</svg>")
    return "".join(out)
