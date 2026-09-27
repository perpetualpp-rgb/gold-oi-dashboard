"""Empirical look-ahead tests on real IS data (never past 2021-12-31).
A) truncate the dataset at CUT, rebuild daily features: all trades dated before CUT must be identical.
B) corrupt all bars at/after 09:00 London on every day: every entry before 09:00 must be identical
   (entry bar, direction, entry price). Daily features are kept (they are prior-day by construction, A tests them).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E
D = E.load()
keys = ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]
cfgs = [E.Params(), E.Params(comp_n=20, comp_max=0.8), E.Params(trend=50), E.Params(min_w_atr=0.3, max_w_atr=1.0),
        E.Params(entry_mode=1, confirm_tf=15, max_trades=2), E.Params(trail_r=1.0, be_r=0.5, tp_r=3),
        E.Params(range_start=-1, range_end=6, entry_end=10, sl_ref=1, sl_k=1.0, buf_atr=0.05),
        E.Params(range_start=-6, range_end=-2, entry_end=3, exit_time=6, trend=20),
        E.Params(entry_mode=2, tp_r=1.0, max_trades=2, limit_pen=0.05), E.Params(max_trades=2, sl_ref=2)]
cols = ["day", "dir", "i_entry", "i_exit", "entry", "exit", "R"]
bad = 0
for CUT in ("2017-06-30", "2020-03-16"):
    n = np.searchsorted(D["index"], pd.Timestamp(CUT, tz="UTC"))
    T = {k: (v[:n] if isinstance(v, np.ndarray) else v) for k, v in D.items() if k not in ("days", "_win_cache", "index")}
    T["index"] = D["index"][:n]
    T["days"] = E._daily(T)
    for p in cfgs:
        a = E.run(p, end=E.IS_END, D=D)
        b = E.run(p, end=E.IS_END, D=T)
        # last London day before the cut may be incomplete in T: compare strictly earlier days
        lim = pd.Timestamp(CUT) - pd.Timedelta(days=1)
        a = a[a.date < lim][cols].reset_index(drop=True)
        b = b[b.date < lim][cols].reset_index(drop=True)
        # day index is identical because days before the cut are identical
        same = a.shape == b.shape and np.allclose(a.values, b.values, equal_nan=True)
        bad += not same
        print(f"A cut={CUT} {'OK ' if same else 'DIFF'} n={len(a)} vs {len(b)}  {p}" if not same else f"A cut={CUT} OK n={len(a)}")
# B: intraday corruption
lt = D["index"].tz_convert("Europe/London")
late = (lt.hour >= 9) & (lt.hour < 23)   # 23:00 bars can belong to a previous-evening range
C = dict(D); C.pop("_win_cache", None)
rng = np.random.default_rng(1)
noise = rng.normal(0, 30, late.sum())
for k in keys:
    v = D[k].copy()
    v[late] = v[late] + noise           # consistent shift keeps o/h/l/c ordering per bar
    C[k] = v
for p in cfgs[:7]:
    if p.range_end < 0:
        continue
    a = E.run(p, end=E.IS_END, D=D); b = E.run(p, end=E.IS_END, D=C)
    ea = a[lt[a.i_entry.values].hour < 9][["day", "dir", "i_entry", "entry"]].groupby("day").first()
    eb = b[lt[b.i_entry.values].hour < 9][["day", "dir", "i_entry", "entry"]].groupby("day").first()
    same = ea.shape == eb.shape and np.allclose(ea.values, eb.values)
    bad += not same
    print(f"B {'OK' if same else 'DIFF'} first entries before 09:00: {len(ea)} vs {len(eb)}")
print("FAILURES:", bad, " configs:", len(cfgs))
