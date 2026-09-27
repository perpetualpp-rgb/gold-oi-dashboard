"""Shared helpers for the EXITS & RISK axis.

Rules enforced here:
- IS-only evaluation by default (end=E.IS_END). VAL only through val_stats() for <=10 finalists.
- Never runs with end >= 2024-01-01 and never calls E.holdout().
- Every engine configuration evaluated through evaluate()/run_is() is logged to out/configs_log.csv
  so configs_tested is auditable.
"""
import os
import sys
import json
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import engine as E  # noqa: E402

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "configs_log.csv")
IS_YEARS = list(range(2014, 2022))
DEF = E.Params()
_D = None
_seen = set()


def data():
    global _D
    if _D is None:
        t0 = time.time()
        _D = E.load()
        print(f"[load] {time.time() - t0:.1f}s", flush=True)
    return _D


def cost_stressed(spread_add=0.0):
    """Dataset copy with ASK shifted up by spread_add (own window cache)."""
    D = data()
    D2 = {k: v for k, v in D.items() if k != "_win_cache"}
    for k in ("ao", "ah", "al", "ac"):
        D2[k] = D[k] + spread_add
    D2["_win_cache"] = {}
    return D2


def pdiff(p):
    return {k: v for k, v in p.to_dict().items() if v != getattr(DEF, k)}


def _log(tag, p, stage):
    key = (stage, json.dumps(pdiff(p), sort_keys=True, default=str))
    new = not os.path.exists(LOG)
    with open(LOG, "a") as f:
        if new:
            f.write("tag|stage|params\n")
        f.write(f"{tag}|{stage}|{key[1]}\n")
    _seen.add(key)


def run_is(p, D=None, tag="", log=True):
    if log:
        _log(tag, p, "IS")
    return E.run(p, end=E.IS_END, D=D or data())


def run_val(p, D=None, tag=""):
    """VAL only (2022-2023). end=VAL_END, trades filtered to > IS_END."""
    _log(tag, p, "VAL")
    t = E.run(p, start="2022-01-01", end=E.VAL_END, D=D or data())
    return t


def skew(x):
    x = np.asarray(x, float)
    if len(x) < 3:
        return np.nan
    m, s = x.mean(), x.std()
    return float(((x - m) ** 3).mean() / s ** 3) if s > 0 else np.nan


def kurt(x):
    x = np.asarray(x, float)
    m, s = x.mean(), x.std()
    return float(((x - m) ** 4).mean() / s ** 4 - 3) if s > 0 else np.nan


def years_pos(t, years=IS_YEARS):
    if len(t) == 0:
        return 0
    g = t.groupby(t["date"].dt.year)["R"].sum()
    return int(sum(g.get(y, 0) > 0 for y in years))


def summ(t, prefix=""):
    s = E.stats(t)
    if s.get("n", 0) == 0:
        return {prefix + "n": 0}
    keys = ("n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R")
    return {prefix + k: float(s[k]) for k in keys}


def full_summ(t, years=IS_YEARS):
    """Summary incl. long/short split, positive years, skew, exit-reason mix and scale-free PnL."""
    d = summ(t)
    if len(t) == 0:
        return d
    d["yrs_pos"] = years_pos(t, years)
    L, S = t[t.dir == 1], t[t.dir == -1]
    for pre, x in (("L_", L), ("S_", S)):
        d[pre + "n"] = len(x)
        d[pre + "avg_R"] = round(float(x.R.mean()), 4) if len(x) else np.nan
        d[pre + "t"] = round(float(x.R.mean() / x.R.std(ddof=1) * np.sqrt(len(x))), 2) if len(x) > 2 else np.nan
    d["skew"] = round(skew(t.R.values), 2)
    d["med_R"] = round(float(np.median(t.R.values)), 3)
    # PnL in ATR units (scale-free across stop sizes)
    d["avg_pnl_atr"] = round(float((t.pnl / t.atr).mean()), 4)
    d["avg_risk_usd"] = round(float(t.risk.mean()), 2)
    tot_pos = t.R[t.R > 0].sum()
    for r in ("sl", "tp", "trail", "time"):
        m = t.reason == r
        d["sh_" + r] = round(float(m.mean()), 3)
        d["sumR_" + r] = round(float(t.R[m].sum()), 1)
        d["posR_" + r] = round(float(t.R[m & (t.R > 0)].sum() / tot_pos), 3) if tot_pos > 0 else np.nan
    return d


def evaluate(p, tag="", D=None):
    t = run_is(p, D=D, tag=tag)
    return full_summ(t), t


def n_logged():
    if not os.path.exists(LOG):
        return 0
    return sum(1 for _ in open(LOG)) - 1
