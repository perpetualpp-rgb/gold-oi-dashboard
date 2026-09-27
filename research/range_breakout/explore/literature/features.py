"""Causal per-day features for the literature leads, computed from engine.load() arrays up to a cut date.

Never pass a cut later than 2024-01-01 (holdout is sealed). Default cut = 2022-01-01 (IS only).
All features for day d use only data available before the moment they are used:
  relact_lon : range(07:00-07:30 London) / mean of the same window over the previous 14 days  (known 07:30)
  volstate   : (ATR14_prev / price at 00:00) / median of that ratio over the previous 250 days  (known 00:00)
  nr7_prev / nr4_prev : previous London day's daily range is the smallest of the last 7 / 4 days (known 00:00)
  wa         : Asian range (00-07) width / ATR14_prev  (known 07:00)
"""
import numpy as np
import pandas as pd

import engine

HOLDOUT = pd.Timestamp("2024-01-01", tz="UTC")


def day_features(cut="2022-01-01"):
    cut = pd.Timestamp(cut, tz="UTC")
    assert cut <= HOLDOUT, "holdout is sealed"
    D = engine.load()
    n = int(np.searchsorted(D["index"].values, cut.to_datetime64()))
    lmin, bh, bl, bc = D["lmin"][:n], D["bh"][:n], D["bl"][:n], D["bc"][:n]
    days = D["days"]
    days = days[days.index < cut.tz_localize(None)]
    base = days.index.values.astype("datetime64[m]").astype(np.int64)

    def wrange(t0, t1):
        i0 = np.searchsorted(lmin, base + t0)
        i1 = np.searchsorted(lmin, base + t1)
        out = np.full(len(base), np.nan)
        for k in range(len(base)):
            if i1[k] - i0[k] >= 0.6 * (t1 - t0):
                out[k] = bh[i0[k]:i1[k]].max() - bl[i0[k]:i1[k]].min()
        return out

    F = pd.DataFrame(index=days.index)
    r = pd.Series(wrange(420, 450), index=days.index)
    F["relact_lon"] = r / r.rolling(14, min_periods=10).mean().shift(1)
    W = pd.Series(wrange(0, 420), index=days.index)
    F["wa"] = W / days["atr14_prev"]
    j = np.searchsorted(lmin, base) - 1
    p0 = np.where(j >= 0, bc[np.maximum(j, 0)], np.nan)
    atrp = days["atr14_prev"] / p0
    F["volstate"] = atrp / atrp.rolling(250, min_periods=120).median().shift(1)
    rng = days["h"] - days["l"]
    rp = rng.shift(1)
    F["nr7_prev"] = (rp <= rp.rolling(7).min()).astype(float).where(rp.notna())
    F["nr4_prev"] = (rp <= rp.rolling(4).min()).astype(float).where(rp.notna())
    return F
