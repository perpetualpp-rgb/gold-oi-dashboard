"""Check C: volatility compression -> expansion (Crabel NR4/NR7) vs 'higher volatility state -> better ORB'
(Lundstrom 2014), on the engine-default Asian session (range 00-07 London, breaks 07-12, exit 20:00). IS only.

Two different questions, often conflated:
  (1) Does a narrow range expand more afterwards, measured in units of the range? (mechanically yes: the
      next session's range is much less variable than the Asian range, so post/W falls with W)
  (2) Does a narrow range give better DIRECTIONAL follow-through after the break (race prob > 0.5,
      ft > cost)? That is what a breakout EA needs; (1) alone only says the stop is small relative to moves,
      which also raises cost per R.
Output: out_s04_compression.txt
"""
import numpy as np
import pandas as pd

from common import tstat

T = pd.read_parquet("out/daytable.parquet")
COST_USD = 0.47
lines = []
P = lines.append

T["wa"] = T["asia_W"] / T["atr14_prev"]
T["comp20"] = T["asia_W"] / T["asia_W"].rolling(20, min_periods=10).median().shift(1)
T["nr7_asia"] = (T["asia_W"] <= T["asia_W"].rolling(7).min()).astype(float)
T["nr4_asia"] = (T["asia_W"] <= T["asia_W"].rolling(4).min()).astype(float)
T["post_W"] = T["asia_post_rng"] / T["asia_W"]
T["post_atr"] = T["asia_post_rng"] / T["atr14_prev"]
# volatility state (Lundstrom): ATR14 as % of price, relative to its trailing 250-day median
T["atr_pct"] = T["atr14_prev"] / T["p0000"]
T["volstate"] = T["atr_pct"] / T["atr_pct"].rolling(250, min_periods=120).median().shift(1)


def summarize(mask_name, m):
    x = T[m & (T["asia_dir"] != 0)]
    rc = x["asia_race1.0"]
    res = rc[rc != 0]
    p = ((res == 1).sum() + 0.5 * (res == 0.5).sum()) / max(len(res), 1)
    rc2 = x["asia_race0.5"]
    res2 = rc2[rc2 != 0]
    p2 = ((res2 == 1).sum() + 0.5 * (res2 == 0.5).sum()) / max(len(res2), 1)
    ft = x["asia_ft"]
    cw = COST_USD / x["asia_W"]
    net = ft - cw
    by = net.groupby(x["year"]).mean()
    L = x["asia_dir"] == 1
    allday = T[m]
    return dict(subset=mask_name, days=int(m.sum()), breaks=len(x),
                W_med=round(allday["asia_W"].median(), 2),
                post_over_W=round(allday["post_W"].median(), 2), post_over_ATR=round(allday["post_atr"].median(), 2),
                P0_5=round(p2, 3), P1_0=round(p, 3), z1_0=round((p - 0.5) / np.sqrt(0.25 / max(len(res), 1)), 2),
                ft=round(ft.mean(), 3), cost_W=round(cw.mean(), 3), net=round(net.mean(), 3),
                net_t=round(tstat(net.values), 2), net_L=round(net[L].mean(), 3), net_S=round(net[~L].mean(), 3),
                yrs_pos=int((by > 0).sum()))


rows = [summarize("all", np.ones(len(T), bool))]
for col, lab in [("wa", "W/ATR14"), ("comp20", "W/median20(W)"), ("volstate", "ATR%/median250(ATR%)")]:
    q = pd.qcut(T[col], 5, labels=False)
    for k in range(5):
        lo, hi = T[col][q == k].min(), T[col][q == k].max()
        rows.append(summarize(f"{lab} Q{k+1} [{lo:.2f},{hi:.2f}]", (q == k).values))
for col, lab in [("nr7_asia", "Asian NR7 (narrowest of 7)"), ("nr4_asia", "Asian NR4"),
                 ("nr7_daily_prev", "prev-day daily NR7"), ("nr4_daily_prev", "prev-day daily NR4")]:
    rows.append(summarize(f"{lab} = 1", (T[col] == 1).values))
    rows.append(summarize(f"{lab} = 0", (T[col] == 0).values))
R = pd.DataFrame(rows)
P("Check C: compression vs follow-through, Asian range 00-07 London, breaks 07-12, exit 20:00 (gross; "
  "net = ft - 0.47/W). P = race probability of +kW before -kW from the broken level (0.5 under a random walk).")
with pd.option_context("display.width", 250, "display.max_columns", 30):
    P(R.to_string(index=False))

# correlation of expansion multiple with W
P("\nSpearman corr(W/ATR, post/W) = %.3f ; corr(W/ATR, post/ATR) = %.3f" % (
    T[["wa", "post_W"]].corr(method="spearman").iloc[0, 1], T[["wa", "post_atr"]].corr(method="spearman").iloc[0, 1]))

open("out_s04_compression.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
