"""Real Dukascopy BID/ASK spread (data_cache/raw sample days) vs the modelled ASK-BID spread used by the
engine, in the entry window 05:00-12:00 London, per year. Also bar coverage per year (data quality)."""
import glob, os, sys
import numpy as np
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import engine as E
RAW = os.path.join(ROOT, "data_cache", "raw")
D = E.load()
model = pd.DataFrame({"spr": D["ao"] - D["bo"], "bid": D["bo"]}, index=D["index"])
rows = []
for fb in sorted(glob.glob(os.path.join(RAW, "XAUUSD_BID_*.npy"))):
    day = os.path.basename(fb)[-12:-4]
    fa = fb.replace("_BID_", "_ASK_")
    if not os.path.exists(fa):
        continue
    b, a = np.load(fb), np.load(fa)
    if len(b) == 0 or len(a) == 0:
        continue
    base = pd.Timestamp(day, tz="UTC")
    bi = pd.Series(b[:, 1] / 1000, index=base + pd.to_timedelta(b[:, 0].astype(np.int64), unit="s"))
    ai = pd.Series(a[:, 1] / 1000, index=base + pd.to_timedelta(a[:, 0].astype(np.int64), unit="s"))
    vol = pd.Series(b[:, 5], index=bi.index)
    df = pd.DataFrame({"b": bi, "a": ai, "v": vol}).dropna()
    df = df[df.v > 0]
    loc = df.index.tz_convert("Europe/London")
    h = loc.hour
    df = df[(h >= 5) & (h < 12) & (loc.dayofweek < 5)]
    if len(df) < 60:
        continue
    j = model.index.intersection(df.index)
    if len(j) < 60:
        continue
    rows.append(dict(day=day, year=int(day[:4]), real_spr=(df.a - df.b).loc[j].mean(),
                     real_spr_med=(df.a - df.b).loc[j].median(), model_spr=model.spr.loc[j].mean(),
                     bid_diff=(model.bid.loc[j] - df.b.loc[j]).abs().median(), price=df.b.mean()))
r = pd.DataFrame(rows)
g = r.groupby("year").agg(days=("day", "size"), price=("price", "mean"), real_spr=("real_spr", "mean"),
                          real_spr_med=("real_spr_med", "mean"), model_spr=("model_spr", "mean"),
                          bid_absdiff_med=("bid_diff", "median")).round(3)
g["real_bp"] = (g.real_spr / g.price * 1e4).round(2)
g["model_bp"] = (g.model_spr / g.price * 1e4).round(2)
print(g.to_string())
g.to_csv(os.path.join(HERE, "spread_real_vs_model_by_year.csv"))
# coverage: M1 bars per weekday per year in the 00:00-20:00 London session
lm = D["lmin"]; day = lm // 1440; mod = lm % 1440
s = pd.DataFrame({"day": day, "in": mod < 20 * 60})
per = s[s["in"]].groupby("day").size()
yr = pd.to_datetime(per.index * 86400, unit="s").year
cov = per.groupby(yr).agg(["size", "median", lambda x: (x < 0.9 * 1200).mean()])
cov.columns = ["days", "median_bars_00_20", "share_days_lt90pct"]
print(cov.round(3).to_string())
cov.to_csv(os.path.join(HERE, "coverage_by_year.csv"))
