"""Descriptive: mean BID move into/out of the London AM (10:30) and PM (15:00) fixes and around the
COMEX open (13:20) / US data (13:30), IS days only, by year. No trading.
Output: out/fix_windows.txt"""
import numpy as np
import pandas as pd

from common import E, data, OUT, md_table

D = data()
days = D["days"].index
lmin, bo = D["lmin"], D["bo"]
base = days.values.astype("datetime64[m]").astype(np.int64)
is_day = (days >= pd.Timestamp("2014-01-01")) & (days <= pd.Timestamp(E.IS_END)) & (days.dayofweek < 5)


def px(h, m):
    t = base + h * 60 + m
    i = np.searchsorted(lmin, t)
    ok = is_day & (i < len(lmin)) & (lmin[np.minimum(i, len(lmin) - 1)] - t < 3)
    return np.where(ok, bo[np.minimum(i, len(bo) - 1)], np.nan)


W = {"AM fix 10:15->10:30": ((10, 15), (10, 30)), "AM fix 10:30->10:45": ((10, 30), (10, 45)),
     "COMEX/US 13:15->13:29": ((13, 15), (13, 29)), "US data 13:29->13:45": ((13, 29), (13, 45)),
     "PM fix 14:45->15:00": ((14, 45), (15, 0)), "PM fix 15:00->15:15": ((15, 0), (15, 15)),
     "London open 07:00->08:00": ((7, 0), (8, 0))}
yrs = days.year.values
rows = []
for nm, (a, b) in W.items():
    r = (px(*b) - px(*a)) / px(*a) * 1e4
    row = dict(window=nm)
    ok = np.isfinite(r)
    row["n"] = ok.sum()
    row["mean_bp"] = r[ok].mean()
    row["t"] = r[ok].mean() / r[ok].std() * np.sqrt(ok.sum())
    for y in range(2014, 2022):
        m = ok & (yrs == y)
        row[str(y)] = r[m].mean()
    rows.append(row)
txt = md_table(pd.DataFrame(rows), 2)
print(txt)
open(f"{OUT}/fix_windows.txt", "w").write(txt)
