"""Data audit on IS+VAL only (<= 2023-12-31). Never looks at 2024+."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E

bid = pd.read_parquet(os.path.join(E.CACHE, "XAUUSD_M1_BID.parquet"))
ask = pd.read_parquet(os.path.join(E.CACHE, "XAUUSD_M1_ASK.parquet"))
END = pd.Timestamp("2024-01-01", tz="UTC")
bid = bid[bid.index < END]; ask = ask[ask.index < END]
print("rows", len(bid), bid.index[0], bid.index[-1], "tz", bid.index.tz)
print("index monotonic", bid.index.is_monotonic_increasing, "dups", bid.index.duplicated().sum())
print("ask index equal", bid.index.equals(ask.index))
print("non-minute ts", (bid.index.second != 0).sum())
# OHLC consistency
b = bid
bad = (b.high < b[["open", "close"]].max(axis=1) - 1e-9) | (b.low > b[["open", "close"]].min(axis=1) + 1e-9) | (b.high < b.low)
print("OHLC inconsistent bars", bad.sum())
print(b[bad].head())
# london clock monotonic
local = b.index.tz_convert("Europe/London").tz_localize(None)
lmin = local.values.astype("datetime64[m]").astype(np.int64)
dl = np.diff(lmin)
print("lmin non-increasing steps", (dl <= 0).sum())
if (dl <= 0).any():
    j = np.where(dl <= 0)[0]
    print(b.index[j][:10])
# spikes
ret = np.log(b.close).diff()
rng = (b.high - b.low) / b.close
print("bars with |close-to-close| > 1%:", (ret.abs() > 0.01).sum())
print(pd.DataFrame({"ret": ret[ret.abs() > 0.01]}).assign(year=lambda x: x.index.year).groupby("year").size())
print("bars with H-L range > 1%:", (rng > 0.01).sum())
big = rng[rng > 0.01].sort_values(ascending=False)
print(pd.concat([b.loc[big.index[:25]], big[:25].rename("rng")], axis=1))
# spike-and-revert: bar high/low far from both neighbours' closes
pc = b.close.shift(1); nc = b.close.shift(-1)
up_sp = (b.high - np.maximum(pc, nc)) / b.close
dn_sp = (np.minimum(pc, nc) - b.low) / b.close
sp = pd.concat([up_sp, dn_sp], axis=1).max(axis=1)
print("spike-revert wicks > 0.5%:", (sp > 0.005).sum(), " > 0.3%:", (sp > 0.003).sum())
print(pd.concat([b.loc[sp[sp > 0.005].index], sp[sp > 0.005].rename("wick")], axis=1).head(40))
# flat bars
flat = (b.high == b.low)
print("flat bars share by year:\n", flat.groupby(b.index.year).mean().round(4).to_string())
# runs of identical closes (stale feed)
same = (b.close.diff() == 0) & flat
runid = (~same).cumsum()
runs = same.groupby(runid).sum()
print("longest stale runs (minutes):", runs.sort_values(ascending=False).head(10).to_dict())
# source mix
print("dukascopy-patched bars by year:\n", (b.volume < 0).groupby(b.index.year).sum().to_string())
# gaps inside London 00:00-20:00 on weekdays
lt = b.index.tz_convert("Europe/London")
g = pd.Series(b.index).diff().dt.total_seconds().div(60).values
gp = pd.DataFrame({"t": lt, "gap": g})
gp = gp[(gp.gap > 5) & (gp.t.dt.dayofweek < 5) & (gp.t.dt.hour >= 1) & (gp.t.dt.hour < 21)]
print("intra-session gaps >5min (London 01-21h, weekdays) by year:\n", gp.groupby(gp.t.dt.year).agg(n=("gap", "size"), mx=("gap", "max")).to_string())
print(gp.sort_values("gap", ascending=False).head(20).to_string())
# spread
spr = ask.close - bid.close
print("spread quantiles", spr.quantile([0, .01, .5, .99, 1]).round(3).to_dict())
print("spread constant within hour?", (ask.high - bid.high - spr).abs().max())
# weekend
print("bars on Saturday (UTC):", (b.index.dayofweek == 5).sum(), " Sunday bars before 21:00 UTC:", ((b.index.dayofweek == 6) & (b.index.hour < 21)).sum())
fri_last = b.groupby(lt.normalize()).apply(lambda x: x.index[-1].tz_convert("Europe/London").strftime("%H:%M"))
fri = fri_last[fri_last.index.dayofweek == 4]
print("Friday last bar London time distribution:", fri.value_counts().head(8).to_dict())
sun_first = b.groupby(lt.normalize()).apply(lambda x: x.index[0].tz_convert("Europe/London").strftime("%H:%M"))
print("Sunday first bar London:", sun_first[sun_first.index.dayofweek == 6].value_counts().head(8).to_dict())
