"""Run the pre-declared 24-config grid (grid_spec.json) on IS only; save grid_results.csv."""
import json
import os

import numpy as np
import pandas as pd

from common import E, data, HERE

spec = json.load(open(os.path.join(HERE, "grid_spec.json")))
D = data()
IS_YEARS = range(2014, 2022)
rows = []
for name, pd_ in spec["configs"].items():
    p = E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in pd_.items()})
    t = E.run(p, end=E.IS_END, D=D)
    s = E.stats(t)
    yr = t.groupby(t.date.dt.year)["R"].sum().reindex(IS_YEARS, fill_value=0.0)
    L, S = t[t.dir == 1], t[t.dir == -1]
    rows.append(dict(name=name, range_end=p.range_end, min_w_atr=p.min_w_atr, regime=p.atr_regime_n,
                     sl_ref=p.sl_ref, sl_k=p.sl_k, n=s["n"], trades_per_year=s["trades_per_year"],
                     avg_R=float(t.R.mean()), t_stat=s["t_stat"], PF=s["PF"], win_rate=s["win_rate"],
                     maxDD_R=s["maxDD_R"], sharpe_ann=s["sharpe_ann"], yrs_pos=int((yr > 0).sum()),
                     L_n=len(L), L_avg_R=float(L.R.mean()), S_n=len(S), S_avg_R=float(S.R.mean()),
                     usd_per_trade=float(t.pnl.mean()),
                     **{f"y{y}": round(float(v), 2) for y, v in yr.items()}))
g = pd.DataFrame(rows)
g.to_csv(os.path.join(HERE, "grid_results.csv"), index=False)
pd.set_option("display.width", 250)
print(g.drop(columns=[c for c in g.columns if c.startswith("y2")]).round(4).to_string(index=False))
