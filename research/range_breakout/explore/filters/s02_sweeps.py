"""Stage 2: single-filter sweeps on the default timing/stop entry. IS only. Every config is logged.

Groups:
 A comp_n x comp_max (compression, the brief's grid) + comp_min (the opposite: expansion days)
 B min_w_atr / max_w_atr bounds
 C trend x trend_mode
 D dow_mask variants
 E skip_nfp
 F custom vol-regime masks (post hoc, symmetric) from stage 1: ATR vs its trailing mean / rank, prev-day range
"""
import numpy as np
import pandas as pd

from common import E, Counter, md, full_summary
from features import day_features, run_mask

D = E.load()
C = Counter("s02")
BASE_N = len(E.run(E.Params(), end=E.IS_END, D=D))


def ev(group, name, p):
    d, t = C.eval(name, p, D, extra={"group": group})
    d["keep"] = round(d["n"] / BASE_N, 3) if d.get("n") else 0
    return d


ev("0 base", "default", E.Params())

# A: compression
for n in (10, 20, 50):
    for mx in (0.6, 0.8, 1.0, 1.2):
        ev("A comp_max", f"comp{n}<={mx}", E.Params(comp_n=n, comp_max=mx))
for n in (10, 20, 50):
    for mn in (0.8, 1.0, 1.2, 1.5):
        ev("A comp_min", f"comp{n}>={mn}", E.Params(comp_n=n, comp_min=mn))

# B: width / ATR bounds
for mn in (0.2, 0.25, 0.3, 0.35, 0.4, 0.5):
    ev("B min_w_atr", f"w_atr>={mn}", E.Params(min_w_atr=mn))
for mx in (0.3, 0.4, 0.5, 0.6, 0.8, 1.0):
    ev("B max_w_atr", f"w_atr<={mx}", E.Params(max_w_atr=mx))
for mn in (0.25, 0.3, 0.35):
    for mx in (0.6, 0.8, 1.0):
        ev("B band", f"{mn}<=w_atr<={mx}", E.Params(min_w_atr=mn, max_w_atr=mx))

# C: trend
for n in (20, 50, 100, 200):
    for m in (0, 1):
        ev("C trend", f"trend{n}_{'with' if m == 0 else 'against'}", E.Params(trend=n, trend_mode=m))

# D: day of week
names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
for k in range(5):
    mask = tuple(0 if j == k else 1 for j in range(5))
    ev("D dow_excl", f"no_{names[k]}", E.Params(dow_mask=mask))
for k in range(5):
    mask = tuple(1 if j == k else 0 for j in range(5))
    ev("D dow_only", f"only_{names[k]}", E.Params(dow_mask=mask))
ev("D dow", "Tue-Thu", E.Params(dow_mask=(0, 1, 1, 1, 0)))
ev("D dow", "no_Wed_Fri(data-mined)", E.Params(dow_mask=(1, 1, 0, 1, 0)))

# E: NFP
ev("E nfp", "skip_nfp", E.Params(skip_nfp=True))

# F: custom vol-regime masks (post hoc on default trades; symmetric day masks)
f = day_features(D)
base_p = E.Params()
custom = []
for thr in (0.2, 0.33, 0.5):
    custom.append(("F atr_rank250", f"atr_rank250<={thr}", f["atr_rank250"] <= thr))
for n in (20, 50, 100):
    for thr in (0.9, 1.0, 1.1):
        custom.append(("F atr_vs_mean", f"atr/mean{n}<={thr}", f[f"atr_vs_mean{n}"] <= thr))
for thr in (0.8, 1.0):
    custom.append(("F prevday", f"prevday_rng/atr<={thr}", f["prevday_rng_atr"] <= thr))
for grp, name, m in custom:
    t = run_mask(base_p, m.fillna(False).values, D)
    d = {"stage": "s02", "name": name, "tag": "posthoc", "group": grp}
    d.update(full_summary(t))
    d["params"] = f"default + custom mask {name}"
    d["keep"] = round(d["n"] / BASE_N, 3)
    C.rows.append(d)

df = C.save()
df = df[df.stage == "s02"]
cols = ["group", "name", "n", "keep", "avg_R", "win_rate", "PF", "t_stat", "maxDD_R", "yrs_pos",
        "L_n", "L_avg_R", "L_t_stat", "S_n", "S_avg_R", "S_t_stat"]
txt = md(df[cols], "{:.3f}")
print(txt)
with open("out_s02_sweeps.txt", "w") as fh:
    fh.write(f"# Stage 2 single-filter sweeps (IS 2014-2021), {len(df)} configs\n\n" + txt + "\n")
print("configs in s02:", len(df))
