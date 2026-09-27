"""Family x timing overview of all net IS results (reads the s0x result CSVs)."""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
fam = {
    "stop entry + buffers": "s01_results.csv",
    "bar-close confirm": "s02_results.csv",
    "stop-and-reverse": "s03_results.csv",
    "fade limit (R targets)": "s04_results.csv",
    "fade limit (mid/opp target)": "s05a_results.csv",
    "failed-break reversal": "s05b_results.csv",
    "break-then-retest (with)": "s06_results.csv",
}
rows = []
for f, fn in fam.items():
    df = pd.read_csv(os.path.join(HERE, fn))
    for tn, g in df.groupby("timing"):
        g150 = g[g.n >= 150]
        b = g150.sort_values("t_stat", ascending=False).iloc[0]
        rows.append(dict(family=f, timing=tn, configs=len(g), share_pos=round((g.avg_R > 0).mean(), 2),
                         median_R=round(g.avg_R.median(), 3), best_R=b.avg_R, best_t=b.t_stat, best_n=int(b.n),
                         best_yrs=int(b.yrs_pos), best_L=b.L_avg, best_S=b.S_avg))
out = pd.DataFrame(rows)
out.to_csv(os.path.join(HERE, "s13_family_summary.csv"), index=False)
print(out.to_string(index=False))
