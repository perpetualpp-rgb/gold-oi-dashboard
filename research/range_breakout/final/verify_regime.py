"""Check the native ATR-regime filter reproduces explore/filters F1/F2/F5 (post-hoc run_mask on
features.day_features()['atr_vs_mean20'] <= 1), and that load(until=VAL_END) gives the same trades as
the full load up to VAL_END."""
import numpy as np
import pandas as pd

from common import E, data
from features import day_features, run_mask

D = data()
f = day_features(D)
a20 = (f["atr_vs_mean20"] <= 1.0).values
out = []
for name, mw in (("F5", 0.0), ("F1", 0.30), ("F2", 0.35), ("w0.40", 0.40)):
    for re_ in (7, 5):
        p_old = E.Params(min_w_atr=mw, range_end=re_)
        p_new = E.Params(min_w_atr=mw, range_end=re_, atr_regime_n=20, atr_regime_max=1.0)
        t_old = run_mask(p_old, a20 if re_ == 7 else (day_features(D, p_old)["atr_vs_mean20"] <= 1.0).values,
                         D=D, end=E.VAL_END)
        t_new = E.run(p_new, end=E.VAL_END, D=D)
        same = len(t_old) == len(t_new) and np.array_equal(t_old["i_entry"].values, t_new["i_entry"].values) \
            and np.allclose(t_old["R"].values, t_new["R"].values, atol=1e-12)
        out.append(dict(cfg=name, range_end=re_, n_posthoc=len(t_old), n_native=len(t_new), identical=same,
                        IS_avgR=round(t_new[t_new.date <= E.IS_END].R.mean(), 4)))
print(pd.DataFrame(out).to_string(index=False))
# ratio form vs product form: count days where they disagree
atr = D["days"]["atr14_prev"].values
ma = pd.Series(atr).rolling(20, min_periods=12).mean().values
print("days where atr/ma<=1 != atr<=ma:", int(((atr / ma <= 1.0) != (atr <= ma)).sum()))

Dfull = E.load()
for p in (E.Params(), E.Params(min_w_atr=0.35, atr_regime_n=20)):
    a = E.run(p, end=E.VAL_END, D=D)
    b = E.run(p, end=E.VAL_END, D=Dfull)
    print("load(until) vs load():", len(a), len(b), np.array_equal(a.i_entry.values, b.i_entry.values),
          np.allclose(a.R.values, b.R.values, atol=1e-12))
