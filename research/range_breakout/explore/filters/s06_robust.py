"""Stage 6: robustness of the shortlisted filters. IS only.

 a) cost stress: slip 0.10, spread +0.10, both
 b) circular-shift null for the vol-regime mask (keeps its autocorrelation; shifts only within IS days)
 c) sub-periods 2014-17 vs 2018-21, long/short
 d) other session timings (is the vol-regime effect specific to the 00-07 Asian range?)
"""
import numpy as np
import pandas as pd

from common import E, Counter, md, full_summary, cost_D, IS_YEARS
from features import day_features, run_mask

D = E.load()
C = Counter("s06")
f = day_features(D)
a20 = (f["atr_vs_mean20"] <= 1.0).values
a50 = (f["atr_vs_mean50"] <= 1.0).values
n_is = int((D["days"].index <= E.IS_END).sum())

SHORT = {
    "default": ({}, None),
    "F4 w>=0.35": (dict(min_w_atr=0.35), None),
    "F5 a20<=1": ({}, a20),
    "F1 w>=0.3&a20<=1": (dict(min_w_atr=0.3), a20),
    "F2 w>=0.35&a20<=1": (dict(min_w_atr=0.35), a20),
    "F3 w>=0.3&a50<=1": (dict(min_w_atr=0.3), a50),
    "F6 F1+noFri": (dict(min_w_atr=0.3, dow_mask=(1, 1, 1, 1, 0)), a20),
}


def ev(name, p, mask, DD):
    if mask is None:
        d, t = C.eval(name, p, DD)
    else:
        t = run_mask(p, mask, DD)
        d = {"stage": "s06", "name": name, "tag": "posthoc", **full_summary(t), "params": name}
        C.rows.append(d)
    return d, t


# a) cost stress
D_sp = cost_D(D, 0.10)
rows = []
for fname, (kw, mask) in SHORT.items():
    for cname, DD, extra in (("base", D, {}), ("slip0.10", D, dict(slip=0.10)),
                             ("spread+0.10", D_sp, {}), ("both", D_sp, dict(slip=0.10))):
        if cname == "base":
            t = run_mask(E.Params(**kw), mask, D) if mask is not None else E.run(E.Params(**kw), end=E.IS_END, D=D)
            d = full_summary(t)          # already counted in s02/s04
        else:
            d, t = ev(f"{fname}|{cname}", E.Params(**kw, **extra), mask, DD)
        rows.append({"filter": fname, "costs": cname, "n": d["n"], "avg_R": d["avg_R"], "t": d["t_stat"],
                     "PF": d["PF"], "yrs_pos": d["yrs_pos"], "L_avg_R": d["L_avg_R"], "S_avg_R": d["S_avg_R"]})
cost_tab = pd.DataFrame(rows)
txt = "## a) cost stress (IS)\n\n" + md(cost_tab)

# b) circular-shift null for the vol mask, on top of w>=0.3 and on top of nothing
rng_shifts = np.arange(40, n_is - 40, 7)
nul_rows = []
for base_name, kw in (("none", {}), ("w>=0.3", dict(min_w_atr=0.3))):
    t = E.run(E.Params(**kw), end=E.IS_END, D=D)
    tday = t["day"].values
    R = t["R"].values
    for mname, m in (("a20<=1", a20), ("a50<=1", a50)):
        m_is = m[:n_is].copy()
        obs = R[m_is[tday]].mean()
        null = np.array([R[np.roll(m_is, k)[tday]].mean() for k in rng_shifts])
        p = (null >= obs).mean()
        nul_rows.append({"base": base_name, "mask": mname, "obs_avgR": obs, "null_mean": null.mean(),
                         "null_p95": np.quantile(null, 0.95), "null_max": null.max(), "p_value": p,
                         "n_shifts": len(null)})
null_tab = pd.DataFrame(nul_rows)
txt += "\n\n## b) circular-shift null of the ATR-regime mask (IS days only)\n\n" + md(null_tab)

# c) sub-periods + by year for the shortlist
sub_rows = []
yr_rows = []
for fname, (kw, mask) in SHORT.items():
    t = run_mask(E.Params(**kw), mask, D) if mask is not None else E.run(E.Params(**kw), end=E.IS_END, D=D)
    for lab, lo, hi in (("2014-17", "2014-01-01", "2017-12-31"), ("2018-21", "2018-01-01", "2021-12-31")):
        s = t[(t.date >= lo) & (t.date <= hi)]
        d = full_summary(s)
        sub_rows.append({"filter": fname, "period": lab, "n": d["n"], "avg_R": d["avg_R"], "t": d["t_stat"],
                         "L_n": d["L_n"], "L_avg_R": d["L_avg_R"], "S_n": d["S_n"], "S_avg_R": d["S_avg_R"]})
    y = t.groupby(t.date.dt.year).R.mean().reindex(IS_YEARS).round(3)
    yr_rows.append({"filter": fname, **{str(k): v for k, v in y.items()}})
txt += "\n\n## c) sub-periods\n\n" + md(pd.DataFrame(sub_rows)) + "\n\n### avg_R by year\n\n" + md(pd.DataFrame(yr_rows))

# d) other session timings: does the ATR-regime filter help there too?
TIM = {
    "asia0-8/ee13": dict(range_start=0.0, range_end=8.0, entry_end=13.0),
    "asia1-7": dict(range_start=1.0, range_end=7.0),
    "ldn7-8": dict(range_start=7.0, range_end=8.0),
    "ldn8-13/ee17": dict(range_start=8.0, range_end=13.0, entry_end=17.0),
}
tim_rows = []
for tn, kw in TIM.items():
    for fn, extra, mask in (("none", {}, None), ("a20<=1", {}, a20), ("w>=0.3", dict(min_w_atr=0.3), None),
                            ("w>=0.3&a20<=1", dict(min_w_atr=0.3), a20)):
        d, t = ev(f"{tn}|{fn}", E.Params(**kw, **extra), mask, D)
        tim_rows.append({"timing": tn, "filter": fn, "n": d["n"], "avg_R": d["avg_R"], "t": d["t_stat"],
                         "yrs_pos": d["yrs_pos"], "L_avg_R": d["L_avg_R"], "S_avg_R": d["S_avg_R"]})
txt += "\n\n## d) other session timings (IS)\n\n" + md(pd.DataFrame(tim_rows))

df = C.save()
print(txt)
open("out_s06_robust.txt", "w").write("# Stage 6 robustness (IS)\n\n" + txt + "\n")
print("configs:", len(df[df.stage == "s06"]))
