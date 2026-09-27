"""Stage 7: VALIDATION (2022-2023) for the pre-declared finalists. <= 10 configs; logged to val_log.csv.
Never touches 2024+ (end=E.VAL_END). Primary candidate declared BEFORE this run: F1.
"""
import json
import os

import numpy as np
import pandas as pd

from common import E, md, summ, years_pos, diff_params, cost_D, VAL_LOG
from features import day_features, run_mask

D = E.load()
f = day_features(D)
a20 = (f["atr_vs_mean20"] <= 1.0).values
a50 = (f["atr_vs_mean50"] <= 1.0).values
D_sp = cost_D(D, 0.10)

FINALISTS = [
    ("REF default", E.Params(), None, D),
    ("F4 w>=0.35", E.Params(min_w_atr=0.35), None, D),
    ("F5 a20<=1", E.Params(), a20, D),
    ("F1 w>=0.3&a20<=1 [PRIMARY]", E.Params(min_w_atr=0.3), a20, D),
    ("F2 w>=0.35&a20<=1", E.Params(min_w_atr=0.35), a20, D),
    ("F3 w>=0.3&a50<=1", E.Params(min_w_atr=0.3), a50, D),
    ("F6 F1+noFri", E.Params(min_w_atr=0.3, dow_mask=(1, 1, 1, 1, 0)), a20, D),
    ("F1 stress slip0.10+spread0.10", E.Params(min_w_atr=0.3, slip=0.10), a20, D_sp),
]
assert len(FINALISTS) <= 10
if os.path.exists(VAL_LOG):
    os.remove(VAL_LOG)
rows, yrows = [], []
for name, p, mask, DD in FINALISTS:
    t = E.run(p, end=E.VAL_END, D=DD)
    if mask is not None:
        t = t[mask[t["day"].values]]
    assert t["date"].max() <= pd.Timestamp(E.VAL_END)
    ti, tv = t[t.date <= E.IS_END], t[t.date > E.IS_END]
    r = {"name": name, "params": json.dumps({**diff_params(p), **({"custom_mask": name.split()[1]} if mask is not None else {})})}
    for lab, sub in (("IS", ti), ("VAL", tv)):
        r.update(summ(sub, lab + "_"))
        r.update(summ(sub[sub.dir == 1], lab + "_L_"))
        r.update(summ(sub[sub.dir == -1], lab + "_S_"))
    r["IS_yrs_pos"] = years_pos(ti)
    rows.append(r)
    y = tv.groupby(tv.date.dt.year).R.agg(["size", "mean"])
    yrows.append({"name": name, **{f"{yy}_n": int(y.loc[yy, "size"]) for yy in y.index},
                  **{f"{yy}_avgR": round(y.loc[yy, "mean"], 3) for yy in y.index}})
df = pd.DataFrame(rows)
df.to_csv(VAL_LOG, index=False)
cols_main = ["name", "IS_n", "IS_avg_R", "IS_win_rate", "IS_PF", "IS_t_stat", "IS_trades_per_year", "IS_maxDD_R",
             "IS_yrs_pos", "VAL_n", "VAL_avg_R", "VAL_win_rate", "VAL_PF", "VAL_t_stat", "VAL_trades_per_year",
             "VAL_maxDD_R"]
cols_ls = ["name", "IS_L_n", "IS_L_avg_R", "IS_L_t_stat", "IS_S_n", "IS_S_avg_R", "IS_S_t_stat",
           "VAL_L_n", "VAL_L_avg_R", "VAL_L_t_stat", "VAL_S_n", "VAL_S_avg_R", "VAL_S_t_stat"]
txt = "## IS vs VAL\n\n" + md(df[cols_main]) + "\n\n## long / short\n\n" + md(df[cols_ls]) + \
      "\n\n## VAL by year\n\n" + md(pd.DataFrame(yrows))
print(txt)
open("out_s07_val.txt", "w").write(f"# Stage 7 VAL check ({len(FINALISTS)} configs)\n\n" + txt + "\n")
