"""New York session variants on IS (2014-2021): range = London morning/midday, entries around the
COMEX open (13:20 London) / US data (13:30) / PM fix (15:00), exit 16-21 London.
Net (default costs) and gross (zero costs) side by side.
Output: out/grid_ny_is.csv
"""
import itertools
import time

import pandas as pd

from common import E, evaluate, data, OUT, cost_stressed

RS = [7, 8, 9, 10, 11, 12, 13]
RE = [12.5, 13, 13.25, 13.5, 14, 15]
EE = [14, 15, 16, 17]
EX = [16, 17, 18, 19, 20, 21]

D = data()
Dz = cost_stressed()
Dz["ao"], Dz["ah"], Dz["al"], Dz["ac"] = D["bo"], D["bh"], D["bl"], D["bc"]
rows, seen = [], set()
t0 = time.time()
for rs, re_, ee, ex in itertools.product(RS, RE, EE, EX):
    ee_eff = min(ee, ex)
    if re_ - rs < 0.5 or ee_eff <= re_ or (rs, re_, ee_eff, ex) in seen:
        continue
    seen.add((rs, re_, ee_eff, ex))
    p = E.Params(range_start=rs, range_end=re_, entry_end=ee_eff, exit_time=ex)
    s, t = evaluate(p, tag="ny")
    pz = E.Params(range_start=rs, range_end=re_, entry_end=ee_eff, exit_time=ex, commission=0.0, slip=0.0)
    sz, _ = evaluate(pz, tag="ny_gross", stage="IS_gross", D=Dz)
    s.update(rs=rs, re=re_, ee=ee_eff, ex=ex, gross_avg=sz.get("avg_R"), gross_t=sz.get("t_stat"),
             gross_L=sz.get("L_avg"), gross_S=sz.get("S_avg"),
             med_width=float(t.width.median()) if len(t) else float("nan"))
    rows.append(s)
df = pd.DataFrame(rows)
df.to_csv(f"{OUT}/grid_ny_is.csv", index=False)
print("configs", len(df), f"{time.time() - t0:.0f}s")
