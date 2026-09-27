"""Modelled spread (median by year x London hour) vs actual Dukascopy M1 spreads on the raw days (<=2023)."""
import sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E
m = pd.read_csv(os.path.join(E.CACHE, "spread_model.csv"), index_col=0)
rows = []
for fb in sorted(glob.glob(os.path.join(E.CACHE, "raw", "XAUUSD_BID_*.npy"))):
    day = pd.Timestamp(os.path.basename(fb)[11:19], tz="UTC")
    if day >= pd.Timestamp("2024-01-01", tz="UTC"):
        continue
    fa = fb.replace("_BID_", "_ASK_")
    if not os.path.exists(fa):
        continue
    b, a = np.load(fb), np.load(fa)
    if len(b) == 0 or len(a) != len(b):
        continue
    live = b[:, 5] > 0
    ts = day + pd.to_timedelta(b[:, 0].astype(np.int64), unit="s")
    lt = ts.tz_convert("Europe/London")
    so = (a[:, 1] - b[:, 1]) / 1000   # spread at bar open
    rng = (b[:, 4] - b[:, 3]) / 1000
    rows.append(pd.DataFrame({"y": day.year, "h": lt.hour, "dow": lt.dayofweek, "spr": so, "rng": rng})[live])
df = pd.concat(rows)
print("days:", len(rows), "bars:", len(df))
df["model"] = [m.loc[y, str(h)] for y, h in zip(df.y, df.h)]
df["model"] = np.maximum(df["model"], 0.15)
sess = df[(df.h >= 7) & (df.h < 20)]
g = sess.groupby("y").agg(model=("model", "median"), act_med=("spr", "median"), act_mean=("spr", "mean"),
                           act_p90=("spr", lambda x: x.quantile(.9)), n=("spr", "size"))
print("07-20 London:\n", g.round(3).to_string())
# spread on high-activity bars (range in top 5% of that day-hour) -- breakout bars
sess = sess.assign(q=sess.groupby("y").rng.rank(pct=True))
hi = sess[sess.q > 0.95]
print("top-5% range bars: actual mean spread / model:\n",
      hi.groupby("y").apply(lambda x: pd.Series({"act_mean": x.spr.mean(), "model": x.model.mean(), "ratio": x.spr.mean() / x.model.mean()})).round(3).to_string())
# 07-09 London (breakout hours)
b7 = df[(df.h >= 7) & (df.h < 9)]
print("07-09 London mean actual vs model:", round(b7.spr.mean(), 3), round(b7.model.mean(), 3))
