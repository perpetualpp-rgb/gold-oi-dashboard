"""IS-only null tests + break-even cost for finalists published by the other axes (as of this run),
where they are expressible as engine Params (+ a post-hoc day mask for the filters' a20 rule).
No VAL, no tuning: just "does the direction beat random at the same times, and what cost kills it"."""
import numpy as np
import pandas as pd
import common as C
import null as N

E = C.E
D = E.load()
MGRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
Dk = {m: C.spread_scaled(D, m) for m in MGRID}


def spread_added(D, x):
    D2 = {kk: v for kk, v in D.items() if kk != "_win_cache"}
    for c in "ohlc":
        D2["a" + c] = D["a" + c] + x
    return D2


Dadd = spread_added(D, 0.10)

atr = D["days"]["atr14_prev"]
a20 = (atr / atr.rolling(20, min_periods=12).mean()).values
A20_OK = np.isfinite(a20) & (a20 <= 1.0)

CANDS = {
    "exits F1 trail2": (E.Params(trail_r=2.0), None),
    "exits F2 ATR0.75 BE1 trail1.5 x21": (E.Params(sl_ref=1, sl_k=0.75, be_r=1.0, trail_r=1.5, exit_time=21.0), None),
    "exits F3 ATR1.5 time exit": (E.Params(sl_ref=1, sl_k=1.5), None),
    "entry B buf0.05": (E.Params(buf_k=0.05), None),
    "timing F1 asia00-05": (E.Params(range_end=5.0), None),
    "timing F2 asia00-0530 ee07 ex21": (E.Params(range_end=5.5, entry_end=7.0, exit_time=21.0), None),
    "timing F3 range02-09": (E.Params(range_start=2.0, range_end=9.0), None),
    "filters F4 w/atr>=0.35": (E.Params(min_w_atr=0.35), None),
    "filters F1 w/atr>=0.3 & a20<=1": (E.Params(min_w_atr=0.3), A20_OK),
    "filters F2 w/atr>=0.35 & a20<=1": (E.Params(min_w_atr=0.35), A20_OK),
}
n_cfg = 0


def run(p, mask, Dx):
    global n_cfg
    n_cfg += 1
    t = E.run(p, end=E.IS_END, D=Dx)
    if mask is not None and len(t):
        t = t[mask[t["day"].values]].reset_index(drop=True)
    return t


def be_interp(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if y[0] <= 0:
        return 0.0
    for i in range(1, len(x)):
        if y[i] <= 0:
            return x[i - 1] + (x[i] - x[i - 1]) * y[i - 1] / (y[i - 1] - y[i])
    return np.inf


rows = []
per = {"IS": (None, E.IS_END)}
for name, (p, mask) in CANDS.items():
    C.log_config("others: " + name, p, False, "IS null + cost, post-hoc a20 mask" if mask is not None else "IS null + cost")
    t1 = run(p, mask, D)
    pf = E.Params(**{**p.to_dict(), "commission": 0.0, "slip": 0.0})
    t0 = run(pf, mask, Dk[0.0])
    r1 = N.null_test(p, n_perm=10000, seed=21, D=D, end=E.IS_END, trades=t1, periods=per)["IS"]
    r0 = N.null_test(pf, n_perm=10000, seed=22, D=Dk[0.0], end=E.IS_END, trades=t0, periods=per)["IS"]
    ms = []
    for m in MGRID:
        if m in (0.0, 1.0):
            ms.append(t0.R.mean() if m == 0.0 else t1.R.mean())
            continue
        pm = E.Params(**{**p.to_dict(), "commission": 0.07 * m, "slip": 0.05 * m})
        ms.append(run(pm, mask, Dk[m]).R.mean())
    ts = run(E.Params(**{**p.to_dict(), "slip": 0.10}), mask, Dadd)
    spr = D["ao"][t1.i_entry.values] - D["bo"][t1.i_entry.values]
    nom = p.commission + spr + p.slip * (1 + (t1.reason.values != "tp"))
    m_star = be_interp(MGRID, ms)
    rows.append(dict(candidate=name, n=len(t1), net_avg_R=t1.R.mean(), net_t=C.s(t1)["t_stat"],
                     net_L=t1[t1.dir == 1].R.mean(), net_S=t1[t1.dir == -1].R.mean(),
                     p_coin=r1["coin"]["p"], p_shuffle=r1["shuffle"]["p"], coin_mean=r1["coin"]["mean"],
                     up_break_diff=r1["long_trades"]["diff"], down_break_diff=r1["short_trades"]["diff"],
                     gross_avg_R=t0.R.mean(), gross_p_coin=r0["coin"]["p"], gross_coin_mean=r0["coin"]["mean"],
                     cost_R=(nom / t1.risk.values).mean(), stress_avg_R=ts.R.mean(),
                     m_star=m_star, be_rt_cost_usd=m_star * nom.mean() if np.isfinite(m_star) else np.inf,
                     nominal_rt_usd=nom.mean()))
df = pd.DataFrame(rows)
print(C.fmt_table(df.round(4)))
df.to_csv(C.os.path.join(C.HERE, "out_null_others.csv"), index=False)
print("configs evaluated in this script:", n_cfg)
