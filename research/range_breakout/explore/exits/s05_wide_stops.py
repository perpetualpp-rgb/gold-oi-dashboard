"""Extension: wider stops than the brief's grid (net avg_R rose monotonically with stop width).
ATR {1,1.5,2,3}, W {2,3}, x tp {0,3} x be {0,1} x trail {0,1.5,2} x exit {18,20,21}; net + gross. IS only.
Also reports the sizing view: avg pnl in ATR units (constant-vol sizing) vs R (fixed-fractional)."""
import itertools
import numpy as np
import pandas as pd
import common as C
import engine as E

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 300)
D = C.data()
D0 = C.cost_stressed(0.0)
for k in ("ao", "ah", "al", "ac"):
    D0[k] = D["b" + k[1]].copy()
STOPS = [(1, 1.0), (1, 1.5), (1, 2.0), (1, 3.0), (0, 2.0), (0, 3.0)]
rows = []
for mode in ("net", "gross"):
    for (sr, sk), tp, be, tr, ex in itertools.product(STOPS, [0, 3], [0, 1], [0, 1.5, 2], [18, 20, 21]):
        kw = dict(sl_ref=sr, sl_k=sk, tp_r=tp, be_r=be, trail_r=tr, exit_time=float(ex))
        if mode == "gross":
            kw.update(commission=0.0, slip=0.0)
        t = C.run_is(E.Params(**kw), D=(D if mode == "net" else D0), tag=f"s05_{mode}")
        d = C.full_summ(t)
        d.update(mode=mode, sl_ref=sr, sl_k=sk, tp_r=tp, be_r=be, trail_r=tr, exit_time=ex)
        rows.append(d)
X = pd.DataFrame(rows)
X.to_csv(C.OUT + "/s05_wide.csv", index=False)
K = ["sl_ref", "sl_k", "tp_r", "be_r", "trail_r", "exit_time"]
J = X[X["mode"] == "net"].set_index(K).join(X[X["mode"] == "gross"].set_index(K)[["avg_R", "t_stat"]], rsuffix="_g").reset_index()
J["cost_R"] = J.avg_R_g - J.avg_R
cols = K + ["n", "avg_R", "win_rate", "PF", "t_stat", "maxDD_R", "yrs_pos", "L_avg_R", "L_t", "S_avg_R", "S_t", "skew", "sh_sl", "sh_time", "avg_pnl_atr", "avg_R_g", "t_stat_g", "cost_R"]
print("net t>1:", (J.t_stat > 1).sum(), "max t", J.t_stat.max())
print(J.groupby(["sl_ref", "sl_k"]).agg(net_avgR=("avg_R", "mean"), net_t=("t_stat", "mean"), net_tmax=("t_stat", "max"),
      g_avgR=("avg_R_g", "mean"), g_t=("t_stat_g", "mean"), cost=("cost_R", "mean"), sh_sl=("sh_sl", "mean"), yrs=("yrs_pos", "mean")).round(3).to_string())
print(J.sort_values("t_stat", ascending=False)[cols].head(20).to_string(index=False))
m = (J.tp_r == 0) & (J.be_r == 0) & (J.trail_r == 0) & (J.exit_time == 20)
print(J[m][cols].to_string(index=False))
