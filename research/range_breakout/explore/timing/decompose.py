"""Decompose engine P&L for a few reference timings (IS only):
- gross (zero commission, zero slip, ASK=BID) vs net -> how much of the edge costs eat
- by entry hour (London), long vs short
- by exit reason
- drift control: the same trades' R if the position were entered at the same bar in a random direction
  is not available from the engine; instead we report the unconditional session drift per trade:
  mean (close_at_exit - price_at_entry)/risk over ALL days, same clock times (computed in descriptive.py).
Output: out/decompose.txt
"""
import numpy as np
import pandas as pd

from common import E, data, evaluate, OUT, md_table, cost_stressed

D = data()
Dz = cost_stressed()
Dz["ao"], Dz["ah"], Dz["al"], Dz["ac"] = D["bo"], D["bh"], D["bl"], D["bc"]   # ASK = BID (zero spread)
lines = []


def P(s=""):
    print(s)
    lines.append(str(s))


REFS = {
    "default 0-7/12/20": E.Params(),
    "0-5/12/21": E.Params(range_end=5, exit_time=21),
    "0-5/12/18": E.Params(range_end=5, exit_time=18),
    "2-9/12/20": E.Params(range_start=2, range_end=9, exit_time=20),
    "0-7/12/12": E.Params(exit_time=12),
}
lmin = D["lmin"]
for name, p in REFS.items():
    s, t = evaluate(p, tag="decomp")
    pz = E.Params(**{**p.to_dict(), "commission": 0.0, "slip": 0.0})
    sz, tz = evaluate(pz, tag="decomp_gross", D=Dz)
    cost = (t.pnl.values - tz.pnl.values) if len(t) == len(tz) else np.full(len(t), np.nan)
    P(f"\n## {name}  params={ {k: v for k, v in p.to_dict().items() if v != getattr(E.Params(), k)} }")
    P(f"net: n={s['n']} avg={s['avg_R']:+.4f} t={s['t_stat']} | L {s['L_avg']:+.4f} (t {s['L_t']}) S {s['S_avg']:+.4f} (t {s['S_t']})")
    P(f"gross(no costs): n={sz['n']} avg={sz['avg_R']:+.4f} t={sz['t_stat']} | L {sz['L_avg']:+.4f} (t {sz['L_t']}) S {sz['S_avg']:+.4f} (t {sz['S_t']})")
    P(f"median risk USD {t.risk.median():.2f}; median cost/trade in R {np.nanmedian(-cost / t.risk):.3f}, mean {np.nanmean(-cost / t.risk):.3f}"
      f" (same-trade match: {len(t) == len(tz)})")
    hr = ((lmin[t.i_entry.values] % 1440) // 60)
    t = t.assign(hr=hr)
    rows = []
    for h, g in t.groupby("hr"):
        r = dict(entry_hr=h, n=len(g), avg=g.R.mean(), t=g.R.mean() / g.R.std() * np.sqrt(len(g)) if len(g) > 2 else np.nan)
        for d, nm in ((1, "L"), (-1, "S")):
            gg = g[g.dir == d]
            r[f"{nm}_n"] = len(gg)
            r[f"{nm}_avg"] = gg.R.mean() if len(gg) else np.nan
        rows.append(r)
    P(md_table(pd.DataFrame(rows)))
    rr = t.groupby("reason").R.agg(["size", "mean"]).reset_index()
    P(md_table(rr))
    yb = E.by_year(t).reset_index()
    P(md_table(yb))

with open(f"{OUT}/decompose.txt", "w") as f:
    f.write("\n".join(lines))
