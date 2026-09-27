"""Analysis of the s02 grid (no new engine runs): marginal effects, plateau of the best net configs,
cost ratio (gross/cost) and distribution reshaping."""
import numpy as np
import pandas as pd
import common as C

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50); pd.set_option("display.max_rows", 300)
G = pd.read_csv(C.OUT + "/s02_grid.csv")
K = ["sl_ref", "sl_k", "tp_r", "be_r", "trail_r", "exit_time"]
N = G[G["mode"] == "net"].set_index(K)
S = G[G["mode"] == "gross"].set_index(K)
J = N.join(S[["avg_R", "t_stat", "n"]], rsuffix="_g").reset_index()
J["cost_R"] = J.avg_R_g - J.avg_R
J["stop"] = J.sl_ref.map({0: "W", 1: "ATR", 2: "OPP"}) + J.sl_k.astype(str)
out = []
def pr(s=""):
    print(s); out.append(str(s))

pr("## counts: net configs %d, gross %d" % (len(N), len(S)))
pr("net t>0: %d, t>1: %d, t>2: %d ; avg_R>0: %d ; max t %.2f" % ((J.t_stat > 0).sum(), (J.t_stat > 1).sum(), (J.t_stat > 2).sum(), (J.avg_R > 0).sum(), J.t_stat.max()))
pr("gross t>2: %d of %d, min %.2f max %.2f" % ((J.t_stat_g > 2).sum(), len(J), J.t_stat_g.min(), J.t_stat_g.max()))
pr("gross/cost ratio (gross avg_R / cost_R): median %.2f max %.2f" % ((J.avg_R_g / J.cost_R).median(), (J.avg_R_g / J.cost_R).max()))
for k in ["stop", "tp_r", "be_r", "trail_r", "exit_time"]:
    g = J.groupby(k).agg(net_avgR=("avg_R", "mean"), net_t=("t_stat", "mean"), net_t_max=("t_stat", "max"),
                         gross_avgR=("avg_R_g", "mean"), gross_t=("t_stat_g", "mean"), cost_R=("cost_R", "mean"),
                         win=("win_rate", "mean"), skew=("skew", "mean"), yrs_pos=("yrs_pos", "mean")).round(3)
    pr(f"\n## marginal over the rest of the grid: {k}")
    pr(g.to_string())

# plateau: for each net config, mean t of its grid neighbours (+-1 step on each axis, same stop family)
AX = {"tp_r": [0, 1, 1.5, 2, 3, 4], "be_r": [0, 0.5, 1], "trail_r": [0, 0.5, 1, 1.5, 2], "exit_time": [14, 16, 18, 20, 21]}
SK = {0: [0.5, 0.75, 1.0, 1.5], 1: [0.15, 0.25, 0.35, 0.5, 0.75], 2: [1.0]}
Ji = J.set_index(K)
def neigh(r):
    res = []
    for ax, vals in list(AX.items()) + [("sl_k", SK[r.sl_ref])]:
        j = vals.index(getattr(r, ax))
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(vals):
                key = tuple(vals[jj] if a == ax else getattr(r, a) for a in K)
                if key in Ji.index:
                    res.append(Ji.loc[key, "t_stat"])
    return np.mean(res), np.min(res), len(res)
top = J.sort_values("t_stat", ascending=False).head(25).copy()
nb = [neigh(r) for r in top.itertuples()]
top["nb_mean_t"] = [round(x[0], 2) for x in nb]; top["nb_min_t"] = [round(x[1], 2) for x in nb]; top["nb_n"] = [x[2] for x in nb]
cols = K + ["n", "avg_R", "win_rate", "PF", "t_stat", "maxDD_R", "yrs_pos", "L_avg_R", "L_t", "S_avg_R", "S_t", "skew", "avg_R_g", "t_stat_g", "cost_R", "nb_mean_t", "nb_min_t", "nb_n"]
pr("\n## top 25 net configs by t with neighbour plateau")
pr(top[cols].to_string(index=False))
top[cols].to_csv(C.OUT + "/s03_top25.csv", index=False)

# distribution reshaping at the default stop (W1.0), exit 20
m = (J.sl_ref == 0) & (J.sl_k == 1.0) & (J.exit_time == 20)
pr("\n## default stop (1 x width), exit 20: how exits reshape the R distribution")
c2 = ["tp_r", "be_r", "trail_r", "avg_R", "t_stat", "win_rate", "PF", "skew", "med_R", "maxDD_R", "sh_sl", "sh_tp", "sh_trail", "sh_time",
      "sumR_sl", "sumR_tp", "sumR_trail", "sumR_time", "posR_tp", "posR_trail", "posR_time", "avg_R_g", "t_stat_g"]
pr(J[m][c2].to_string(index=False))
J[m][c2].to_csv(C.OUT + "/s03_reshape_W1_ex20.csv", index=False)
# spread of net avg_R vs gross avg_R within one stop: does exit choice change the mean?
pr("\n## within each stop: range of avg_R across the 450 exit combos (net and gross)")
pr(J.groupby("stop").agg(net_min=("avg_R", "min"), net_med=("avg_R", "median"), net_max=("avg_R", "max"),
                         g_min=("avg_R_g", "min"), g_med=("avg_R_g", "median"), g_max=("avg_R_g", "max"),
                         gt_med=("t_stat_g", "median"), cost=("cost_R", "median"), risk_usd=("avg_risk_usd", "median")).round(4).to_string())
with open(C.OUT + "/s03_grid_analysis.txt", "w") as f:
    f.write("\n".join(out))
