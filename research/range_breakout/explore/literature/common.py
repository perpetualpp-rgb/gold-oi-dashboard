"""Shared IS-only data access for the literature axis descriptive checks.

Everything here is restricted to the in-sample period (bars with UTC time < 2022-01-01).
The holdout (2024+) is never sliced, printed or used; VAL (2022-2023) is not used either.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import engine  # noqa: E402

IS_CUT = pd.Timestamp("2022-01-01", tz="UTC")


def load_is():
    """Return a dict of IS-only numpy arrays: UTC index, London/NY local minute clocks, BID OHLC."""
    D = engine.load()
    idx = D["index"]
    n = int(np.searchsorted(idx.values, IS_CUT.to_datetime64()))
    idx = idx[:n]
    lon = idx.tz_convert("Europe/London").tz_localize(None)
    ny = idx.tz_convert("America/New_York").tz_localize(None)
    out = dict(
        index=idx,
        lmin=D["lmin"][:n],
        nymin=ny.values.astype("datetime64[m]").astype(np.int64),
        bo=D["bo"][:n], bh=D["bh"][:n], bl=D["bl"][:n], bc=D["bc"][:n],
        ao=D["ao"][:n], ah=D["ah"][:n], al=D["al"][:n], ac=D["ac"][:n],
    )
    out["lday"] = out["lmin"] // 1440              # London calendar day number
    out["lmod"] = out["lmin"] % 1440               # London minute of day
    out["nyday"] = out["nymin"] // 1440
    out["nymod"] = out["nymin"] % 1440
    out["ldow"] = pd.to_datetime(out["lday"] * 86400, unit="s").dayofweek.values
    out["year"] = lon.year.values
    return out


def price_at(lmin, px, targets):
    """Price of the last bar strictly before each target minute (i.e. the 'close at time T').
    Returns (price, bar_index, age_minutes). age = minutes between that bar and T."""
    j = np.searchsorted(lmin, targets, side="left") - 1
    ok = j >= 0
    jj = np.where(ok, j, 0)
    p = np.where(ok, px[jj], np.nan)
    age = np.where(ok, targets - lmin[jj], 10 ** 9)
    return p, jj, age


def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x))


def ols(y, x):
    """Univariate OLS with White (HC0) t-stat. Returns slope, t, R2, n."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    X = np.c_[np.ones(len(x)), x]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    S = (X * e[:, None] ** 2).T @ X
    V = XtX_inv @ S @ XtX_inv
    r2 = 1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))
    return beta[1], beta[1] / np.sqrt(V[1, 1]), r2, len(x)
