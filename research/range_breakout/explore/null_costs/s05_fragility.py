"""Which configs are cost-fragile? (IS only)
1. stop-size sweep (range-width stops and ATR stops, with/without TP 2R) at default costs vs frictionless.
2. default trades bucketed by range width / ATR and by range width in USD: gross vs net R and cost in R.
3. narrow-range filter (max_w_atr) at default vs frictionless."""
import numpy as np
import pandas as pd
import common as C
import null as N

E = C.E
D = E.load()
D0 = C.spread_scaled(D, 0.0)

already = {("sl0", 1.0, 0.0), ("sl0", 0.5, 2.0), ("sl0", 2.0, 0.0)}   # counted in s03 (x2 costs)
new_cfg = 0
rows = []
sweeps = [("sl0", k, 0.0) for k in (0.25, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)] + \
         [("sl0", k, 2.0) for k in (0.25, 0.5, 1.0, 2.0)] + \
         [("sl1", k, 0.0) for k in (0.1, 0.2, 0.35, 0.5, 1.0)]
for ref, k, tp in sweeps:
    p = E.Params(sl_ref=0 if ref == "sl0" else 1, sl_k=k, tp_r=tp)
    pf = E.Params(**{**p.to_dict(), "commission": 0.0, "slip": 0.0})
    if (ref, k, tp) not in already:
        new_cfg += 2
        C.log_config(f"fragility {ref} k={k} tp={tp}", p, False, "IS only")
        C.log_config(f"fragility {ref} k={k} tp={tp} frictionless", pf, False, "IS only")
    t1 = E.run(p, end=E.IS_END, D=D)
    t0 = E.run(pf, end=E.IS_END, D=D0)
    nb = N.both_ways(p, D=D, end=E.IS_END, trades=t1)
    s1, s0 = C.s(t1), C.s(t0)
    rows.append(dict(stop=("width" if ref == "sl0" else "ATR") + f" x{k}", tp_r=tp, n=s1["n"],
                     median_risk_usd=t1.risk.median(),
                     gross_avg_R=s0["avg_R"], gross_t=s0["t_stat"], net_avg_R=s1["avg_R"], net_t=s1["t_stat"],
                     net_L=t1[t1.dir == 1].R.mean(), net_S=t1[t1.dir == -1].R.mean(),
                     cost_drag_R=s0["avg_R"] - s1["avg_R"],
                     gross_usd_per_trade=t0.pnl.mean(), net_usd_per_trade=t1.pnl.mean(),
                     dir_info_R=(nb.R_same - (nb.R_same + nb.R_flip) / 2).mean(),
                     net_PF=s1["PF"], net_maxDD=s1["maxDD_R"]))
sw = pd.DataFrame(rows)
print(C.fmt_table(sw.round(4)))
sw.to_csv(C.os.path.join(C.HERE, "out_fragility_sweep.csv"), index=False)

# 2. default trades by width/ATR and width bucket (same days in both runs)
p = E.Params()
t1 = E.run(p, end=E.IS_END, D=D)
t0 = E.run(E.Params(commission=0.0, slip=0.0), end=E.IS_END, D=D0)
spr = D["ao"][t1.i_entry.values] - D["bo"][t1.i_entry.values]
t1["nom_cost_R"] = (0.07 + spr + 0.05 * (1 + (t1.reason.values != "tp"))) / t1.risk
for col, lab in (("wa", "width/ATR"), ("width", "width USD")):
    for t in (t1, t0):
        t["wa"] = t.width / t.atr
    q = np.quantile(t1[col], [0, .2, .4, .6, .8, 1])
    q[0] -= 1e-9
    q[-1] += 1e-9
    b1 = pd.cut(t1[col], q)
    b0 = pd.cut(t0[col], q)
    g1 = t1.groupby(b1, observed=True)
    g0 = t0.groupby(b0, observed=True)
    tab = pd.DataFrame({"n": g1.size(), "median_width": g1.width.median(), "median_ATR": g1.atr.median(),
                        "gross_avg_R": g0.R.mean(), "net_avg_R": g1.R.mean(),
                        "net_L": g1.apply(lambda x: x[x.dir == 1].R.mean()),
                        "net_S": g1.apply(lambda x: x[x.dir == -1].R.mean()),
                        "nominal_cost_R": g1.nom_cost_R.mean()})
    tab.index = [f"{lab} {iv.left:.2f}-{iv.right:.2f}" for iv in tab.index]
    print()
    print(lab, "quintiles (default config, IS)")
    print(C.fmt_table(tab.reset_index().rename(columns={"index": "bucket"}).round(4)))
    tab.to_csv(C.os.path.join(C.HERE, f"out_fragility_bucket_{col}.csv"))

# 3. narrow / wide range filters
frows = []
for lo, hi in ((0.0, 0.4), (0.0, 0.6), (0.0, 0.8), (0.4, 99), (0.6, 99), (0.8, 99)):
    p = E.Params(min_w_atr=lo, max_w_atr=hi)
    pf = E.Params(min_w_atr=lo, max_w_atr=hi, commission=0.0, slip=0.0)
    new_cfg += 2
    C.log_config(f"fragility w/atr {lo}-{hi}", p, False, "IS only")
    C.log_config(f"fragility w/atr {lo}-{hi} frictionless", pf, False, "IS only")
    t1 = E.run(p, end=E.IS_END, D=D)
    t0 = E.run(pf, end=E.IS_END, D=D0)
    s1, s0 = C.s(t1), C.s(t0)
    frows.append(dict(w_atr=f"{lo}-{hi}", n=s1["n"], median_risk_usd=t1.risk.median(), gross_avg_R=s0["avg_R"],
                      gross_t=s0["t_stat"], net_avg_R=s1["avg_R"], net_t=s1["t_stat"],
                      net_L=t1[t1.dir == 1].R.mean(), net_S=t1[t1.dir == -1].R.mean(),
                      cost_drag_R=s0["avg_R"] - s1["avg_R"]))
fr = pd.DataFrame(frows)
print()
print(C.fmt_table(fr.round(4)))
fr.to_csv(C.os.path.join(C.HERE, "out_fragility_wfilter.csv"), index=False)
print("new configs in this script:", new_cfg)
