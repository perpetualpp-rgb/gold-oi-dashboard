"""Where in the day does breakout follow-through live? Slide a range of length L hours ending at hour h,
entries allowed [h, h+2), exit at h+4 (short hold) or 21:00 (hold to US close). IS only, net and gross.
Output: out/slide_is.csv
"""
import pandas as pd

from common import E, evaluate, data, OUT, cost_stressed

D = data()
Dz = cost_stressed()
Dz["ao"], Dz["ah"], Dz["al"], Dz["ac"] = D["bo"], D["bh"], D["bl"], D["bc"]
rows = []
for L in (2, 4, 6):
    for h in range(1, 18):
        for exmode in ("h+4", "21"):
            ex = h + 4 if exmode == "h+4" else 21
            ee = min(h + 2, ex)
            if ex > 21 or ee <= h:
                continue
            kw = dict(range_start=h - L, range_end=h, entry_end=ee, exit_time=ex)
            s, t = evaluate(E.Params(**kw), tag="slide")
            sz, _ = evaluate(E.Params(**kw, commission=0.0, slip=0.0), tag="slide_gross", stage="IS_gross", D=Dz)
            s.update(L=L, h=h, exmode=exmode, gross_avg=sz.get("avg_R"), gross_t=sz.get("t_stat"),
                     gross_L=sz.get("L_avg"), gross_S=sz.get("S_avg"), med_width=float(t.width.median()))
            rows.append(s)
df = pd.DataFrame(rows)
df.to_csv(f"{OUT}/slide_is.csv", index=False)
print(len(df))
