"""Supplement to s01: trend-regime detail for the primary (IS+VAL only): strength buckets, year x trend,
bear-day edge without 2014, and the fallback/unfiltered comparison in strong-bull regimes."""
import numpy as np
import pandas as pd
from rcommon import summ, HERE, dump
import os
t = pd.read_csv(os.path.join(HERE, "s01_trades_primary.csv"), parse_dates=["date"])
res = {}
bins = [-9, -0.25, -0.10, 0.0, 0.10, 0.25, 0.40, 9]
t["sb"] = pd.cut(t.slope100, bins)
rows = []
for (per, b), s in t.groupby(["per", "sb"], observed=True):
    r = dict(per=per, slope_bucket=str(b), **summ(s.R.values))
    r["L"] = round(s[s.dir == 1].R.mean(), 3); r["S"] = round(s[s.dir == -1].R.mean(), 3)
    rows.append(r)
res["by_slope_bucket"] = rows
print(pd.DataFrame(rows).to_string(index=False))
rows = []
for s_b, s in t.groupby(pd.cut(t.slope100, bins), observed=True):
    rows.append(dict(slope_bucket=str(s_b), **summ(s.R.values), L=round(s[s.dir == 1].R.mean(), 3),
                     S=round(s[s.dir == -1].R.mean(), 3), years=sorted(s.year.unique().tolist())))
res["by_slope_bucket_pooled"] = rows
print(pd.DataFrame(rows).to_string(index=False))
ct = t.pivot_table(index="year", columns="trend", values="R", aggfunc=["mean", "size"]).round(3)
print(ct)
res["year_x_trend"] = ct.reset_index().to_json()
for lab, m in (("bear_IS", (t.per == "IS") & (t.trend == "bear")),
               ("bear_IS_ex2014", (t.per == "IS") & (t.trend == "bear") & (t.year != 2014)),
               ("bear_IS_ex_top3", None), ("nonbear_IS", (t.per == "IS") & (t.trend != "bear")),
               ("nonbear_IS_ex2014", (t.per == "IS") & (t.trend != "bear") & (t.year != 2014)),
               ("bull_strong_gt0.25_ISVAL", t.slope100 > 0.25), ("bull_gt0.10_ISVAL", t.slope100 > 0.10),
               ("slope_gt0_ISVAL", t.slope100 > 0), ("slope_le0_ISVAL", t.slope100 <= 0)):
    if m is None:
        R = np.sort(t[(t.per == "IS") & (t.trend == "bear")].R.values)[:-3]
    else:
        R = t[m].R.values
    res[lab] = summ(R)
    print(lab, res[lab])
# long vs short in up-slope regimes
for lab, m in (("slope>0.10", t.slope100 > 0.10), ("slope<=0.10", t.slope100 <= 0.10)):
    for d in (1, -1):
        s = t[m & (t.dir == d)]
        res[f"{lab}_dir{d}"] = summ(s.R.values)
        print(lab, d, res[f"{lab}_dir{d}"])
dump(res, "s01b_trend_detail.json")
