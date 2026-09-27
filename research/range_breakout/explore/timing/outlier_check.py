"""Outlier dependence of the finalists (IS), and pooled IS+VAL t-stat. Re-uses already-counted configs
(F1, F2 at base costs on IS and VAL); no new configurations. Output: out/outlier_check.txt"""
import numpy as np
import pandas as pd

from common import E, data, OUT

D = data()
FIN = {"F1": E.Params(range_start=0, range_end=5, entry_end=12, exit_time=20),
       "F2": E.Params(range_start=0, range_end=5.5, entry_end=7, exit_time=21)}
lines = []
for nm, p in FIN.items():
    t = E.run(p, end=E.VAL_END, D=D)
    ti = t[t.date <= E.IS_END]
    R = np.sort(ti.R.values)
    for k in (0, 5, 10, 20):
        r = R[:len(R) - k] if k else R
        lines.append(f"{nm} IS drop top {k:2d} trades: avg {r.mean():+.4f} t {r.mean() / r.std() * np.sqrt(len(r)):.2f}")
    lines.append(f"{nm} IS max single-trade R {R[-1]:.2f}, 99th pct {np.percentile(R, 99):.2f}")
    for d, s in ((0, "all"), (1, "long"), (-1, "short")):
        g = t if d == 0 else t[t.dir == d]
        lines.append(f"{nm} pooled IS+VAL {s}: n {len(g)} avg {g.R.mean():+.4f} t {g.R.mean() / g.R.std() * np.sqrt(len(g)):.2f}")
print("\n".join(lines))
open(f"{OUT}/outlier_check.txt", "w").write("\n".join(lines))
