"""Regime breakdown of the frozen primary / fallback on IS+VAL (2014-01..2023-12) only.

Outputs (final/verify_regime/):
  s01_regimes.json         all tables
  s01_trades_primary.csv   primary trades with regime labels (IS+VAL)
  s01_filter_pass_by_year.csv
  s01_rolling12m.csv, s01_rolling100.csv
"""
import numpy as np
import pandas as pd

from rcommon import E, data, cand_params, summ, gross_data, dump, HERE
import os

pd.set_option("display.width", 250)
D = data()
days = D["days"]
C = cand_params()
prim, fb = C["primary"], C["fallback"]
unf = E.Params(**{**prim.to_dict(), "min_w_atr": 0.0, "atr_regime_n": 0})   # same timing, no filters
Dg = gross_data(D)

# ---------------- causal day features (as of the end of the previous London day) ----------------
c = days["c"].values.astype(float)
lc = np.log(c)
n = len(c)
N = 100
slope = np.full(n, np.nan)          # OLS slope of log close over the 100 days ENDING YESTERDAY, annualised
tt = np.arange(N) - (N - 1) / 2
den = (tt ** 2).sum()
for d in range(N, n):
    y = lc[d - N:d]
    slope[d] = (tt * (y - y.mean())).sum() / den * 252
ret100 = np.r_[np.full(N + 1, np.nan), c[N:-1] / c[:-N - 1] - 1] if n > N + 1 else np.full(n, np.nan)
atr = days["atr14_prev"].values
cp = days["close_prev"].values
atr_pct = atr / cp * 100
atr_s = pd.Series(atr)
ma20 = atr_s.rolling(20, min_periods=12).mean().values
ma100 = atr_s.rolling(100, min_periods=60).mean().values
rank250 = atr_s.rolling(250, min_periods=120).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True).values

feat = pd.DataFrame(dict(slope100=slope, ret100=ret100, atr=atr, atr_pct=atr_pct, a_vs_m20=atr / ma20,
                         a_vs_m100=atr / ma100, rank250=rank250, close_prev=cp), index=days.index)
feat["trend"] = np.where(feat.slope100 > 0.10, "bull", np.where(feat.slope100 < -0.10, "bear", "side"))
feat.loc[~np.isfinite(feat.slope100), "trend"] = "na"

# IS-calibrated tercile cut points (so that VAL is labelled with IS thresholds)
isd = feat.index <= pd.Timestamp(E.IS_END)
cuts = {}
for col in ("atr_pct", "rank250", "a_vs_m100", "slope100"):
    q = np.nanquantile(feat.loc[isd, col], [1 / 3, 2 / 3])
    cuts[col] = q.tolist()
    feat[col + "_t"] = np.where(feat[col] <= q[0], "T1low", np.where(feat[col] <= q[1], "T2mid", "T3high"))
    feat.loc[~np.isfinite(feat[col]), col + "_t"] = "na"


def label(t):
    t = t.copy()
    f = feat.iloc[t["day"].values].reset_index(drop=True)
    for col in ("trend", "slope100", "atr_pct", "atr_pct_t", "rank250_t", "a_vs_m100_t", "slope100_t",
                "a_vs_m20", "close_prev"):
        t[col] = f[col].values
    t["per"] = np.where(t.date <= E.IS_END, "IS", "VAL")
    t["year"] = t.date.dt.year
    t["month"] = t.date.dt.month
    t["ym"] = t.date.dt.to_period("M").astype(str)
    return t


res = {"trend_def": "slope100 = OLS slope of log(close) over the 100 London days ending yesterday, x252; "
                    "bull > +0.10/yr, bear < -0.10/yr, else side",
       "tercile_cuts_IS": cuts}
T = {}
for name, p in (("primary", prim), ("fallback", fb), ("unfiltered_re5", unf)):
    t = label(E.run(p, end=E.VAL_END, D=D))
    g = label(E.run(E.Params(**{**p.to_dict(), "commission": 0.0, "slip": 0.0}), end=E.VAL_END, D=Dg))
    T[name] = t
    T[name + "_gross"] = g
T["primary"].to_csv(os.path.join(HERE, "s01_trades_primary.csv"), index=False)


def table(t, by, extra=None):
    rows = []
    keys = [by] if isinstance(by, str) else list(by)
    for k, sub in t.groupby(keys):
        r = dict(zip(keys, k if isinstance(k, tuple) else (k,)))
        r.update(summ(sub.R.values))
        r["L_avg"] = round(sub[sub.dir == 1].R.mean(), 3) if (sub.dir == 1).any() else np.nan
        r["S_avg"] = round(sub[sub.dir == -1].R.mean(), 3) if (sub.dir == -1).any() else np.nan
        r["nL"] = int((sub.dir == 1).sum())
        rows.append(r)
    return pd.DataFrame(rows)


out = {}
for name in ("primary", "fallback", "unfiltered_re5"):
    t, g = T[name], T[name + "_gross"]
    o = {}
    for by in ("trend", "slope100_t", "atr_pct_t", "rank250_t", "a_vs_m100_t"):
        tb = table(t, ["per", by])
        gb = table(g, ["per", by])[["per", by, "avg_R"]].rename(columns={"avg_R": "gross_avg_R"})
        tb = tb.merge(gb, on=["per", by], how="left")
        o[by] = tb
        print(f"\n== {name} by {by}")
        print(tb.to_string(index=False))
    # pooled IS+VAL by trend (more trades)
    o["trend_pooled"] = table(t, "trend")
    # direction x trend: with-trend vs counter-trend
    tt_ = t[t.trend.isin(["bull", "bear"])].copy()
    tt_["with_trend"] = np.where((tt_.trend == "bull") == (tt_.dir == 1), "with", "against")
    o["with_vs_against_trend"] = table(tt_, ["per", "with_trend"])
    print(f"\n== {name} with/against 100d trend (bull/bear days only)")
    print(o["with_vs_against_trend"].to_string(index=False))
    # year, month-of-year
    o["year"] = table(t, "year")
    gy = table(g, "year")[["year", "avg_R"]].rename(columns={"avg_R": "gross_avg_R"})
    o["year"] = o["year"].merge(gy, on="year")
    o["month_of_year"] = table(t, ["per", "month"])
    print(f"\n== {name} by year")
    print(o["year"].to_string(index=False))
    # calendar months
    m = t.groupby("ym").R.agg(["size", "sum"])
    o["calendar_month_stats"] = dict(n_months=int(len(m)), frac_pos=round(float((m["sum"] > 0).mean()), 3),
                                     worst_month_R=round(float(m["sum"].min()), 1),
                                     best_month_R=round(float(m["sum"].max()), 1),
                                     worst_3=m["sum"].nsmallest(3).round(1).to_dict(),
                                     best_3=m["sum"].nlargest(3).round(1).to_dict())
    # outlier dependence by year: drop the single best trade of each year / winsorise at 3R
    yr = []
    for y, sub in t.groupby("year"):
        R = sub.R.values
        yr.append(dict(year=y, avg_R=round(R.mean(), 3), drop_best=round(np.sort(R)[:-1].mean(), 3),
                       winsor3R=round(np.minimum(R, 3).mean(), 3), max_R=round(R.max(), 2)))
    o["year_outlier"] = pd.DataFrame(yr)
    print(o["year_outlier"].to_string(index=False))
    for per in ("IS", "VAL"):
        R = t[t.per == per].R.values
        o[f"{per}_outlier"] = dict(avg=round(R.mean(), 4), drop_best1=round(np.sort(R)[:-1].mean(), 4),
                                   drop_best3=round(np.sort(R)[:-3].mean(), 4),
                                   winsor3R=round(np.minimum(R, 3).mean(), 4),
                                   winsor5R=round(np.minimum(R, 5).mean(), 4),
                                   ex2014=round(t[(t.per == per) & (t.year != 2014)].R.mean(), 4))
    print(name, "outliers", o["IS_outlier"], o["VAL_outlier"])
    out[name] = o

# ---------------- rolling windows (primary + fallback) ----------------
roll = {}
for name in ("primary", "fallback"):
    t = T[name].sort_values("t_entry").reset_index(drop=True)
    m = t.groupby("ym").R.agg(["size", "sum"])
    allm = pd.period_range(t.date.min().to_period("M"), "2023-12", freq="M").astype(str)
    m = m.reindex(allm, fill_value=0)
    r12 = (m["sum"].rolling(12).sum() / m["size"].rolling(12).sum()).dropna()
    r12L = []
    for dirn in (1, -1):
        md = t[t.dir == dirn].groupby("ym").R.agg(["size", "sum"]).reindex(allm, fill_value=0)
        r12L.append((md["sum"].rolling(12).sum() / md["size"].rolling(12).sum()))
    df12 = pd.DataFrame({"avg_R_12m": r12, "n_12m": m["size"].rolling(12).sum().reindex(r12.index),
                         "long_12m": r12L[0].reindex(r12.index), "short_12m": r12L[1].reindex(r12.index)})
    df12.to_csv(os.path.join(HERE, f"s01_rolling12m_{name}.csv"))
    r100 = t.R.rolling(100).mean()
    rL = t.R.where(t.dir == 1).rolling(100, min_periods=100).mean()  # not meaningful (NaNs); per-dir below
    L = t[t.dir == 1].R.rolling(60).mean()
    S = t[t.dir == -1].R.rolling(60).mean()
    df100 = pd.DataFrame({"date": t.date, "avg_R_100": r100}).dropna()
    df100.to_csv(os.path.join(HERE, f"s01_rolling100_{name}.csv"), index=False)
    roll[name] = dict(
        r12m=dict(n_windows=len(r12), min=round(r12.min(), 3), min_end=r12.idxmin(), max=round(r12.max(), 3),
                  max_end=r12.idxmax(), frac_neg=round((r12 < 0).mean(), 3),
                  frac_below_minus0p1=round((r12 < -0.1).mean(), 3), median=round(r12.median(), 3),
                  q10=round(r12.quantile(0.1), 3), q90=round(r12.quantile(0.9), 3),
                  by_dec={k: round(v, 3) for k, v in r12[r12.index.str.endswith("-12")].items()}),
        r100=dict(n_windows=len(df100), min=round(r100.min(), 3), min_date=str(t.date[r100.idxmin()].date()),
                  max=round(r100.max(), 3), max_date=str(t.date[r100.idxmax()].date()),
                  frac_neg=round((r100.dropna() < 0).mean(), 3), median=round(r100.median(), 3),
                  q05=round(r100.quantile(0.05), 3), q10=round(r100.quantile(0.1), 3),
                  last=round(r100.iloc[-1], 3)),
        dir_roll60=dict(long_frac_neg=round((L.dropna() < 0).mean(), 3), long_min=round(L.min(), 3),
                        short_frac_neg=round((S.dropna() < 0).mean(), 3), short_min=round(S.min(), 3)),
        rolling_long_minus_short_12m_corr_with_slope=None,
    )
    # does the long-short spread track the gold trend? 12m windows: mean slope100 over trades in window
    t["slope"] = t.slope100
    ms = t.groupby("ym").slope.mean().reindex(allm)
    diff = (df12.long_12m - df12.short_12m)
    sl12 = ms.rolling(12, min_periods=6).mean().reindex(diff.index)
    ok = diff.notna() & sl12.notna()
    roll[name]["rolling_long_minus_short_12m_corr_with_slope"] = round(float(np.corrcoef(diff[ok], sl12[ok])[0, 1]), 3)
    print(name, roll[name])

# ---------------- filter pass rates per year (does the filter starve?) ----------------
i_rs, i_re, i_ee, i_ex, rh, rl, valid, exc = E._windows_full(D, prim.range_start, prim.range_end,
                                                            prim.entry_end, prim.exit_time)
width = rh - rl
base = valid & np.isfinite(atr) & (width > 0) & np.isfinite(ma20)
wa = width / atr
pw = base & (wa >= prim.min_w_atr)
pr = base & (atr <= ma20)
pb = pw & pr
fw35 = base & (wa >= 0.35)
dfp = pd.DataFrame(dict(base=base, w=pw, reg=pr, both=pb, w35=fw35, wa=np.where(base, wa, np.nan),
                        width=np.where(base, width, np.nan), atr=np.where(base, atr, np.nan),
                        atr_pct=np.where(base, atr_pct, np.nan), slope=slope, cp=cp,
                        corr_w_reg=0), index=days.index)
dfp = dfp[dfp.index <= pd.Timestamp(E.VAL_END)]
dfp["year"] = dfp.index.year
rows = []
for y, s in dfp.groupby("year"):
    b = s.base.sum()
    rows.append(dict(year=y, valid_days=int(b), pass_w030=round(s.w.sum() / b, 3), pass_regime=round(s.reg.sum() / b, 3),
                     pass_both=round(s.both.sum() / b, 3), pass_w035=round(s.w35.sum() / b, 3),
                     pass_regime_given_w=round(s.both.sum() / max(s.w.sum(), 1), 3),
                     med_w_atr=round(s.wa.median(), 3), med_width_usd=round(s.width.median(), 2),
                     med_atr_usd=round(s.atr.median(), 2), med_atr_pct=round(s.atr_pct.median(), 3),
                     med_width_pct=round((s.width / s.cp * 100).median(), 3),
                     mean_slope100=round(np.nanmean(s.slope), 3),
                     trades_primary=int((T["primary"].year == y).sum()),
                     trades_fallback=int((T["fallback"].year == y).sum())))
fp = pd.DataFrame(rows)
fp.to_csv(os.path.join(HERE, "s01_filter_pass_by_year.csv"), index=False)
print(fp.to_string(index=False))

# quarter-level relationships (for reasoning about high-vol / strong-trend regimes)
q = dfp.copy()
q["q"] = q.index.to_period("Q")
qq = q.groupby("q").agg(pass_w=("w", "mean"), pass_reg=("reg", "mean"), pass_both=("both", "mean"),
                        med_wa=("wa", "median"), atr_pct=("atr_pct", "median"), slope=("slope", "mean"),
                        base=("base", "mean"))
# per-quarter pass rates among valid days
for c_ in ("pass_w", "pass_reg", "pass_both"):
    qq[c_] = qq[c_] / qq["base"]
qq["abs_slope"] = qq.slope.abs()
# change in atr level over the quarter (vol expanding?) -> atr at end / atr at start
atr_q = q.groupby("q").atr.agg(lambda s: s.dropna().iloc[-1] / s.dropna().iloc[0] if s.notna().sum() > 1 else np.nan)
qq["atr_growth"] = atr_q
qq = qq.dropna()
corr = qq[["pass_w", "pass_reg", "pass_both", "med_wa"]].corrwith(qq.atr_pct).round(3).to_dict()
corr2 = qq[["pass_w", "pass_reg", "pass_both", "med_wa"]].corrwith(qq.abs_slope).round(3).to_dict()
corr3 = qq[["pass_w", "pass_reg", "pass_both", "med_wa"]].corrwith(qq.slope).round(3).to_dict()
corr4 = qq[["pass_w", "pass_reg", "pass_both", "med_wa"]].corrwith(np.log(qq.atr_growth)).round(3).to_dict()
print("quarter corr with atr_pct", corr, "\nwith |slope|", corr2, "\nwith slope", corr3, "\nwith log atr growth", corr4)
qq.round(3).to_csv(os.path.join(HERE, "s01_filter_pass_by_quarter.csv"))

# day-level: pass rates by trend regime and by atr_pct tercile (IS+VAL)
dfp["trend"] = feat.trend.reindex(dfp.index).values
dfp["atr_pct_t"] = feat.atr_pct_t.reindex(dfp.index).values
dfp["a_vs_m100_t"] = feat.a_vs_m100_t.reindex(dfp.index).values
pass_by = {}
for by in ("trend", "atr_pct_t", "a_vs_m100_t"):
    g = dfp[dfp.base].groupby(by)[["w", "reg", "both"]].mean().round(3)
    g["days"] = dfp[dfp.base].groupby(by).size()
    pass_by[by] = g.reset_index().to_dict(orient="records")
    print(g)

# cost in R vs width in USD (price level): net - gross on common trades
t, g = T["primary"], T["primary_gross"]
mm = t.merge(g[["day", "dir", "R"]], on=["day", "dir"], suffixes=("", "_g"))
mm["cost_R"] = mm.R_g - mm.R
mm["wq"] = pd.qcut(mm.width, 4, labels=["Q1", "Q2", "Q3", "Q4"])
cost_w = mm.groupby("wq", observed=True).agg(width_usd=("width", "median"), cost_R=("cost_R", "mean"),
                                             net=("R", "mean"), gross=("R_g", "mean"), n=("R", "size")).round(3)
mm["wpq"] = pd.qcut(mm.width / mm.close_prev * 100, 4, labels=["Q1", "Q2", "Q3", "Q4"])
cost_wp = mm.groupby("wpq", observed=True).agg(width_pct=("width", lambda s: np.nan), cost_R=("cost_R", "mean"),
                                               net=("R", "mean"), gross=("R_g", "mean"), n=("R", "size")).round(3)
cost_y = mm.groupby("year").agg(width_usd=("width", "median"), cost_R=("cost_R", "mean"),
                                net=("R", "mean"), gross=("R_g", "mean")).round(3)
print(cost_w, cost_wp, cost_y, sep="\n")

# gross edge vs absolute ATR level in USD (does the edge scale with vol?) -- unfiltered re5 gross
gu = T["unfiltered_re5_gross"].copy()
gu["atr_q"] = pd.qcut(gu.atr, 4, labels=["Q1", "Q2", "Q3", "Q4"])
gu["wa_q"] = pd.qcut(gu.width / gu.atr, 4, labels=["Q1", "Q2", "Q3", "Q4"])
g_atr = gu.groupby("atr_q", observed=True).agg(atr=("atr", "median"), gross=("R", "mean"), n=("R", "size")).round(3)
g_wa = gu.groupby(["wa_q"], observed=True).agg(wa=("width", "size"), gross=("R", "mean")).round(3)
print(g_atr, g_wa, sep="\n")

res.update(
    {name: {k: (v.to_dict(orient="records") if isinstance(v, pd.DataFrame) else v) for k, v in o.items()}
     for name, o in out.items()})
res["rolling"] = roll
res["filter_pass_by_year"] = fp.to_dict(orient="records")
res["filter_pass_quarter_corr"] = dict(atr_pct=corr, abs_slope=corr2, slope=corr3, log_atr_growth_in_q=corr4)
res["filter_pass_by_regime"] = pass_by
res["cost_by_width_quartile"] = cost_w.reset_index().astype({"wq": str}).to_dict(orient="records")
res["cost_by_year"] = cost_y.reset_index().to_dict(orient="records")
res["unfiltered_gross_by_atr_usd_quartile"] = g_atr.reset_index().astype({"atr_q": str}).to_dict(orient="records")
dump(res, "s01_regimes.json")
