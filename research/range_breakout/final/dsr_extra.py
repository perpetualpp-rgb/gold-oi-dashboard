"""DSR table for primary/fallback over a range of N_trials (V = 1/T), plus V = within-grid SR variance."""
import json
import os
from statistics import NormalDist

import numpy as np

from common import E, data, HERE

nd = NormalDist()
spec = json.load(open(os.path.join(HERE, "grid_spec.json")))
sel = json.load(open(os.path.join(HERE, "selection.json")))
neff = json.load(open(os.path.join(HERE, "neff.json")))
D = data()


def dsr(R, N, V):
    T = len(R); sr = R.mean() / R.std(ddof=1); d = R - R.mean()
    g3 = (d ** 3).mean() / (d ** 2).mean() ** 1.5; g4 = (d ** 4).mean() / (d ** 2).mean() ** 2
    em = 0.5772156649
    sr0 = 0.0 if N <= 1 else np.sqrt(V) * ((1 - em) * nd.inv_cdf(1 - 1 / N) + em * nd.inv_cdf(1 - 1 / (N * np.e)))
    z = (sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return dict(N=N, SR=round(sr, 4), SR0=round(sr0, 4), skew=round(g3, 2), kurt=round(g4, 2), DSR=round(nd.cdf(z), 4))


out = {}
for lab, name in (("primary", sel["primary"]), ("fallback", sel["fallback"]), ("baseline", None)):
    p = E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in spec["configs"][name].items()}) if name else E.Params()
    R = E.run(p, end=E.IS_END, D=D).R.values
    out[lab] = {"V=1/T": [dsr(R, N, 1 / len(R)) for N in (1, 24, 50, 100, 200, 500, 1000, 2000, 20000)],
                "V=grid": [dsr(R, N, neff["sr_var_grid"]) for N in (50, 100, 200, 20000)]}
    for k, v in out[lab].items():
        print(lab, k, [(d["N"], d["SR0"], d["DSR"]) for d in v])
    print(lab, "SR", out[lab]["V=1/T"][0]["SR"], "skew", out[lab]["V=1/T"][0]["skew"], "kurt", out[lab]["V=1/T"][0]["kurt"], "T", len(R))
json.dump(out, open(os.path.join(HERE, "dsr.json"), "w"), indent=1)
