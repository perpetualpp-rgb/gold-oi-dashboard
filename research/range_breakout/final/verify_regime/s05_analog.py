"""'2024-like' analog regime inside IS+VAL: strong uptrend (slope100 > +0.10/yr, and > +0.25/yr) and high
ATR as % of price (top IS tercile). Performance of primary/fallback/unfiltered there, filter pass rates
there, and the concentration of atr14/mean20(atr14) around 1 (how a small drift in ATR shifts the pass
rate of the regime filter). IS+VAL only."""
import os
import numpy as np
import pandas as pd
from rcommon import E, data, cand_params, summ, dump, HERE

D = data(); C = cand_params(); days = D["days"]
tp = pd.read_csv(os.path.join(HERE, "s01_trades_primary.csv"), parse_dates=["date"])
res = {}
cut_hi = float(np.nanquantile(tp.atr_pct, 0.5))  # placeholder, replaced below with IS day tercile
atr = days["atr14_prev"].values; cp = days["close_prev"].values
ap = atr / cp * 100
isd = days.index <= pd.Timestamp(E.IS_END)
q1, q2 = np.nanquantile(ap[isd], [1 / 3, 2 / 3])
res["atr_pct_IS_terciles"] = [round(q1, 3), round(q2, 3)]
ma20 = pd.Series(atr).rolling(20, min_periods=12).mean().values
ratio = atr / ma20
ok = np.isfinite(ratio) & (days.index <= pd.Timestamp(E.VAL_END))
res["ratio_quantiles"] = {f"q{q}": round(float(np.quantile(ratio[ok], q / 100)), 3) for q in (5, 25, 50, 75, 95)}
res["ratio_pass_at"] = {str(x): round(float((ratio[ok] <= x).mean()), 3) for x in (0.95, 0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.03, 1.05)}
# steady exponential ATR growth g/day shifts the ratio by ~ -(n-1)/2*g ... ratio = atr/mean(last 20) ~ 1 + 9.5 g
for yrs_double in (1, 2, 4):
    g = np.log(2) / (252 * yrs_double)
    res[f"ratio_shift_if_ATR_doubles_in_{yrs_double}y"] = round(float(np.exp(9.5 * g) - 1), 4)
print(res)
# slope feature from s01 trades file (per trade); rebuild day-level slope for pass rates
c = days["c"].values.astype(float); lc = np.log(c); n = len(c); N = 100
tt = np.arange(N) - (N - 1) / 2; den = (tt ** 2).sum(); slope = np.full(n, np.nan)
for d in range(N, n):
    y = lc[d - N:d]; slope[d] = (tt * (y - y.mean())).sum() / den * 252
p = C["primary"]
*_, rh, rl, valid, _ = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
w = rh - rl
base = valid & np.isfinite(atr) & (w > 0) & np.isfinite(ma20) & ok
pw = base & (w / atr >= 0.30); pr = base & (atr <= ma20); pb = pw & pr; p35 = base & (w / atr >= 0.35)
regs = {"all": np.ones(n, bool), "bull>0.10": slope > 0.10, "bull>0.25": slope > 0.25,
        "atr_pct_top_tercile": ap > q2, "bull>0.10&atr_pct_top": (slope > 0.10) & (ap > q2),
        "bull>0.25&atr_pct_top": (slope > 0.25) & (ap > q2), "slope<=0": slope <= 0}
rows = []
for k, m in regs.items():
    b = base & m
    rows.append(dict(regime=k, days=int(b.sum()), pass_w030=round(pw[b].mean(), 3), pass_w035=round(p35[b].mean(), 3),
                     pass_regime=round(pr[b].mean(), 3), pass_both=round(pb[b].mean(), 3),
                     implied_trades_per_yr_primary=round(pb[b].mean() * 252 * 0.93, 0)))
pr_df = pd.DataFrame(rows); print(pr_df.to_string(index=False))
res["pass_rates_by_regime"] = pr_df.to_dict(orient="records")
# performance in the analog regimes
out = []
unf = E.Params(**{**p.to_dict(), "min_w_atr": 0.0, "atr_regime_n": 0})
for name, pp in (("primary", C["primary"]), ("fallback", C["fallback"]), ("unfiltered_re5", unf)):
    t = E.run(pp, end=E.VAL_END, D=D)
    sl = slope[t.day.values]; a = ap[t.day.values]
    for k, m in (("all", np.ones(len(t), bool)), ("bull>0.10", sl > 0.10), ("bull>0.25", sl > 0.25),
                 ("atr_pct_top", a > q2), ("bull>0.10&atr_pct_top", (sl > 0.10) & (a > q2)),
                 ("slope<=0", sl <= 0)):
        s = t[m]
        for per, sp in (("ISVAL", s), ("IS", s[s.date <= E.IS_END]), ("VAL", s[s.date > E.IS_END])):
            r = dict(cfg=name, regime=k, per=per, **summ(sp.R.values),
                     L=round(sp[sp.dir == 1].R.mean(), 3), S=round(sp[sp.dir == -1].R.mean(), 3))
            out.append(r)
o = pd.DataFrame(out); print(o.to_string(index=False))
o.to_csv(os.path.join(HERE, "s05_analog.csv"), index=False)
res["analog_perf"] = o.to_dict(orient="records")
# difference test slope<=0 vs >0 for the primary (Welch t), ISVAL
t = E.run(C["primary"], end=E.VAL_END, D=D); sl = slope[t.day.values]
a_, b_ = t.R[sl <= 0].values, t.R[sl > 0].values
res["welch_slope_le0_vs_gt0"] = dict(diff=round(a_.mean() - b_.mean(), 4),
                                    t=round((a_.mean() - b_.mean()) / np.sqrt(a_.var(ddof=1) / len(a_) + b_.var(ddof=1) / len(b_)), 2))
print(res["welch_slope_le0_vs_gt0"])
dump(res, "s05_analog.json")
