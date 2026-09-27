"""(b) Cost sensitivity: commission x slip x spread-multiplier grid, frictionless reference, joint cost
multiplier break-even, exact break-even extra commission, additive stress (slip 0.10, spread +0.10).
IS for everything; VAL only for the 4 base configs at default costs and frictionless (8 VAL configs)."""
import itertools
import os

import numpy as np
import pandas as pd
import common as C

E = C.E
D = E.load()
OUT = C.HERE

BASES = {
    "default": E.Params(),
    "tight_sl0.5_tp2": E.Params(sl_k=0.5, tp_r=2.0),
    "fade_tp1": E.Params(entry_mode=2, tp_r=1.0),
    "wide_sl2": E.Params(sl_k=2.0),
}
COMM = (0.0, 0.07, 0.15)
SLIP = (0.0, 0.05, 0.15, 0.30)
SPRK = (1.0, 1.5, 2.0)
MGRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)

Dk = {k: C.spread_scaled(D, k) for k in sorted(set(SPRK) | set(MGRID))}


def spread_added(D, x):
    D2 = {kk: v for kk, v in D.items() if kk != "_win_cache"}
    for c in "ohlc":
        D2["a" + c] = D["a" + c] + x
    return D2


D_add10 = spread_added(D, 0.10)

n_cfg = 0
seen = set()


def run(label, p, Dx, key):
    global n_cfg
    if key not in seen:
        seen.add(key)
        n_cfg += 1
    return E.run(p, end=E.VAL_END, D=Dx)


grid_rows, m_rows, key_rows = [], [], []
for name, p0 in BASES.items():
    # full grid (IS)
    for k, c, sl in itertools.product(SPRK, COMM, SLIP):
        p = E.Params(**{**p0.to_dict(), "commission": c, "slip": sl})
        t = run(name, p, Dk[k], (name, "grid", k, c, sl))
        ti = t[t.date <= E.IS_END]
        st = C.s(ti)
        grid_rows.append(dict(config=name, spread_k=k, comm=c, slip=sl, n=st["n"], avg_R=st["avg_R"],
                              t=st["t_stat"], PF=st["PF"],
                              avg_R_L=ti[ti.dir == 1].R.mean(), avg_R_S=ti[ti.dir == -1].R.mean()))
    # joint multiplier m: commission 0.07m, slip 0.05m, spread k=m
    for m in MGRID:
        p = E.Params(**{**p0.to_dict(), "commission": 0.07 * m, "slip": 0.05 * m})
        t = run(name, p, Dk[m], (name, "grid", m, round(0.07 * m, 6), round(0.05 * m, 6)))
        ti = t[t.date <= E.IS_END]
        m_rows.append(dict(config=name, m=m, n=len(ti), avg_R=ti.R.mean(),
                           avg_R_L=ti[ti.dir == 1].R.mean(), avg_R_S=ti[ti.dir == -1].R.mean()))

grid = pd.DataFrame(grid_rows)
mdf = pd.DataFrame(m_rows)
grid.to_csv(os.path.join(OUT, "out_cost_grid.csv"), index=False)
mdf.to_csv(os.path.join(OUT, "out_cost_mgrid.csv"), index=False)


def be_interp(x, y):
    """first x where y crosses 0 going down (linear interpolation); inf if always >0, 0 if <=0 at start."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if y[0] <= 0:
        return 0.0
    for i in range(1, len(x)):
        if y[i] <= 0:
            return x[i - 1] + (x[i] - x[i - 1]) * y[i - 1] / (y[i - 1] - y[i])
    return np.inf


summ = []
for name, p0 in BASES.items():
    t1 = run(name, p0, D, (name, "grid", 1.0, 0.07, 0.05))
    p_fr = E.Params(**{**p0.to_dict(), "commission": 0.0, "slip": 0.0})
    t0 = run(name, p_fr, Dk[0.0], (name, "grid", 0.0, 0.0, 0.0))
    p_st = E.Params(**{**p0.to_dict(), "slip": 0.10})
    ts = run(name, p_st, D_add10, (name, "stress_add"))
    C.log_config(name + "@default_costs", p0, True, "cost base, VAL checked")
    C.log_config(name + "@frictionless", p_fr, True, "spread_k=0, VAL checked")
    C.log_config(name + "@stress", p_st, False, "slip0.10 spread+0.10 IS only")
    i1 = t1[t1.date <= E.IS_END]
    i0 = t0[t0.date <= E.IS_END]
    iS = ts[ts.date <= E.IS_END]
    # nominal per-trade cost in USD at default costs
    spr = D["ao"][i1.i_entry.values] - D["bo"][i1.i_entry.values]
    slip_n = (0 if p0.entry_mode == 2 else 1) + (i1.reason.values != "tp").astype(int)
    nom_usd = p0.commission + spr + p0.slip * slip_n
    nom_R = nom_usd / i1.risk.values
    inv_risk = (1 / i1.risk.values).mean()
    be_extra_comm = i1.R.mean() / inv_risk            # exact: extra round-trip USD/oz that zeroes IS avg_R
    be_extra_comm_gross = i0.R.mean() / (1 / i0.risk.values).mean()
    mm = mdf[mdf.config == name]
    m_star = be_interp(mm.m.values, mm.avg_R.values)
    mL = be_interp(mm.m.values, mm.avg_R_L.values)
    mS = be_interp(mm.m.values, mm.avg_R_S.values)
    # break-even slip (comm .07, spread 1x) and spread multiplier (comm .07, slip .05) from the grid
    g = grid[(grid.config == name)]
    gs = g[(g.spread_k == 1.0) & (g.comm == 0.07)].sort_values("slip")
    gk = g[(g.comm == 0.07) & (g.slip == 0.05)].sort_values("spread_k")
    summ.append(dict(
        config=name, n_IS=len(i1),
        gross_avg_R=i0.R.mean(), gross_L=i0[i0.dir == 1].R.mean(), gross_S=i0[i0.dir == -1].R.mean(),
        net_avg_R=i1.R.mean(), net_L=i1[i1.dir == 1].R.mean(), net_S=i1[i1.dir == -1].R.mean(),
        stress_avg_R=iS.R.mean(),
        cost_drag_R=i0.R.mean() - i1.R.mean(), nominal_cost_R=nom_R.mean(), nominal_cost_R_median=np.median(nom_R),
        nominal_cost_usd=nom_usd.mean(), median_risk_usd=np.median(i1.risk.values),
        m_star=m_star, m_star_L=mL, m_star_S=mS,
        be_rt_cost_usd=m_star * nom_usd.mean() if np.isfinite(m_star) else np.inf,
        be_extra_comm_usd=be_extra_comm, be_rt_cost_from_gross_usd=be_extra_comm_gross,
        be_slip=be_interp(gs.slip.values, gs.avg_R.values) if gs.avg_R.values[0] > 0 else (0.0 if gs.avg_R.values[0] <= 0 else np.nan),
        be_spread_k=be_interp(gk.spread_k.values - 1.0, gk.avg_R.values) + 1.0 if gk.avg_R.values[0] > 0 else np.nan,
    ))
    # key rows: IS/VAL, long/short at default and frictionless (VAL 2 configs each)
    for lab, t in (("frictionless", t0), ("default", t1), ("stress", ts)):
        ss = C.split_stats(t)
        for per in (("IS", "VAL") if lab != "stress" else ("IS",)):
            for side, key in (("all", per), ("long", per + "_L"), ("short", per + "_S")):
                r = dict(config=name, costs=lab, period=per, side=side, **ss[key])
                if side == "all":
                    r["yrs_pos"] = ss[per + "_yrs_pos"]
                key_rows.append(r)

S = pd.DataFrame(summ)
K = pd.DataFrame(key_rows)
S.to_csv(os.path.join(OUT, "out_cost_summary.csv"), index=False)
K.to_csv(os.path.join(OUT, "out_cost_keyrows.csv"), index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
print(S.round(4).T.to_string())
print()
print(C.fmt_table(K.round(4)))
print()
for name in BASES:
    g = grid[grid.config == name].pivot_table(index=["spread_k", "slip"], columns="comm", values="avg_R")
    print(name)
    print(g.round(4).to_string())
print()
print(mdf.pivot_table(index="m", columns="config", values="avg_R").round(4).to_string())
print("configs evaluated in this script:", n_cfg)
