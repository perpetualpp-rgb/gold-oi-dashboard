"""IS robustness for the finalists (no VAL here):
- full IS stats, long/short, by year
- cost stress: slip 0.10; spread +0.10; both
- drift-adjusted R: subtract, per trade, the unconditional IS mean move over the same London clock
  interval (entry minute -> exit minute), signed by trade direction, in R units. What is left is the
  part of the P&L that is specific to the breakout rather than to the time of day.
- plateau neighbourhood (from the grids already run, no new configs)
Output: out/finalists_is.txt
"""
import numpy as np
import pandas as pd

from common import E, data, evaluate, summarize, OUT, md_table, cost_stressed

D = data()
lmin = D["lmin"]
FIN = {
    "F1 asia00-05 ee12 ex20": E.Params(range_start=0, range_end=5, entry_end=12, exit_time=20),
    "F2 asia00-0530 ee07 ex21": E.Params(range_start=0, range_end=5.5, entry_end=7, exit_time=21),
    "F3 range02-09 ee12 ex20": E.Params(range_start=2, range_end=9, entry_end=12, exit_time=20),
    "REF default": E.Params(),
}
lines = []


def P(s=""):
    print(s)
    lines.append(str(s))


# ---- unconditional drift profile per London minute-of-day (IS bars only), in bp of price
isbar = (D["index"] >= pd.Timestamp("2014-01-01", tz="UTC")) & (D["index"] < pd.Timestamp("2022-01-01", tz="UTC"))
ii = np.nonzero(isbar)[0]
bc = D["bc"]
r1 = np.r_[np.nan, np.diff(bc)][ii] / bc[ii - 1] * 1e4
same_day = (lmin[ii] // 1440) == (lmin[ii - 1] // 1440)
mod = lmin[ii] % 1440
ok = np.isfinite(r1) & same_day
# mean bp per minute slot = sum over days / number of IS days (so missing bars count as zero move)
n_days = len(np.unique(lmin[ii] // 1440))
mu = np.bincount(mod[ok], weights=r1[ok], minlength=1440) / n_days
C = np.r_[0.0, np.cumsum(mu)]      # C[m] = expected cum bp from 00:00 to minute m


def drift_adjust(t):
    me = lmin[t.i_entry.values] % 1440
    mx = lmin[np.minimum(t.i_exit.values, len(lmin) - 1)] % 1440
    mx = np.where(mx < me, 1440, mx)
    exp_usd = t.entry.values * (C[mx] - C[me]) / 1e4
    return t.assign(R_drift=t.dir.values * exp_usd / t.risk.values)


D_slip = D
D_spr = cost_stressed(spread_add=0.10)
for name, p in FIN.items():
    P(f"\n## {name}")
    P(f"Params diff: { {k: v for k, v in p.to_dict().items() if v != getattr(E.Params(), k)} }")
    s, t = evaluate(p, tag="fin_is")
    rows = [dict(case="base", **s)]
    s2, _ = evaluate(E.Params(**{**p.to_dict(), "slip": 0.10}), tag="fin_is_slip10", stage="IS_stress")
    rows.append(dict(case="slip 0.10", **s2))
    s3, _ = evaluate(p, tag="fin_is_spr10", stage="IS_stress", D=D_spr)
    rows.append(dict(case="spread +0.10", **s3))
    s4, _ = evaluate(E.Params(**{**p.to_dict(), "slip": 0.10}), tag="fin_is_both", stage="IS_stress", D=D_spr)
    rows.append(dict(case="slip0.10+spr0.10", **s4))
    df = pd.DataFrame(rows)[["case", "n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R",
                             "L_n", "L_avg", "L_t", "S_n", "S_avg", "S_t", "yrs_pos", "worst_yr"]]
    P(md_table(df, 4))
    ta = drift_adjust(t)
    rows = []
    for d, nm in ((1, "long"), (-1, "short"), (0, "all")):
        g = ta if d == 0 else ta[ta.dir == d]
        adj = g.R - g.R_drift
        rows.append(dict(side=nm, n=len(g), avg_R=g.R.mean(), drift_R=g.R_drift.mean(), avg_R_ex_drift=adj.mean(),
                         t_ex_drift=adj.mean() / adj.std() * np.sqrt(len(g))))
    P("drift decomposition (drift_R = time-of-day drift over each trade's holding interval, IS mean profile)")
    P(md_table(pd.DataFrame(rows), 4))
    yb = E.by_year(t)
    yl = t[t.dir == 1].groupby(t.date.dt.year).R.mean().rename("L_avg")
    ys = t[t.dir == -1].groupby(t.date.dt.year).R.mean().rename("S_avg")
    P(md_table(pd.concat([yb, yl, ys], axis=1).reset_index().rename(columns={"date": "year"}), 3))

# ---- plateau neighbourhoods (re-using grid csvs; no new configs)
g = pd.concat([pd.read_csv(f"{OUT}/grid_is.csv"), pd.read_csv(f"{OUT}/grid_asia_local_is.csv")])
g = g.drop_duplicates(subset=["rs", "re", "ee", "ex"])
P("\n## plateau neighbourhoods (all configs already evaluated in the grids)")
for nm, m in (
        ("F1 nbhd: rs {-1,0,1}, re {4,4.5,5,5.5,6}, ee {9,12,13}, ex {18,20,21}",
         g.rs.isin([-1, 0, 1]) & g.re.isin([4, 4.5, 5, 5.5, 6]) & g.ee.isin([9, 12, 13]) & g.ex.isin([18, 20, 21])),
        ("F2 nbhd: rs {0,1}, re {5,5.5,6}, ee {6,7,8}, ex {18,20,21}",
         g.rs.isin([0, 1]) & g.re.isin([5, 5.5, 6]) & g.ee.isin([6, 7, 8]) & g.ex.isin([18, 20, 21])),
        ("F3 nbhd: rs {1,2}, re {8,9}, ee {11,12,13}, ex {18,20,21}",
         g.rs.isin([1, 2]) & g.re.isin([8, 9]) & g.ee.isin([11, 12, 13]) & g.ex.isin([18, 20, 21]))):
    s = g[m]
    P(f"{nm}: n_cfg={len(s)}, avg_R mean {s.avg_R.mean():+.4f}, min {s.avg_R.min():+.4f}, max {s.avg_R.max():+.4f}, "
      f"frac>0 {(s.avg_R > 0).mean():.2f}, mean t {s.t_stat.mean():.2f}, max t {s.t_stat.max():.2f}, "
      f"mean L {s.L_avg.mean():+.4f}, mean S {s.S_avg.mean():+.4f}, mean yrs_pos {s.yrs_pos.mean():.1f}")

with open(f"{OUT}/finalists_is.txt", "w") as f:
    f.write("\n".join(lines))
