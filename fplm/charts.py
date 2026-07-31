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


def fixture_ticker(boot: dict, fixtures: list[dict], start_gw: int, n: int = 10) -> str:
    """Colour grid of every club's next `n` fixtures, hardest to easiest.

    Sorted by total difficulty so the good and bad runs separate visually. This is the
    chart that answers "who should I be buying in three weeks", which no per-month
    average can.
    """
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    gws = list(range(start_gw, min(start_gw + n, 39)))

    # team -> gw -> list of (opponent, difficulty, home)
    grid: dict[int, dict[int, list]] = {t: {g: [] for g in gws} for t in teams}
    for f in fixtures:
        if f["event"] not in gws:
            continue
        grid[f["team_h"]][f["event"]].append((teams[f["team_a"]], f["team_h_difficulty"], True))
        grid[f["team_a"]][f["event"]].append((teams[f["team_h"]], f["team_a_difficulty"], False))

    def total(t):
        return sum(d for g in gws for _, d, _ in grid[t][g]) or 99

    order = sorted(teams, key=total)

    cw, ch, lw, top = 46, 26, 44, 22
    W = lw + cw * len(gws) + 8
    H = top + ch * len(order) + 6

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" '
           f'role="img" aria-label="Fixture difficulty for the next {len(gws)} gameweeks" '
           f'style="max-width:{W}px">']
    for i, g in enumerate(gws):
        out.append(f'<text x="{lw + cw*i + cw/2}" y="14" class="cx" text-anchor="middle">{g}</text>')

    for r, t in enumerate(order):
        y = top + r * ch
        out.append(f'<text x="0" y="{y + 17}" class="cy">{_esc(teams[t])}</text>')
        for i, g in enumerate(gws):
            x = lw + cw * i
            cells = grid[t][g]
            if not cells:
                out.append(f'<rect x="{x+1}" y="{y+1}" width="{cw-3}" height="{ch-3}" '
                           f'rx="4" class="blank"/>'
                           f'<text x="{x+cw/2-1}" y="{y+17}" class="cb" text-anchor="middle">—</text>')
                continue
            n_c = len(cells)
            for j, (opp, diff, home) in enumerate(cells):
                sub = (cw - 3) / n_c
                out.append(
                    f'<rect x="{x+1+j*sub}" y="{y+1}" width="{sub-1}" height="{ch-3}" rx="4" '
                    f'fill="{FDR_FILL.get(diff, FDR_FILL[3])}"/>'
                    f'<text x="{x+1+j*sub+sub/2}" y="{y+17}" text-anchor="middle" '
                    f'class="cf">{_esc(opp if home else opp.lower())}</text>'
                )
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


def value_frontier(table: dict, owned: set[int], limit: int = 190) -> str:
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
        out.append(f'<circle cx="{sx(p.price):.1f}" cy="{sy(p.xp):.1f}" r="3" class="dot"/>')
    for p in pts:
        if p.pid not in owned:
            continue
        out.append(f'<circle cx="{sx(p.price):.1f}" cy="{sy(p.xp):.1f}" r="5" class="dotown">'
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
