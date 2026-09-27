"""Stage 8: implementability check (IS only). MT5 D1 bars usually close at 17:00 New York (server GMT+2/+3),
not at London midnight. Recompute ATR14 (SMA of true range, like MT5 iATR) on NY-close days and re-run the
filters with that ATR. A London day d uses broker days up to d-1 (broker day d-1 ends 22:00 London d-1,
before the Asian range of day d starts).
"""
import numpy as np
import pandas as pd

from common import E, Counter, md, full_summary
from features import run_mask

D = E.load()
C = Counter("s08")
idx = D["index"]
ny = idx.tz_convert("America/New_York").tz_localize(None)
bday = (ny + pd.Timedelta(hours=7)).normalize()          # broker day: 17:00 NY .. 17:00 NY
s = pd.DataFrame({"d": bday, "h": D["bh"], "l": D["bl"], "c": D["bc"]})
g = s.groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
g = g[g.index.dayofweek < 5]
pc = g["c"].shift(1)
tr = np.maximum(g["h"] - g["l"], np.maximum((g["h"] - pc).abs(), (g["l"] - pc).abs()))
atr_b = tr.rolling(14).mean()                                # ATR14 as of the END of broker day
atr_b_prev = atr_b.shift(1)                                  # as of the end of the previous broker day
days = D["days"].index
atr_prev = atr_b_prev.reindex(days).values                   # London day d -> broker days <= d-1
mean20 = pd.Series(atr_prev).rolling(20, min_periods=12).mean().values
mean50 = pd.Series(atr_prev).rolling(50, min_periods=30).mean().values

p0 = E.Params()
*_, rh, rl, valid, _ = E._windows_full(D, p0.range_start, p0.range_end, p0.entry_end, p0.exit_time)
width = rh - rl
w_atr_b = width / atr_prev
eng_atr = D["days"]["atr14_prev"].values
print("corr London-day ATR vs NY-close ATR (IS):",
      np.corrcoef(eng_atr[(days <= E.IS_END) & np.isfinite(atr_prev) & np.isfinite(eng_atr)],
                  atr_prev[(days <= E.IS_END) & np.isfinite(atr_prev) & np.isfinite(eng_atr)])[0, 1].round(4))

rows = []
for name, mask in (
        ("NY-ATR w>=0.35", w_atr_b >= 0.35),
        ("NY-ATR a20<=1", atr_prev / mean20 <= 1.0),
        ("NY-ATR w>=0.3&a20<=1", (w_atr_b >= 0.3) & (atr_prev / mean20 <= 1.0)),
        ("NY-ATR w>=0.35&a20<=1", (w_atr_b >= 0.35) & (atr_prev / mean20 <= 1.0)),
        ("NY-ATR w>=0.3&a50<=1", (w_atr_b >= 0.3) & (atr_prev / mean50 <= 1.0))):
    t = run_mask(p0, np.nan_to_num(mask).astype(bool), D)
    d = {"stage": "s08", "name": name, "tag": "posthoc", **full_summary(t), "params": name}
    C.rows.append(d)
    rows.append({"filter": name, "n": d["n"], "avg_R": d["avg_R"], "PF": d["PF"], "t": d["t_stat"],
                 "yrs_pos": d["yrs_pos"], "L_avg_R": d["L_avg_R"], "S_avg_R": d["S_avg_R"], "maxDD_R": d["maxDD_R"]})
C.save()
txt = md(pd.DataFrame(rows))
print(txt)
open("out_s08_broker_atr.txt", "w").write("# Stage 8: filters with NY-close (MT5-style) daily ATR, IS\n\n" + txt + "\n")
