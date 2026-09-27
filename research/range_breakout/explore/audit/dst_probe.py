import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E
full = pd.read_parquet(os.path.join(E.CACHE, "XAUUSD_M1_BID.parquet"))
full = full[full.index < pd.Timestamp("2024-01-01", tz="UTC")]
t = full.index[full["volume"] >= 0].to_series()
gap = t.diff().dt.total_seconds() / 60
reopen = t[(gap >= 30) & (gap <= 180)]
ny = reopen.dt.tz_convert("America/New_York")
lo = reopen.dt.tz_convert("Europe/London")
us_dst = ny.map(lambda x: x.dst() != pd.Timedelta(0))
eu_dst = lo.map(lambda x: x.dst() != pd.Timedelta(0))
mis = us_dst != eu_dst
ok = (ny.dt.hour == 18) & (ny.dt.minute <= 5)
df = pd.DataFrame({"y": reopen.dt.year, "mis": mis, "ok": ok, "nyh": ny.dt.strftime("%H:%M")})
print(df.groupby(["y", "mis"]).ok.agg(["mean", "size"]).unstack().round(3).to_string())
print(df[df.mis & ~df.ok].head(30).to_string())
# Monday 00:00 London holes
b = full
lt = b.index.tz_convert("Europe/London")
for d in ["2019-04-01", "2022-03-28", "2023-06-05", "2023-06-26"]:
    day = pd.Timestamp(d, tz="Europe/London")
    w = b[(lt >= day - pd.Timedelta(hours=2)) & (lt < day + pd.Timedelta(hours=2))]
    print(d, "bars:", len(w), "first/last:", w.index[0].tz_convert("Europe/London"), w.index[-1].tz_convert("Europe/London"))
    x = w.index.tz_convert("Europe/London").to_series().diff().dt.total_seconds().div(60)
    print("   gaps:", x[x > 2].to_dict(), "vol<0 share", (w.volume < 0).mean().round(2))
