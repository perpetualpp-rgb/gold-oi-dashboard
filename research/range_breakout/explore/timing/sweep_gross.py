"""Same grid as sweep_grid.py but with zero costs (commission 0, slip 0, ASK = BID): where does the
gross breakout signal live, independent of costs? Output: out/grid_is_gross.csv"""
import itertools
import time

import pandas as pd

from common import E, evaluate, data, OUT, cost_stressed

RS = [-3, -2, -1, 0, 1, 2]
RE = [5, 6, 7, 8, 9]
EE = [9, 10, 11, 12, 13, 15]
EX = [12, 14, 16, 17, 18, 20, 21]
D = data()
Dz = cost_stressed()
Dz["ao"], Dz["ah"], Dz["al"], Dz["ac"] = D["bo"], D["bh"], D["bl"], D["bc"]
rows, seen = [], set()
t0 = time.time()
for rs, re_, ee, ex in itertools.product(RS, RE, EE, EX):
    ee_eff = min(ee, ex)
    if ee_eff <= re_ or (rs, re_, ee_eff, ex) in seen:
        continue
    seen.add((rs, re_, ee_eff, ex))
    p = E.Params(range_start=rs, range_end=re_, entry_end=ee_eff, exit_time=ex, commission=0.0, slip=0.0)
    s, t = evaluate(p, tag="grid_gross", stage="IS_gross", D=Dz)
    s.update(rs=rs, re=re_, ee=ee_eff, ex=ex, med_width=float(t.width.median()))
    rows.append(s)
df = pd.DataFrame(rows)
df.to_csv(f"{OUT}/grid_is_gross.csv", index=False)
print("configs", len(df), f"{time.time() - t0:.0f}s")
