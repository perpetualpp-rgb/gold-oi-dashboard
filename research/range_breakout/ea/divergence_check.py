"""Quantify EA-vs-engine divergences on IS/VAL only (data loaded with until=VAL_END).
1. Days the engine skips because both levels are touched inside the first trigger M1 bar (the EA trades them:
   the first touch fills, OCO deletes the other).
2. Performance of the broker-D1 ATR option (EA day decisions with NY-close daily bars) vs the London-day ATR."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import engine as E  # noqa: E402
import parity_check as pc  # noqa: E402

D = E.load(until=E.VAL_END)
prim = E.Params(range_end=5, min_w_atr=0.30, atr_regime_n=20, atr_regime_max=1.0)
fb = E.Params(range_end=5, min_w_atr=0.35, atr_regime_n=0)
for name, p in (("PRIMARY", prim), ("FALLBACK", fb)):
    keys, mask, rh, rl, atr, _ = pc.engine_mask(D, p)
    i_rs, i_re, i_ee, i_ex, *_ = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
    both = 0
    for j in np.where(mask)[0]:
        for i in range(i_re[j], min(i_ee[j], i_ex[j])):
            hl, hs = D["ah"][i] >= rh[j], D["bl"][i] <= rl[j]
            if hl or hs:
                both += int(hl and hs)
                break
    t = E.run(p, end=E.VAL_END, D=D)
    print(f"{name}: armed days {int(mask.sum())}, engine trades {len(t)}, engine both-touch skips {both}")
    # broker-D1 ATR decisions applied to an unfiltered engine run (same entries/exits, different day set)
    ea = pc.run_ea(D, p, pc.Clock("US"), "d1")
    base = E.run(E.Params(range_end=5, min_w_atr=0.0, atr_regime_n=0), end=E.VAL_END, D=D)
    ks = base["date"].values.astype("datetime64[s]").astype(np.int64)
    keep = np.array([bool(ea.get(int(k), {}).get("dec")) for k in ks])
    tb = base[keep]
    for lab, tt in (("London-ATR (engine)", t), ("broker-D1-ATR", tb)):
        for per, sel in (("IS", tt["date"] <= E.IS_END), ("VAL", tt["date"] > E.IS_END)):
            s = E.stats(tt[sel & (tt["date"] >= "2014-03-01")])
            print(f"   {lab:20s} {per}: n {s['n']}, avg_R {s['avg_R']}, t {s['t_stat']}, PF {s['PF']}")
