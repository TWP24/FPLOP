"""Renders a season plan as a self-contained HTML page.

Built to be regenerated daily from live data and republished to the same URL, so the
plan visibly moves as prices, injuries and fixtures change. Everything is inlined —
no external CSS, fonts or scripts — and it reads on a phone.

This is a tool to be operated rather than a document to be read, so the design work
goes into information density: the summary sits above the detail, every figure is set
in tabular monospace, and each month's bar carries a tick marking what the month's
winner is expected to score. The gap between bar and tick is the whole point of the
page, so it is the thing you see first.
"""
from __future__ import annotations

import html

from .plan import SeasonPlan
from . import charts, tracking
from .xp import calibrate

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

# Predicted vs realised by decile, measured over 8,392 player-months across 2022/23 to
# 2025/26. Static because it describes the model, not this week's data.
CALIBRATION_DECILES = [
    (2.3, 2.7), (3.9, 4.3), (5.2, 4.9), (6.3, 6.2), (7.4, 6.6),
    (8.7, 8.1), (10.1, 9.1), (11.7, 11.3), (14.2, 13.2), (19.9, 18.2),
]
CHIP_LABEL = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "bboost": "Bench Boost",
    "3xc": "Triple Cap",
}

CSS = """
:root{
  --paper:#FCFBFD; --ink:#1B0A20; --mut:#6F6377; --line:#E7E2EB;
  --card:#FFFFFF; --accent:#7B2D8E; --accent-wash:#F4EAF7;
  --data:#00875A; --data-wash:#E6F2ED; --warn:#C2410C;
  --shadow:0 1px 2px rgba(27,10,32,.05), 0 6px 20px rgba(27,10,32,.05);
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#120D15; --ink:#EDE8F0; --mut:#9A8FA3; --line:#2A2130;
    --card:#191220; --accent:#C77DDB; --accent-wash:#231331;
    --data:#3FD69B; --data-wash:#12271F; --warn:#F0A868;
    --shadow:none;
  }
}
:root[data-theme=dark]{
  --paper:#120D15; --ink:#EDE8F0; --mut:#9A8FA3; --line:#2A2130;
  --card:#191220; --accent:#C77DDB; --accent-wash:#231331;
  --data:#3FD69B; --data-wash:#12271F; --warn:#F0A868;
  --shadow:none;
}
:root[data-theme=light]{
  --paper:#FCFBFD; --ink:#1B0A20; --mut:#6F6377; --line:#E7E2EB;
  --card:#FFFFFF; --accent:#7B2D8E; --accent-wash:#F4EAF7;
  --data:#00875A; --data-wash:#E6F2ED; --warn:#C2410C;
  --shadow:0 1px 2px rgba(27,10,32,.05), 0 6px 20px rgba(27,10,32,.05);
}

*{box-sizing:border-box}
body{
  margin:0; padding:28px 18px 72px; background:var(--paper); color:var(--ink);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%;
}
.wrap{max-width:960px; margin:0 auto; display:flex; flex-direction:column; gap:34px}
.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
      font-variant-numeric:tabular-nums}

header{display:flex; flex-direction:column; gap:5px}
h1{font-size:23px; font-weight:680; letter-spacing:-.02em; margin:0; text-wrap:balance}
.stamp{font-size:12px; color:var(--mut); letter-spacing:.02em}
.eyebrow{font-size:11px; text-transform:uppercase; letter-spacing:.10em;
         color:var(--accent); font-weight:700}

section{display:flex; flex-direction:column; gap:11px}
h2{font-size:12px; text-transform:uppercase; letter-spacing:.09em; color:var(--mut);
   margin:0; font-weight:700}
h2 span{text-transform:none; letter-spacing:0; font-weight:500; opacity:.8}

.strip{display:grid; grid-template-columns:repeat(auto-fit,minmax(138px,1fr)); gap:10px}
.tile{background:var(--card); border:1px solid var(--line); border-radius:11px;
      padding:12px 14px; box-shadow:var(--shadow); display:flex; flex-direction:column; gap:3px}
.tile .k{font-size:10.5px; text-transform:uppercase; letter-spacing:.07em; color:var(--mut);
         font-weight:650}
.tile .v{font-size:21px; font-weight:670; letter-spacing:-.02em; line-height:1.15}
.tile .v u{text-decoration:none; font-size:12px; font-weight:500; color:var(--mut)}

.scroll{overflow-x:auto; -webkit-overflow-scrolling:touch;
        border:1px solid var(--line); border-radius:11px; background:var(--card);
        box-shadow:var(--shadow)}
table{width:100%; border-collapse:collapse; font-size:14px; min-width:540px}
th{text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:.07em;
   color:var(--mut); font-weight:650; padding:9px 10px; border-bottom:1px solid var(--line);
   white-space:nowrap}
td{padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
.r{text-align:right}
.nm{font-weight:570}
.dim{color:var(--mut)}
.badge{width:26px; color:var(--accent); font-weight:750; font-size:11px}
.bench td{opacity:.60}
.q{color:var(--warn); font-weight:750; cursor:help}

tr.target td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
tr.target{background:var(--accent-wash)}
.tag{display:inline-block; background:var(--accent); color:var(--paper); font-size:9.5px;
     font-weight:750; letter-spacing:.06em; padding:2px 6px; border-radius:20px;
     vertical-align:1.5px; margin-left:6px}

.chip{display:inline-block; border:1px solid var(--accent); color:var(--accent);
      border-radius:6px; padding:1.5px 6px; font-size:11px; font-weight:650;
      margin:2px 5px 2px 0; white-space:nowrap}
.chip u{text-decoration:none; font-weight:500; opacity:.72}
.fx{display:inline-block; font-size:10.5px; color:var(--mut); margin:2px 9px 0 0}

.meter{position:relative; min-width:168px; height:22px}
.meter .fill{position:absolute; left:0; top:7px; height:8px; border-radius:5px;
             background:var(--data); opacity:.85}
.meter .tick{position:absolute; top:2px; width:2px; height:18px; background:var(--accent);
             border-radius:2px}
.meter .val{position:absolute; right:0; top:3px; font-size:11.5px; color:var(--mut)}

.legend{display:flex; flex-wrap:wrap; gap:16px; font-size:12px; color:var(--mut);
        align-items:center}
.legend i{font-style:normal; display:inline-flex; align-items:center; gap:6px}
.swatch{width:16px; height:8px; border-radius:4px; background:var(--data); opacity:.85}
.needle{width:2px; height:14px; background:var(--accent); border-radius:2px}

.note{background:var(--card); border:1px solid var(--line);
      border-left:3px solid var(--accent); border-radius:10px; padding:14px 16px;
      font-size:13.5px}
.note h3{margin:0 0 7px; font-size:12px; text-transform:uppercase; letter-spacing:.07em;
         color:var(--mut); font-weight:700}
.note ul{margin:0; padding-left:17px; display:flex; flex-direction:column; gap:5px}
tr.mrule td{background:var(--accent-wash); font-size:10.5px; font-weight:700;
            text-transform:uppercase; letter-spacing:.08em; color:var(--accent);
            padding:5px 10px}
.move{display:inline-block; font-size:12px; margin-right:10px; white-space:nowrap}
.move s{color:var(--mut); text-decoration:line-through}
.move b{font-weight:620}
.moves{min-width:230px}
.hit{display:inline-block; color:var(--warn); font-weight:700; font-size:11px;
     border:1px solid var(--warn); border-radius:5px; padding:0 5px; margin-left:4px}
/* Tabs, driven entirely by hidden radios so the page needs no JavaScript. */
.tabin{position:absolute; opacity:0; pointer-events:none}
nav.tabs{display:flex; gap:4px; flex-wrap:wrap; border-bottom:1px solid var(--line);
         margin-bottom:6px}
nav.tabs label{padding:9px 14px; font-size:13px; font-weight:600; color:var(--mut);
  cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px;
  white-space:nowrap; border-radius:7px 7px 0 0; transition:color .12s, background .12s}
nav.tabs label:hover{color:var(--ink); background:var(--accent-wash)}
nav.tabs label b{font-weight:600; font-variant-numeric:tabular-nums; opacity:.55;
                 margin-left:5px; font-size:11.5px}
.panel{display:none; flex-direction:column; gap:26px}
#t1:checked~.panels .p1, #t2:checked~.panels .p2, #t3:checked~.panels .p3,
#t4:checked~.panels .p4, #t5:checked~.panels .p5{display:flex}
#t1:checked~nav.tabs label[for=t1], #t2:checked~nav.tabs label[for=t2],
#t3:checked~nav.tabs label[for=t3], #t4:checked~nav.tabs label[for=t4],
#t5:checked~nav.tabs label[for=t5]{
  color:var(--accent); border-bottom-color:var(--accent)}
.tabin:focus-visible~nav.tabs label{outline:2px solid var(--accent); outline-offset:2px}
@media (max-width:520px){ nav.tabs label{padding:8px 10px; font-size:12.5px} }
/* Fixture difficulty: its own semantic scale, deliberately not the accent hue. */
:root{--fdr1:#1a7f5a; --fdr2:#54a375; --fdr3:#9aa0a6; --fdr4:#d97757; --fdr5:#b3402f;
      --chart:#7B2D8E; --chart-soft:#C9A6D6;}
@media (prefers-color-scheme:dark){:root{
  --fdr1:#2e9c72; --fdr2:#4e8f68; --fdr3:#6b7280; --fdr4:#c96a4a; --fdr5:#a33b2c;
  --chart:#C77DDB; --chart-soft:#5B3468;}}
:root[data-theme=dark]{--fdr1:#2e9c72; --fdr2:#4e8f68; --fdr3:#6b7280; --fdr4:#c96a4a;
  --fdr5:#a33b2c; --chart:#C77DDB; --chart-soft:#5B3468;}
:root[data-theme=light]{--fdr1:#1a7f5a; --fdr2:#54a375; --fdr3:#9aa0a6; --fdr4:#d97757;
  --fdr5:#b3402f; --chart:#7B2D8E; --chart-soft:#C9A6D6;}

.chartbox{background:var(--card); border:1px solid var(--line); border-radius:11px;
  padding:14px; box-shadow:var(--shadow); overflow-x:auto}
svg text{font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-variant-numeric:tabular-nums}
svg .cx,svg .cy{font-size:10px; fill:var(--mut)}
svg .cy{font-weight:650}
svg .cf{font-size:9.5px; fill:#fff; font-weight:600}
svg .cb{font-size:10px; fill:var(--mut)}
svg .cq{font-size:9px; fill:var(--mut)}
svg .cd{font-size:9px; fill:var(--mut); font-weight:650}
svg .barpred{fill:var(--mut); opacity:.35}
svg .predline{stroke:var(--chart); stroke-width:2.5; stroke-linejoin:round}
svg .preddot{fill:var(--chart)}
svg .pt{font-size:9.5px; fill:var(--mut)}
svg .blank{fill:var(--line)}
svg .grid{stroke:var(--line); stroke-width:1}
svg .axis{stroke:var(--mut); stroke-width:1; opacity:.4}
svg .barwin{fill:var(--data); opacity:.85}
svg .barlose{fill:var(--mut); opacity:.30}
svg .vline{stroke:var(--warn); stroke-width:2; stroke-dasharray:3 3}
svg .vlab{font-size:10px; fill:var(--warn); font-weight:700}
svg .mline{stroke:var(--chart); stroke-width:2}
svg .mlab{font-size:10px; fill:var(--chart); font-weight:700}
svg .dot{fill:var(--mut); opacity:.42}
svg .dotown{fill:var(--chart)}
svg .sparkline{stroke:var(--chart); stroke-width:1.5}
.fdrkey{display:flex; gap:12px; flex-wrap:wrap; font-size:11px; color:var(--mut);
        align-items:center; margin-top:2px}
.fdrkey i{font-style:normal; display:inline-flex; align-items:center; gap:5px}
.fdrkey b{width:14px; height:10px; border-radius:3px; display:inline-block}
footer{color:var(--mut); font-size:12px; border-top:1px solid var(--line); padding-top:15px}
"""


def _esc(s) -> str:
    return html.escape(str(s))


def _gameweek_section(gwplans) -> str:
    """The week-by-week forward plan: transfers, captain, chips, projected points."""
    if not gwplans:
        return ""

    rows = ""
    total_hits = sum(g.hits for g in gwplans)
    total_moves = sum(len(g.moves) for g in gwplans)
    total_pts = sum(g.net_projected for g in gwplans)
    peak = max((g.net_projected for g in gwplans), default=1) or 1

    last_month = None
    for g in gwplans:
        # A rule between months makes the scoring periods legible at a glance.
        if g.month != last_month:
            rows += (f'<tr class="mrule"><td colspan="6">{_esc(g.month)}</td></tr>')
            last_month = g.month

        moves = "".join(
            f'<span class="move"><s>{_esc(m.out_name)}</s> &rarr; '
            f'<b>{_esc(m.in_name)}</b></span>'
            for m in g.moves
        ) or '<span class="dim">roll transfer</span>'
        if g.hits:
            moves += f'<span class="hit">&minus;{4 * g.hits}</span>'

        chip = (f'<span class="chip">{_esc(g.chip_label)}</span>' if g.chip else '')
        w = 100 * g.net_projected / peak
        rows += (
            f'<tr class="{"target" if g.chip else ""}">'
            f'<td class="mono nm">{g.gw}</td>'
            f'<td class="nm">{_esc(g.captain_name)}</td>'
            f'<td class="dim mono">{_esc(g.formation)}</td>'
            f'<td><div class="meter"><span class="fill" style="width:{w:.1f}%"></span>'
            f'<span class="val mono">{g.net_projected:.0f}</span></div></td>'
            f'<td>{chip or "<span class=dim>—</span>"}</td>'
            f'<td class="moves">{moves}</td></tr>'
        )

    return f"""<section>
    <h2>Gameweek plan <span>— projected to the end of the season</span></h2>
    <div class="strip">
      <div class="tile"><div class="k">Projected total</div>
        <div class="v mono">{total_pts:.0f}<u> pts</u></div></div>
      <div class="tile"><div class="k">Transfers</div>
        <div class="v mono">{total_moves}</div></div>
      <div class="tile"><div class="k">Hits taken</div>
        <div class="v mono">{total_hits}<u> ({4 * total_hits} pts)</u></div></div>
    </div>
    <div class="scroll"><table>
      <thead><tr><th>GW</th><th>Captain</th><th>Form</th><th>Projected</th>
        <th>Chip</th><th>Transfers</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <div class="legend">
      <i>Weeks further out say "a good squad for these fixtures" more than
         "these exact players" — the near weeks are the actionable ones.</i>
    </div>
  </section>"""


def _league_section(view, my_squad, table) -> str:
    """Your mini-league: rivals priced through the same model, and real ownership."""
    from . import rivals as rv

    if view is None:
        return """<section>
    <h2>Your league</h2>
    <div class="note"><h3>No league connected</h3>
      <p style="margin:0 0 8px">Pass your mini-league id and this fills with every
      rival&rsquo;s actual squad, priced through the same model as yours &mdash; their
      projected points, their captain, and the ownership that matters.</p>
      <p style="margin:0"><b>Why it matters:</b> a player most of your league owns
      cannot win you the month, because his haul lifts everyone. Ownership measured
      across your nineteen rivals is the number the differential maths needs &mdash;
      not FPL&rsquo;s global figure, which describes six million strangers.</p>
      <p style="margin:8px 0 0" class="dim">Find the id in your league URL
      (<code>.../leagues/<b>123456</b>/standings/c</code>), then run with
      <code>--league 123456</code>.</p></div>
  </section>"""

    if not view.available:
        return f"""<section>
    <h2>Your league <span>&mdash; {_esc(view.league_name)}</span></h2>
    <div class="note"><h3>Not available yet</h3>
      <p style="margin:0">{_esc(view.note)}. This fills in automatically once the
      first deadline passes, and every rival&rsquo;s squad then gets priced through the
      same model as yours.</p></div>
  </section>"""

    rows = ""
    for i, r in enumerate(view.with_picks, 1):
        cap = table.get(r.captain)
        chip = f'<span class="chip">{_esc(r.chip)}</span>' if r.chip else ""
        rows += (
            f'<tr><td class="mono dim">{i}</td>'
            f'<td class="nm">{_esc(r.team_name)}</td>'
            f'<td class="dim">{_esc(r.manager)}</td>'
            f'<td class="r mono" style="font-weight:650">{r.xp:.1f}</td>'
            f'<td>{_esc(cap.name) if cap else "&mdash;"}</td>'
            f'<td class="r mono dim">{r.total_points}</td>'
            f'<td>{chip}</td></tr>'
        )

    diffs, template = rv.differentials(view, my_squad, table)
    thr = rv.threats(view, my_squad, table)

    def own_rows(items, label):
        out = ""
        for p, own in items[:8]:
            bar = f'<div class="meter"><span class="fill" style="width:{own*100:.0f}%"></span>' \
                  f'<span class="val mono">{own*100:.0f}%</span></div>'
            out += (f'<tr><td class="nm">{_esc(p.name)}</td>'
                    f'<td class="dim mono">{_esc(p.team_name)}</td>'
                    f'<td class="r mono">{p.xp:.1f}</td><td>{bar}</td></tr>')
        return out or f'<tr><td colspan="4" class="dim">no {label}</td></tr>'

    return f"""<section>
    <h2>Your league <span>&mdash; {_esc(view.league_name)}, GW{view.gameweek}</span></h2>
    <div class="scroll"><table>
      <thead><tr><th>#</th><th>Team</th><th>Manager</th><th class="r">Projected</th>
        <th>Captain</th><th class="r">Total</th><th>Chip</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <div class="legend"><i>Every rival&rsquo;s actual squad, priced through the same
      model as yours. Projected is this month&rsquo;s expected points for their XI plus
      captain.</i></div>
  </section>

  <section>
    <h2>Where you differ <span>&mdash; ownership measured in your league, not globally</span></h2>
    <div class="scroll"><table>
      <thead><tr><th colspan="4">Your differentials &mdash; the league mostly does not own these</th></tr>
        <tr><th>Player</th><th>Team</th><th class="r">xP</th><th>League ownership</th></tr></thead>
      <tbody>{own_rows(diffs, "differentials")}</tbody>
    </table></div>
    <div class="scroll"><table>
      <thead><tr><th colspan="4">Threats &mdash; rivals own these, you do not</th></tr>
        <tr><th>Player</th><th>Team</th><th class="r">xP</th><th>League ownership</th></tr></thead>
      <tbody>{own_rows(thr, "threats")}</tbody>
    </table></div>
    <div class="legend"><i>A player most of your league owns cannot win you the month
      &mdash; his haul lifts everyone. Only the gap between your squad and theirs moves
      you up the table.</i></div>
  </section>"""


def render(plan: SeasonPlan, rivals: int = 19, title: str = "FPL monthly plan",
           gwplans=None, league_view=None, boot_ref=None, fixtures_ref=None) -> str:
    squad = plan.squad
    cap = next((p for p in squad.players if p.pid == squad.captain), None)
    total_chip = sum(m.chip_value for m in plan.months)
    contested = [m for m in plan.months if m.contest]

    def row(p, mark="") -> str:
        q = ' <span class="q" title="No Premier League history — role inferred from price">?</span>' if "no-PL-history" in p.flags else ""
        return (
            f'<tr><td class="badge mono">{_esc(mark)}</td>'
            f'<td class="nm">{_esc(p.name)}{q}</td>'
            f'<td class="dim mono">{_esc(p.team_name)}</td>'
            f'<td class="dim mono">{POS[p.pos]}</td>'
            f'<td class="r mono">{p.price:.1f}</td>'
            f'<td class="r mono" style="font-weight:650">{p.xp:.1f}</td>'
            f'<td class="r mono dim">{calibrate(p.xp, p.n_fixtures, p.pos):.1f}</td>'
            f'<td class="dim mono" style="font-size:11.5px">{_esc(p.fdr_string)}</td></tr>'
        )

    xi = "".join(
        row(p, "C" if p.pid == squad.captain else ("V" if p.pid == squad.vice else ""))
        for p in squad.xi
    )
    bench = "".join(row(p) for p in squad.bench)

    owned = {p.pid for p in squad.players}
    month_key = plan.months[0].month.name if plan.months else None
    now_table = plan.tables.get(month_key, {}) if month_key else {}

    dist_svg = charts.score_distribution(plan.sim_scores, plan.sim_target,
                                         float(plan.sim_scores.mean())
                                         if plan.sim_scores is not None else 0.0)
    dist_block = f'''<section>
    <h2>How the month lands <span>&mdash; 6,000 simulated seasons of this squad</span></h2>
    <div class="chartbox">{dist_svg}</div>
    <div class="legend"><i>Green is where you finish ahead of the month&rsquo;s winner,
      grey is where you do not. <b>P(win) {plan.sim_p_win*100:.1f}%</b> against a
      {rivals}-rival field &mdash; chance alone would be {100/(rivals+1):.1f}%.</i></div>
  </section>''' if dist_svg else ""

    my_clubs = {p.team for p in squad.players}
    ticker_svg = charts.fixture_ticker(boot_ref, fixtures_ref, plan.next_gw, 8,
                                       only_teams=my_clubs) \
        if boot_ref and fixtures_ref else ""
    ticker_block = f'''<section>
    <h2>Your fixtures <span>&mdash; the {len(my_clubs)} clubs you own, next 8 gameweeks</span></h2>
    <div class="chartbox">{ticker_svg}</div>
    <div class="fdrkey">
      <i><b style="background:var(--fdr1)"></b>1</i><i><b style="background:var(--fdr2)"></b>2</i>
      <i><b style="background:var(--fdr3)"></b>3</i><i><b style="background:var(--fdr4)"></b>4</i>
      <i><b style="background:var(--fdr5)"></b>5</i>
      <i>UPPERCASE = home, lowercase = away. Easiest run at the top. Two blocks in one
        cell is a double gameweek, a dash is a blank.</i>
    </div>
  </section>''' if ticker_svg else ""

    value_svg = charts.value_frontier(now_table, owned)
    value_block = f'''<section>
    <h2>Value frontier <span>&mdash; expected points against price</span></h2>
    <div class="chartbox">{value_svg}</div>
    <div class="legend"><i>Purple is your squad. The upper-left edge is the efficient
      frontier &mdash; most points per pound. A ranked table shows who scores most;
      this shows who is worth buying under a &pound;100m cap.</i></div>
  </section>''' if value_svg else ""

    team_svg = charts.team_scatter(plan.team_ratings)
    team_block = f'''<section>
    <h2>Team ratings <span>&mdash; why a fixture is easy</span></h2>
    <div class="chartbox">{team_svg}</div>
    <div class="legend"><i>Purple = scores more and concedes less than average. Facing a
      weak attack helps your defenders; facing a weak defence helps your forwards. One
      difficulty number cannot tell you which you are getting.</i></div>
  </section>''' if team_svg else ""

    track_recs = tracking.load()
    track = tracking.summary(track_recs)
    avx_svg = charts.actual_vs_xp(track_recs)
    if avx_svg:
        r = track
        verdict = ("running hot — the squad is beating its forecast"
                   if r["ratio"] > 1.04 else
                   "running cold — the model is over-predicting"
                   if r["ratio"] < 0.96 else "well calibrated")
        avx_block = f'''<section>
    <h2>Actual vs predicted <span>&mdash; {r["n"]} gameweeks played</span></h2>
    <div class="strip">
      <div class="tile"><div class="k">Predicted</div>
        <div class="v mono">{r["predicted"]:.0f}</div></div>
      <div class="tile"><div class="k">Actual</div>
        <div class="v mono">{r["actual"]:.0f}</div></div>
      <div class="tile"><div class="k">Ratio</div>
        <div class="v mono">{r["ratio"]:.2f}<u> {verdict.split(" —")[0]}</u></div></div>
      <div class="tile"><div class="k">Avg miss</div>
        <div class="v mono">{r["mae"]:.1f}<u> pts/GW</u></div></div>
      <div class="tile"><div class="k">Beat forecast</div>
        <div class="v mono">{r["beat"]}<u> of {r["n"]}</u></div></div>
    </div>
    <div class="chartbox">{avx_svg}</div>
    <div class="legend"><i>Bars are what you actually scored, the line is what was
      predicted before the deadline. Predictions are written down once and never
      revised, so this is a fair test rather than a flattering one. Verdict:
      <b>{verdict}</b>.</i></div>
  </section>'''
    else:
        avx_block = '''<section>
    <h2>Actual vs predicted</h2>
    <div class="note"><h3>Starts at GW1</h3>
      <p style="margin:0 0 8px">Each gameweek&rsquo;s prediction is written down before
      the deadline and scored against what actually happened afterwards. Nothing else
      here keeps a record &mdash; every run rebuilds from scratch &mdash; so without
      this there is no way to tell whether the model is working <i>now</i>, on this
      season, rather than on the seasons it was tested against.</p>
      <p style="margin:0">Predictions are never revised once written. A forecast you
      can edit after the fact is not a forecast.</p></div>
  </section>'''

    # How the model performed on four backtested seasons, as context for the above.
    calib_block = f'''<section>
    <h2>Model accuracy <span>&mdash; 8,392 player-months across four seasons</span></h2>
    <div class="chartbox">{charts.calibration_bars(CALIBRATION_DECILES)}</div>
    <div class="legend"><i>Grey is predicted, green is what actually happened, in tenths
      from weakest prediction to strongest. Equal heights would be perfect. The model
      runs about 6% hot and most so at the top &mdash; which is why the squad tables
      carry an <b>xP adj</b> column beside <b>xP</b>.</i></div>
  </section>'''

    gw_section = _gameweek_section(gwplans)
    n_months = len(plan.months)
    n_gws = len(gwplans) if gwplans else 0
    league_badge = (f"<b>{len(league_view.with_picks)}</b>"
                    if league_view is not None and league_view.available else "")
    month_now = plan.months[0].month.name if plan.months else None
    league_section = _league_section(
        league_view, [p.pid for p in squad.players],
        plan.tables.get(month_now, {}) if month_now else {},
    )
    scale = max([m.field_target for m in plan.months] + [1])
    months = ""
    for m in plan.months:
        chips = "".join(
            f'<span class="chip">{CHIP_LABEL.get(c.chip, c.chip)}'
            f'<u> GW{c.gw} · +{c.value:.0f}</u></span>'
            for c in m.chips
        )
        notes = ""
        if m.doubles:
            notes += f'<span class="fx">DGW {_esc(", ".join(m.doubles[:5]))}</span>'
        if m.blanks:
            notes += f'<span class="fx">BGW {_esc(", ".join(m.blanks[:5]))}</span>'
        fill = 100 * m.projected / scale
        tick = 100 * m.field_target / scale
        months += (
            f'<tr class="{"target" if m.contest else ""}">'
            f'<td class="nm">{_esc(m.month.name)}'
            f'{"<span class=tag>TARGET</span>" if m.contest else ""}</td>'
            f'<td class="dim mono">{m.month.start_event}–{m.month.stop_event}</td>'
            f'<td class="r mono">{m.n_gws}</td>'
            f'<td><div class="meter"><span class="fill" style="width:{fill:.1f}%"></span>'
            f'<span class="tick" style="left:{tick:.1f}%"></span>'
            f'<span class="val mono">{m.projected:.0f} / {m.field_target:.0f}</span></div></td>'
            f'<td>{chips or "<span class=dim>—</span>"}{notes}</td></tr>'
        )

    return f"""<title>{_esc(title)}</title>
<style>{CSS}</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Season 2026/27 · monthly prize league</div>
    <h1>{_esc(title)}</h1>
    <div class="stamp mono">Refreshed {_esc(plan.generated)} &nbsp;·&nbsp;
        next deadline GW{plan.next_gw} &nbsp;·&nbsp; {rivals + 1} managers</div>
  </header>

  <div class="strip">
    <div class="tile"><div class="k">Squad cost</div>
      <div class="v mono">£{squad.cost:.1f}<u>m</u></div></div>
    <div class="tile"><div class="k">Formation</div>
      <div class="v mono">{_esc(squad.formation)}</div></div>
    <div class="tile"><div class="k">Captain</div>
      <div class="v" style="font-size:16px">{_esc(cap.name if cap else '—')}</div></div>
    <div class="tile"><div class="k">Months targeted</div>
      <div class="v mono">{len(contested)}<u> of {len(plan.months)}</u></div></div>
    <div class="tile"><div class="k">Chip value</div>
      <div class="v mono">+{total_chip:.0f}<u> pts</u></div></div>
  </div>

  <input class="tabin" type="radio" name="tab" id="t1" checked>
  <input class="tabin" type="radio" name="tab" id="t2">
  <input class="tabin" type="radio" name="tab" id="t3">
  <input class="tabin" type="radio" name="tab" id="t4">
  <input class="tabin" type="radio" name="tab" id="t5">
  <nav class="tabs">
    <label for="t1">Squad</label>
    <label for="t2">Season<b>{n_months}</b></label>
    <label for="t3">Gameweeks<b>{n_gws}</b></label>
    <label for="t4">League{league_badge}</label>
    <label for="t5">Charts</label>
  </nav>

  <div class="panels">
    <div class="panel p1">
  <section>
    <h2>Starting XI</h2>
    <div class="scroll"><table>
      <thead><tr><th></th><th>Player</th><th>Team</th><th>Pos</th><th class="r">£m</th>
        <th class="r">xP</th><th class="r" title="xP corrected for the model's measured bias — still a forecast, not an outcome">xP adj</th>
        <th>Fixtures</th></tr></thead>
      <tbody>{xi}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Bench <span>— in substitution order</span></h2>
    <div class="scroll"><table class="bench">
      <thead><tr><th></th><th>Player</th><th>Team</th><th>Pos</th><th class="r">£m</th>
        <th class="r">xP</th><th class="r">xP adj</th><th>Fixtures</th></tr></thead>
      <tbody>{bench}</tbody>
    </table></div>
  </section>

    </div>

    <div class="panel p2">
  <section>
    <h2>Season plan <span>— which months to contest</span></h2>
    <div class="scroll"><table>
      <thead><tr><th>Month</th><th>GWs</th><th class="r">#</th>
        <th>Projected vs winning score</th><th>Chips &amp; fixtures</th></tr></thead>
      <tbody>{months}</tbody>
    </table></div>
    <div class="legend">
      <i><span class="swatch"></span> your projected points</i>
      <i><span class="needle"></span> what the month's winner scores</i>
      <i>the gap between them is what a chip has to close</i>
    </div>
  </section>

  {dist_block}
    </div>

    <div class="panel p3">
  {gw_section}
    </div>

    <div class="panel p4">
  {league_section}
    </div>

    <div class="panel p5">
  {avx_block}

  {calib_block}

  {ticker_block}

  {value_block}

  {team_block}
    </div>
  </div>

  <div class="note">
    <h3>How to read this</h3>
    <ul>
      <li><b>Both columns are forecasts — neither is actual points.</b> <b>xP</b> is the
          model's raw output, which is what the optimiser ranks on. <b>xP adj</b> is the
          same number corrected for bias the model is known to have: measured over 8,392
          player-months it runs about 6% hot and over-spreads at the top, so a defender
          projected high realises around 0.79 of it. <b>xP adj</b> is the one to believe
          for "what will this actually score". Real outcomes appear on the
          <b>Charts</b> tab, from gameweek 1 onward.</li>
      <li>You cannot contest all ten months — eight chips across ten months means
          picking your battles. <b>TARGET</b> months are where the chips land.</li>
      <li><b>?</b> marks a player with no Premier League history, whose role is inferred
          from price alone. Check these against team news before trusting them.</li>
      <li>Chip values are low right now because the fixture list has no double or blank
          gameweeks in it yet. They appear from around December, and Bench Boost and
          Free Hit get much more valuable when they do. This page re-prices daily.</li>
      <li>A two-gameweek month is close to a coin toss whatever your squad looks like.
          Spend chips where there are more gameweeks to work with.</li>
    </ul>
  </div>

  <footer>
    Built from the live FPL API. Validated by walk-forward backtest across three
    completed seasons under real transfer rules. Expected points are estimates, not
    predictions.
  </footer>
</div>"""


def write(plan: SeasonPlan, path: str, rivals: int = 19,
          title: str = "FPL monthly plan", gwplans=None, league_view=None,
          boot_ref=None, fixtures_ref=None) -> str:
    # Create the parent directory. Writing beside an existing file works everywhere,
    # so this only bites when the output goes somewhere new — which is exactly what
    # CI does, publishing to site/index.html on a fresh checkout.
    import os

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(render(plan, rivals=rivals, title=title, gwplans=gwplans,
                        league_view=league_view, boot_ref=boot_ref,
                        fixtures_ref=fixtures_ref))
    return path
