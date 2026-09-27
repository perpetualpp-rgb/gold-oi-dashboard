"""Stage 1: descriptive conditional analysis of the DEFAULT config's IS trades (one engine run).

Buckets IS trades by day features and reports avg_R / n / t per bucket, separately for longs and shorts.
Also: per-year Spearman correlation of continuous features vs R (sign consistency), and an estimate of
cost in R per bucket (narrow ranges pay proportionally more costs).
Counts as 1 config (the default) -- buckets are descriptive, not tested configs.
"""
import numpy as np
import pandas as pd

from common import E, run_is, IS_YEARS, md


class _Sp:
    def __init__(self, v):
        self.statistic = v


def spearmanr(a, b):
    return _Sp(pd.Series(np.asarray(a)).rank().corr(pd.Series(np.asarray(b)).rank()))

D = E.load()
p = E.Params()
t = run_is(p, D)
days = D["days"]
print("default IS:", E.stats(t))

# ---- day-level features (all causal: as of end of previous London day, or the finished range) ----
i_rs, i_re, i_ee, i_ex, rh, rl, valid, _ = E._windows_full(D, p.range_start, p.range_end, p.entry_end,
                                                           p.exit_time)
width = rh - rl
atr = days["atr14_prev"].values
cp = days["close_prev"].values
f = pd.DataFrame(index=np.arange(len(days)))
f["w_atr"] = width / atr
for n in (10, 20, 50):
    med = pd.Series(width).rolling(n, min_periods=max(5, n // 2)).median().shift(1).values
    f[f"comp{n}"] = width / med
f["atr_pct_price"] = atr / cp * 100                                     # vol level normalised by price
# causal percentile of ATR14 vs its own trailing 250 trading days (vol regime)
atr_s = pd.Series(atr)
f["atr_rank250"] = atr_s.rolling(250, min_periods=120).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True).values
# ATR trend: ATR14 vs its 50-day mean (rising / falling vol)
f["atr_vs_mean50"] = atr / atr_s.rolling(50, min_periods=30).mean().values
for n in (20, 50, 100, 200):
    f[f"up{n}"] = np.where(np.isfinite(days[f"sma{n}_prev"].values), (cp > days[f"sma{n}_prev"].values), np.nan)
f["dow"] = days.index.dayofweek.values
f["month"] = days.index.month.values
f["nfp"] = ((f["dow"] == 4) & (days.index.day.values <= 7)).astype(int)
# previous day: range / ATR and direction (close vs open)
prev_rng = (days["h"] - days["l"]).shift(1).values
f["prevday_rng_atr"] = prev_rng / atr
f["prevday_dir"] = np.sign((days["c"] - days["o"]).shift(1).values)
f["width_pct"] = width / cp * 100

tt = t.join(f, on="day")
# approximate cost in R: spread at entry bar + 2 x slip + commission
spr = D["ao"][t["i_entry"].values] - D["bo"][t["i_entry"].values]
tt["cost_R"] = (spr + 2 * p.slip + p.commission) / t["risk"].values
tt["grossR"] = tt["R"] + tt["cost_R"]
tt["year"] = tt["date"].dt.year


def tstat(r):
    return r.mean() / r.std(ddof=1) * np.sqrt(len(r)) if len(r) > 2 and r.std(ddof=1) > 0 else np.nan


def bucket_table(col, bins=None, q=5, labels=None):
    x = tt[col]
    if bins == "cat":
        b = x
    elif bins is not None:
        b = pd.cut(x, bins)
    else:
        b = pd.qcut(x, q, duplicates="drop")
    rows = []
    for key, g in tt.groupby(b, observed=True):
        r = {"bucket": str(key), "n": len(g), "avgR": g.R.mean(), "t": tstat(g.R), "grossR": g.grossR.mean(),
             "costR": g.cost_R.mean()}
        for d, nm in ((1, "L"), (-1, "S")):
            gg = g[g.dir == d]
            r[f"n_{nm}"] = len(gg)
            r[f"avgR_{nm}"] = gg.R.mean()
            r[f"t_{nm}"] = tstat(gg.R)
        yr = g.groupby("year").R.sum().reindex(IS_YEARS, fill_value=0)
        r["yrs_pos"] = int((yr > 0).sum())
        rows.append(r)
    out = pd.DataFrame(rows)
    return out.round(3)


def yearly_split(col):
    """Mean R in the upper half minus the lower half of the feature (IS median split), overall and per
    year (how many of 8 years the sign agrees). Welch t for the overall difference."""
    res = {}
    for d, nm in ((0, "all"), (1, "L"), (-1, "S")):
        sub = tt if d == 0 else tt[tt.dir == d]
        sub = sub[np.isfinite(sub[col])]
        med = sub[col].median()
        hi, lo = sub[sub[col] > med].R, sub[sub[col] <= med].R
        diff = hi.mean() - lo.mean()
        se = np.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
        yrs = []
        for _, g in sub.groupby("year"):
            yrs.append(g[g[col] > med].R.mean() - g[g[col] <= med].R.mean())
        res[nm] = f"hi-lo={diff:+.3f}R (t={diff / se:+.2f}, same sign {sum(np.sign(y) == np.sign(diff) for y in yrs)}/{len(yrs)} yrs)"
    return res


out = []
sections = [
    ("width / ATR14 quintile", "w_atr", None),
    ("compression width/median(prior 10d) quintile", "comp10", None),
    ("compression width/median(prior 20d) quintile", "comp20", None),
    ("compression width/median(prior 50d) quintile", "comp50", None),
    ("ATR14 / price (%) quintile (vol level)", "atr_pct_price", None),
    ("ATR14 rank vs trailing 250d (causal vol regime) quintile", "atr_rank250", None),
    ("ATR14 / mean ATR14 50d (vol rising/falling) quintile", "atr_vs_mean50", None),
    ("prev-day range / ATR quintile", "prevday_rng_atr", None),
    ("range width as % of price quintile", "width_pct", None),
]
for title, col, bins in sections:
    tab = bucket_table(col, bins)
    sp = yearly_split(col)
    txt = f"\n### {title}\nMedian split: {sp}\n\n" + md(tab)
    print(txt)
    out.append(txt)

# categorical
tt["dow_name"] = tt["dow"].map(dict(enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"])))
for title, col in (("day of week", "dow"), ("month", "month"), ("NFP Friday (first Friday of month)", "nfp")):
    tab = bucket_table(col, "cat")
    txt = f"\n### {title}\n\n" + md(tab)
    print(txt)
    out.append(txt)

# NFP vs other Fridays
fri = tt[tt.dow == 4].copy()
rows = []
for key, g in fri.groupby("nfp"):
    rows.append({"bucket": "NFP Fri" if key else "other Fri", "n": len(g), "avgR": g.R.mean(), "t": tstat(g.R),
                 "avgR_L": g[g.dir == 1].R.mean(), "avgR_S": g[g.dir == -1].R.mean()})
txt = "\n### Fridays: NFP vs other\n\n" + md(pd.DataFrame(rows).round(3))
print(txt)
out.append(txt)

# trend state: with-trend vs against-trend per direction
rows = []
for n in (20, 50, 100, 200):
    up = tt[f"up{n}"]
    ok = np.isfinite(up)
    with_tr = ok & (((tt.dir == 1) & (up == 1)) | ((tt.dir == -1) & (up == 0)))
    against = ok & ~with_tr
    for lab, m in (("with", with_tr), ("against", against)):
        g = tt[m]
        yr = g.groupby("year").R.sum().reindex(IS_YEARS, fill_value=0)
        rows.append({"sma": n, "side": lab, "n": len(g), "avgR": g.R.mean(), "t": tstat(g.R),
                     "n_L": (g.dir == 1).sum(), "avgR_L": g[g.dir == 1].R.mean(),
                     "n_S": (g.dir == -1).sum(), "avgR_S": g[g.dir == -1].R.mean(), "yrs_pos": int((yr > 0).sum())})
txt = "\n### trend state (prev close vs SMA_N): trades with vs against trend\n\n" + \
      md(pd.DataFrame(rows).round(3))
print(txt)
out.append(txt)

# prev-day direction relative to trade direction (momentum continuation)
tt["prev_same"] = np.where(tt.prevday_dir == 0, np.nan, (tt.prevday_dir == tt.dir).astype(float))
tab = bucket_table("prev_same", "cat")
txt = "\n### previous day direction same as breakout direction (1) or opposite (0)\n\n" + md(tab)
print(txt)
out.append(txt)

# how many days does each quintile of w_atr represent / what share of trades end in each exit reason
rows = []
for key, g in tt.groupby(pd.qcut(tt.w_atr, 5), observed=True):
    rows.append({"w_atr_q": str(key), **(g.reason.value_counts(normalize=True).round(3).to_dict()),
                 "med_risk_usd": g.risk.median()})
txt = "\n### exit reasons by width/ATR quintile\n\n" + md(pd.DataFrame(rows))
print(txt)
out.append(txt)

with open("out_s01_conditional.md", "w") as fh:
    fh.write("# Stage 1: conditional analysis of default IS trades\n\n")
    fh.write(f"default IS: {E.stats(t)}\n")
    fh.write("\n".join(out))
tt.to_pickle("s01_trades.pkl")
