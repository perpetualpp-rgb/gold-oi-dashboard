"""MFE / MAE of the naive breakout entry (default timing, stop entries), IS only.

Re-walks M1 bars after each entry using the engine.load() arrays.
- MFE_stop : max favourable excursion (exit side: BID high for longs, ASK low for shorts) before the
             initial 1R stop is hit (the engine's 'best' logic: entry bar counts only its close, stop bar
             is assumed to hit the stop first).
- MFE_full / MAE_full : excursions up to the exit_time bar ignoring the stop.
- Barrier test on MID prices (no costs): P(+k*R before -1*R) vs the martingale value 1/(1+k), for the
  breakout direction and for the mirror direction at the same moment.
- Mid-price drift in the breakout direction at fixed horizons (no stop), in R units.
All R here = default risk (1 x Asian range width).
"""
import numpy as np
import pandas as pd
import common as C
import engine as E

D = C.data()
p = E.Params()
t = C.run_is(p, tag="s01_default")
_, _, _, i_ex, _, _, _, ex_close = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
bo, bh, bl, bc, ao, ah, al, ac = (D[k] for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
mh, ml, mc, mo = (bh + ah) / 2, (bl + al) / 2, (bc + ac) / 2, (bo + ao) / 2
lmin = D["lmin"]

KS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
HOR = [1, 5, 15, 30, 60, 120, 240]
rows = []
for r in t.itertuples():
    i0, pos, e, risk = r.i_entry, r.dir, r.entry, r.risk
    iend = i_ex[r.day]                      # bar at exit_time (time-exit fill bar); path = i0..iend-1
    if ex_close[r.day]:
        iend = iend                          # market closed: last bar is iend-1 either way
    sl = e - pos * risk
    # exit-side favourable/adverse series (entry bar: close only for favourable, full bar for adverse)
    if pos == 1:
        fav = np.r_[bc[i0], bh[i0 + 1:iend]] - e
        adv = e - np.r_[bl[i0], bl[i0 + 1:iend]]
    else:
        fav = e - np.r_[ac[i0], al[i0 + 1:iend]]
        adv = np.r_[ah[i0], ah[i0 + 1:iend]] - e
    fav, adv = fav / risk, adv / risk
    hit = np.nonzero(adv >= 1.0)[0]
    j_stop = hit[0] if len(hit) else len(adv)
    mfe_stop = max(0.0, fav[:j_stop].max()) if j_stop > 0 else 0.0
    mfe_full = max(0.0, fav.max())
    mae_full = max(0.0, adv.max())
    j_mfe = int(np.argmax(fav[:j_stop])) if j_stop > 0 else 0
    mae_before_mfe = adv[:j_mfe + 1].max() if j_stop > 0 else 1.0
    # MID-price barrier test (no costs)
    sp = ao[i0] - bo[i0]
    em = (e - C.DEF.slip - sp / 2) if pos == 1 else (e + C.DEF.slip + sp / 2)
    up = (np.r_[mc[i0], mh[i0 + 1:iend]] - em) / risk      # mid excursion up (from entry-bar close on)
    dn = (em - np.r_[mc[i0], ml[i0 + 1:iend]]) / risk
    favm, advm = (up, dn) if pos == 1 else (dn, up)
    res = {}
    for k in KS:
        for nm, f_, a_ in (("dir", favm, advm), ("mir", advm, favm)):
            jf = np.nonzero(f_ >= k)[0]
            ja = np.nonzero(a_ >= 1.0)[0]
            jf = jf[0] if len(jf) else 10**9
            ja = ja[0] if len(ja) else 10**9
            if jf == 10**9 and ja == 10**9:
                v = np.nan           # neither barrier before exit_time
            elif jf < ja:
                v = 1.0
            elif ja < jf:
                v = 0.0
            else:
                v = 0.5              # both in the same bar: ambiguous
            res[f"{nm}_{k}"] = v
    # mid drift (no stop) at horizons, in R, breakout direction
    for h in HOR:
        j = i0 + h
        res[f"drift_{h}"] = pos * (mc[j] - em) / risk if j < iend else np.nan
    res["drift_exit"] = pos * (mo[min(iend, len(mo) - 1)] - em) / risk
    rows.append(dict(date=r.date, dir=pos, R=r.R, reason=r.reason, risk=risk, width=r.width, atr=r.atr,
                     mfe_stop=mfe_stop, mfe_full=mfe_full, mae_full=mae_full,
                     mae_before_mfe=mae_before_mfe, bars_to_mfe=j_mfe,
                     mfe_hour=int((lmin[min(i0 + j_mfe, len(lmin) - 1)] % 1440) // 60),
                     entry_hour=int((lmin[i0] % 1440) // 60),
                     bars_held=j_stop, cost_R=(C.DEF.commission + 2 * C.DEF.slip + sp) / risk, **res))
M = pd.DataFrame(rows)
M.to_parquet(C.OUT + "/s01_mfe.parquet")

pd.set_option("display.width", 200)
out = []
def pr(*a):
    s = " ".join(str(x) for x in a)
    print(s); out.append(s)

pr("## Default trades IS:", len(M), "longs", (M.dir == 1).sum(), "shorts", (M.dir == -1).sum())
pr("median risk USD", M.risk.median().round(2), " median cost in R", M.cost_R.median().round(3),
   " mean cost R", M.cost_R.mean().round(3))
pr("\n## R distribution (default exit)")
q = M.R.quantile([.05, .1, .25, .5, .75, .9, .95, .99]).round(2)
pr("mean", M.R.mean().round(4), "skew", round(C.skew(M.R), 2), "kurt", round(C.kurt(M.R), 2))
pr("quantiles", dict(q))
pr("share of total positive R from top 10% trades:",
   round(M.R.sort_values(ascending=False).head(len(M) // 10).sum() / M.R[M.R > 0].sum(), 3))
pr("\n## MFE (before stop) / MFE_full / MAE_full quantiles, R units")
for c in ("mfe_stop", "mfe_full", "mae_full", "mae_before_mfe"):
    pr(c, dict(M[c].quantile([.1, .25, .5, .75, .9]).round(2)), "mean", round(M[c].mean(), 3))
pr("\n## P(MFE_before_stop >= k): exit-side prices incl. spread+slip at entry")
for d_, nm in ((0, "all"), (1, "long"), (-1, "short")):
    x = M if d_ == 0 else M[M.dir == d_]
    pr(nm, {k: round((x.mfe_stop >= k).mean(), 3) for k in KS})
pr("\n## Stopped trades (R<=-0.9): share that first went >= k R in favour")
st = M[M.reason == "sl"]
pr({k: round((st.mfe_stop >= k).mean(), 3) for k in (0.25, 0.5, 0.75, 1.0, 1.5)}, "n", len(st))
pr("\n## Barrier test on MID prices (no costs): P(+kR before -1R); martingale = 1/(1+k)")
tab = []
for k in KS:
    for d_, nm in ((0, "all"), (1, "long"), (-1, "short")):
        x = M if d_ == 0 else M[M.dir == d_]
        a = x[f"dir_{k}"].dropna(); b = x[f"mir_{k}"].dropna()
        pa, pb = a.mean(), b.mean()
        se = np.sqrt(pa * (1 - pa) / len(a))
        tab.append(dict(k=k, side=nm, fair=round(1 / (1 + k), 3), P_dir=round(pa, 3), z_vs_fair=round((pa - 1 / (1 + k)) / se, 2),
                        P_mirror=round(pb, 3), n=len(a), n_unresolved=int(x[f"dir_{k}"].isna().sum())))
tab = pd.DataFrame(tab)
pr(tab.to_string(index=False))
tab.to_csv(C.OUT + "/s01_barrier.csv", index=False)
pr("\n## Mid-price drift in breakout direction, R units (no stop, no costs)")
dr = []
for h in HOR + ["exit"]:
    for d_, nm in ((0, "all"), (1, "long"), (-1, "short")):
        x = (M if d_ == 0 else M[M.dir == d_])[f"drift_{h}"].dropna()
        dr.append(dict(h=h, side=nm, mean=round(x.mean(), 4), t=round(x.mean() / x.std() * np.sqrt(len(x)), 2),
                       n=len(x), p_pos=round((x > 0).mean(), 3)))
dr = pd.DataFrame(dr)
pr(dr.to_string(index=False))
dr.to_csv(C.OUT + "/s01_drift.csv", index=False)
pr("\n## Timing of MFE (before stop), bars after entry")
pr(dict(M.bars_to_mfe.quantile([.1, .25, .5, .75, .9]).round(0)))
pr("MFE hour (London) distribution:", dict(M.mfe_hour.value_counts(normalize=True).sort_index().round(3)))
pr("entry hour distribution:", dict(M.entry_hour.value_counts(normalize=True).sort_index().round(3)))
pr("\n## Capture: mean realized R / mean MFE_stop =", round(M.R.mean() / M.mfe_stop.mean(), 3),
   " (ex-post perfect exit avg:", round(M.mfe_stop.mean(), 3), "R minus exit costs)")
with open(C.OUT + "/s01_mfe.txt", "w") as f:
    f.write("\n".join(out))
