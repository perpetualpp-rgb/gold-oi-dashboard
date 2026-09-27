"""Stage 4: joint plateau grid of the a-priori sensible filters. IS only.

 min_w_atr {0,.25,.3,.35,.4} x vol regime {none, ATR14/SMA_n(ATR14) <= thr for n in 20,50, thr .9/1/1.1}
 then trend overlay (with-trend, N in 20/50/100) and a no-Friday overlay on a few cells.
"""
import numpy as np
import pandas as pd

from common import E, Counter, md, full_summary
from features import day_features, run_mask

D = E.load()
C = Counter("s04")
f = day_features(D)
BASE_N = 1828


def ev(name, p, mask=None, group=""):
    if mask is None:
        d, t = C.eval(name, p, D, extra={"group": group})
    else:
        t = run_mask(p, mask, D)
        d = {"stage": "s04", "name": name, "tag": "posthoc", "group": group, **full_summary(t),
             "params": str({**{k: v for k, v in p.to_dict().items() if v != E.Params().to_dict()[k]},
                            "custom": name.split("|")[1] if "|" in name else ""})}
        C.rows.append(d)
    d["keep"] = round(d["n"] / BASE_N, 3)
    return d


VOL = {"none": None}
for n in (20, 50):
    for thr in (0.9, 1.0, 1.1):
        VOL[f"atr/mean{n}<={thr}"] = (f[f"atr_vs_mean{n}"] <= thr).values

res = []
for mw in (0.0, 0.25, 0.3, 0.35, 0.4):
    for vname, m in VOL.items():
        res.append(ev(f"w>={mw}|{vname}", E.Params(min_w_atr=mw), m, "grid"))

for mw in (0.0, 0.3, 0.35):
    for vname in ("none", "atr/mean20<=1.0"):
        for tr in (20, 50, 100):
            res.append(ev(f"w>={mw}|{vname}|trend{tr}", E.Params(min_w_atr=mw, trend=tr), VOL[vname], "trend"))

for mw in (0.0, 0.3, 0.35):
    for vname in ("none", "atr/mean20<=1.0"):
        res.append(ev(f"w>={mw}|{vname}|noFri", E.Params(min_w_atr=mw, dow_mask=(1, 1, 1, 1, 0)), VOL[vname],
                      "noFri"))

df = C.save()
df = df[df.stage == "s04"]
cols = ["group", "name", "n", "keep", "avg_R", "win_rate", "PF", "t_stat", "maxDD_R", "yrs_pos",
        "L_n", "L_avg_R", "L_t_stat", "L_yrs_pos", "S_n", "S_avg_R", "S_t_stat", "S_yrs_pos"]
txt = md(df[cols])
print(txt)

# plateau view: avg_R and t in a min_w_atr x vol matrix
g = df[df.group == "grid"].copy()
g["mw"] = g.name.str.split("|").str[0]
g["vol"] = g.name.str.split("|").str[1]
piv = g.pivot(index="vol", columns="mw", values="avg_R").round(3)
pivt = g.pivot(index="vol", columns="mw", values="t_stat").round(2)
pivy = g.pivot(index="vol", columns="mw", values="yrs_pos")
pv = "\n\n### avg_R (rows vol filter, cols min_w_atr)\n\n" + md(piv.reset_index()) + \
     "\n\n### t_stat\n\n" + md(pivt.reset_index(), "{:.2f}") + "\n\n### IS years positive\n\n" + \
     md(pivy.reset_index(), "{:.0f}")
print(pv)
open("out_s04_combos.txt", "w").write(f"# Stage 4 combos (IS), {len(df)} configs\n\n" + txt + pv + "\n")
print("configs:", len(df))
