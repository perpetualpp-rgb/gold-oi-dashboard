"""Main timing grid on IS (2014-2021): range_start x range_end x entry_end x exit_time.
Everything else at Params() defaults (stop entry at range edges, SL = 1 x width, no TP, 1 trade/day).

entry_end > exit_time is equivalent to entry_end = exit_time, so those combos are deduplicated to the
effective config. range_end >= entry_end (empty entry window) is skipped.
Output: out/grid_is.csv
"""
import itertools
import time

import pandas as pd

from common import E, evaluate, data, OUT

RS = [-3, -2, -1, 0, 1, 2]
RE = [5, 6, 7, 8, 9]
EE = [9, 10, 11, 12, 13, 15]
EX = [12, 14, 16, 17, 18, 20, 21]

data()
rows = []
seen = set()
t0 = time.time()
for rs, re_, ee, ex in itertools.product(RS, RE, EE, EX):
    ee_eff = min(ee, ex)
    if ee_eff <= re_:
        continue
    key = (rs, re_, ee_eff, ex)
    if key in seen:
        continue
    seen.add(key)
    p = E.Params(range_start=rs, range_end=re_, entry_end=ee_eff, exit_time=ex)
    s, _ = evaluate(p, tag="grid")
    s.update(rs=rs, re=re_, ee=ee_eff, ex=ex)
    rows.append(s)
    if len(rows) % 100 == 0:
        print(len(rows), f"{time.time() - t0:.0f}s", flush=True)
df = pd.DataFrame(rows)
df.to_csv(f"{OUT}/grid_is.csv", index=False)
print("configs", len(df), f"{time.time() - t0:.0f}s")
