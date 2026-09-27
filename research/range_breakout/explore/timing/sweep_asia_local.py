"""Local grid around the best main-grid region (range_end=5 was the grid boundary):
range_start {-1,0,1,2}, range_end {3,3.5,4,4.5,5,5.5,6}, entry_end {6,7,8,9,12}, exit {18,20,21}.
Also the 'late break' idea from descriptive.py: Asian 00-07 range still intact at 10:00 -> trade breaks
10:00-12:00 (implemented as range 0-10 restricted to days where range(0-10) == range(0-7)).
IS only. Output: out/grid_asia_local_is.csv, out/late_break_is.txt
"""
import itertools

import numpy as np
import pandas as pd

from common import E, evaluate, data, OUT, summarize

D = data()
RS = [-1, 0, 1, 2]
RE = [3, 3.5, 4, 4.5, 5, 5.5, 6]
EE = [6, 7, 8, 9, 12]
EX = [18, 20, 21]
rows = []
for rs, re_, ee, ex in itertools.product(RS, RE, EE, EX):
    if ee <= re_ or re_ - rs < 2:
        continue
    s, t = evaluate(E.Params(range_start=rs, range_end=re_, entry_end=ee, exit_time=ex), tag="asia_local")
    s.update(rs=rs, re=re_, ee=ee, ex=ex, med_width=float(t.width.median()))
    rows.append(s)
df = pd.DataFrame(rows)
df.to_csv(f"{OUT}/grid_asia_local_is.csv", index=False)
print("local configs", len(df))

# late-break variant
lines = []
_, _, _, _, rh7, rl7, v7, _ = E._windows_full(D, 0, 7, 12, 20)
_, _, _, _, rh10, rl10, v10, _ = E._windows_full(D, 0, 10, 12, 20)
intact = v7 & v10 & (rh10 == rh7) & (rl10 == rl7)
for ex in (16, 18, 20, 21):
    s_all, t = evaluate(E.Params(range_start=0, range_end=10, entry_end=12, exit_time=ex), tag="late_break")
    tt = t[intact[t.day.values]]
    s = summarize(tt)
    lines.append(f"late-break ex={ex}: {s}")
    lines.append(E.by_year(tt).to_string())
print("\n".join(lines))
with open(f"{OUT}/late_break_is.txt", "w") as f:
    f.write("\n".join(lines))
