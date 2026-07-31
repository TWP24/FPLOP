"""Command line interface."""
from __future__ import annotations

import argparse
import csv
import sys

from . import api, monthly, optimise, ratings, xp

POS_NAME = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"


def _hr(char: str = "-", n: int = 78) -> str:
    return char * n


def _load(args) -> tuple[dict, list[dict], dict, dict, monthly.Month, dict]:
    boot = api.bootstrap(ttl=0 if getattr(args, "refresh", False) else 3600)
    fixtures = api.fixtures(ttl=0 if getattr(args, "refresh", False) else 3600)
    team_ratings = ratings.build(boot, fixtures, prior_weight=args.prior_weight)

    overrides = {}
    if getattr(args, "minutes_csv", None):
        overrides = _read_minutes_csv(args.minutes_csv, boot)

    rates = xp.build_rates(boot, minutes_override=overrides)
    ew = getattr(args, "empirical_weight", None)
    if ew is not None:
        for r in rates.values():
            r.emp_weight = ew
    month = monthly.resolve_month(boot, getattr(args, "month", None))
    table = monthly.build_table(boot, fixtures, rates, team_ratings, month)
    return boot, fixtures, team_ratings, rates, month, table


def _read_minutes_csv(path: str, boot: dict) -> dict[int, float]:
    """CSV of `name,minutes_per_start` (or `id,minutes_per_start`) to override the model."""
    by_name = {e["web_name"].lower(): e["id"] for e in boot["elements"]}
    out: dict[int, float] = {}
    with open(path) as fh:
        for row in csv.reader(fh):
            if not row or row[0].startswith("#"):
                continue
            key, val = row[0].strip(), float(row[1])
            pid = int(key) if key.isdigit() else by_name.get(key.lower())
            if pid is None:
                print(f"  ! minutes-csv: no player matching {key!r}", file=sys.stderr)
                continue
            out[pid] = val
    return out


# --------------------------------------------------------------------- #


def cmd_months(args) -> None:
    boot = api.bootstrap()
    fixtures = api.fixtures()
    months = monthly.get_months(boot)

    print(f"\n{BOLD}Scoring months — 2026/27{RESET}")
    print(_hr())
    print(f"{'Month':<12}{'GWs':<10}{'#':<5}{'Fixtures':<11}{'Prize weight':<14}")
    print(_hr())

    total_gws = sum(m.n_events for m in months)
    for m in months:
        counts = monthly.fixture_counts(fixtures, m)
        n_fix = sum(counts.values()) // 2
        doubles = [t for t, c in counts.items() if c > m.n_events]
        blanks = [t for t, c in counts.items() if c < m.n_events]
        share = m.n_events / total_gws
        note = ""
        if doubles:
            note += f" {len(doubles)} DGW"
        if blanks:
            note += f" {len(blanks)} BGW"
        bar = "#" * m.n_events
        print(
            f"{m.name:<12}{f'{m.start_event}-{m.stop_event}':<10}{m.n_events:<5}"
            f"{n_fix:<11}{bar:<14}{DIM}{note}{RESET}"
        )
    print(_hr())
    print(
        f"{DIM}Every month pays the same prize but they are not the same size. "
        f"A {min(m.n_events for m in months)}-gameweek month is far more{RESET}"
    )
    print(f"{DIM}volatile than a {max(m.n_events for m in months)}-gameweek one — "
          f"that asymmetry is the core edge in a monthly league.{RESET}\n")


def cmd_teams(args) -> None:
    boot, fixtures, tr, _, month, _ = _load(args)
    counts = monthly.fixture_counts(fixtures, month)

    print(f"\n{BOLD}Team ratings — {month}{RESET}")
    print(_hr())
    print(f"{'Team':<7}{'Attack':>8}{'Defence':>9}{'Net':>8}{'Fix':>6}   {'Prior wt':>9}")
    print(_hr())
    for r in sorted(tr.values(), key=lambda r: -r.net):
        print(
            f"{r.short_name:<7}{r.attack:>8.2f}{r.defence:>9.2f}{r.net:>8.2f}"
            f"{counts.get(r.team_id, 0):>6}   {r.prior_weight:>9.2f}"
        )
    print(_hr())
    print(f"{DIM}Attack/defence are multipliers on league-average goals. Defence below "
          f"1.00 concedes less.{RESET}")
    print(f"{DIM}Prior wt = share of the rating taken from FPL's own strength ratings "
          f"rather than squad data.{RESET}\n")


def cmd_players(args) -> None:
    boot, fixtures, tr, rates, month, table = _load(args)

    rows = [p for p in table.values() if p.n_fixtures > 0 and p.exp_minutes >= args.min_minutes]
    if args.position:
        want = args.position.upper()
        rows = [p for p in rows if POS_NAME[p.pos] == want]
    if args.max_price:
        rows = [p for p in rows if p.price <= args.max_price]

    key = {"xp": lambda p: -p.xp, "value": lambda p: -p.xp_per_million, "sd": lambda p: -p.sd}
    rows.sort(key=key[args.sort])

    print(f"\n{BOLD}Player outlook — {month}{RESET}  {DIM}sorted by {args.sort}{RESET}")
    print(_hr(n=92))
    print(
        f"{'Player':<16}{'Tm':<5}{'Pos':<5}{'£':>6}{'xP':>7}{'SD':>6}{'xP/£':>7}"
        f"{'Own%':>7}{'Mins':>6}  {'Fixtures':<12}"
    )
    print(_hr(n=92))
    for p in rows[: args.limit]:
        flag = " *" if "no-PL-history" in p.flags else ""
        print(
            f"{(p.name + flag)[:15]:<16}{p.team_name:<5}{POS_NAME[p.pos]:<5}{p.price:>6.1f}"
            f"{p.xp:>7.1f}{p.sd:>6.1f}{p.xp_per_million:>7.2f}{p.selected_by:>7.1f}"
            f"{p.exp_minutes:>6.0f}  {p.fdr_string:<12}"
        )
    print(_hr(n=92))
    print(f"{DIM}* no Premier League history — role inferred from price, treat with "
          f"suspicion.{RESET}")
    print(f"{DIM}Fixtures show FPL difficulty and venue, e.g. 2H = difficulty 2 at "
          f"home.{RESET}\n")


def _print_squad(s: optimise.Squad, sim_result=None, label: str = "") -> None:
    head = f"{BOLD}{label or 'Squad'}{RESET}  {DIM}risk lam={s.lam:g}{RESET}"
    print(f"\n{head}")
    print(_hr())
    print(f"{'':<3}{'Player':<16}{'Tm':<5}{'Pos':<5}{'£':>6}{'xP':>7}{'SD':>6}  {'Fixtures':<12}")
    print(_hr())
    for p in s.xi:
        mark = "(C)" if p.pid == s.captain else ("(V)" if p.pid == s.vice else "")
        print(
            f"{mark:<3}{p.name[:15]:<16}{p.team_name:<5}{POS_NAME[p.pos]:<5}{p.price:>6.1f}"
            f"{p.xp:>7.1f}{p.sd:>6.1f}  {p.fdr_string:<12}"
        )
    print(f"{DIM}{'':<3}{'-- bench --':<16}{RESET}")
    for p in s.bench:
        print(
            f"{DIM}{'':<3}{p.name[:15]:<16}{p.team_name:<5}{POS_NAME[p.pos]:<5}{p.price:>6.1f}"
            f"{p.xp:>7.1f}{p.sd:>6.1f}  {p.fdr_string:<12}{RESET}"
        )
    print(_hr())
    line = (
        f"formation {s.formation}   cost £{s.cost:.1f}m   "
        f"xP {s.xp:.1f}   SD {s.sd:.1f}"
    )
    if s.transfers:
        line += f"   transfers {s.transfers} ({s.hits} hits, -{4*s.hits})"
    print(line)
    if sim_result:
        r = sim_result
        print(
            f"simulated: mean {r.mean:.1f}  p10 {r.p10:.0f}  p90 {r.p90:.0f}  "
            f"| beat-the-field target {r.target:.0f}"
        )
        print(f"{BOLD}P(win month) {r.p_win*100:.1f}%{RESET}   P(top 3) {r.p_top3*100:.1f}%")
    print()


def _constraints(args, boot) -> optimise.Constraints:
    by_name = {e["web_name"].lower(): e["id"] for e in boot["elements"]}

    def resolve(names: list[str]) -> set[int]:
        out = set()
        for n in names or []:
            pid = int(n) if n.isdigit() else by_name.get(n.lower())
            if pid is None:
                print(f"  ! unknown player {n!r}", file=sys.stderr)
            else:
                out.add(pid)
        return out

    current: set[int] = set()
    if args.entry:
        next_ev = next((e["id"] for e in boot["events"] if e.get("is_next")), 1)
        try:
            picks = api.entry_picks(args.entry, max(next_ev - 1, 1))
            current = {p["element"] for p in picks["picks"]}
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not load entry {args.entry}: {exc}", file=sys.stderr)

    return optimise.Constraints(
        budget=args.budget,
        max_per_team=args.max_per_team,
        exclude=resolve(args.exclude),
        include=resolve(args.include),
        current_squad=current,
        free_transfers=args.free_transfers,
        max_hits=args.max_hits,
        min_expected_minutes=args.min_minutes,
    )


def cmd_template(args) -> None:
    """The squad the crowd is picking, and how it compares to the model's."""
    import copy as _copy

    boot, fixtures, tr, rates, month, table = _load(args)

    # Same optimiser, same rules, different objective: maximise total ownership rather
    # than expected points. Solving it matters — taking the most-owned players in order
    # spends the budget on premiums and then cannot fill the last few slots, which is
    # not what real managers do.
    own_table = {}
    for pid, p in table.items():
        q = _copy.copy(p)
        q.xp = p.selected_by
        own_table[pid] = q

    cons = optimise.Constraints(budget=args.budget, min_expected_minutes=0.0)
    tmpl = optimise.solve(own_table, lam=0.0, cons=cons)
    if tmpl is None:
        raise SystemExit("Could not build a legal template squad.")

    # Re-price it on expected points so the two squads are comparable.
    real = optimise.Squad(
        players=[table[p.pid] for p in tmpl.players],
        starters=tmpl.starters, captain=tmpl.captain, vice=tmpl.vice,
        lam=0.0, cost=tmpl.cost,
    )
    model = optimise.solve(table, lam=0.0, cons=cons)

    _print_squad(real, label=f"Template squad — most-owned legal fifteen, {month}")
    tset = {p.pid for p in real.players}
    mset = {p.pid for p in model.players}
    shared = tset & mset

    print(f"{BOLD}Template vs model{RESET}")
    print(_hr())
    print(f"  template : {real.xp:>6.1f} xP   £{real.cost:.1f}m   "
          f"mean ownership {sum(p.selected_by for p in real.players)/15:.1f}%")
    print(f"  model    : {model.xp:>6.1f} xP   £{model.cost:.1f}m   "
          f"mean ownership {sum(p.selected_by for p in model.players)/15:.1f}%")
    print(f"  overlap  : {len(shared)}/15 players")
    print()
    print(f"{DIM}  model picks the template does not have:{RESET}")
    for p in sorted((table[i] for i in mset - tset), key=lambda p: -p.xp):
        print(f"    {p.name[:16]:<17}{p.team_name:<5}{POS_NAME[p.pos]:<5}"
              f"£{p.price:>5.1f}  {p.xp:>5.1f} xP  {p.selected_by:>5.1f}% owned")
    print(f"{DIM}  template picks the model does not have:{RESET}")
    for p in sorted((table[i] for i in tset - mset), key=lambda p: -p.selected_by):
        print(f"    {p.name[:16]:<17}{p.team_name:<5}{POS_NAME[p.pos]:<5}"
              f"£{p.price:>5.1f}  {p.xp:>5.1f} xP  {p.selected_by:>5.1f}% owned")
    print(_hr())
    print(f"{DIM}Across three backtested seasons, following the template scored 1,976 a"
          f" season against{RESET}")
    print(f"{DIM}1,879 for the model. It is a defensible starting point, not a"
          f" compromise.{RESET}\n")


def cmd_build(args) -> None:
    boot, fixtures, tr, rates, month, table = _load(args)
    cons = _constraints(args, boot)

    lam = optimise.suggested_lam(args.rivals) if args.lam is None else args.lam
    if args.lam is None and lam > 0:
        print(f"{DIM}using risk lam={lam:g} for a {args.rivals + 1}-manager league; "
              f"see 'Why chasing differentials usually loses' in the README{RESET}")

    squad = optimise.solve(table, lam=lam, cons=cons)
    if squad is None:
        raise SystemExit("No feasible squad under those constraints.")

    result = None
    if not args.no_sim:
        from .simulate import MonthSimulator

        print(f"{DIM}simulating {args.sims} months against {args.rivals} rivals...{RESET}")
        sim = MonthSimulator(boot, fixtures, table, rates, tr, month, n_sims=args.sims)
        field = sim.build_field(args.rivals, cons)
        result = sim.evaluate(squad, field)

    _print_squad(squad, result, label=f"Best squad — {month}")


def cmd_frontier(args) -> None:
    from .simulate import MonthSimulator

    boot, fixtures, tr, rates, month, table = _load(args)
    cons = _constraints(args, boot)

    lams = [float(x) for x in args.lams.split(",")]

    # Stage 1: simulate the month and build the rival field, before choosing anything.
    print(f"{DIM}simulating {args.sims} months and building a {args.rivals}-rival "
          f"field...{RESET}")
    sim = MonthSimulator(boot, fixtures, table, rates, tr, month, n_sims=args.sims)
    field = sim.build_field(args.rivals, cons)

    # Stage 2: re-price differential risk against what the field actually owns, then
    # solve. Optimising against published ownership while being scored against this
    # field would leave the objective and the evaluation measuring different things.
    priced = sim.apply_field_ownership(table)
    own = sim.field_ownership()

    print(f"{DIM}solving {len(lams)} risk levels against measured field ownership..."
          f"{RESET}")
    squads = optimise.frontier(priced, lams, cons)
    if not squads:
        raise SystemExit("No feasible squads under those constraints.")

    results = [(s, sim.evaluate(s, field)) for s in squads]

    print(f"\n{BOLD}Risk frontier — {month}{RESET}")
    print(_hr())
    print(f"{'lam':>7}{'xP':>8}{'SD':>7}{'p10':>7}{'p90':>7}{'P(win)':>9}{'P(top3)':>9}  {'Captain':<14}")
    print(_hr())
    best = max(results, key=lambda x: x[1].p_win)
    for s, r in results:
        cap = next(p for p in s.players if p.pid == s.captain)
        mark = f"{BOLD}" if (s, r) == best else ""
        end = RESET if mark else ""
        print(
            f"{mark}{s.lam:>7g}{r.mean:>8.1f}{r.sd:>7.1f}{r.p10:>7.0f}{r.p90:>7.0f}"
            f"{r.p_win*100:>8.1f}%{r.p_top3*100:>8.1f}%  {cap.name[:13]:<14}{end}"
        )
    print(_hr())
    r0 = results[0][1]
    print(
        f"{DIM}Field: mean {r0.field_mean:.0f}, best-rival target {r0.target:.0f}. "
        f"You need the tail, not the mean.{RESET}"
    )
    hot = sorted(own.items(), key=lambda kv: -kv[1])[:6]
    if hot:
        names = ", ".join(f"{table[p].name} {o*100:.0f}%" for p, o in hot if p in table)
        print(f"{DIM}Field template: {names}{RESET}")
    _print_squad(best[0], best[1], label=f"Highest win probability — {month}")


def cmd_plan(args) -> None:
    from . import dashboard, plan as planmod

    boot = api.bootstrap(ttl=0 if args.refresh else 3600)
    fixtures = api.fixtures(ttl=0 if args.refresh else 3600)
    overrides = _read_minutes_csv(args.minutes_csv, boot) if args.minutes_csv else {}

    current: set[int] = set()
    if args.entry:
        next_ev = next((e["id"] for e in boot["events"] if e.get("is_next")), 1)
        try:
            picks = api.entry_picks(args.entry, max(next_ev - 1, 1))
            current = {p["element"] for p in picks["picks"]}
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not load entry {args.entry}: {exc}", file=sys.stderr)

    p = planmod.build(
        boot, fixtures, prior_weight=args.prior_weight, minutes_override=overrides,
        rivals=args.rivals, monthly_weight=args.monthly_weight,
        min_minutes=args.min_minutes, budget=args.budget, current_squad=current,
        start=args.start,
    )

    from . import forecast as fcmod

    gwplans = None
    if not args.no_gameweeks:
        gwplans = fcmod.build(boot, fixtures, p, budget=args.budget,
                              min_minutes=args.min_minutes)

    # Write this gameweek's prediction down before the deadline, and pull in the
    # actuals for any gameweek already played, so the model can be scored honestly.
    from . import tracking

    if p.months:
        gw_xp = p.months[0].squad_xp / max(p.months[0].n_gws, 1)
        cap = next((x.name for x in p.squad.players if x.pid == p.squad.captain), "")
        tracking.record_prediction(p.next_gw, gw_xp, captain=cap)
    if args.entry:
        tracking.fill_actuals(args.entry)

    league_views = []
    if args.league:
        from . import rivals as rvmod

        month_now = p.months[0].month.name if p.months else None
        tbl = p.tables.get(month_now, {}) if month_now else {}
        for lid in args.league:
            v = rvmod.build(lid, p.next_gw, tbl, my_entry=args.entry)
            league_views.append(v)
            state = f"{len(v.with_picks)} rivals priced" if v.available else v.note
            print(f"{DIM}league {lid} ({v.league_name}): {state}{RESET}")

    out = args.out or "plan.html"
    dashboard.write(p, out, rivals=args.rivals, title=args.title, gwplans=gwplans,
                    league_view=league_views, boot_ref=boot, fixtures_ref=fixtures,
                    rates_ref=xp.build_rates(boot),
                    deadline_ref=next((e["deadline_time"] for e in boot["events"]
                                       if e.get("is_next")), ""))
    print(f"\n{BOLD}Season plan — next deadline GW{p.next_gw}{RESET}")
    print(_hr())
    for m in p.months:
        chips = ", ".join(f"{c.chip}@GW{c.gw} +{c.value:.0f}" for c in m.chips) or "-"
        tag = f"{BOLD}TARGET{RESET}" if m.contest else "      "
        print(f"{m.month.name:<11}{m.n_gws}GW  xP {m.squad_xp:>6.0f}  "
              f"need {m.field_target:>6.0f}  {tag}  {DIM}{chips}{RESET}")
    print(_hr())
    print(f"wrote {out}\n")


def cmd_backtest(args) -> None:
    from .backtest import run_backtest

    run_backtest(args)


# --------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="fplm",
        description="Fantasy Premier League team builder optimised for monthly prizes.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, month: bool = True):
        if month:
            sp.add_argument("-m", "--month", help="Month name, e.g. August. Default: next.")
        sp.add_argument("--prior-weight", type=float, default=0.5,
                        help="Weight on FPL's own team strength vs squad data (0-1).")
        sp.add_argument("--minutes-csv", help="CSV of name,minutes_per_start overrides.")
        sp.add_argument("--refresh", action="store_true", help="Bypass the cache.")
        sp.add_argument("--min-minutes", type=float, default=25.0,
                        help="Drop players below this expected minutes per match.")
        sp.add_argument("--empirical-weight", type=float, default=None,
                        help="0-1: trust realised points per 90 over the structural "
                             "model. Default scales with each player's sample size.")

    def build_opts(sp):
        sp.add_argument("--budget", type=float, default=100.0)
        sp.add_argument("--max-per-team", type=int, default=3)
        sp.add_argument("--exclude", nargs="*", default=[])
        sp.add_argument("--include", nargs="*", default=[])
        sp.add_argument("--entry", type=int, help="Your FPL entry id, to plan transfers.")
        sp.add_argument("--free-transfers", type=int, default=1)
        sp.add_argument("--max-hits", type=int, default=0)
        sp.add_argument("--rivals", type=int, default=19,
                        help="Rivals in your monthly league (league size minus you).")
        sp.add_argument("--sims", type=int, default=10000)

    sp = sub.add_parser("months", help="Show the monthly scoring buckets and their sizes.")
    sp.set_defaults(func=cmd_months)

    sp = sub.add_parser("teams", help="Derived team attack/defence ratings.")
    common(sp)
    sp.set_defaults(func=cmd_teams)

    sp = sub.add_parser("players", help="Ranked player outlook for a month.")
    common(sp)
    sp.add_argument("--position", help="GKP/DEF/MID/FWD")
    sp.add_argument("--max-price", type=float)
    sp.add_argument("--sort", choices=["xp", "value", "sd"], default="xp")
    sp.add_argument("--limit", type=int, default=30)
    sp.set_defaults(func=cmd_players)

    sp = sub.add_parser("build", help="Optimise a squad for a month.")
    common(sp)
    build_opts(sp)
    sp.add_argument("--lam", type=float, default=None,
                    help="Risk appetite. 0 = pure expected points. "
                         "Default is chosen from league size.")
    sp.add_argument("--no-sim", action="store_true")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("template", help="The most-owned legal squad, vs the model's.")
    common(sp)
    sp.add_argument("--budget", type=float, default=100.0)
    sp.set_defaults(func=cmd_template)

    sp = sub.add_parser("frontier", help="Sweep risk appetite and rank by P(win month).")
    common(sp)
    build_opts(sp)
    sp.add_argument("--lams", default="0,0.1,0.25,0.5,1.0,2.0,4.0,8.0")
    sp.set_defaults(func=cmd_frontier)

    sp = sub.add_parser("plan", help="Whole-season plan + HTML dashboard.")
    sp.add_argument("--prior-weight", type=float, default=0.5)
    sp.add_argument("--minutes-csv")
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument("--min-minutes", type=float, default=25.0)
    sp.add_argument("--budget", type=float, default=100.0)
    sp.add_argument("--rivals", type=int, default=19)
    sp.add_argument("--entry", type=int, help="Your FPL entry id.")
    sp.add_argument("--monthly-weight", type=float, default=0.75,
                    help="1.0 plans purely for monthly prizes, 0.0 purely for the season.")
    sp.add_argument("--out", help="HTML output path (default plan.html)")
    sp.add_argument("--title", default="FPL monthly plan")
    sp.add_argument("--start", choices=["template", "xp"], default="template",
                    help="How to pick the starting squad. 'template' takes the "
                         "most-owned legal fifteen, which beat pure expected points by "
                         "184 points a season across four backtested seasons.")
    sp.add_argument("--league", type=int, nargs="*", default=[],
                    help="One or more mini-league ids, to price rivals' actual squads. "
                         "Ownership is reported per league, since it differs between them.")
    sp.add_argument("--no-gameweeks", action="store_true",
                    help="Skip the week-by-week forward plan (faster).")
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("backtest", help="Validate the model on the 2025/26 season.")
    sp.add_argument("--csv", default=None, help="Path to merged_gw CSV.")
    sp.add_argument("--from-month", type=int, default=3,
                    help="First month index to score (needs prior months to train).")
    sp.add_argument("--rivals", type=int, default=19)
    sp.add_argument("--sims", type=int, default=2000)
    sp.set_defaults(func=cmd_backtest)

    sp = sub.add_parser("clear-cache", help="Delete cached API responses.")
    sp.set_defaults(func=lambda a: print(f"removed {api.clear_cache()} cached files"))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
