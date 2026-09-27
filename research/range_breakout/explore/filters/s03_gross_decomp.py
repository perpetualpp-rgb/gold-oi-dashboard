"""Stage 3: is the width/ATR effect a gross edge or just lower cost-in-R?

Zero-cost dataset: ASK = BID, commission 0, slip 0. Compare the default and the w_atr / vol-regime filters
gross vs net, by year and by direction. IS only.
"""
import numpy as np
import pandas as pd

from common import E, Counter, md, full_summary, cost_D, IS_YEARS
from features import day_features, run_mask

D = E.load()
D0 = cost_D(D, 0.0)
for c in ("ao", "ah", "al", "ac"):
    D0[c] = D["b" + c[1]].copy()          # ASK = BID  -> zero spread
C = Counter("s03")
f = day_features(D)

rows = []
yrs = []
cfgs = [
    ("default", {}, None),
    ("w_atr>=0.35", dict(min_w_atr=0.35), None),
    ("w_atr<0.35", dict(max_w_atr=0.35), None),
    ("atr/mean20<=1", {}, (f["atr_vs_mean20"] <= 1.0).values),
    ("atr/mean20>1", {}, (f["atr_vs_mean20"] > 1.0).values),
    ("atr_rank250<=0.2", {}, (f["atr_rank250"] <= 0.2).values),
]
for name, kw, mask in cfgs:
    for lab, DD, cost in (("net", D, {}), ("gross", D0, dict(commission=0.0, slip=0.0))):
        p = E.Params(**kw, **cost)
        if mask is None:
            d, t = C.eval(f"{name}|{lab}", p, DD)
        else:
            t = run_mask(p, mask, DD)
            d = {"stage": "s03", "name": f"{name}|{lab}", **full_summary(t), "params": f"custom {name} {cost}"}
            C.rows.append(d)
        rows.append({"filter": name, "costs": lab, "n": d["n"], "avg_R": d["avg_R"], "t": d["t_stat"],
                     "yrs_pos": d["yrs_pos"], "L_avg_R": d["L_avg_R"], "S_avg_R": d["S_avg_R"],
                     "med_risk_usd": t["risk"].median(), "avg_pnl_usd": t["pnl"].mean()})
        y = t.groupby(t.date.dt.year).R.mean().reindex(IS_YEARS)
        yrs.append(pd.Series(y.values, index=IS_YEARS, name=f"{name}|{lab}"))
C.save()
tab = pd.DataFrame(rows)
ytab = pd.DataFrame(yrs).reset_index().rename(columns={"index": "config"})
txt = "## gross vs net (IS)\n\n" + md(tab) + "\n\n## avg R by year\n\n" + md(ytab)
print(txt)
open("out_s03_gross.txt", "w").write("# Stage 3: gross (zero-cost) vs net\n\n" + txt + "\n")
