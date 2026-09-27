"""Shared helpers: data variants with scaled spread, stats rows split IS/VAL and long/short, config log."""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import engine as E  # noqa: E402

LOG = os.path.join(HERE, "configs_log.csv")
KEYS = ("n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R")


def spread_scaled(D, k):
    """Copy of the data dict with ask = bid + k * (ask - bid). Windows/daily features are BID-based."""
    if k == 1.0:
        return D
    D2 = {kk: v for kk, v in D.items() if kk != "_win_cache"}
    for c in "ohlc":
        D2["a" + c] = D["b" + c] + k * (D["a" + c] - D["b" + c])
    return D2


def s(t):
    st = E.stats(t)
    return {k: (float(st[k]) if k in st and st[k] is not None else np.nan) for k in KEYS}


def split_stats(t):
    """IS/VAL x all/long/short stats for a trades frame (already end<=VAL_END)."""
    out = {}
    for per, m in (("IS", t["date"] <= E.IS_END), ("VAL", t["date"] > E.IS_END)):
        sub = t[m]
        out[per] = s(sub)
        out[per + "_L"] = s(sub[sub.dir == 1])
        out[per + "_S"] = s(sub[sub.dir == -1])
        out[per + "_yrs_pos"] = int((sub.groupby(sub.date.dt.year)["R"].mean() > 0).sum()) if len(sub) else 0
    return out


def log_config(label, params, val_checked, note="", **extra):
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["label", "val_checked", "note", "params", "extra"])
        w.writerow([label, int(bool(val_checked)), note, json.dumps(diff_params(params)), json.dumps(extra)])


def diff_params(p):
    base = E.Params().to_dict()
    return {k: v for k, v in p.to_dict().items() if base[k] != v}


def fmt_table(df, floatfmt=4):
    """Markdown table."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                vals.append(f"{v:.{floatfmt}f}" if np.isfinite(v) else "nan")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)
