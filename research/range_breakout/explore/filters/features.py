"""Causal day-level regime features (indexed like D['days']) for custom filters not in engine.Params.

All features are known before the entry window opens: they use atr14_prev / close_prev (end of the
previous London day) and the finished range. Only valid for sessions with range_end >= 0 (no extra lag).

Custom filters are applied post hoc to the engine's trades by day. For a SYMMETRIC day mask (both sides
allowed or both blocked) this is exactly what the engine's own mask does: days are simulated
independently, and a masked day produces no trades. verify_posthoc() checks this on real data.
"""
import numpy as np
import pandas as pd

from common import E


def day_features(D, p=None):
    p = p or E.Params()
    assert p.range_end >= 0, "features assume range_end >= 0"
    days = D["days"]
    *_, rh, rl, valid, _ = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
    width = rh - rl
    atr = days["atr14_prev"].values
    cp = days["close_prev"].values
    f = pd.DataFrame(index=np.arange(len(days)))
    f["w_atr"] = width / atr
    atr_s = pd.Series(atr)
    f["atr_rank250"] = atr_s.rolling(250, min_periods=120).apply(lambda x: (x[:-1] < x[-1]).mean(),
                                                                  raw=True).values
    for n in (20, 50, 100):
        f[f"atr_vs_mean{n}"] = atr / atr_s.rolling(n, min_periods=int(n * 0.6)).mean().values
    f["atr_pct_price"] = atr / cp * 100
    f["prevday_rng_atr"] = (days["h"] - days["l"]).shift(1).values / atr
    f["dow"] = days.index.dayofweek.values
    return f


def run_mask(p, mask, D=None, end=E.IS_END, start=None):
    """Engine run, then keep only trades on days where mask (bool array over D['days']) is True."""
    t = E.run(p, start=start, end=end, D=D)
    if len(t) == 0:
        return t
    m = np.asarray(mask, dtype=bool)[t["day"].values]
    return t[m].reset_index(drop=True)


def verify_posthoc(D):
    """Engine comp filter vs post-hoc mask with the same ratio: must give identical trades."""
    p = E.Params()
    *_, rh, rl, valid, _ = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
    width = rh - rl
    ok = True
    for n, mx in ((20, 1.0), (50, 0.8)):
        med = pd.Series(width).rolling(n, min_periods=max(5, n // 2)).median().shift(1).values
        ratio = width / med
        mask = np.isfinite(ratio) & (ratio <= mx)
        a = E.run(E.Params(comp_n=n, comp_max=mx), end=E.IS_END, D=D)
        b = run_mask(p, mask, D)
        same = len(a) == len(b) and np.allclose(a["R"].values, b["R"].values) and \
            (a["day"].values == b["day"].values).all()
        print(f"posthoc check comp_n={n} comp_max={mx}: engine n={len(a)} posthoc n={len(b)} identical={same}")
        ok &= bool(same)
    return ok
