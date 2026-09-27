"""(c) Range width, ATR, spread and cost-in-R by year, 2014-2023 only (holdout never touched)."""
import numpy as np
import pandas as pd
import common as C

E = C.E
D = E.load()
D0 = C.spread_scaled(D, 0.0)
CUT = pd.Timestamp("2024-01-01")

days = D["days"]
days = days[days.index < CUT]
i_rs, i_re, i_ee, i_ex, rh, rl, valid, _ = E._windows_full(D, 0.0, 7.0, 12.0, 20.0)
nd = len(days)
width = (rh - rl)[:nd]
valid = valid[:nd]
yr = days.index.year

# spread by year in the entry window 07:00-12:00 London and over 00:00-20:00, pre-2024 bars only
nb = int(D["index"].searchsorted(CUT.tz_localize("UTC")))
lmin = D["lmin"][:nb]
hh = (lmin % 1440) / 60.0
spr = (D["ao"] - D["bo"])[:nb]
byr = D["index"][:nb].year
sp = pd.DataFrame({"y": byr, "h": hh, "s": spr})
sp_entry = sp[(sp.h >= 7) & (sp.h < 12)].groupby("y").s.mean()
sp_day = sp[(sp.h >= 0) & (sp.h < 20)].groupby("y").s.mean()

t1 = E.run(E.Params(), end=E.VAL_END, D=D)
t0 = E.run(E.Params(commission=0.0, slip=0.0), end=E.VAL_END, D=D0)
t1["y"] = t1.date.dt.year
t0["y"] = t0.date.dt.year
t1["spr_entry"] = D["ao"][t1.i_entry.values] - D["bo"][t1.i_entry.values]
t1["nom_cost_usd"] = 0.07 + t1.spr_entry + 0.05 * 2
t1["nom_cost_R"] = t1.nom_cost_usd / t1.risk

df = pd.DataFrame({"y": yr, "w": width, "valid": valid, "atr": days["atr14_prev"].values,
                   "c": days["c"].values})
df = df[df.valid]
g = df.groupby("y")
tab = pd.DataFrame({
    "gold_avg_close": g.c.mean(),
    "asian_width_mean": g.w.mean(),
    "asian_width_median": g.w.median(),
    "ATR14_mean": g.atr.mean(),
    "width_over_ATR_median": g.apply(lambda x: (x.w / x.atr).median()),
    "width_pct_of_price": g.apply(lambda x: (x.w / x.c).median() * 100),
    "spread_07_12_mean": sp_entry,
    "spread_00_20_mean": sp_day,
    "spread_at_entries": t1.groupby("y").spr_entry.mean(),
    "rt_cost_usd": t1.groupby("y").nom_cost_usd.mean(),
    "cost_over_median_width_R": t1.groupby("y").nom_cost_usd.mean() / g.w.median(),
    "nominal_cost_R_mean": t1.groupby("y").nom_cost_R.mean(),
    "cost_R_tight_0.5w": t1.groupby("y").apply(lambda x: (x.nom_cost_usd / (0.5 * x.risk)).mean()),
    "cost_over_ATR_pct": t1.groupby("y").nom_cost_usd.mean() / g.atr.mean() * 100,
    "gross_avg_R": t0.groupby("y").R.mean(),
    "net_avg_R": t1.groupby("y").R.mean(),
    "net_avg_R_L": t1[t1.dir == 1].groupby("y").R.mean(),
    "net_avg_R_S": t1[t1.dir == -1].groupby("y").R.mean(),
})
tab = tab.loc[2014:2023]
print(C.fmt_table(tab.reset_index().rename(columns={"index": "year"}).round(3), floatfmt=3))
tab.to_csv(C.os.path.join(C.HERE, "out_year_table.csv"))
