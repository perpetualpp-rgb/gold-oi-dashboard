"""Check A: time-of-day drift and volatility in spot gold, IS 2014-2021 only.

Literature claims checked:
  - Blose & Gondhalekar (2014), Blose, Gondhalekar & Kort (2018): gold overnight returns > 0, day (COMEX
    pit hours) returns < 0.
  - Abrantes-Metz & Metz (2014 draft): large moves at the London PM fix skew downward (2004-2013).
  - Caminschi & Heaney (2014): elevated volatility right after the PM fix starts.
  - Andersen & Bollerslev (1998), Cai, Cheung & Wong (2001), Elder et al (2012): volatility peaks at the
    European open and at 8:30 ET US macro releases.
Output: out_s01_timeofday.txt
"""
import numpy as np
import pandas as pd

from common import load_is, tstat

D = load_is()
lmin, bc, bh, bl = D["lmin"], D["bc"], D["bh"], D["bl"]
lines = []
P = lines.append

# ---- bar-to-bar log returns, excluding weekend gaps -------------------------------------------------
gap = np.r_[10 ** 6, np.diff(lmin)]
r = np.r_[np.nan, np.diff(np.log(bc))]
ok = gap <= 120                      # keeps the 22:00-23:00 London daily halt, drops weekends
r = np.where(ok, r, np.nan)
hour = D["lmod"] // 60
day = D["lday"]
dow = D["ldow"]
year = D["year"]

df = pd.DataFrame({"day": day, "hour": hour, "r": r, "year": year, "dow": dow,
                   "rng": np.log(bh / bl)})
df = df[df["dow"] < 5 + 2]           # keep all (Sunday evening bars belong to Monday's Asian session)
hr = df.groupby(["day", "hour"]).agg(r=("r", "sum"), year=("year", "first")).reset_index()
tot_daily = hr.groupby("day")["r"].sum()
P("Check A1: mean London-hour log return, bps (IS 2014-2021; BID close-to-close, weekend gaps dropped)")
P(f"Average total per London day: {tot_daily.mean()*1e4:.2f} bps (days={len(tot_daily)}); "
  f"sum over IS = {tot_daily.sum():.3f} log")
rows = []
for h in range(24):
    x = hr.loc[hr["hour"] == h]
    if len(x) < 100:
        continue
    by = x.groupby("year")["r"].mean()
    rows.append(dict(hour=h, n=len(x), mean_bps=x["r"].mean() * 1e4, t=tstat(x["r"].values),
                     yrs_pos=int((by > 0).sum()), yrs=len(by),
                     share_of_total=x["r"].sum() / tot_daily.sum()))
T = pd.DataFrame(rows)
P(T.round(3).to_string(index=False))

# ---- session buckets (London clock) -----------------------------------------------------------------
P("\nCheck A2: session buckets (London clock), mean bps per day, t-stat, years positive of 8")
buckets = {"Asia 23-07": list(range(23, 24)) + list(range(0, 7)), "Asia 00-07 (no reopen)": list(range(0, 7)),
           "London AM 07-12": list(range(7, 12)),
           "NY overlap 12-17": list(range(12, 17)), "NY PM 17-22": list(range(17, 22)),
           "NY PM 17-21 (no rollover)": list(range(17, 21)), "engine window 07-20": list(range(7, 20)),
           "rollover 21+22+23": [21, 22, 23]}
rows = []
for name, hs in buckets.items():
    x = hr[hr["hour"].isin(hs)].groupby("day").agg(r=("r", "sum"), year=("year", "first"))
    by = x.groupby("year")["r"].mean()
    rows.append(dict(bucket=name, n=len(x), mean_bps=x["r"].mean() * 1e4, t=tstat(x["r"].values),
                     yrs_pos=int((by > 0).sum()), share=x["r"].sum() / tot_daily.sum(),
                     **{str(y): round(v * 1e4, 1) for y, v in by.items()}))
P(pd.DataFrame(rows).round(2).to_string(index=False))

# ---- Blose-Gondhalekar definition: COMEX pit day 08:20-13:30 ET vs overnight 13:30 ET -> 08:20 ET ----
P("\nCheck A3: COMEX pit 'day' (08:20-13:30 New York) vs 'overnight' (13:30 NY -> next 08:20 NY)")
nymod, nyday = D["nymod"], D["nyday"]
ny = pd.DataFrame({"nyday": nyday, "nymod": nymod, "r": r, "year": year})
ny["seg"] = np.where((ny["nymod"] >= 8 * 60 + 20) & (ny["nymod"] < 13 * 60 + 30), "day", "night")
# overnight segment belongs to the NEXT pit day if after 13:30
ny["key"] = np.where(ny["nymod"] >= 13 * 60 + 30, ny["nyday"] + 1, ny["nyday"])
g = ny.groupby(["key", "seg"]).agg(r=("r", "sum"), year=("year", "first")).reset_index()
rows = []
for seg in ("day", "night"):
    x = g[g["seg"] == seg]
    x = x[x["r"] != 0]
    by = x.groupby("year")["r"].mean()
    rows.append(dict(segment=seg, n=len(x), mean_bps=x["r"].mean() * 1e4, t=tstat(x["r"].values),
                     yrs_pos=int((by > 0).sum()), **{str(y): round(v * 1e4, 1) for y, v in by.items()}))
P(pd.DataFrame(rows).round(2).to_string(index=False))

# ---- London fix / auction windows -------------------------------------------------------------------
P("\nCheck A4: returns around the London gold fix/auction (10:30 AM, 15:00 PM London). bps, t, "
  "mean |r| vs same-length control window 1h earlier.")
REFORM = pd.Timestamp("2015-03-20").value // 60_000_000_000 // 1440  # London day number of the first IBA auction


def window_ret(t0, t1, sub=None):
    base = (np.unique(D["lday"]) * 1440)
    base = base[pd.to_datetime(base // 1440 * 86400, unit="s").dayofweek < 5]
    if sub is not None:
        base = base[sub(base // 1440)]
    j0 = np.searchsorted(lmin, base + t0) - 1
    j1 = np.searchsorted(lmin, base + t1) - 1
    good = (j0 >= 0) & (base + t0 - lmin[j0] <= 5) & (base + t1 - lmin[j1] <= 5) & (j1 > j0)
    return np.log(bc[j1[good]] / bc[j0[good]])


rows = []
for label, t0, t1 in [("AM fix 10:25-10:45", 625, 645), ("control 09:25-09:45", 565, 585),
                      ("PM fix 14:55-15:15", 895, 915), ("control 13:55-14:15", 835, 855),
                      ("PM fix 15:00-15:05", 900, 905), ("pre-PM 14:30-15:00", 870, 900),
                      ("post-PM 15:15-16:00", 915, 960)]:
    for per, sub in (("2014..2015-03-19 (old fix)", lambda d: d < REFORM), ("2015-03-20..2021 (IBA)", lambda d: d >= REFORM)):
        x = window_ret(t0, t1, sub)
        rows.append(dict(window=label, period=per, n=len(x), mean_bps=x.mean() * 1e4, t=tstat(x),
                         pct_down=(x < 0).mean(), mean_abs_bps=np.abs(x).mean() * 1e4,
                         big_moves_down=(x[np.abs(x) > np.quantile(np.abs(x), 0.9)] < 0).mean()))
P(pd.DataFrame(rows).round(3).to_string(index=False))

# ---- volatility profile ------------------------------------------------------------------------------
P("\nCheck A5: volatility profile by London hour: mean |1-min log return| (bps) and mean 1-min "
  "high-low (bps), relative to the 24h mean")
vol = df.groupby("hour").agg(abs_r=("r", lambda s: np.nanmean(np.abs(s)) * 1e4),
                             rng=("rng", lambda s: np.nanmean(s) * 1e4))
vol["abs_r_rel"] = vol["abs_r"] / vol["abs_r"].mean()
P(vol.round(3).to_string())

# minute-level spikes: top 15 London minutes by mean |r|
mm = pd.DataFrame({"lmod": D["lmod"], "ar": np.abs(r)}).groupby("lmod")["ar"].mean() * 1e4
P("\nTop 15 London minutes-of-day by mean |1-min return| (bps):")
top = mm.sort_values(ascending=False).head(15)
P("  " + ", ".join(f"{m//60:02d}:{m%60:02d}={v:.2f}" for m, v in top.items()))
P(f"  median minute = {mm.median():.2f} bps")
nym = pd.DataFrame({"nymod": D["nymod"], "ar": np.abs(r)}).groupby("nymod")["ar"].mean() * 1e4
P("Top 10 New York minutes-of-day by mean |1-min return| (bps):")
P("  " + ", ".join(f"{m//60:02d}:{m%60:02d}={v:.2f}" for m, v in nym.sort_values(ascending=False).head(10).items()))

open("out_s01_timeofday.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
