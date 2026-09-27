"""Pivot-table heatmaps (avg_R, IS 2014-2021) from the grid CSVs already produced. No new configs.
Output: out/heatmaps.txt"""
import pandas as pd

from common import OUT, md_table

g = pd.read_csv(f"{OUT}/grid_is.csv")
gz = pd.read_csv(f"{OUT}/grid_is_gross.csv")
ny = pd.read_csv(f"{OUT}/grid_ny_is.csv")
sl = pd.read_csv(f"{OUT}/slide_is.csv")
lo = pd.read_csv(f"{OUT}/grid_asia_local_is.csv")
m = g.merge(gz[["rs", "re", "ee", "ex", "avg_R", "t_stat", "L_avg", "S_avg", "med_width"]],
            on=["rs", "re", "ee", "ex"], suffixes=("", "_g"))
m["cost"] = m.avg_R_g - m.avg_R
L = []


def H(title, piv, fmt=3):
    piv = piv.copy()
    piv.columns = [str(c) for c in piv.columns]
    L.append(f"\n### {title}\n")
    L.append(md_table(piv.reset_index(), fmt))


H("Main grid, net avg_R: range_end x exit_time (rs=0, ee=12)", g[(g.rs == 0) & (g.ee == 12)].pivot(index="re", columns="ex", values="avg_R"), 4)
H("Main grid, net t_stat: range_end x exit_time (rs=0, ee=12)", g[(g.rs == 0) & (g.ee == 12)].pivot(index="re", columns="ex", values="t_stat"), 2)
H("Main grid, net avg_R: range_end x exit_time (mean over rs, ee)", g.groupby(["re", "ex"]).avg_R.mean().unstack(), 4)
H("Main grid, net avg_R LONGS: range_end x exit_time (mean over rs, ee)", g.groupby(["re", "ex"]).L_avg.mean().unstack(), 4)
H("Main grid, net avg_R SHORTS: range_end x exit_time (mean over rs, ee)", g.groupby(["re", "ex"]).S_avg.mean().unstack(), 4)
H("Main grid, net avg_R: range_start x range_end (ee=12, ex=20)", g[(g.ee == 12) & (g.ex == 20)].pivot(index="rs", columns="re", values="avg_R"), 4)
H("Main grid, IS years positive (of 8): range_start x range_end (ee=12, ex=20)", g[(g.ee == 12) & (g.ex == 20)].pivot(index="rs", columns="re", values="yrs_pos"), 0)
H("Main grid, net avg_R: entry_end x exit_time (mean over rs, re)", g.groupby(["ee", "ex"]).avg_R.mean().unstack(), 4)
H("Main grid, GROSS (zero-cost) avg_R: range_end x exit_time (mean over rs, ee)", m.groupby(["re", "ex"]).avg_R_g.mean().unstack(), 3)
H("Main grid, GROSS avg_R: range_start x range_end (mean over ee, ex>=16)", m[m.ex >= 16].groupby(["rs", "re"]).avg_R_g.mean().unstack(), 3)
H("Main grid, cost per trade in R (gross - net): range_start x range_end", m.groupby(["rs", "re"]).cost.mean().unstack(), 3)
H("Main grid, median range width USD: range_start x range_end", m.groupby(["rs", "re"]).med_width.mean().unstack(), 2)
H("Local late-Asia grid, net avg_R: range_start x range_end (ee=12, ex=20)", lo[(lo.ee == 12) & (lo.ex == 20)].pivot(index="rs", columns="re", values="avg_R"), 4)
H("Local late-Asia grid, net avg_R: range_end x entry_end (rs=0, ex=20)", lo[(lo.rs == 0) & (lo.ex == 20)].pivot(index="re", columns="ee", values="avg_R"), 4)
H("Local late-Asia grid, LONG avg_R: range_end x entry_end (rs=0, ex=20)", lo[(lo.rs == 0) & (lo.ex == 20)].pivot(index="re", columns="ee", values="L_avg"), 4)
H("Local late-Asia grid, SHORT avg_R: range_end x entry_end (rs=0, ex=20)", lo[(lo.rs == 0) & (lo.ex == 20)].pivot(index="re", columns="ee", values="S_avg"), 4)
H("NY session, net avg_R: range_start x range_end (mean over ee, ex)", ny.groupby(["rs", "re"]).avg_R.mean().unstack(), 4)
H("NY session, GROSS avg_R: range_start x range_end (mean over ee, ex)", ny.groupby(["rs", "re"]).gross_avg.mean().unstack(), 3)
H("NY session, net avg_R: range_end x exit_time (mean over rs, ee)", ny.groupby(["re", "ex"]).avg_R.mean().unstack(), 4)
H("NY session, net avg_R: range 08:00-13:30: entry_end x exit_time", ny[(ny.rs == 8) & (ny.re == 13.5)].pivot(index="ee", columns="ex", values="avg_R"), 4)
for ex in ("21", "h+4"):
    s = sl[sl.exmode == ex]
    H(f"Sliding map (range [h-L,h), entries [h,h+2), exit {ex}), net avg_R: L x h", s.pivot(index="L", columns="h", values="avg_R"), 3)
    H(f"Sliding map, GROSS avg_R, exit {ex}: L x h", s.pivot(index="L", columns="h", values="gross_avg"), 3)
    H(f"Sliding map, GROSS LONG avg_R, exit {ex}: L x h", s.pivot(index="L", columns="h", values="gross_L"), 3)
    H(f"Sliding map, GROSS SHORT avg_R, exit {ex}: L x h", s.pivot(index="L", columns="h", values="gross_S"), 3)

L.append("\n### Distribution of net IS t_stat across all net grids")
allnet = pd.concat([g.assign(grid="main"), ny.assign(grid="ny"), sl.assign(grid="slide"), lo.assign(grid="local")])
d = allnet.groupby("grid").agg(n_cfg=("t_stat", "size"), mean_avgR=("avg_R", "mean"), max_avgR=("avg_R", "max"),
                               max_t=("t_stat", "max"), n_t_gt2=("t_stat", lambda x: (x > 2).sum()),
                               n_t_lt_m2=("t_stat", lambda x: (x < -2).sum()))
L.append(md_table(d.reset_index(), 4))
txt = "\n".join(L)
open(f"{OUT}/heatmaps.txt", "w").write(txt)
print(txt[-1500:])
