"""Effective number of independent trials in the 24-config grid (IS daily R correlation eigenvalues) and
cross-sectional SR variance inside the grid; used to interpret the DSR N_trials sensitivity."""
import json
import os

import numpy as np
import pandas as pd

from common import E, data, HERE

spec = json.load(open(os.path.join(HERE, "grid_spec.json")))
D = data()
cols, srs = {}, []
for n, d in spec["configs"].items():
    t = E.run(E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()}), end=E.IS_END, D=D)
    cols[n] = t.groupby("date").R.sum()
    srs.append(t.R.mean() / t.R.std(ddof=1))
M = pd.DataFrame(cols).fillna(0.0)          # no trade that day = 0 R
C = np.corrcoef(M.values.T)
lam = np.clip(np.linalg.eigvalsh(C), 0, None)
neff_pr = lam.sum() ** 2 / (lam ** 2).sum()                     # participation ratio
neff_90 = int(np.searchsorted(np.cumsum(np.sort(lam)[::-1]) / lam.sum(), 0.90) + 1)
off = C[np.triu_indices_from(C, 1)]
out = dict(n_configs=len(cols), mean_pairwise_corr=float(off.mean()), min_pairwise_corr=float(off.min()),
           neff_participation=float(neff_pr), n_eig_for_90pct=neff_90,
           sr_var_grid=float(np.var(srs, ddof=1)), sr_mean_grid=float(np.mean(srs)))
print(out)
json.dump(out, open(os.path.join(HERE, "neff.json"), "w"), indent=1)
