"""Build a per-London-day table of prices, ranges and breakout outcomes (IS 2014-2021 only).

Used by s03 (intraday momentum) and s04 (compression). Output: out/daytable.parquet
All prices BID. Gross (no costs); cost is reported separately as COST_USD / W.

Breakout outcome for a range [rs, re) broken between re and entry_end, evaluated to exit time:
  dir     +1 up-break (BID high > H), -1 down-break (BID low < L); 0 no break; days where both edges are
          crossed inside the same M1 bar are dropped (dir=0, both=1), like engine.py
  ft      dir * (P(exit) - level) / W            gross follow-through in units of range width, no stop
  race_k  outcome of the race from the level: +1 if price reaches level + dir*k*W before level - dir*k*W
          (checked from the bar AFTER the break bar, conservative both-in-one-bar -> 0.5), -1 if the adverse
          barrier is first, 0 if neither before exit. Under a driftless random walk P(+1 | resolved) = 0.5.
"""
import os

import numpy as np
import pandas as pd
from numba import njit

from common import load_is

os.makedirs("out", exist_ok=True)
D = load_is()
lmin, bh, bl, bc, bo = D["lmin"], D["bh"], D["bl"], D["bc"], D["bo"]
days = np.unique(D["lday"])
days = days[pd.to_datetime(days * 86400, unit="s").dayofweek < 5]
base = days * 1440


def px(tmin, tol=5):
    """BID close of the last bar strictly before London minute tmin (per day), NaN if stale > tol min."""
    t = base + tmin
    j = np.searchsorted(lmin, t) - 1
    okj = j >= 0
    j = np.where(okj, j, 0)
    good = okj & (t - lmin[j] <= tol)
    return np.where(good, bc[j], np.nan)


def idx(tmin):
    return np.searchsorted(lmin, base + tmin)


@njit(cache=True)
def breakout(bh, bl, bc, i_rs, i_re, i_ee, i_ex, ks):
    n = len(i_rs)
    nk = len(ks)
    H = np.full(n, np.nan); L = np.full(n, np.nan)
    dirn = np.zeros(n, np.int64); both = np.zeros(n, np.int64)
    i_brk = np.full(n, -1, np.int64)
    ft = np.full(n, np.nan)
    race = np.full((n, nk), np.nan)
    mfe = np.full(n, np.nan); mae = np.full(n, np.nan)
    for d in range(n):
        a, b = i_rs[d], i_re[d]
        if b - a < 1 or i_ex[d] <= b:
            continue
        h = bh[a:b].max(); l = bl[a:b].min()
        H[d] = h; L[d] = l
        W = h - l
        if W <= 0:
            continue
        s = 0
        ib = -1
        for i in range(b, min(i_ee[d], i_ex[d])):
            up = bh[i] > h
            dn = bl[i] < l
            if up and dn:
                both[d] = 1
                break
            if up:
                s = 1; ib = i; break
            if dn:
                s = -1; ib = i; break
        if s == 0:
            continue
        dirn[d] = s
        i_brk[d] = ib
        lvl = h if s == 1 else l
        ft[d] = s * (bc[i_ex[d] - 1] - lvl) / W
        best = 0.0
        worst = 0.0
        for kk in range(nk):
            race[d, kk] = 0.0
        done = np.zeros(nk, np.bool_)
        for i in range(ib + 1, i_ex[d]):
            fav = (bh[i] - lvl) / W if s == 1 else (lvl - bl[i]) / W
            adv = (lvl - bl[i]) / W if s == 1 else (bh[i] - lvl) / W
            if fav > best:
                best = fav
            if adv > worst:
                worst = adv
            for kk in range(nk):
                if done[kk]:
                    continue
                k = ks[kk]
                hitf = fav >= k
                hita = adv >= k
                if hitf and hita:
                    race[d, kk] = 0.5
                    done[kk] = True
                elif hitf:
                    race[d, kk] = 1.0
                    done[kk] = True
                elif hita:
                    race[d, kk] = -1.0
                    done[kk] = True
        mfe[d] = best
        mae[d] = worst
    return H, L, dirn, both, i_brk, ft, race, mfe, mae


KS = np.array([0.5, 1.0, 2.0])
T = pd.DataFrame(index=pd.to_datetime(days * 86400, unit="s"))
T.index.name = "date"
T["year"] = T.index.year
T["dow"] = T.index.dayofweek

# London-clock prices
for name, hh in [("p0000", 0), ("p0700", 7 * 60), ("p0730", 7 * 60 + 30), ("p0800", 8 * 60), ("p1200", 12 * 60),
                 ("p1300", 13 * 60), ("p2000", 20 * 60)]:
    T[name] = px(hh)

# New York clock prices (COMEX pit 08:20-13:30 ET), aligned to the same London date (NY date == London date
# for all these times since NY is 5h behind London).
nymin, nyday = D["nymin"], D["nyday"]


def px_ny(tmin, tol=5):
    t = days * 1440 + tmin
    j = np.searchsorted(nymin, t) - 1
    okj = j >= 0
    j = np.where(okj, j, 0)
    good = okj & (t - nymin[j] <= tol)
    return np.where(good, bc[j], np.nan)


for name, hh in [("ny0820", 8 * 60 + 20), ("ny0850", 8 * 60 + 50), ("ny1300", 13 * 60), ("ny1330", 13 * 60 + 30)]:
    T[name] = px_ny(hh)
T["ny1330_prev"] = T["ny1330"].shift(1)      # previous trading day's pit close

# relative activity: high-low range of a window vs its mean over the previous 14 days (Zarattini's
# relative volume proxy; HistData has no volume)


def win_range(t0, t1):
    i0, i1 = idx(t0), idx(t1)
    out = np.full(len(days), np.nan)
    for k in range(len(days)):
        if i1[k] - i0[k] >= 0.6 * (t1 - t0):
            out[k] = bh[i0[k]:i1[k]].max() - bl[i0[k]:i1[k]].min()
    return out


T["rng_0700_0730"] = win_range(7 * 60, 7 * 60 + 30)
T["relact_lon"] = T["rng_0700_0730"] / T["rng_0700_0730"].rolling(14, min_periods=10).mean().shift(1)
# NY first 30 minutes of COMEX pit on the NY clock
i0 = np.searchsorted(nymin, days * 1440 + 8 * 60 + 20)
i1 = np.searchsorted(nymin, days * 1440 + 8 * 60 + 50)
ny30 = np.full(len(days), np.nan)
for k in range(len(days)):
    if i1[k] - i0[k] >= 18:
        ny30[k] = bh[i0[k]:i1[k]].max() - bl[i0[k]:i1[k]].min()
T["rng_ny30"] = ny30
T["relact_ny"] = T["rng_ny30"] / T["rng_ny30"].rolling(14, min_periods=10).mean().shift(1)

# daily range features (engine's daily table, previous-day values only)
dd = D  # noqa
eng_days = __import__("engine").load()["days"]
eng_days = eng_days[eng_days.index < "2022-01-01"]
T = T.join(eng_days[["h", "l", "atr14_prev"]].rename(columns={"h": "d_h", "l": "d_l"}), how="left")
T["d_rng"] = T["d_h"] - T["d_l"]
T["d_rng_prev"] = T["d_rng"].shift(1)
T["nr7_daily_prev"] = (T["d_rng_prev"] <= T["d_rng_prev"].rolling(7).min()).astype(float)
T["nr4_daily_prev"] = (T["d_rng_prev"] <= T["d_rng_prev"].rolling(4).min()).astype(float)
T.loc[T["d_rng_prev"].isna(), ["nr7_daily_prev", "nr4_daily_prev"]] = np.nan

# breakout tables for a few session definitions (London clock minutes)
SESS = {
    "asia": (0, 7 * 60, 12 * 60, 20 * 60),        # engine default Params(): range 00-07, entries to 12:00, exit 20:00
    "lonam": (7 * 60, 13 * 60, 17 * 60, 20 * 60),  # London-morning range 07-13, breaks 13-17 (NY), exit 20:00
}
for tag, (rs, re_, ee, ex) in SESS.items():
    i_rs, i_re, i_ee, i_ex = idx(rs), idx(re_), idx(ee), idx(ex)
    # completeness: at least 60% of range minutes and bar at i_re within 30 min of re
    good = (i_re - i_rs >= 0.6 * (re_ - rs)) & (i_re < len(lmin))
    good &= (lmin[np.minimum(i_re, len(lmin) - 1)] - (base + re_) < 30)
    H, L, dirn, both, i_brk, ft, race, mfe, mae = breakout(bh, bl, bc, i_rs.astype(np.int64), i_re.astype(np.int64),
                                                          i_ee.astype(np.int64), i_ex.astype(np.int64), KS)
    H[~good] = np.nan; L[~good] = np.nan; dirn[~good] = 0
    T[f"{tag}_W"] = H - L
    T[f"{tag}_dir"] = dirn
    T[f"{tag}_both"] = both
    T[f"{tag}_ft"] = np.where(dirn != 0, ft, np.nan)
    for kk, k in enumerate(KS):
        T[f"{tag}_race{k}"] = np.where(dirn != 0, race[:, kk], np.nan)
    T[f"{tag}_mfe"] = np.where(dirn != 0, mfe, np.nan)
    T[f"{tag}_mae"] = np.where(dirn != 0, mae, np.nan)
    tb = np.where(dirn != 0, lmin[np.maximum(i_brk, 0)] % 1440, -1)
    T[f"{tag}_brk_min"] = np.where(dirn != 0, tb, np.nan)
    post = np.full(len(days), np.nan)
    for k in range(len(days)):
        if good[k] and i_ex[k] > i_re[k]:
            post[k] = bh[i_re[k]:i_ex[k]].max() - bl[i_re[k]:i_ex[k]].min()
    T[f"{tag}_post_rng"] = post

T = T[T.index < "2022-01-01"]
T.to_parquet("out/daytable.parquet")
print(T.describe().T.round(3).to_string())
