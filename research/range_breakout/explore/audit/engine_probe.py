import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E
D = E.load()
days = D["days"]
lmin = D["lmin"]
print("lmin strictly increasing:", bool((np.diff(lmin) > 0).all()))
print("days index weekday only:", set(days.index.dayofweek))
p = E.Params()
t = E.run(p, end=E.VAL_END)
print(E.stats(t))
i_rs, i_re, i_ee, i_ex, rh, rl, valid = E._windows(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
base = days.index.values.astype("datetime64[m]").astype(np.int64)
late_ex = (lmin[np.minimum(i_ex, len(lmin)-1)] - (base + 20*60))
late_ee = (lmin[np.minimum(i_ee, len(lmin)-1)] - (base + 12*60))
m = (days.index <= "2023-12-31") & valid
print("valid days with exit bar >30 min late:", days.index[m & (late_ex > 30)].strftime("%Y-%m-%d %a").tolist())
print("valid days with entry-end bar >30 min late:", days.index[m & (late_ee > 30)].strftime("%Y-%m-%d %a").tolist())
tt = t[t.reason == "time"]
lag = lmin[tt.i_exit.values] - (base[tt.day.values] + 20*60)
print("time exits more than 5 min late:", (lag > 5).sum(), tt[lag > 5][["date","dir","R","t_exit"]].to_string())
# trades whose exit is on a later London day
xd = lmin[t.i_exit.values] // 1440
print("trades exiting on a later day:", (xd != base[t.day.values] // 1440).sum())
# range with negative start: Monday handling
for rs in (-2.0, -1.0):
    i_rs2, i_re2, _, _, rh2, rl2, v2 = E._windows(D, rs, 7.0, 12.0, 20.0)
    mon = days.index.dayofweek == 0
    first = lmin[np.minimum(i_rs2, len(lmin)-1)] - (base + int(rs*60))
    print(f"rs={rs}: valid Mondays {v2[mon].mean():.3f}, median minutes late of first range bar on Mon {np.median(first[mon])}, other days {np.median(first[~mon])}")
# bars per range
nb = i_re - i_rs
print("range bar count quantiles (valid days):", np.percentile(nb[valid], [0, 1, 5, 50]))
print("days invalid (<=2023):", days.index[(days.index <= "2023-12-31") & ~valid].strftime("%Y-%m-%d %a").tolist())
# dir split
for dd in (1, -1):
    print(dd, E.stats(t[(t.dir == dd) & (t.date <= E.IS_END)]))
print(t.reason.value_counts())
