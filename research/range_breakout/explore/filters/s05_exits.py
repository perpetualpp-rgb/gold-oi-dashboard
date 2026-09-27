"""Stage 5: best filters x exit settings (tp_r x sl_k). IS only."""
import numpy as np
import pandas as pd

from common import E, Counter, md, full_summary
from features import day_features, run_mask

D = E.load()
C = Counter("s05")
f = day_features(D)

FILT = {
    "none": ({}, None),
    "w>=0.3": (dict(min_w_atr=0.3), None),
    "w>=0.3&a20<=1": (dict(min_w_atr=0.3), (f["atr_vs_mean20"] <= 1.0).values),
    "w>=0.35&a20<=1": (dict(min_w_atr=0.35), (f["atr_vs_mean20"] <= 1.0).values),
    "w>=0.3&a50<=1": (dict(min_w_atr=0.3), (f["atr_vs_mean50"] <= 1.0).values),
}
rows = []
for fname, (kw, mask) in FILT.items():
    for sl_k in (0.5, 0.75, 1.0):
        for tp in (0.0, 1.0, 2.0, 3.0):
            p = E.Params(sl_k=sl_k, tp_r=tp, **kw)
            name = f"{fname}|sl{sl_k}|tp{tp}"
            if mask is None:
                d, t = C.eval(name, p, D)
            else:
                t = run_mask(p, mask, D)
                d = {"stage": "s05", "name": name, "tag": "posthoc", **full_summary(t),
                     "params": str({"sl_k": sl_k, "tp_r": tp, **kw, "custom": fname})}
                C.rows.append(d)
            d["filter"], d["sl_k"], d["tp_r"] = fname, sl_k, tp
            rows.append(d)
df = pd.DataFrame(rows)
C.save()
cols = ["filter", "sl_k", "tp_r", "n", "avg_R", "win_rate", "PF", "t_stat", "maxDD_R", "yrs_pos",
        "L_avg_R", "L_t_stat", "S_avg_R", "S_t_stat"]
txt = md(df[cols])
print(txt)
piv = df.pivot_table(index=["sl_k", "tp_r"], columns="filter", values="t_stat").round(2)
pv = "\n\n### t_stat matrix\n\n" + md(piv.reset_index(), "{:.2f}")
piv2 = df.pivot_table(index=["sl_k", "tp_r"], columns="filter", values="avg_R").round(3)
pv += "\n\n### avg_R matrix\n\n" + md(piv2.reset_index())
print(pv)
open("out_s05_exits.txt", "w").write(f"# Stage 5 filters x exits (IS), {len(df)} configs\n\n" + txt + pv + "\n")
print("configs:", len(df))
