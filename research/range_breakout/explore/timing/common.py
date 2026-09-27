"""Shared helpers for the SESSION TIMING axis.

- IS-only evaluation by default (end=E.IS_END). VAL is only touched by val_check.py for finalists.
- Every engine configuration evaluated through `evaluate` is counted in configs_log.csv, so the total
  number of configurations tested is auditable (for a multiple-testing correction).
- Never runs with end >= 2024-01-01, never calls E.holdout().
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
COUNT_FILE = os.path.join(OUT, "configs_log.csv")

IS_YEARS = list(range(2014, 2022))
_D = None


def data():
    global _D
    if _D is None:
        t0 = time.time()
        _D = E.load()
        print(f"[load] {time.time() - t0:.1f}s", flush=True)
    return _D


def cost_stressed(slip_add=0.0, spread_add=0.0):
    """Return (D2, slip_add): a dataset copy with ASK shifted up by spread_add. Windows depend only on
    BID so the copy gets its own (empty) window cache anyway."""
    D = data()
    D2 = dict(D)
    for k in ("ao", "ah", "al", "ac"):
        D2[k] = D[k] + spread_add
    D2["_win_cache"] = {}
    return D2


def _log(tag, p, stage):
    d = {k: v for k, v in p.to_dict().items() if v != getattr(E.Params(), k)}
    new = not os.path.exists(COUNT_FILE)
    with open(COUNT_FILE, "a") as f:
        if new:
            f.write("tag|stage|params\n")
        f.write(f"{tag}|{stage}|{json.dumps(d, default=str)}\n")


def summarize(t):
    """IS-style summary: overall, long/short, years positive."""
    keys = ("n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R")
    if t is None or len(t) == 0:
        return dict(n=0)
    s = E.stats(t)
    r = {k: (float(s[k]) if k != "n" else int(s[k])) for k in keys}
    for d, nm in ((1, "L"), (-1, "S")):
        sub = t[t.dir == d]
        if len(sub) > 1:
            ss = E.stats(sub)
            r[f"{nm}_n"] = int(ss["n"])
            r[f"{nm}_avg"] = float(ss["avg_R"])
            r[f"{nm}_t"] = float(ss["t_stat"])
        else:
            r[f"{nm}_n"], r[f"{nm}_avg"], r[f"{nm}_t"] = len(sub), np.nan, np.nan
    yr = t.groupby(t["date"].dt.year)["R"].sum()
    r["yrs_pos"] = int((yr > 0).sum())
    r["yrs_n"] = int(len(yr))
    r["worst_yr"] = float(yr.min().round(1))
    return r


def evaluate(p, tag="", stage="IS", D=None):
    """Run the engine on IS only (2014-2021) and summarise. Counts the config."""
    _log(tag, p, stage)
    D = D or data()
    t = E.run(p, end=E.IS_END, D=D)
    return summarize(t), t


def n_logged(stage=None):
    if not os.path.exists(COUNT_FILE):
        return 0
    df = pd.read_csv(COUNT_FILE, sep="|")
    if stage:
        df = df[df.stage == stage]
    return len(df)


def md_table(df, floatfmt=3):
    """Minimal markdown table (no tabulate dependency)."""
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        vals = []
        for v in row.values:
            if isinstance(v, (float, np.floating)):
                vals.append("" if np.isnan(v) else f"{v:.{floatfmt}f}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)
