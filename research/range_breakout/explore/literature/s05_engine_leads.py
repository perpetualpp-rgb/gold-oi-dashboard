"""Check the three literature leads with the real engine (costs, 1W stop, 20:00 exit), IS only.

Base = engine default Params() (Asian range 00-07, stop entries at the edges, entries to 12:00, exit 20:00).
Leads are applied as day filters on the base trades. With max_trades=1 this is exactly what an EA would do
if it cancels the day's orders when the filter says no, because every filter is known before the entry:
  L1 relative activity (Zarattini/Aziz relative volume proxy): only days with no break before 07:30 and
     range(07:00-07:30)/14-day mean >= x   (decision at 07:30; trades entering before 07:30 are dropped)
  L2 calm volatility regime (inverse of Lundstrom): ATR%/median250 <= x   (decision at 00:00)
  L3 previous-day daily NR7/NR4 (Crabel)  (decision at 00:00)
  L4 wide Asian range W/ATR >= x (the opposite of the NR/compression claim)  (decision at 07:00)
Output: out_s05_engine_leads.txt and configs_log.csv
"""
import numpy as np
import pandas as pd

import common  # noqa: F401  (sets sys.path)
import engine
from features import day_features

D = engine.load()
F = day_features("2022-01-01")
base = engine.run(engine.Params(), end=engine.IS_END)
base = base.join(F, on="date")
base["lmod_entry"] = D["lmin"][base["i_entry"].values] % 1440

lines = []
P = lines.append
log = []


def row(name, t):
    s = engine.stats(t, name)
    L, S = t[t["dir"] == 1], t[t["dir"] == -1]
    by = engine.by_year(t)
    return dict(config=name, n=s["n"], tpy=s.get("trades_per_year"), avg_R=s.get("avg_R"), win=s.get("win_rate"),
                PF=s.get("PF"), t=s.get("t_stat"), maxDD=s.get("maxDD_R"),
                yrs_pos=int((by["avg_R"] > 0).sum()) if len(by) else 0,
                L_n=len(L), L_avgR=round(L["R"].mean(), 4) if len(L) else np.nan,
                S_n=len(S), S_avgR=round(S["R"].mean(), 4) if len(S) else np.nan)


configs = [("base Params()", np.ones(len(base), bool)),
           ("L1 entry>=07:30 (no filter)", base["lmod_entry"].values >= 450)]
for x in (1.0, 1.25, 1.5):
    configs.append((f"L1 entry>=07:30 & relact_lon>={x}", (base["lmod_entry"].values >= 450) & (base["relact_lon"].values >= x)))
for x in (0.85, 0.9, 1.0):
    configs.append((f"L2 volstate<={x}", base["volstate"].values <= x))
configs.append(("L3 prev daily NR7", base["nr7_prev"].values == 1))
configs.append(("L3 prev daily NR4", base["nr4_prev"].values == 1))
for x in (0.32, 0.39):
    configs.append((f"L4 W/ATR>={x}", base["wa"].values >= x))

rows = [row(n, base[m]) for n, m in configs]
R = pd.DataFrame(rows)
P("IS 2014-2021, engine default costs. avg_R net of costs. L_/S_ = longs/shorts.")
with pd.option_context("display.width", 250, "display.max_columns", 30):
    P(R.to_string(index=False))

# year-by-year for the L1/L2/L3 central values
for n, m in configs:
    if n in ("L1 entry>=07:30 & relact_lon>=1.25", "L2 volstate<=0.9", "L3 prev daily NR7"):
        by = engine.by_year(base[m])
        P(f"\n{n} by year:\n" + by.to_string())

R.to_csv("configs_log.csv", index=False)
open("out_s05_engine_leads.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
