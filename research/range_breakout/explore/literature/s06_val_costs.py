"""Three literature leads, frozen on IS, checked for cost sensitivity on IS and then once on VAL (2022-2023).
VAL configs checked = 3 (the 3 leads at default costs). Holdout never touched (all runs end <= VAL_END).
  F1 L4 wide Asian range: Params(min_w_atr=0.39)                     (engine-native)
  F2 L2 calm regime: Params() + day filter volstate <= 0.85           (features.py)
  F3 L3 Crabel: Params() + day filter previous-day daily NR7          (features.py)
"""
import numpy as np
import pandas as pd

import common  # noqa: F401
import engine
from features import day_features

D = engine.load()
F = day_features("2024-01-01")       # features through 2023-12-31 (IS+VAL); holdout never read


def with_spread(D, add):
    D2 = {k: v for k, v in D.items() if k != "_win_cache"}
    for c in ("ao", "ah", "al", "ac"):
        D2[c] = D[c] + add
    return D2


D_sp = with_spread(D, 0.10)
LEADS = {
    "F1 min_w_atr=0.39": (dict(min_w_atr=0.39), None),
    "F2 volstate<=0.85": ({}, lambda t: t["volstate"] <= 0.85),
    "F3 prev daily NR7": ({}, lambda t: t["nr7_prev"] == 1),
    "base Params()": ({}, None),
}
COSTS = {"default": ({}, D), "slip0.10": (dict(slip=0.10), D), "spread+0.10": ({}, D_sp),
         "slip0.10+spread0.10": (dict(slip=0.10), D_sp)}

lines = []
P = lines.append


def st(t):
    s = engine.stats(t)
    by = engine.by_year(t)
    return dict(n=s["n"], tpy=s.get("trades_per_year"), avg_R=s.get("avg_R"), win=s.get("win_rate"), PF=s.get("PF"),
                t=s.get("t_stat"), maxDD=s.get("maxDD_R"), yrs_pos=f"{int((by['avg_R'] > 0).sum())}/{len(by)}",
                L_avgR=round(t.loc[t.dir == 1, "R"].mean(), 4), S_avgR=round(t.loc[t.dir == -1, "R"].mean(), 4))


rows = []
for name, (kw, filt) in LEADS.items():
    for cname, (ckw, DD) in COSTS.items():
        p = engine.Params(**{**kw, **ckw})
        t = engine.run(p, end=engine.IS_END, D=DD).join(F, on="date")
        if filt is not None:
            t = t[filt(t).values]
        rows.append(dict(lead=name, period="IS", costs=cname, **st(t)))
    # VAL once, default costs
    t = engine.run(engine.Params(**kw), start="2022-01-01", end=engine.VAL_END, D=D).join(F, on="date")
    if filt is not None:
        t = t[filt(t).values]
    rows.append(dict(lead=name, period="VAL", costs="default", **st(t)))
R = pd.DataFrame(rows)
with pd.option_context("display.width", 250, "display.max_columns", 30):
    P(R.to_string(index=False))
open("out_s06_val_costs.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
