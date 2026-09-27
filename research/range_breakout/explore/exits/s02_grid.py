"""Full exit/risk grid on IS with default timing + stop entries.
sl_ref 0: sl_k {0.5,0.75,1,1.5}; sl_ref 1: sl_k {0.15,0.25,0.35,0.5,0.75}; sl_ref 2 (opposite edge).
tp_r {0,1,1.5,2,3,4} x be_r {0,0.5,1} x trail_r {0,0.5,1,1.5,2} x exit_time {14,16,18,20,21}.
Run twice: NET (engine default costs) and GROSS (zero commission, zero slip, ASK=BID) as a diagnostic.
"""
import itertools
import time
import numpy as np
import pandas as pd
import common as C
import engine as E

D = C.data()
D0 = C.cost_stressed(0.0)
for k in ("ao", "ah", "al", "ac"):
    D0[k] = D["b" + k[1]].copy()          # ASK = BID  -> zero spread
STOPS = [(0, k) for k in (0.5, 0.75, 1.0, 1.5)] + [(1, k) for k in (0.15, 0.25, 0.35, 0.5, 0.75)] + [(2, 1.0)]
TPS = [0, 1, 1.5, 2, 3, 4]
BES = [0, 0.5, 1]
TRS = [0, 0.5, 1, 1.5, 2]
EXS = [14, 16, 18, 20, 21]
rows = []
t0 = time.time()
for mode in ("net", "gross"):
    for (sr, sk), tp, be, tr, ex in itertools.product(STOPS, TPS, BES, TRS, EXS):
        kw = dict(sl_ref=sr, sl_k=sk, tp_r=tp, be_r=be, trail_r=tr, exit_time=float(ex))
        if mode == "gross":
            kw.update(commission=0.0, slip=0.0)
        p = E.Params(**kw)
        t = C.run_is(p, D=(D if mode == "net" else D0), tag=f"s02_{mode}")
        d = C.full_summ(t)
        d.update(mode=mode, sl_ref=sr, sl_k=sk, tp_r=tp, be_r=be, trail_r=tr, exit_time=ex)
        rows.append(d)
    print(mode, "done", len(rows), f"{time.time() - t0:.0f}s", flush=True)
G = pd.DataFrame(rows)
G.to_csv(C.OUT + "/s02_grid.csv", index=False)
print("saved", len(G))
