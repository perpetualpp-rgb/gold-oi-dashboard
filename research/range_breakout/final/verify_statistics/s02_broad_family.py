"""Broad pre-declared proxy of the round-1 search space (engine-native knobs only), run on IS and VAL.
Used for: (1) a studentised stationary-bootstrap reality check (max-t) where the frozen PRIMARY is one
member of a ~13k-config family, (2) an empirical effective number of trials N_eff (max-t equivalence),
(3) the cross-sectional SR variance V for the DSR, (4) empirical-Bayes / IS->VAL shrinkage.
Writes broad_family_S_IS.npz, broad_family_S_VAL.npz, broad_family.csv"""
import itertools, json, os, sys, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common import E, data  # noqa

D = data()
days = D["days"].index
ranges = [(0, 5, 12), (0, 6, 12), (0, 7, 12), (1, 7, 12), (0, 8, 13)]
wmins = [0.0, 0.2, 0.3, 0.35, 0.4, 0.5]
regimes = [(0, 1.0), (20, 1.0), (50, 1.0), (20, 0.9)]
stops = [dict(sl_ref=0, sl_k=1.0), dict(sl_ref=0, sl_k=0.75), dict(sl_ref=1, sl_k=0.75), dict(sl_ref=1, sl_k=1.0),
         dict(sl_ref=2, sl_k=1.0), dict(sl_ref=0, sl_k=1.0, tp_r=2.0)]
exits = [18.0, 20.0, 21.0]
comps = [dict(), dict(comp_n=20, comp_max=0.8), dict(comp_n=20, comp_min=1.0)]
trends = [0, 50]
cfgs = []
for (rs, re_, ee), w, (an, am), st, ex, cp, tr in itertools.product(ranges, wmins, regimes, stops, exits, comps, trends):
    kw = dict(range_start=rs, range_end=re_, entry_end=ee, exit_time=ex, min_w_atr=w, atr_regime_n=an,
              atr_regime_max=am, trend=tr, **st, **cp)
    cfgs.append(kw)
print("configs", len(cfgs))
PRIM = dict(range_start=0, range_end=5, entry_end=12, exit_time=20.0, min_w_atr=0.3, atr_regime_n=20, atr_regime_max=1.0,
            trend=0, sl_ref=0, sl_k=1.0)
iprim = cfgs.index(PRIM)
FALL = dict(PRIM, min_w_atr=0.35, atr_regime_n=0)
ifall = cfgs.index(FALL)
out = {}
for per, lo, hi in (("IS", "2014-01-01", E.IS_END), ("VAL", "2022-01-01", E.VAL_END)):
    dd = days[(days >= pd.Timestamp(lo)) & (days <= pd.Timestamp(hi))]
    S = np.zeros((len(cfgs), len(dd)), np.float32); N = np.zeros((len(cfgs), len(dd)), np.float32)
    t0 = time.time()
    for j, kw in enumerate(cfgs):
        t = E.run(E.Params(**kw), start=lo, end=hi, D=D)
        if len(t):
            t = t[(t.date >= lo) & (t.date <= hi)]
            ix = np.searchsorted(dd.values, t.date.values)
            np.add.at(S[j], ix, t.R.values); np.add.at(N[j], ix, 1)
        if j % 2000 == 0:
            print(per, j, round(time.time() - t0, 1), flush=True)
    np.savez_compressed(os.path.join(HERE, f"broad_family_S_{per}.npz"), S=S, N=N, dates=dd.values.astype("datetime64[D]").astype(str))
json.dump(dict(configs=cfgs, i_primary=iprim, i_fallback=ifall), open(os.path.join(HERE, "broad_family_configs.json"), "w"))
print("done", iprim, ifall)
