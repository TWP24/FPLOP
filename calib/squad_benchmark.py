"""Which set of ratings builds the better squad? The comparison that decides it.

`calib/benchmark.py` scores predictions against outcomes and reports that this model
ranks worst of three. This asks the question an FPL manager actually faces — take
each model's ratings, run the same optimiser, field the squad — and gets the
opposite answer, because ranking every player rewards knowing who will not play,
and an optimiser never sees those players: the minutes floor removes them first.

Held-out weeks only, GW14-24, with GW2-13 reserved for anything needing tuning.

    ./.venv/bin/python -m calib.squad_benchmark
"""
import collections, csv, json, statistics
from pathlib import Path
from fplm import backtest as bt, monthly as mo, optimise as opt, ratings as rt, xp as xpmod

ref={}
for r in csv.DictReader(open("/tmp/openfpl.csv")):
    ref[(int(r["element"]),int(r["gw"]))]={
        "ep": float(r["ep_next"] or 0), "ofpl": float(r["openfpl_xpts"]),
        "act": float(r["actual_points"]), "mins": float(r["minutes"] or 0)}

rows=bt.load_rows(Path("data/merged_gw_2025-26.csv")); n2i=bt.team_ids(rows)
by_gw=collections.defaultdict(list)
for r in rows: by_gw[r["gw"]].append(r)

scores=collections.defaultdict(list)
for gw in range(14,25):                      # held-out weeks only
    hist=[r for r in rows if r["gw"]<gw]; fut=by_gw.get(gw,[])
    if not hist or not fut: continue
    els=bt.elements_from_history(hist,gw)
    for e in els: e["team"]=n2i.get(e["team_name"],0)
    els=[e for e in els if e["team"]]
    if len(els)<100: continue
    rates=xpmod.build_rates({"elements":els})
    tr=bt.ratings_from_results(hist,n2i)
    if not tr: continue
    fixtures,seen=[],set()
    for r in fut:
        tid=n2i.get(r["team_name"])
        if tid is None: continue
        h,a=(tid,r["opponent"]) if r["home"] else (r["opponent"],tid)
        if (h,a) in seen: continue
        seen.add((h,a)); fixtures.append({"event":gw,"team_h":h,"team_a":a,
            "team_h_difficulty":3,"team_a_difficulty":3})
    for t in ({f["team_h"] for f in fixtures}|{f["team_a"] for f in fixtures})-set(tr):
        tr[t]=rt.TeamRating(t,"","",1.0,1.0,1.0)
    boot={"elements":els,"teams":[{"id":t,"short_name":str(t)} for t in tr]}
    tbl=mo.build_table(boot,fixtures,rates,tr,mo.Month(0,f"gw{gw}",gw,gw))

    tbl={p:v for p,v in tbl.items() if (p,gw) in ref}
    if len(tbl)<200: continue
    actual={p: ref[(p,gw)]["act"] for p in tbl}

    import copy
    variants={"fplm": None, "ep_next":"ep", "openfpl":"ofpl"}
    for name,key in variants.items():
        view={}
        for p,v in tbl.items():
            q=copy.copy(v)
            if key: q.xp=ref[(p,gw)][key]
            view[p]=q
        sq=opt.solve(view, lam=0.0, cons=opt.Constraints(min_expected_minutes=20))
        if not sq: continue
        pts=sum(actual.get(p.pid,0.0) for p in sq.xi)
        pts+=max((actual.get(p.pid,0.0) for p in sq.xi if p.pid==sq.captain), default=0.0)
        scores[name].append(pts)

print("squad built fresh each gameweek from each rating source, scored on actual points")
print("held-out weeks GW14-24\n")
print(f"  {'ratings':12}{'mean pts/gw':>13}{'n':>5}")
for name in ("fplm","ep_next","openfpl"):
    v=scores[name]
    if v: print(f"  {name:12}{statistics.mean(v):13.1f}{len(v):5}")
base=scores["fplm"]
print("\n  paired against fplm:")
for name in ("ep_next","openfpl"):
    v=scores[name]
    if not v or len(v)!=len(base): continue
    d=[b-a for a,b in zip(base,v)]
    se=statistics.stdev(d)/(len(d)**0.5) if len(d)>1 else 0
    print(f"    {name:10}{statistics.mean(d):+7.2f} pts/gw (se {se:.2f}), "
          f"better in {sum(1 for x in d if x>0)}/{len(d)}")
