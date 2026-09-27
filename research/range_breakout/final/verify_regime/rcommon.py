"""Shared setup for the REGIME ROBUSTNESS lens. Data is loaded with engine.load(until=VAL_END), so no
holdout bar (London date >= 2024-01-01) is ever in memory."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.abspath(os.path.join(HERE, ".."))
if FINAL not in sys.path:
    sys.path.insert(0, FINAL)
from common import E, data  # noqa: E402  (final/common.py also puts engine + explore dirs on sys.path)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CAND = json.load(open(os.path.join(FINAL, "candidates.json")))["candidates"]


def P(d):
    return E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})


def cand_params():
    out = {}
    for k, v in CAND.items():
        d = v.get("params", v) if isinstance(v, dict) else v
        out[k] = P(d)
    return out


def tstat(R):
    R = np.asarray(R, float)
    if len(R) < 3:
        return np.nan
    s = R.std(ddof=1)
    return R.mean() / s * np.sqrt(len(R)) if s > 0 else np.nan


def summ(R):
    R = np.asarray(R, float)
    return dict(n=len(R), avg_R=round(float(R.mean()), 4) if len(R) else np.nan,
                t=round(float(tstat(R)), 2) if len(R) > 2 else np.nan,
                sum_R=round(float(R.sum()), 1), win=round(float((R > 0).mean()), 3) if len(R) else np.nan)


def gross_data(D):
    Dg = {k: v for k, v in D.items() if k != "_win_cache"}
    for c in "ohlc":
        Dg["a" + c] = D["b" + c]
    return Dg


def dump(obj, name):
    json.dump(obj, open(os.path.join(HERE, name), "w"), indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))
