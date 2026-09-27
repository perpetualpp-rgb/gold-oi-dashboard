"""Start-date / window sensitivity of the primary and fallback (IS+VAL only).
- start month sweep: trades from start month .. 2021-12 (IS) and .. 2023-12 (IS+VAL)
- all 24-month and 36-month windows (monthly steps): distribution of avg_R
- year jackknife (drop one IS year)
Outputs s03_start_date.json, s03_start_sweep_{name}.csv"""
import os
import numpy as np
import pandas as pd

from rcommon import E, data, cand_params, tstat, dump, HERE

D = data()
C = cand_params()
res = {}
for name in ("primary", "fallback"):
    t = E.run(C[name], end=E.VAL_END, D=D)
    t["ym"] = t.date.dt.to_period("M")
    rows = []
    for st in pd.period_range("2014-02", "2021-01", freq="M"):
        a = t[(t.ym >= st) & (t.date <= E.IS_END)].R.values
        b = t[t.ym >= st].R.values
        rows.append(dict(start=str(st), IS_n=len(a), IS_avg=round(a.mean(), 4), IS_t=round(tstat(a), 2),
                         ALL_n=len(b), ALL_avg=round(b.mean(), 4), ALL_t=round(tstat(b), 2)))
    sw = pd.DataFrame(rows)
    sw.to_csv(os.path.join(HERE, f"s03_start_sweep_{name}.csv"), index=False)
    r = dict(start_sweep_IS_avg_by_Jan={x.start: x.IS_avg for x in sw.itertuples() if x.start.endswith("-01")},
             start_sweep_ALL_avg_by_Jan={x.start: x.ALL_avg for x in sw.itertuples() if x.start.endswith("-01")},
             start_sweep_ALL_t_by_Jan={x.start: x.ALL_t for x in sw.itertuples() if x.start.endswith("-01")},
             IS_avg_range=[sw.IS_avg.min(), sw.IS_avg.max()], ALL_avg_range=[sw.ALL_avg.min(), sw.ALL_avg.max()],
             frac_starts_ALL_t_gt2=round((sw.ALL_t > 2).mean(), 3))
    # fixed-length windows
    months = pd.period_range(t.ym.min(), "2023-12", freq="M")
    m = t.groupby("ym").R.agg(["size", "sum"]).reindex(months, fill_value=0)
    for L in (12, 24, 36):
        avg = (m["sum"].rolling(L).sum() / m["size"].rolling(L).sum()).dropna()
        r[f"win{L}m"] = dict(n=len(avg), frac_neg=round((avg < 0).mean(), 3), min=round(avg.min(), 3),
                             q05=round(avg.quantile(0.05), 3), q25=round(avg.quantile(0.25), 3),
                             median=round(avg.median(), 3), max=round(avg.max(), 3),
                             frac_neg_excluding_windows_with_2014=round((avg[avg.index >= pd.Period("2014-12", "M") + L]
                                                                        < 0).mean(), 3))
    # jackknife by IS year
    isr = t[t.date <= E.IS_END]
    r["jackknife_IS_drop_year"] = {int(y): round(isr[isr.date.dt.year != y].R.mean(), 4) for y in range(2014, 2022)}
    r["halves"] = {"2014-2017": round(isr[isr.date.dt.year <= 2017].R.mean(), 4),
                   "2018-2021": round(isr[isr.date.dt.year >= 2018].R.mean(), 4),
                   "2015-2021": round(isr[isr.date.dt.year >= 2015].R.mean(), 4),
                   "2015-2023": round(t[t.date.dt.year >= 2015].R.mean(), 4),
                   "2015-2023_t": round(tstat(t[t.date.dt.year >= 2015].R.values), 2)}
    res[name] = r
    print(name, r)
dump(res, "s03_start_date.json")
