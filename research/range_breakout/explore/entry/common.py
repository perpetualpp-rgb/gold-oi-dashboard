"""Shared helpers for the ENTRY-mechanics axis. IS-only by default; VAL only via val_check()."""
import os
import sys
import json
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
import engine as E  # noqa: E402

IS_START = "2014-01-01"
LOG = os.path.join(HERE, "configs_log.csv")

# timings used to check that a finding is not specific to one session definition
TIMINGS = {
    "T0_asia0-7": dict(range_start=0.0, range_end=7.0, entry_end=12.0, exit_time=20.0),
    "T1_asia0-8": dict(range_start=0.0, range_end=8.0, entry_end=13.0, exit_time=20.0),
    "T2_ldn7-8": dict(range_start=7.0, range_end=8.0, entry_end=12.0, exit_time=20.0),
    "T3_ldn8-13": dict(range_start=8.0, range_end=13.0, entry_end=17.0, exit_time=20.0),
}

_seen = set()


def D():
    return E.load()


def run_is(p, D_=None):
    """Run on IS only (end=IS_END). Never touches VAL/holdout."""
    return E.run(p, end=E.IS_END, D=D_)


def years_pos(t):
    if len(t) == 0:
        return 0
    g = t.groupby(t["date"].dt.year)["R"].sum()
    return int((g > 0).sum())


def summ(t, prefix=""):
    """Compact stats dict for one trade set."""
    s = E.stats(t)
    if s.get("n", 0) == 0:
        return {prefix + "n": 0}
    keys = ("n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R")
    d = {prefix + k: float(s[k]) for k in keys}
    return d


def full_summ(t):
    """IS summary incl. long/short split and positive years."""
    d = summ(t)
    if len(t) == 0:
        return d
    d["yrs_pos"] = years_pos(t)
    L, S = t[t.dir == 1], t[t.dir == -1]
    d["L_n"] = len(L)
    d["L_avg"] = round(L.R.mean(), 4) if len(L) else np.nan
    d["L_t"] = summ(L).get("t_stat", np.nan) if len(L) > 1 else np.nan
    d["S_n"] = len(S)
    d["S_avg"] = round(S.R.mean(), 4) if len(S) else np.nan
    d["S_t"] = summ(S).get("t_stat", np.nan) if len(S) > 1 else np.nan
    d["cost_R"] = round(float(np.median(0.47 / t["risk"])), 3)
    return d


def params_key(p):
    return json.dumps(p.to_dict(), sort_keys=True, default=str)


def log_config(tag, p_or_desc, res):
    """Append one evaluated config to the axis log (for configs_tested)."""
    key = p_or_desc if isinstance(p_or_desc, str) else params_key(p_or_desc)
    new = (tag, key) not in _seen
    _seen.add((tag, key))
    row = dict(tag=tag, key=key, **res)
    df = pd.DataFrame([row])
    df.to_csv(LOG, mode="a", header=not os.path.exists(LOG), index=False)
    return new


def diff_params(p):
    base = E.Params().to_dict()
    return {k: v for k, v in p.to_dict().items() if base[k] != v}


def eval_is(tag, p, D_=None, extra=None):
    t = run_is(p, D_)
    r = full_summ(t)
    if extra:
        r.update(extra)
    r["params"] = json.dumps(diff_params(p), default=str)
    log_config(tag, p, r)
    return r, t


def val_check(p, D_=None):
    """VAL-period stats (2022-2023). Use for finalists only."""
    t = E.run(p, end=E.VAL_END, D=D_)
    tv = t[t["date"] > E.IS_END]
    return full_summ(tv), tv


def zero_cost_D():
    """Copy of the data with ASK = BID (no spread). For gross-edge diagnostics only."""
    base = E.load()
    Z = dict(base)
    Z["ao"], Z["ah"], Z["al"], Z["ac"] = base["bo"], base["bh"], base["bl"], base["bc"]
    Z.pop("_win_cache", None)
    Z["_win_cache"] = {}
    return Z


def wide_spread_D(extra=0.10):
    base = E.load()
    Z = dict(base)
    Z["ao"], Z["ah"], Z["al"], Z["ac"] = (base["ao"] + extra, base["ah"] + extra,
                                          base["al"] + extra, base["ac"] + extra)
    Z["_win_cache"] = {}
    return Z


def fmt(df, cols=None):
    cols = cols or [c for c in df.columns]
    return df[cols].to_string(index=False)


def md(df, index=True, floatfmt=None):
    """Minimal markdown table (tabulate is not installed)."""
    d = df.copy()
    if index:
        d = d.reset_index()
    cols = [str(c) for c in d.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in d.iterrows():
        cells = []
        for v in r.values:
            if isinstance(v, float):
                cells.append("" if np.isnan(v) else (f"{v:{floatfmt}}" if floatfmt else f"{v:g}"))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)
