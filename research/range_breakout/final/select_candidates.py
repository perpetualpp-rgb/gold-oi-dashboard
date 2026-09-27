"""Apply the pre-declared selection rule (grid_spec.json) mechanically to grid_results.csv.
VAL avg_R is computed only for the configs the rule reaches (veto only)."""
import json
import os

import numpy as np
import pandas as pd

from common import E, data, HERE

spec = json.load(open(os.path.join(HERE, "grid_spec.json")))
g = pd.read_csv(os.path.join(HERE, "grid_results.csv"))
g["eligible"] = (g.trades_per_year >= 50) & (g.yrs_pos >= 6) & (g.L_avg_R > 0) & (g.S_avg_R > 0)
WS = [0.30, 0.35, 0.40]


def score(r):
    k = WS.index(round(r.min_w_atr, 2))
    nb = [WS[j] for j in (k - 1, k, k + 1) if 0 <= j < len(WS)]
    m = (g.range_end == r.range_end) & (g.regime == r.regime) & (g.sl_ref == r.sl_ref) & (g.sl_k == r.sl_k) & \
        g.min_w_atr.round(2).isin(nb)
    assert m.sum() == len(nb)
    return g.loc[m, "avg_R"].mean()


g["score"] = g.apply(score, axis=1)
# ordering: score desc, ties -> no regime first, then range_end 7 first
g["_tie1"] = (g.regime > 0).astype(int)
g["_tie2"] = -g.range_end
g = g.sort_values(["score", "_tie1", "_tie2"], ascending=[False, True, True]).reset_index(drop=True)
D = data()
val_cache = {}


def val_avgR(name):
    if name not in val_cache:
        p = E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in spec["configs"][name].items()})
        t = E.run(p, start="2022-01-01", end=E.VAL_END, D=D)
        val_cache[name] = float(t.R.mean())
    return val_cache[name]


log = []


def pick(cands, label, exclude=()):
    for _, r in cands.iterrows():
        if r["name"] in exclude:
            continue
        v = val_avgR(r["name"])
        if v < 0:
            log.append(f"{label}: {r['name']} (score {r.score:.4f}) VETOED by VAL avg_R {v:.4f}; moving to next")
            continue
        log.append(f"{label}: {r['name']} (score {r.score:.4f}, IS avg_R {r.avg_R:.4f}) VAL avg_R {v:.4f} >= 0 -> accepted")
        return r
    raise RuntimeError("no candidate")


el = g[g.eligible]
prim = pick(el, "PRIMARY")
if prim.regime > 0:
    fb = pick(el[el.regime == 0], "FALLBACK", exclude=(prim["name"],))
else:
    fb = pick(el[el.sl_ref != prim.sl_ref], "FALLBACK", exclude=(prim["name"],))
cols = ["name", "n", "trades_per_year", "yrs_pos", "L_avg_R", "S_avg_R", "avg_R", "t_stat", "eligible", "score"]
tab = g[cols].copy()
tab["VAL_avg_R(veto check)"] = tab["name"].map(val_cache)
print(tab.round(4).to_string(index=False))
print("\n".join(log))
json.dump({"primary": prim["name"], "fallback": fb["name"], "log": log,
           "val_checked": val_cache, "table": tab.round(5).to_dict(orient="records")},
          open(os.path.join(HERE, "selection.json"), "w"), indent=1, default=str)
tab.to_csv(os.path.join(HERE, "selection_table.csv"), index=False)
