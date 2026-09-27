"""Demonstration of family_null (max-T over a searched family) on a proxy of the filters axis search:
min_w_atr x a20 (ATR14 / its 20-day mean) grid, IS only. The filters axis searched a larger family,
so the adjusted p-values here are optimistic (a lower bound on the true family-adjusted p)."""
import itertools
import numpy as np
import pandas as pd
import common as C
import null as N

E = C.E
D = E.load()
atr = D["days"]["atr14_prev"]
a20 = (atr / atr.rolling(20, min_periods=12).mean()).values
import os
LOGGED = os.path.exists(os.path.join(C.HERE, '.family_logged'))
base = {}
new = 0
for w, a in itertools.product((0.0, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5), (None, 0.9, 1.0, 1.1)):
    p = E.Params(min_w_atr=w)
    t = E.run(p, end=E.IS_END, D=D)
    if a is not None:
        t = t[(np.isfinite(a20) & (a20 <= a))[t["day"].values]].reset_index(drop=True)
    name = f"w/atr>={w}" + (f" & a20<={a}" if a is not None else "")
    base[name] = (p, t)
    if (w, a) not in ((0.0, None), (0.35, None), (0.3, 1.0), (0.35, 1.0)):
        new += 1
        if not LOGGED:
            C.log_config("family proxy " + name, p, False, "IS only, family null demo")
for label, Dx, cm in (("default costs", D, None),):
    res = N.family_null(base, n_perm=5000, seed=7, D=Dx, end=E.IS_END)
    print(label, "DIRECTION test, configs:", res.attrs["n_configs"], " 95% quantile of max-z null:", round(res.attrs["max_null_q95"], 2))
    print(C.fmt_table(res.round(4)))
    res.to_csv(C.os.path.join(C.HERE, "out_family_null_filters_proxy.csv"), index=False)
    rb = N.family_bootstrap(base, n_boot=2000, block=10, seed=9, D=Dx, end=E.IS_END)
    print(label, "PROFITABILITY reality check, configs:", rb.attrs["n_configs"], " 95% quantile of max-t:", round(rb.attrs["max_t_q95"], 2))
    print(C.fmt_table(rb.round(4)))
    rb.to_csv(C.os.path.join(C.HERE, "out_family_boot_filters_proxy.csv"), index=False)
# same idea for the stop-size family of s05 (exits differ, entry times identical)
fam2 = {}
for k in (0.25, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
    for tp in (0.0, 2.0):
        fam2[f"sl{k}w tp{tp}"] = E.Params(sl_k=k, tp_r=tp)
res2 = N.family_null(fam2, n_perm=5000, seed=8, D=D, end=E.IS_END)
new += 0   # these configs were counted in s05 (width x k, tp 0/2) except tp2 at 0.35/0.75/1.5/3.0
new += 4
print("stop-size family DIRECTION test: configs:", res2.attrs["n_configs"], " q95 max-z:", round(res2.attrs["max_null_q95"], 2))
print(C.fmt_table(res2.round(4)))
res2.to_csv(C.os.path.join(C.HERE, "out_family_null_stops.csv"), index=False)
rb2 = N.family_bootstrap(fam2, n_boot=2000, block=10, seed=10, D=D, end=E.IS_END)
print("stop-size family PROFITABILITY reality check: q95 max-t:", round(rb2.attrs["max_t_q95"], 2))
print(C.fmt_table(rb2.round(4)))
# single pre-specified default: plain (not family) bootstrap
rb0 = N.family_bootstrap({"default": E.Params()}, n_boot=2000, block=10, seed=11, D=D, end=E.IS_END)
print("default alone:", C.fmt_table(rb0.round(4)))
print("new configs in this script:", new)

open(os.path.join(C.HERE, '.family_logged'), 'w').write('1')
