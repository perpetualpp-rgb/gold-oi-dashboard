"""Full IS/VAL evaluation of the frozen primary, fallback and naive baseline (selection.json).
Everything is on data loaded with engine.load(until=VAL_END); the holdout is never in memory."""
import glob
import json
import os

import numpy as np
import pandas as pd
from statistics import NormalDist

_N = NormalDist()


class norm:  # scipy is not installed
    cdf = staticmethod(_N.cdf)
    ppf = staticmethod(_N.inv_cdf)


def skew(x):
    x = np.asarray(x, float); d = x - x.mean()
    return float((d ** 3).mean() / (d ** 2).mean() ** 1.5)


def kurtosis(x, fisher=False):
    x = np.asarray(x, float); d = x - x.mean()
    k = float((d ** 4).mean() / (d ** 2).mean() ** 2)
    return k - 3 if fisher else k

from common import E, data, HERE, ROOT
import null as NL

pd.set_option("display.width", 250)
spec = json.load(open(os.path.join(HERE, "grid_spec.json")))
sel = json.load(open(os.path.join(HERE, "selection.json")))


def P(d):
    return E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})


CANDS = {"primary": P(spec["configs"][sel["primary"]]),
         "fallback": P(spec["configs"][sel["fallback"]]),
         "baseline": E.Params()}
D = data()


def with_spread(D, add):
    D2 = {k: v for k, v in D.items() if k != "_win_cache"}
    for c in ("ao", "ah", "al", "ac"):
        D2[c] = D[c] + add
    return D2


D_sp = with_spread(D, 0.10)
D_gross = {k: v for k, v in D.items() if k != "_win_cache"}
for c in "ohlc":
    D_gross["a" + c] = D["b" + c]
KEYS = ("n", "trades_per_year", "win_rate", "avg_R", "t_stat", "PF", "sharpe_ann", "maxDD_R", "usd_per_oz")


def st(t):
    s = E.stats(t)
    return {k: s.get(k) for k in KEYS}


def periods(t):
    return {"IS": t[t.date <= E.IS_END], "VAL": t[(t.date > E.IS_END) & (t.date <= E.VAL_END)]}


def topk(t, k):
    R = np.sort(t.R.values)[::-1][k:]
    return dict(avg_R=round(R.mean(), 4), t=round(R.mean() / R.std(ddof=1) * np.sqrt(len(R)), 2), n=len(R))


def dsr(R, N, V):
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014), per-trade SR, T = len(R).
    SR0 = sqrt(V) * ((1-g) z(1-1/N) + g z(1-1/(N e))) is the expected max SR of N trials with true SR 0
    whose SR estimates have cross-trial variance V."""
    T = len(R)
    sr = R.mean() / R.std(ddof=1)
    g3 = skew(R)
    g4 = kurtosis(R, fisher=False)
    em = 0.5772156649
    sr0 = 0.0 if N <= 1 else np.sqrt(V) * ((1 - em) * norm.ppf(1 - 1 / N) + em * norm.ppf(1 - 1 / (N * np.e)))
    z = (sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return dict(N=N, V=V, SR=sr, SR0=sr0, skew=g3, kurt=g4, T=T, DSR=norm.cdf(z), z=z)


def empirical_sr_var():
    """Cross-sectional variance of per-trade SR (t/sqrt(n)) over round-1 NET-cost IS config logs."""
    files = [f for f in glob.glob(os.path.join(ROOT, "explore", "**", "*.csv"), recursive=True)
             if "gross" not in f and "val" not in f.lower() and "keyrows" not in f and "cost" not in f]
    srs, fam = [], {}
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if not {"n", "t_stat"} <= set(df.columns):
            continue
        df = df[(df.n >= 100) & np.isfinite(df.t_stat)]
        if len(df) == 0:
            continue
        s = (df.t_stat / np.sqrt(df.n)).values
        srs.append(s)
        fam[os.path.relpath(f, ROOT)] = (len(s), float(np.var(s, ddof=1)) if len(s) > 1 else np.nan)
    allsr = np.concatenate(srs)
    return float(np.var(allsr, ddof=1)), len(allsr), fam


res = {"selection": sel["log"], "candidates": {k: v.to_dict() for k, v in CANDS.items()}}
trades = {}
for name, p in CANDS.items():
    r = {}
    t = E.run(p, end=E.VAL_END, D=D)
    trades[name] = t
    for per, sub in periods(t).items():
        r[per] = st(sub)
        r[per + "_long"] = st(sub[sub.dir == 1])
        r[per + "_short"] = st(sub[sub.dir == -1])
        r[per + "_top5_removed"] = topk(sub, 5)
        r[per + "_top10_removed"] = topk(sub, 10)
    r["IS_yrs_pos"] = int((periods(t)["IS"].groupby(periods(t)["IS"].date.dt.year).R.sum() > 0).sum())
    by = E.by_year(t)
    by["L_avg_R"] = t[t.dir == 1].groupby(t.date.dt.year).R.mean().round(3)
    by["S_avg_R"] = t[t.dir == -1].groupby(t.date.dt.year).R.mean().round(3)
    r["by_year"] = by.reset_index().rename(columns={"date": "year"}).to_dict(orient="records")
    # cost stress
    stress = {}
    for lab, pp, DD in (("default", p, D), ("slip0.10", E.Params(**{**p.to_dict(), "slip": 0.10}), D),
                        ("spread+0.10", p, D_sp),
                        ("slip0.10+spread+0.10", E.Params(**{**p.to_dict(), "slip": 0.10}), D_sp),
                        ("gross(no costs)", E.Params(**{**p.to_dict(), "slip": 0.0, "commission": 0.0}), D_gross)):
        ts = E.run(pp, end=E.VAL_END, D=DD)
        for per, sub in periods(ts).items():
            stress[f"{lab}|{per}"] = dict(n=len(sub), avg_R=round(sub.R.mean(), 4),
                                          t=round(sub.R.mean() / sub.R.std(ddof=1) * np.sqrt(len(sub)), 2))
    r["cost_stress"] = stress
    # random-direction null
    nt = NL.null_test(p, n_perm=10000, seed=1, D=D, end=E.VAL_END)
    r["null_test"] = {per: {k: v for k, v in nt[per].items() if not k.startswith("_")} for per in ("IS", "VAL")}
    # DSR (IS)
    Ris = periods(t)["IS"].R.values
    r["dsr"] = [dsr(Ris, 1, 1 / len(Ris))] + [dsr(Ris, N, 1 / len(Ris)) for N in (24, 50, 100, 200, 20000)]
    res[name] = r
    print(f"== {name}: {p.to_dict()}")
    print(pd.DataFrame({k: r[k] for k in ("IS", "VAL", "IS_long", "IS_short", "VAL_long", "VAL_short")}).T.to_string())
    print(by.to_string())
    print(pd.DataFrame(stress).T.to_string())
    print("top-k removed:", {k: r[k] for k in r if "top" in k})
    print(pd.DataFrame(NL.summary_rows(nt, name)).to_string(index=False))

# empirical cross-trial SR variance for the DSR sensitivity
V_emp, n_emp, fam = empirical_sr_var()
res["dsr_empirical_V"] = dict(V=V_emp, n_configs=n_emp, files=fam)
for name in CANDS:
    Ris = periods(trades[name])["IS"].R.values
    res[name]["dsr_empV"] = [dsr(Ris, N, V_emp) for N in (50, 100, 200, 20000)]

# family-wise reality check over the 24-config grid
grid = {n: P(d) for n, d in spec["configs"].items()}
fb_is = NL.family_bootstrap(grid, n_boot=5000, block=10, seed=0, D=D, end=E.IS_END)
fb_val = NL.family_bootstrap(grid, n_boot=5000, block=10, seed=0, D=D, start="2022-01-01", end=E.VAL_END)
fn_is = NL.family_null(grid, n_perm=5000, seed=0, D=D, end=E.IS_END)
for lab, df in (("family_bootstrap_IS", fb_is), ("family_bootstrap_VAL", fb_val), ("family_null_IS", fn_is)):
    df.to_csv(os.path.join(HERE, f"{lab}.csv"), index=False)
    res[lab] = dict(table=df.round(5).to_dict(orient="records"), **{k: v for k, v in df.attrs.items()})
    print(lab, df.attrs)
    print(df.round(4).to_string(index=False))
for name in CANDS:
    print(name, "DSR (V=1/T):", [(d["N"], round(d["SR"], 4), round(d["SR0"], 4), round(d["DSR"], 4)) for d in res[name]["dsr"]])
    print(name, "DSR (V emp):", [(d["N"], round(d["SR0"], 4), round(d["DSR"], 4)) for d in res[name]["dsr_empV"]])
print("V_emp", V_emp, n_emp)
json.dump(res, open(os.path.join(HERE, "eval_results.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
