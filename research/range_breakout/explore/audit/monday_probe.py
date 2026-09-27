import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E
full = pd.read_parquet(os.path.join(E.CACHE, "XAUUSD_M1_BID.parquet"))
full = full[full.index < pd.Timestamp("2024-01-01", tz="UTC")]
u = full.index
sun = u[(u.dayofweek == 6)]
s = pd.Series(1, index=sun)
hr = s.groupby([sun.normalize(), sun.hour]).size().unstack(fill_value=0)
print("Sunday bars per UTC hour (share of Sundays with >=30 bars):")
print((hr >= 30).groupby(hr.index.year).mean().round(2).to_string())
# per hour of Monday London 00-07 coverage: minutes present per hour, Mondays vs Tue-Fri
lt = u.tz_convert("Europe/London")
m = (lt.hour < 7) & (lt.dayofweek < 5)
df = pd.DataFrame({"d": lt[m].normalize(), "h": lt[m].hour, "dow": lt[m].dayofweek, "y": lt[m].year})
c = df.groupby(["d", "h"]).size().unstack(fill_value=0)
dow = pd.Index(c.index).dayofweek
print("mean minutes present in London hour 0..6, Mondays:\n", c[dow == 0].groupby(c[dow == 0].index.year).mean().round(0).to_string())
print("Tue-Fri:\n", c[dow > 0].groupby(c[dow > 0].index.year).mean().round(0).to_string())
