"""Stage 9: pooled 2014-2023 view + by-year table for the SAME finalists already checked in s07
(no new VAL configs, no tuning). Never touches 2024+."""
import numpy as np
import pandas as pd
from common import E, md, summ
from features import day_features

D = E.load()
f = day_features(D)
a20 = (f["atr_vs_mean20"] <= 1.0).values
FIN = [("REF default", E.Params(), None), ("F4 w>=0.35", E.Params(min_w_atr=0.35), None),
       ("F1 w>=0.3&a20<=1", E.Params(min_w_atr=0.3), a20), ("F2 w>=0.35&a20<=1", E.Params(min_w_atr=0.35), a20)]
rows, yrows = [], []
for name, p, m in FIN:
    t = E.run(p, end=E.VAL_END, D=D)
    if m is not None:
        t = t[m[t["day"].values]]
    assert t.date.max() <= pd.Timestamp(E.VAL_END)
    rows.append({"name": name, **summ(t), **summ(t[t.dir == 1], "L_"), **summ(t[t.dir == -1], "S_")})
    y = t.groupby(t.date.dt.year).R
    yrows.append({"name": name, **{str(k): round(v, 3) for k, v in y.mean().items()}})
cols = ["name", "n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R", "L_n", "L_avg_R", "L_t_stat",
        "S_n", "S_avg_R", "S_t_stat"]
txt = "## pooled 2014-2023 (IS+VAL)\n\n" + md(pd.DataFrame(rows)[cols]) + "\n\n## avg_R by year 2014-2023\n\n" + md(pd.DataFrame(yrows))
print(txt)
open("out_s09_pooled.txt", "w").write("# Stage 9: pooled IS+VAL for finalists already validated\n\n" + txt + "\n")
