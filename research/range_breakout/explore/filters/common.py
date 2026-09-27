"""Shared helpers for the DAY FILTERS & REGIME axis.

IS-only by default (end=IS_END). VAL is only touched through val_check(), which logs every call so the
10-config cap can be audited. Holdout is never touched (no end dates >= 2024-01-01 anywhere).
"""
import os
import sys
import csv
import json

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
import engine as E  # noqa: E402

LOG = os.path.join(HERE, "configs_log.csv")
VAL_LOG = os.path.join(HERE, "val_log.csv")
IS_YEARS = list(range(2014, 2022))
DEFAULTS = E.Params().to_dict()

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 500)


def diff_params(p):
    d = p.to_dict()
    return {k: v for k, v in d.items() if v != DEFAULTS[k]}


def run_is(p, D=None):
    return E.run(p, end=E.IS_END, D=D)


def years_pos(t):
    if len(t) == 0:
        return 0
    g = t.groupby(t["date"].dt.year)["R"].sum().reindex(IS_YEARS, fill_value=0.0)
    return int((g > 0).sum())


KEYS = ("n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R")


def summ(t, prefix=""):
    s = E.stats(t)
    if s.get("n", 0) == 0:
        return {prefix + "n": 0}
    return {prefix + k: float(s[k]) for k in KEYS}


def full_summary(t):
    """Overall + long + short + years positive (IS)."""
    d = summ(t)
    d.update(summ(t[t.dir == 1], "L_"))
    d.update(summ(t[t.dir == -1], "S_"))
    d["yrs_pos"] = years_pos(t)
    d["L_yrs_pos"] = years_pos(t[t.dir == 1])
    d["S_yrs_pos"] = years_pos(t[t.dir == -1])
    return d


class Counter:
    """Counts and logs every configuration evaluated (for multiple-testing correction)."""

    def __init__(self, stage):
        self.stage = stage
        self.rows = []

    def eval(self, name, p, D=None, extra=None, tag=""):
        t = run_is(p, D)
        d = {"stage": self.stage, "name": name, "tag": tag}
        d.update(full_summary(t))
        d["params"] = json.dumps(diff_params(p), default=str)
        if extra:
            d.update(extra)
        self.rows.append(d)
        return d, t

    def save(self):
        df = pd.DataFrame(self.rows)
        new = not os.path.exists(LOG)
        # append, stage-tagged; rerunning a stage first removes its old rows
        if not new:
            old = pd.read_csv(LOG)
            old = old[old["stage"] != self.stage]
            df = pd.concat([old, df], ignore_index=True)
        df.to_csv(LOG, index=False)
        return df


def cost_D(D, spread_add=0.0):
    """A copy of the dataset with the ASK shifted by spread_add (for cost stress tests)."""
    D2 = {k: v for k, v in D.items() if k != "_win_cache"}
    for c in ("ao", "ah", "al", "ac"):
        D2[c] = D[c] + spread_add
    return D2


def val_check(name, p, D=None):
    """IS + VAL stats for one finalist. Logged to val_log.csv (cap: 10 per agent)."""
    t = E.run(p, end=E.VAL_END, D=D)
    ti = t[t["date"] <= E.IS_END]
    tv = t[t["date"] > E.IS_END]
    row = {"name": name, "params": json.dumps(diff_params(p), default=str)}
    for lab, sub in (("IS", ti), ("VAL", tv)):
        row.update(summ(sub, lab + "_"))
        row.update(summ(sub[sub.dir == 1], lab + "_L_"))
        row.update(summ(sub[sub.dir == -1], lab + "_S_"))
    row["IS_yrs_pos"] = years_pos(ti)
    row["VAL_by_year"] = json.dumps(tv.groupby(tv["date"].dt.year)["R"].agg(["size", "mean"]).round(3)
                                    .to_dict(orient="index"), default=str)
    new = not os.path.exists(VAL_LOG)
    with open(VAL_LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)
    return row, t


def md(df, floatfmt="{:.3f}"):
    """Minimal DataFrame -> markdown table (tabulate is not installed)."""
    cols = list(df.columns)

    def fmt(v):
        if isinstance(v, (float, np.floating)):
            return "" if not np.isfinite(v) else floatfmt.format(v)
        return str(v)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines)
