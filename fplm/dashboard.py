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
  --bg:#F7F6F9; --surface:#FFFFFF; --surface-2:#FBFAFC;
  --ink:#17101C; --ink-2:#4A4152; --mut:#7C7288; --line:#E6E2EC;
  --accent:#6D28A8; --accent-ink:#FFFFFF; --accent-wash:#F3EDF9; --accent-line:#DCCBEC;
  --ok:#0F7A52; --ok-wash:#E7F4EE; --warn:#B4530E; --warn-wash:#FDF0E4;
  --data:#00875A;
  --fdr1:#1a7f5a; --fdr2:#54a375; --fdr3:#9aa0a6; --fdr4:#d97757; --fdr5:#b3402f;
  --chart:#6D28A8; --shadow:0 1px 2px rgba(23,16,28,.04),0 1px 3px rgba(23,16,28,.06);
  --shadow-lg:0 4px 6px -1px rgba(23,16,28,.05),0 10px 24px -6px rgba(23,16,28,.10);
  --r:10px; --rail:224px;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0D0A10; --surface:#161120; --surface-2:#1B1526;
  --ink:#EFEBF3; --ink-2:#BDB4C8; --mut:#8F859C; --line:#2A2235;
  --accent:#B98BD9; --accent-ink:#1A1020; --accent-wash:#241733; --accent-line:#3B2A4E;
  --ok:#4ED9A0; --ok-wash:#12291F; --warn:#E9A45F; --warn-wash:#2C1E11;
  --data:#3FD69B;
  --fdr1:#2e9c72; --fdr2:#4e8f68; --fdr3:#6b7280; --fdr4:#c96a4a; --fdr5:#a33b2c;
  --chart:#B98BD9; --shadow:none; --shadow-lg:none;
}}
:root[data-theme=dark]{
  --bg:#0D0A10; --surface:#161120; --surface-2:#1B1526;
  --ink:#EFEBF3; --ink-2:#BDB4C8; --mut:#8F859C; --line:#2A2235;
  --accent:#B98BD9; --accent-ink:#1A1020; --accent-wash:#241733; --accent-line:#3B2A4E;
  --ok:#4ED9A0; --ok-wash:#12291F; --warn:#E9A45F; --warn-wash:#2C1E11;
  --data:#3FD69B; --fdr1:#2e9c72; --fdr2:#4e8f68; --fdr3:#6b7280;
  --fdr4:#c96a4a; --fdr5:#a33b2c; --chart:#B98BD9; --shadow:none; --shadow-lg:none;
}
:root[data-theme=light]{
  --bg:#F7F6F9; --surface:#FFFFFF; --surface-2:#FBFAFC;
  --ink:#17101C; --ink-2:#4A4152; --mut:#7C7288; --line:#E6E2EC;
  --accent:#6D28A8; --accent-ink:#FFFFFF; --accent-wash:#F3EDF9; --accent-line:#DCCBEC;
  --ok:#0F7A52; --ok-wash:#E7F4EE; --warn:#B4530E; --warn-wash:#FDF0E4;
  --data:#00875A; --fdr1:#1a7f5a; --fdr2:#54a375; --fdr3:#9aa0a6;
  --fdr4:#d97757; --fdr5:#b3402f; --chart:#6D28A8;
  --shadow:0 1px 2px rgba(23,16,28,.04),0 1px 3px rgba(23,16,28,.06);
  --shadow-lg:0 4px 6px -1px rgba(23,16,28,.05),0 10px 24px -6px rgba(23,16,28,.10);
}

*{box-sizing:border-box}
body{margin:0; background:var(--bg); color:var(--ink);
  font:14.5px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%; -webkit-font-smoothing:antialiased}
.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  font-variant-numeric:tabular-nums; font-feature-settings:"tnum"}

/* ---- app shell: fixed rail on desktop, horizontal nav on mobile ---- */
.app{display:flex; min-height:100vh}
.tabin{position:absolute; opacity:0; pointer-events:none}

.rail{width:var(--rail); flex:0 0 var(--rail); background:var(--surface);
  border-right:1px solid var(--line); padding:20px 14px; position:sticky; top:0;
  height:100vh; display:flex; flex-direction:column; gap:22px}
.brand{display:flex; align-items:center; gap:10px; padding:0 6px}
.brand .mark{width:30px; height:30px; border-radius:8px; background:var(--accent);
  color:var(--accent-ink); display:grid; place-items:center; font-weight:750;
  font-size:13px; letter-spacing:-.03em; flex:0 0 30px}
.brand b{font-size:14.5px; font-weight:680; letter-spacing:-.01em; display:block}
.brand span{font-size:11px; color:var(--mut); display:block; margin-top:-1px}
nav.tabs{display:flex; flex-direction:column; gap:2px}
nav.tabs .grp{font-size:10px; text-transform:uppercase; letter-spacing:.09em;
  color:var(--mut); font-weight:700; padding:6px 8px 4px}
nav.tabs label{display:flex; align-items:center; gap:9px; padding:8px 10px;
  border-radius:8px; font-size:13.5px; font-weight:550; color:var(--ink-2);
  cursor:pointer; transition:background .12s,color .12s; white-space:nowrap}
nav.tabs label:hover{background:var(--surface-2); color:var(--ink)}
nav.tabs label i{font-style:normal; width:16px; text-align:center; opacity:.75; font-size:14px}
nav.tabs label b{margin-left:auto; font-size:11px; font-weight:600; color:var(--mut);
  background:var(--surface-2); border:1px solid var(--line); border-radius:20px;
  padding:0 6px; font-variant-numeric:tabular-nums}
.railfoot{margin-top:auto; font-size:11px; color:var(--mut); padding:0 8px; line-height:1.5}

main{flex:1; min-width:0; display:flex; flex-direction:column}
.topbar{position:sticky; top:0; z-index:5; background:var(--surface);
  border-bottom:1px solid var(--line); padding:12px 24px; display:flex;
  align-items:center; gap:12px; flex-wrap:wrap}
.topbar h1{font-size:15.5px; font-weight:650; margin:0; letter-spacing:-.01em}
.spacer{flex:1}
.content{padding:22px 24px 60px; display:flex; flex-direction:column; gap:22px;
  max-width:1180px; width:100%}

/* ---- primitives ---- */
.pill{display:inline-flex; align-items:center; gap:5px; font-size:11.5px; font-weight:600;
  padding:3px 9px; border-radius:20px; border:1px solid var(--line);
  background:var(--surface-2); color:var(--ink-2); white-space:nowrap}
.pill.accent{background:var(--accent-wash); border-color:var(--accent-line); color:var(--accent)}
.pill.ok{background:var(--ok-wash); border-color:transparent; color:var(--ok)}
.pill.warn{background:var(--warn-wash); border-color:transparent; color:var(--warn)}
.dot{width:6px; height:6px; border-radius:50%; background:currentColor; flex:0 0 6px}

.card{background:var(--surface); border:1px solid var(--line); border-radius:var(--r);
  box-shadow:var(--shadow); overflow:hidden}
.card > .hd{padding:13px 16px; border-bottom:1px solid var(--line);
  display:flex; align-items:center; gap:10px; flex-wrap:wrap}
.card > .hd h2{font-size:13.5px; font-weight:640; margin:0; letter-spacing:-.005em;
  text-transform:none; color:var(--ink)}
.card > .hd .sub{font-size:12px; color:var(--mut)}
.card > .bd{padding:14px 16px}
.card > .bd.flush{padding:0}
.card > .ft{padding:10px 16px; border-top:1px solid var(--line); background:var(--surface-2);
  font-size:12px; color:var(--mut); line-height:1.5}

.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px}
.kpi{background:var(--surface); border:1px solid var(--line); border-radius:var(--r);
  padding:13px 15px; box-shadow:var(--shadow)}
.kpi .k{font-size:10.5px; text-transform:uppercase; letter-spacing:.07em;
  color:var(--mut); font-weight:650}
.kpi .v{font-size:22px; font-weight:660; letter-spacing:-.025em; line-height:1.2; margin-top:3px}
.kpi .v u{text-decoration:none; font-size:12px; font-weight:500; color:var(--mut)}

.scroll{overflow-x:auto; -webkit-overflow-scrolling:touch}
table{width:100%; border-collapse:collapse; font-size:13.5px; min-width:520px}
thead th{text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--mut); font-weight:650; padding:9px 14px; background:var(--surface-2);
  border-bottom:1px solid var(--line); white-space:nowrap; position:sticky; top:0}
td{padding:9px 14px; border-bottom:1px solid var(--line); vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--surface-2)}
.r{text-align:right} .nm{font-weight:570} .dim{color:var(--mut)}
.badge{width:24px; color:var(--accent); font-weight:750; font-size:11px}
.bench td{opacity:.62}
.q{color:var(--warn); font-weight:750; cursor:help}
tr.target{background:var(--accent-wash)}
tr.target td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
.tag{display:inline-block; background:var(--accent); color:var(--accent-ink); font-size:9.5px;
  font-weight:750; letter-spacing:.05em; padding:2px 6px; border-radius:20px;
  vertical-align:1.5px; margin-left:6px}
tr.mrule td{background:var(--accent-wash); font-size:10px; font-weight:700;
  text-transform:uppercase; letter-spacing:.08em; color:var(--accent); padding:5px 14px}

.chip{display:inline-block; border:1px solid var(--accent-line); background:var(--accent-wash);
  color:var(--accent); border-radius:6px; padding:2px 7px; font-size:11px; font-weight:640;
  margin:2px 5px 2px 0; white-space:nowrap}
.chip u{text-decoration:none; font-weight:500; opacity:.75}
.fx{display:inline-block; font-size:10.5px; color:var(--mut); margin:2px 9px 0 0}
.move{display:inline-block; font-size:12px; margin-right:10px; white-space:nowrap}
.move s{color:var(--mut); text-decoration:line-through}
.move b{font-weight:620}
.moves{min-width:220px}
.hit{display:inline-block; color:var(--warn); font-weight:700; font-size:11px;
  border:1px solid var(--warn); border-radius:5px; padding:0 5px; margin-left:4px}
.warncell{color:var(--warn); font-size:12.5px}
.okline{font-size:13px; color:var(--mut); display:flex; align-items:center; gap:8px}

.meter{position:relative; min-width:160px; height:20px}
.meter .fill{position:absolute; left:0; top:6px; height:8px; border-radius:5px;
  background:var(--data); opacity:.85}
.meter .tick{position:absolute; top:1px; width:2px; height:18px; background:var(--accent);
  border-radius:2px}
.meter .val{position:absolute; right:0; top:2px; font-size:11.5px; color:var(--mut)}

.legend{display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--mut); align-items:center}
.legend i{font-style:normal; display:inline-flex; align-items:center; gap:6px}
.swatch{width:15px; height:8px; border-radius:4px; background:var(--data); opacity:.85}
.needle{width:2px; height:13px; background:var(--accent); border-radius:2px}
.fdrkey{display:flex; gap:11px; flex-wrap:wrap; font-size:11px; color:var(--mut); align-items:center}
.fdrkey i{font-style:normal; display:inline-flex; align-items:center; gap:5px}
.fdrkey b{width:14px; height:10px; border-radius:3px; display:inline-block}

.empty{padding:26px 18px; text-align:center; color:var(--mut); font-size:13.5px;
  line-height:1.6; max-width:620px; margin:0 auto}
.empty h3{font-size:14px; font-weight:640; color:var(--ink); margin:0 0 6px}
.empty code{background:var(--surface-2); border:1px solid var(--line); border-radius:5px;
  padding:1px 5px; font-size:12px}

svg text{font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-variant-numeric:tabular-nums}
svg .cx,svg .cy{font-size:10px; fill:var(--mut)}
svg .cy{font-weight:650}
svg .cf{font-size:9.5px; fill:#fff; font-weight:600}
svg .cb,svg .cq{font-size:10px; fill:var(--mut)}
svg .cd{font-size:9px; fill:var(--mut); font-weight:650}
svg .pt{font-size:9.5px; fill:var(--mut)}
svg .blank{fill:var(--line)}
svg .grid{stroke:var(--line); stroke-width:1}
svg .axis{stroke:var(--mut); stroke-width:1; opacity:.4}
svg .barwin{fill:var(--data); opacity:.85}
svg .barlose{fill:var(--mut); opacity:.30}
svg .barpred{fill:var(--mut); opacity:.35}
svg .vline{stroke:var(--warn); stroke-width:2; stroke-dasharray:3 3}
svg .vlab{font-size:10px; fill:var(--warn); font-weight:700}
svg .mline,svg .predline{stroke:var(--chart); stroke-width:2}
svg .predline{stroke-width:2.5; stroke-linejoin:round}
svg .mlab{font-size:10px; fill:var(--chart); font-weight:700}
svg .dot{fill:var(--mut); opacity:.42}
svg .dotown,svg .preddot{fill:var(--chart)}
svg .pitch{fill:var(--ok-wash); stroke:var(--line)}
svg .pline{stroke:var(--line); stroke-width:1.5; fill:none}
svg .pdot{fill:var(--surface); stroke:var(--accent); stroke-width:2}
svg .parm{fill:var(--accent)}
svg .parmt{font-size:9px; fill:var(--accent-ink); font-weight:750}
svg .pxp{font-size:12.5px; fill:var(--ink); font-weight:700}
svg .pnm{font-size:10.5px; fill:var(--ink); font-weight:600}
svg .ppr{font-size:9.5px; fill:var(--mut)}
svg .band{fill:var(--surface-2)}

/* Player dialogs: :target rather than JavaScript, so back also closes them. */
.modal{position:fixed; inset:0; display:none; place-items:center; z-index:60; padding:18px}
.modal:target{display:grid}
.modal .backdrop{position:absolute; inset:0; background:rgba(12,8,16,.55);
  backdrop-filter:blur(2px)}
.modal .box{position:relative; width:min(460px,100%); max-height:86vh; overflow-y:auto;
  background:var(--surface); border:1px solid var(--line); border-radius:14px;
  box-shadow:var(--shadow-lg)}
.modal .hd{position:sticky; top:0; z-index:1; background:var(--surface);
  display:flex; align-items:flex-start; gap:10px; padding:13px 16px;
  border-bottom:1px solid var(--line)}
.modal .bd{padding:14px 16px}
.modal .ft{padding:10px 16px; border-top:1px solid var(--line);
  background:var(--surface-2); font-size:11.5px; color:var(--mut); line-height:1.5}
.modal .who{display:flex; flex-direction:column; gap:2px; min-width:0; flex:1 1 auto}
.modal .who h2{font-size:17px; line-height:1.2}
.modal .who .sub{font-size:11.5px}
/* 44px of tap target, pulled back with negative margin so it does not
   push the title down on a phone. */
.modal .x{margin:-8px -8px 0 auto; flex:none; color:var(--mut); text-decoration:none;
  font-size:22px; line-height:1; width:44px; height:44px; display:grid;
  place-items:center; border-radius:8px}
/* Three across even at 375px — these are three short numbers, not three cards. */
.mstats{display:grid; grid-template-columns:repeat(3,1fr); gap:1px; margin-bottom:4px;
  background:var(--line); border:1px solid var(--line); border-radius:10px;
  overflow:hidden}
.mstats>div{background:var(--surface-2); padding:8px 10px}
.mstats .k{font-size:9.5px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--mut); font-weight:700}
.mstats .v{font-size:18px; font-weight:700; color:var(--ink); margin-top:1px}
.modal .x:hover{color:var(--ink); background:var(--surface-2)}
.modal h3{font-size:10.5px; text-transform:uppercase; letter-spacing:.07em;
  color:var(--mut); font-weight:700; margin:16px 0 6px}
.modal table{min-width:0; font-size:13px}
.modal td{padding:5px 0; border-bottom:1px solid var(--line)}
.modal tr:last-child td{border-bottom:none}
.modal .flags{display:flex; gap:6px; flex-wrap:wrap; margin-top:10px}
.cbar{width:100%; max-width:88px; height:5px; border-radius:4px;
  background:var(--surface-2); overflow:hidden; margin:3px 0 0 auto}
/* One column per gameweek. Six-gameweek months are wider than a phone, so the
   table scrolls inside the dialog rather than stretching it. */
.tscroll{overflow-x:auto; margin:0 -2px}
.gwtab th{font-size:9.5px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--mut); font-weight:700; padding:2px 0; border:none; text-align:left}
.gwtab th.r,.gwtab td.r{text-align:right}
.gwtab th.r{padding-left:12px}
.gwtab td{padding:6px 0 6px 12px; vertical-align:top; white-space:nowrap}
.gwtab td.nm{padding-left:0; white-space:normal}
.gwtab tr.tot td{border-bottom:none; border-top:1px solid var(--line);
  font-weight:700; color:var(--ink)}
.cbar span{display:block; height:100%; border-radius:4px}
.cbar .pos{background:var(--data)} .cbar .neg{background:var(--warn)}
a.plink{color:inherit; text-decoration:none; border-bottom:1px dotted var(--line)}
a.plink:hover{color:var(--accent); border-bottom-color:var(--accent)}

.panel{display:none; flex-direction:column; gap:22px}
#t1:checked~main .p1, #t2:checked~main .p2, #t3:checked~main .p3,
#t4:checked~main .p4, #t5:checked~main .p5{display:flex}
#t1:checked~.rail label[for=t1], #t2:checked~.rail label[for=t2],
#t3:checked~.rail label[for=t3], #t4:checked~.rail label[for=t4],
#t5:checked~.rail label[for=t5]{background:var(--accent-wash); color:var(--accent)}
#t1:checked~.rail label[for=t1] b, #t2:checked~.rail label[for=t2] b,
#t3:checked~.rail label[for=t3] b, #t4:checked~.rail label[for=t4] b,
#t5:checked~.rail label[for=t5] b{border-color:var(--accent-line); color:var(--accent)}
.tabin:focus-visible~.rail label{outline:2px solid var(--accent); outline-offset:-2px}

@media (max-width:860px){
  .app{flex-direction:column}
  .rail{width:auto; flex:none; height:auto; position:static; border-right:none;
    border-bottom:1px solid var(--line); padding:12px 14px; gap:12px}
  .rail .railfoot, nav.tabs .grp{display:none}
  nav.tabs{flex-direction:row; gap:4px; overflow-x:auto; padding-bottom:2px}
  nav.tabs label{padding:7px 11px; font-size:13px}
  nav.tabs label i{display:none}
  .topbar{padding:11px 15px} .content{padding:16px 15px 56px}
}
"""


def _esc(s) -> str:
    return html.escape(str(s))


COMPONENT_LABEL = {
    "appearance": "Appearance", "goals": "Goals", "assists": "Assists",
    "clean_sheet": "Clean sheet", "defcon": "Defensive contribution",
    "bonus": "Bonus", "saves": "Saves", "conceded": "Goals conceded", "cards": "Cards",
}


def _player_modals(squad, table, rates) -> str:
    """One dialog per squad player, explaining where their xP comes from.

    Driven by :target rather than JavaScript, so the page stays a static file and the
    browser back button closes the dialog for free.

    The point is auditability. Every number on this page is a model output, and a model
    output you cannot interrogate is just an assertion. This shows the fixtures, the
    per-component split and the underlying per-90 rates that produced it, so a figure
    that looks wrong can be checked rather than trusted.
    """
    out = []
    for p in squad.players:
        r = rates.get(p.pid)
        fixtures = sorted(p.fixtures, key=lambda x: x.event)
        if not fixtures:
            continue

        # Per gameweek, not summed over the month. A month total invites exactly the
        # wrong reading: appearance at 3.84 looks like a big edge until you notice it
        # is two matches of the 2 points every starter gets. Per gameweek the numbers
        # sit on a scale you already know from the scoring rules.
        keys = [k for k in {k for f in fixtures for k in f.components}
                if any(abs(f.components.get(k, 0.0)) >= 0.005 for f in fixtures)]
        keys.sort(key=lambda k: -sum(abs(f.components.get(k, 0.0)) for f in fixtures))
        if not keys:
            continue
        span = max((abs(f.components.get(k, 0.0)) for k in keys for f in fixtures),
                   default=1.0) or 1.0

        head = "".join(f'<th class="r">GW{f.event}</th>' for f in fixtures)
        venue = "".join(f'<th class="r dim">{"H" if f.home else "A"} &middot; fdr {f.fdr}'
                        f'</th>' for f in fixtures)
        comp = (f'<tr><th></th>{head}</tr><tr><th></th>{venue}</tr>')
        for k in keys:
            cells = ""
            for f in fixtures:
                v = f.components.get(k, 0.0)
                w = abs(v) / span * 100
                cells += (f'<td class="r mono">{v:+.2f}'
                          f'<div class="cbar"><span class="{"neg" if v < 0 else "pos"}" '
                          f'style="width:{w:.0f}%"></span></div></td>')
            comp += f'<tr><td class="nm">{COMPONENT_LABEL.get(k, k)}</td>{cells}</tr>'
        comp += ('<tr class="tot"><td class="nm">Total</td>'
                 + "".join(f'<td class="r mono">{f.xp:.2f}</td>' for f in fixtures)
                 + '</tr>')

        rate_rows = ""
        if r:
            for label, val, unit in [
                ("Expected minutes", r.exp_minutes, " per match"),
                ("Chance of starting", r.p_start * 100, "%"),
                ("Goals per 90", r.xg90, ""),
                ("Assists per 90", r.xa90, ""),
                ("Bonus per 90", r.bonus90, ""),
                ("Points per 90 last season", r.pp90, ""),
            ]:
                rate_rows += (f'<tr><td class="dim">{label}</td>'
                              f'<td class="r mono">{val:.2f}{unit}</td></tr>')

        flags = ""
        if r:
            ORD = {1: "first", 2: "second", 3: "third"}
            for label, val in (("penalties", r.penalties_order),
                               ("free kicks", r.freekicks_order),
                               ("corners", r.corners_order)):
                if val:
                    flags += (f'<span class="pill accent">{ORD.get(val, f"#{val}")} '
                              f'on {label}</span>')
        if r and "no-PL-history" in r.flags:
            flags += '<span class="pill warn">no Premier League history</span>'
        if r and r.news:
            flags += f'<span class="pill warn">{_esc(r.news[:52])}</span>'

        out.append(f'''<div class="modal" id="p{p.pid}">
  <a class="backdrop" href="#" aria-label="Close"></a>
  <div class="box">
    <div class="hd">
      <div class="who"><h2>{_esc(p.name)}</h2>
        <span class="sub">{POS[p.pos]} &middot; {_esc(p.team_name)} &middot;
          &pound;{p.price:.1f}m &middot; {p.selected_by:.1f}% owned</span></div>
      <a class="x" href="#" aria-label="Close">&times;</a></div>
    <div class="bd">
      <div class="mstats">
        <div><div class="k">xP / GW</div>
          <div class="v mono">{p.xp / max(p.n_fixtures, 1):.1f}</div></div>
        <div><div class="k">xP adj / GW</div>
          <div class="v mono">{calibrate(p.xp, p.n_fixtures, p.pos)
                               / max(p.n_fixtures, 1):.1f}</div></div>
        <div><div class="k">Gameweeks</div><div class="v mono">{p.n_fixtures}</div></div>
      </div>
      {f'<div class="flags">{flags}</div>' if flags else ''}
      <h3>Expected points per gameweek</h3>
      <div class="tscroll"><table class="gwtab">{comp}</table></div>
      <h3>Underlying rates</h3>
      <table>{rate_rows}</table>
    </div>
    <div class="ft">Every figure is one gameweek, already scaled by expected minutes
      and that fixture's difficulty. Each column's components sum to its Total.
      Across {p.n_fixtures} gameweeks that is {p.xp:.1f} xP, which is the number the
      squad tables rank on.</div>
  </div>
</div>''')
    return "".join(out)


def _countdown(deadline: str) -> str:
    """Time to the next deadline, as a chip the top bar can wear."""
    import datetime as _dt

    if not deadline:
        return ""
    try:
        d = _dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    except ValueError:
        return ""
    delta = d - _dt.datetime.now(_dt.timezone.utc)
    if delta.total_seconds() < 0:
        return "deadline passed"
    days, hrs = delta.days, delta.seconds // 3600
    return f"{days}d {hrs}h to deadline" if days else f"{hrs}h to deadline"


def _action_panel(plan, squad, rates, gwplans, deadline: str) -> str:
    """What to do before the next deadline, above everything else.

    The rest of the page is analysis; this is instructions. It leads with availability
    because expected minutes is the largest single input to the model and a squad with
    an injured captain is the one thing worth knowing before anything else on the page.
    """
    import datetime as _dt

    when = ""
    if deadline:
        try:
            d = _dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            delta = d - _dt.datetime.now(_dt.timezone.utc)
            days, hrs = delta.days, delta.seconds // 3600
            when = f"{days}d {hrs}h" if days >= 0 else "passed"
        except ValueError:
            when = ""

    # Availability problems inside the squad, worst first.
    alerts = []
    for p in squad.players:
        r = rates.get(p.pid)
        if r is None:
            continue
        chance = None if r.status == "a" and not r.news else r.status
        if r.status != "a" or r.news:
            starting = p.pid in squad.starters
            alerts.append((0 if starting else 1, p, r))
    alerts.sort(key=lambda x: (x[0], -x[1].xp))

    if alerts:
        rows = "".join(
            f'<tr><td class="nm"><a class="plink" href="#p{p.pid}">{_esc(p.name)}</a>'
            f'{" <span class=tag>STARTING</span>" if inxi == 0 else ""}</td>'
            f'<td class="dim mono">{_esc(p.team_name)}</td>'
            f'<td class="r mono">{p.xp:.1f}</td>'
            f'<td class="warncell">{_esc(r.news or r.status)}</td></tr>'
            for inxi, p, r in alerts
        )
        alert_block = f'''<div class="scroll"><table>
        <thead><tr><th>Player</th><th>Team</th><th class="r">xP</th>
          <th>Team news</th></tr></thead><tbody>{rows}</tbody></table></div>'''
    else:
        alert_block = ('<div class="okline">No injury or availability flags in your '
                       'squad.</div>')

    nxt = gwplans[0] if gwplans else None
    moves = ""
    # The plan's own move comes first. The forward planner begins from the squad this
    # already chose and does not transfer into its first gameweek, so asking it what
    # to do this week returns nothing however the squad was reached.
    if getattr(plan, "moves_now", None):
        moves = "".join(f'<span class="move"><s>{_esc(o)}</s> &rarr; '
                        f'<b>{_esc(i)}</b></span>' for o, i in plan.moves_now)
    elif nxt and nxt.moves:
        moves = "".join(f'<span class="move"><s>{_esc(m.out_name)}</s> &rarr; '
                        f'<b>{_esc(m.in_name)}</b></span>' for m in nxt.moves)
    elif nxt:
        moves = '<span class="dim">no transfer — roll it</span>'

    cap = next((p for p in squad.players if p.pid == squad.captain), None)
    vice = next((p for p in squad.players if p.pid == squad.vice), None)

    return f'''<section class="card action">
    <div class="hd"><h2>Before the deadline</h2>
      <span class="sub">GW{plan.next_gw}, {when} away</span></div>
    <div class="bd"><div class="kpis">
      <div class="kpi"><div class="k">Captain</div>
        <div class="v" style="font-size:16px">{_esc(cap.name if cap else "—")}</div></div>
      <div class="kpi"><div class="k">Vice</div>
        <div class="v" style="font-size:16px">{_esc(vice.name if vice else "—")}</div></div>
      <div class="kpi"><div class="k">Transfer</div>
        <div class="v" style="font-size:14px">{moves or "&mdash;"}</div></div>
      <div class="kpi"><div class="k">Flags</div>
        <div class="v mono">{len(alerts)}<u> in squad</u></div></div>
    </div>
    {alert_block}</div>
  </section>'''


def _gameweek_section(gwplans) -> str:
    """The week-by-week forward plan: transfers, captain, chips, projected points."""
    if not gwplans:
        return ""

    rows = ""
    total_hits = sum(g.hits for g in gwplans)
    total_moves = sum(len(g.moves) for g in gwplans)
    total_pts = sum(g.net_projected for g in gwplans)
    peak = max((g.net_projected for g in gwplans), default=1) or 1

    # Month subtotals, because the prize is monthly — a divider that only carries a
    # name makes you add up six rows in your head to answer the question the whole
    # tool exists for.
    by_month: dict[str, float] = {}
    for g in gwplans:
        by_month[g.month] = by_month.get(g.month, 0.0) + g.net_projected

    running = 0.0
    last_month = None
    for g in gwplans:
        if g.month != last_month:
            sub = by_month[g.month]
            n_gw = sum(1 for x in gwplans if x.month == g.month)
            rows += (f'<tr class="mrule"><td colspan="4">{_esc(g.month)}</td>'
                     f'<td colspan="3" class="r">{sub:.0f} pts over {n_gw} GW</td></tr>')
            last_month = g.month
        running += g.net_projected

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
            f'<td class="r mono dim">{running:.0f}</td>'
            f'<td>{chip or "<span class=dim>—</span>"}</td>'
            f'<td class="moves">{moves}</td></tr>'
        )

    return f"""<section class="card">
    <div class="hd"><h2>Gameweek plan</h2><span class="sub">projected to the end of the season</span></div>
    <div class="bd"><div class="kpis">
      <div class="kpi"><div class="k">Season total xP</div>
        <div class="v mono">{total_pts:.0f}<u> pts, net of hits</u></div></div>
      <div class="kpi"><div class="k">Per gameweek</div>
        <div class="v mono">{total_pts / max(len(gwplans), 1):.1f}<u> avg</u></div></div>
      <div class="kpi"><div class="k">Transfers</div>
        <div class="v mono">{total_moves}</div></div>
      <div class="kpi"><div class="k">Hits taken</div>
        <div class="v mono">{total_hits}<u> ({4 * total_hits} pts)</u></div></div>
    </div>
    <div class="scroll"><table>
      <thead><tr><th>GW</th><th>Captain</th><th>Form</th><th>Projected</th>
        <th class="r">Cumulative</th><th>Chip</th><th>Transfers</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div></div>
    <div class="ft">Weeks further out say a good squad for these fixtures more than
      these exact players &mdash; the near weeks are the actionable ones.</div>
  </section>"""


def _league_section(views, my_squad, table) -> str:
    """Your mini-leagues: rivals priced through the same model, and real ownership.

    Rendered once per league rather than pooled. Ownership is the whole point of this
    view and it is league-specific — a player who is template in a twenty-person work
    league can be a genuine differential in a smaller one, and averaging the two would
    describe neither.
    """
    from . import rivals as rv

    if not views:
        return """<section class="card">
    <div class="hd"><h2>Your league</h2></div>
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
      <code>--league 123456 789012</code> &mdash; as many as you have.</p></div>
  </section>"""

    return "".join(_one_league(v, my_squad, table) for v in views)


def _one_league(view, my_squad, table) -> str:
    """One league's standings, ownership and differentials."""
    from . import rivals as rv

    if not view.available:
        return f"""<section class="card">
    <div class="hd"><h2>{_esc(view.league_name)} </h2><span class="sub">league {view.league_id}</span></div>
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

    return f"""<section class="card">
    <div class="hd"><h2>{_esc(view.league_name)} </h2><span class="sub">{len(view.with_picks)} rivals, GW{view.gameweek}</span></div>
    <div class="scroll"><table>
      <thead><tr><th>#</th><th>Team</th><th>Manager</th><th class="r">Projected</th>
        <th>Captain</th><th class="r">Total</th><th>Chip</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <div class="legend"><i>Every rival&rsquo;s actual squad, priced through the same
      model as yours. Projected is this month&rsquo;s expected points for their XI plus
      captain.</i></div>
  </section>

  <section class="card">
    <div class="hd"><h2>Where you differ in {_esc(view.league_name)} </h2><span class="sub">ownership measured in
      this league, not globally</span></div>
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
           gwplans=None, league_view=None, boot_ref=None, fixtures_ref=None,
           rates_ref=None, deadline_ref="") -> str:
    squad = plan.squad
    cap = next((p for p in squad.players if p.pid == squad.captain), None)
    total_chip = sum(m.chip_value for m in plan.months)
    contested = [m for m in plan.months if m.contest]

    def row(p, mark="") -> str:
        q = ' <span class="q" title="No Premier League history — role inferred from price">?</span>' if "no-PL-history" in p.flags else ""
        return (
            f'<tr><td class="badge mono">{_esc(mark)}</td>'
            f'<td class="nm"><a class="plink" href="#p{p.pid}">{_esc(p.name)}</a>{q}</td>'
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
    dist_block = f'''<section class="card">
    <div class="hd"><h2>How the month lands </h2><span class="sub">6,000 simulated seasons of this squad</span></div>
    <div class="chartbox">{dist_svg}</div>
    <div class="legend"><i>Green is where you finish ahead of the month&rsquo;s winner,
      grey is where you do not. <b>P(win) {plan.sim_p_win*100:.1f}%</b> against a
      {rivals}-rival field &mdash; chance alone would be {100/(rivals+1):.1f}%.</i></div>
  </section>''' if dist_svg else ""

    my_clubs = {p.team for p in squad.players}
    ticker_svg = charts.fixture_ticker(boot_ref, fixtures_ref, plan.next_gw, 8,
                                       only_teams=my_clubs) \
        if boot_ref and fixtures_ref else ""
    ticker_block = f'''<section class="card">
    <div class="hd"><h2>Your fixtures </h2><span class="sub">the {len(my_clubs)} clubs you own, next 8 gameweeks</span></div>
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
    value_block = f'''<section class="card">
    <div class="hd"><h2>Value frontier </h2><span class="sub">expected points against price</span></div>
    <div class="chartbox">{value_svg}</div>
    <div class="legend"><i>Purple is your squad. The upper-left edge is the efficient
      frontier &mdash; most points per pound. A ranked table shows who scores most;
      this shows who is worth buying under a &pound;100m cap.</i></div>
  </section>''' if value_svg else ""

    team_svg = charts.team_scatter(plan.team_ratings)
    team_block = f'''<section class="card">
    <div class="hd"><h2>Team ratings </h2><span class="sub">why a fixture is easy</span></div>
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
        avx_block = f'''<section class="card">
    <div class="hd"><h2>Actual vs predicted </h2><span class="sub">{r["n"]} gameweeks played</span></div>
    <div class="kpis">
      <div class="kpi"><div class="k">Predicted</div>
        <div class="v mono">{r["predicted"]:.0f}</div></div>
      <div class="kpi"><div class="k">Actual</div>
        <div class="v mono">{r["actual"]:.0f}</div></div>
      <div class="kpi"><div class="k">Ratio</div>
        <div class="v mono">{r["ratio"]:.2f}<u> {verdict.split(" —")[0]}</u></div></div>
      <div class="kpi"><div class="k">Avg miss</div>
        <div class="v mono">{r["mae"]:.1f}<u> pts/GW</u></div></div>
      <div class="kpi"><div class="k">Beat forecast</div>
        <div class="v mono">{r["beat"]}<u> of {r["n"]}</u></div></div>
    </div>
    <div class="chartbox">{avx_svg}</div>
    <div class="legend"><i>Bars are what you actually scored, the line is what was
      predicted before the deadline. Predictions are written down once and never
      revised, so this is a fair test rather than a flattering one. Verdict:
      <b>{verdict}</b>.</i></div>
  </section>'''
    else:
        avx_block = '''<section class="card">
    <div class="hd"><h2>Actual vs predicted</h2></div>
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
    calib_block = f'''<section class="card">
    <div class="hd"><h2>Model accuracy </h2><span class="sub">8,392 player-months across four seasons</span></div>
    <div class="chartbox">{charts.calibration_bars(CALIBRATION_DECILES)}</div>
    <div class="legend"><i>Grey is predicted, green is what actually happened, in tenths
      from weakest prediction to strongest. Equal heights would be perfect. The model
      runs about 6% hot and most so at the top &mdash; which is why the squad tables
      carry an <b>xP adj</b> column beside <b>xP</b>.</i></div>
  </section>'''

    action_panel = _action_panel(plan, squad, rates_ref or {}, gwplans, deadline_ref)
    deadline_chip = _countdown(deadline_ref) or f"GW{plan.next_gw}"
    model_chip = (f'<span class="pill warn">{_esc(plan.provider_note[:46])}</span>'
                  if plan.provider_note else '<span class="pill ok">'
                  '<span class="dot"></span>model ok</span>')
    # Which squad the plan was built on. This was silently wrong for a week — the
    # page showed a freshly solved template fifteen while the manager owned a real
    # team — so it now says so on the page rather than being inferred from the names.
    note_chip = (f'<span class="pill accent">{_esc(plan.note[:60])}</span>'
                 if getattr(plan, "note", "") else "")
    kept = getattr(plan, "kept", set())
    if kept:
        names = ", ".join(sorted(p.name for p in squad.players if p.pid in kept))
        note_chip += f'<span class="pill">keeping {_esc(names[:40])}</span>'

    warn = plan.start_note.startswith("WARNING") or "could not" in plan.start_note
    squad_chip = (f'<span class="pill {"warn" if warn else ""}">'
                  f'{_esc(plan.start_note[:60])}</span>') if plan.start_note else ''
    player_modals = _player_modals(squad, now_table, rates_ref or {})
    pitch_block = f'''<section class="card">
    <div class="hd"><h2>On the pitch</h2>
      <span class="sub">{squad.formation}, captain and vice marked</span></div>
    <div class="bd">{charts.pitch(squad.xi, squad.bench, squad.captain, squad.vice, link=True)}</div>
    <div class="ft">Numbers inside each shirt are expected points for the month. A table
      says who is in the team; this says where the money went.</div>
  </section>'''

    traj_block = (f'''<section class="card">
    <div class="hd"><h2>Season trajectory</h2>
      <span class="sub">cumulative projected points, banded by month</span></div>
    <div class="bd">{charts.season_trajectory(gwplans)}</div>
    <div class="ft">Shaded blocks are months and dots are chips. A season total is one
      number; this shows where it accumulates &mdash; the six-gameweek December block is
      the one that pays.</div>
  </section>''' if gwplans else "")

    gw_section = _gameweek_section(gwplans)
    n_months = len(plan.months)
    n_gws = len(gwplans) if gwplans else 0
    _views = league_view if isinstance(league_view, list) else (
        [league_view] if league_view is not None else [])
    league_badge = f"<b>{len(_views)}</b>" if len(_views) > 1 else (
        f"<b>{len(_views[0].with_picks)}</b>"
        if _views and _views[0].available else "")
    month_now = plan.months[0].month.name if plan.months else None
    league_section = _league_section(
        _views, [p.pid for p in squad.players],
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

    # The charset and viewport declarations matter more than they look. This file is
    # read three ways, and only one of them is an HTTP server that supplies a charset
    # header — opened from iCloud Drive on a phone it is a file:// URL with no headers
    # at all, which rendered every accented name as mojibake. Without the viewport line
    # a phone lays the page out at 980px and zooms out to fit.
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{CSS}</style>
<div class="app">
  <input class="tabin" type="radio" name="tab" id="t1" checked>
  <input class="tabin" type="radio" name="tab" id="t2">
  <input class="tabin" type="radio" name="tab" id="t3">
  <input class="tabin" type="radio" name="tab" id="t4">
  <input class="tabin" type="radio" name="tab" id="t5">

  <aside class="rail">
    <div class="brand">
      <div class="mark">FP</div>
      <div><b>{_esc(title)}</b><span>2026/27 &middot; monthly prizes</span></div>
    </div>
    <nav class="tabs">
      <div class="grp">Plan</div>
      <label for="t1"><i>&#9679;</i>Squad</label>
      <label for="t2"><i>&#9632;</i>Season<b>{n_months}</b></label>
      <label for="t3"><i>&#9642;</i>Gameweeks<b>{n_gws}</b></label>
      <div class="grp">Analysis</div>
      <label for="t4"><i>&#9650;</i>League{league_badge}</label>
      <label for="t5"><i>&#9644;</i>Charts</label>
    </nav>
    <div class="railfoot">
      Rebuilt daily from the live FPL API.<br>{_esc(plan.generated)}
    </div>
  </aside>

  <main>
    <div class="topbar">
      <h1>Gameweek {plan.next_gw}</h1>
      <span class="pill accent"><span class="dot"></span>{_esc(deadline_chip)}</span>
      <span class="pill">{rivals + 1} managers</span>
      {model_chip}{squad_chip}{note_chip}
      <span class="spacer"></span>
      <span class="pill mono">&pound;{squad.cost:.1f}m</span>
      <span class="pill">C: {_esc(cap.name if cap else "&mdash;")}</span>
    </div>

    <div class="content">
      {action_panel}

    <div class="panel p1">
  {pitch_block}

  <section class="card">
    <div class="hd"><h2>Starting XI</h2><span class="pill accent">{squad.formation}</span>
      <span class="spacer"></span><span class="sub">&pound;{squad.cost:.1f}m</span></div>
    <div class="bd flush"><div class="scroll"><table>
      <thead><tr><th></th><th>Player</th><th>Team</th><th>Pos</th><th class="r">£m</th>
        <th class="r">xP</th><th class="r" title="xP corrected for the model's measured bias — still a forecast, not an outcome">xP adj</th>
        <th>Fixtures</th></tr></thead>
      <tbody>{xi}</tbody>
    </table></div></div>
  </section>

  <section class="card">
    <div class="hd"><h2>Bench</h2><span class="sub">in substitution order</span></div>
    <div class="bd flush"><div class="scroll"><table class="bench">
      <thead><tr><th></th><th>Player</th><th>Team</th><th>Pos</th><th class="r">£m</th>
        <th class="r">xP</th><th class="r">xP adj</th><th>Fixtures</th></tr></thead>
      <tbody>{bench}</tbody>
    </table></div></div>
  </section>

    </div>

    <div class="panel p2">
  <section class="card">
    <div class="hd"><h2>Season plan</h2><span class="sub">which months to contest</span></div>
    <div class="bd flush"><div class="scroll"><table>
      <thead><tr><th>Month</th><th>GWs</th><th class="r">#</th>
        <th>Projected vs winning score</th><th>Chips &amp; fixtures</th></tr></thead>
      <tbody>{months}</tbody>
    </table></div></div>
    <div class="ft"><div class="legend">
      <i><span class="swatch"></span> your projected points</i>
      <i><span class="needle"></span> what the month's winner scores</i>
      <i>the gap between them is what a chip has to close</i>
    </div></div>
  </section>

  {dist_block}
    </div>

    <div class="panel p3">
  {gw_section}

  {traj_block}
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

  <section class="card">
    <div class="hd"><h2>How to read this</h2></div>
    <div class="bd">
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
    </ul></div>
  </section>

  <footer style="color:var(--mut);font-size:12px;border-top:1px solid var(--line);padding-top:14px">
    Built from the live FPL API. Validated by walk-forward backtest across four
    completed seasons under real transfer rules. Expected points are estimates, not
    predictions.
  </footer>
    </div>
  </main>
</div>
{player_modals}
"""


def write(plan: SeasonPlan, path: str, rivals: int = 19,
          title: str = "FPL monthly plan", gwplans=None, league_view=None,
          boot_ref=None, fixtures_ref=None, rates_ref=None,
          deadline_ref="") -> str:
    # Create the parent directory. Writing beside an existing file works everywhere,
    # so this only bites when the output goes somewhere new — which is exactly what
    # CI does, publishing to site/index.html on a fresh checkout.
    import os

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(render(plan, rivals=rivals, title=title, gwplans=gwplans,
                        league_view=league_view, boot_ref=boot_ref,
                        fixtures_ref=fixtures_ref, rates_ref=rates_ref,
                        deadline_ref=deadline_ref))
    return path
