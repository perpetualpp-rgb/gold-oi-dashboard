"""Diagnostic: buy stops trigger on ASK, so a long can open when BID is still up to one spread below the
(BID) range high. How many default-config longs are such 'spread-only' triggers, and how do they do?
Also per-trade gross R by range-width quintile computed by adding each trade's own costs back. IS only."""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, log_config, params_key  # noqa

Dd = D()
for tn in ("T0_asia0-7", "T1_asia0-8"):
    p = E.Params(**TIMINGS[tn])
    t = E.run(p, end=E.IS_END)
    log_config("s07b", params_key(p), dict(n=len(t)))
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, exc = E._windows_full(Dd, p.range_start, p.range_end, p.entry_end,
                                                                  p.exit_time)
    L = t[t.dir == 1].copy()
    # did BID ever reach the range high in the whole trade (entry bar to exit bar)?
    bid_max = np.array([Dd["bh"][a:b + 1].max() for a, b in zip(L.i_entry, L.i_exit)])
    bid_entry_bar = Dd["bh"][L.i_entry.values]
    L["spread_only_bar"] = bid_entry_bar < rh[L.day.values]
    L["never_bid_break"] = bid_max < rh[L.day.values]
    print(tn, "longs", len(L), "entry bar BID below range high:", int(L.spread_only_bar.sum()),
          "avgR", round(L[L.spread_only_bar].R.mean(), 3), "| BID never broke during trade:",
          int(L.never_bid_break.sum()), "avgR", round(L[L.never_bid_break].R.mean(), 3),
          "| rest avgR", round(L[~L.spread_only_bar].R.mean(), 3))
    # per-trade cost add-back
    spr = Dd["ao"][t.i_entry.values] - Dd["bo"][t.i_entry.values]
    nslip = 1 + (t.reason != "tp").astype(int)
    cost = p.commission + p.slip * nslip + spr
    t["gR"] = t.R + cost / t.risk
    t["cR"] = cost / t.risk
    t["q"] = pd.qcut(t.width, 5)
    g = t.groupby("q", observed=True).agg(n=("R", "size"), W_med=("width", "median"), gross_R=("gR", "mean"),
                                          cost_R=("cR", "mean"), net_R=("R", "mean"),
                                          net_L=("R", lambda r: r[t.loc[r.index, "dir"] == 1].mean()),
                                          net_S=("R", lambda r: r[t.loc[r.index, "dir"] == -1].mean()))
    print(tn, "all trades: gross", round(t.gR.mean(), 4), "cost", round(t.cR.mean(), 4), "net", round(t.R.mean(), 4))
    print(g.round(3).to_string())
    yq = t.groupby([t.date.dt.year])["width"].median()
    print("median W by year:", yq.round(2).to_dict())
