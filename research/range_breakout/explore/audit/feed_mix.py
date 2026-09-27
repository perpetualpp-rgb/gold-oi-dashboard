"""Does the Dukascopy patch (2023 mostly) have different bar ranges from HistData? Same-day comparison."""
import sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E
full = pd.read_parquet(os.path.join(E.CACHE, "XAUUSD_M1_BID.parquet"))
full = full[full.index < pd.Timestamp("2024-01-01", tz="UTC")]
hd = full[full.volume >= 0]
res = []
for fb in sorted(glob.glob(os.path.join(E.CACHE, "raw", "XAUUSD_BID_*.npy"))):
    day = pd.Timestamp(os.path.basename(fb)[11:19], tz="UTC")
    if day >= pd.Timestamp("2024-01-01", tz="UTC"):
        continue
    r = np.load(fb)
    if len(r) == 0:
        continue
    r = r[r[:, 5] > 0]
    ts = day + pd.to_timedelta(r[:, 0].astype(np.int64), unit="s")
    dk = pd.DataFrame({"h": r[:, 4] / 1000, "l": r[:, 3] / 1000, "c": r[:, 2] / 1000}, index=ts)
    h = hd.loc[day: day + pd.Timedelta(hours=23, minutes=59)]
    j = dk.join(h[["high", "low", "close"]], how="inner")
    lt = j.index.tz_convert("Europe/London")
    j = j[(lt.hour >= 0) & (lt.hour < 12)]
    if len(j) < 300:
        continue
    res.append(dict(day=day.date(), n=len(j), dk_rng=(j.h - j.l).mean(), hd_rng=(j.high - j.low).mean(),
                    # Asian (00-07 London) range width on each feed
                    dk_w=(j.h[lt[(lt.hour >= 0) & (lt.hour < 12)].hour < 7].max() - j.l[lt[(lt.hour >= 0) & (lt.hour < 12)].hour < 7].min()),
                    hd_w=(j.high[lt[(lt.hour >= 0) & (lt.hour < 12)].hour < 7].max() - j.low[lt[(lt.hour >= 0) & (lt.hour < 12)].hour < 7].min())))
df = pd.DataFrame(res)
df["y"] = pd.to_datetime(df.day).dt.year
df["bar_ratio"] = df.dk_rng / df.hd_rng
df["w_ratio"] = df.dk_w / df.hd_w
print("same-day comparisons:", len(df))
print(df.groupby("y")[["bar_ratio", "w_ratio"]].agg(["median", "size"]).round(3).to_string())
# 2023: mean M1 range 07-12 London, patched vs HistData days, normalised by price
lt = full.index.tz_convert("Europe/London")
x = full[(lt.year == 2023) & (lt.hour >= 7) & (lt.hour < 12)]
xr = (x.high - x.low) / x.close * 1e4
print("2023 07-12 London mean M1 range (bp): HistData", round(xr[x.volume >= 0].mean(), 3), " Dukascopy-patched", round(xr[x.volume < 0].mean(), 3))
