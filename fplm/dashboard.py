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

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
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
footer{color:var(--mut); font-size:12px; border-top:1px solid var(--line); padding-top:15px}
"""


def _esc(s) -> str:
    return html.escape(str(s))


def render(plan: SeasonPlan, rivals: int = 19, title: str = "FPL monthly plan") -> str:
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
            f'<td class="dim mono" style="font-size:11.5px">{_esc(p.fdr_string)}</td></tr>'
        )

    xi = "".join(
        row(p, "C" if p.pid == squad.captain else ("V" if p.pid == squad.vice else ""))
        for p in squad.xi
    )
    bench = "".join(row(p) for p in squad.bench)

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

  <section>
    <h2>Starting XI</h2>
    <div class="scroll"><table>
      <thead><tr><th></th><th>Player</th><th>Team</th><th>Pos</th><th class="r">£m</th>
        <th class="r">xP</th><th>Fixtures</th></tr></thead>
      <tbody>{xi}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Bench <span>— in substitution order</span></h2>
    <div class="scroll"><table class="bench">
      <thead><tr><th></th><th>Player</th><th>Team</th><th>Pos</th><th class="r">£m</th>
        <th class="r">xP</th><th>Fixtures</th></tr></thead>
      <tbody>{bench}</tbody>
    </table></div>
  </section>

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

  <div class="note">
    <h3>How to read this</h3>
    <ul>
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


def write(plan: SeasonPlan, path: str, rivals: int = 19, title: str = "FPL monthly plan") -> str:
    with open(path, "w") as fh:
        fh.write(render(plan, rivals=rivals, title=title))
    return path
