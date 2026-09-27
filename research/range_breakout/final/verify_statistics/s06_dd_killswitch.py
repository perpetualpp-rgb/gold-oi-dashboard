"""Drawdown / kill-switch bands for live monitoring: resample IS+VAL primary trades (iid, and 10-trade
blocks), shifted to a true mean mu, over horizons of 60/120/250 trades."""
import json, os
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
t = pd.read_csv(os.path.join(HERE, "trades_primary.csv"), parse_dates=["date"])
R = t.R.values; rng = np.random.default_rng(11); out = {}
w = t.width.values
out["risk_usd_per_oz"] = dict(median=round(np.median(w), 2), p10=round(np.quantile(w, .1), 2), p90=round(np.quantile(w, .9), 2))
for mu in (0.12, 0.03, 0.0, -0.05):
    base = R - R.mean() + mu
    for H in (60, 120, 250, 600):
        s = base[rng.integers(0, len(base), (20000, H))]
        eq = np.cumsum(s, 1); dd = (np.maximum.accumulate(np.maximum(eq, 0), 1) - eq).max(1)
        out[f"mu{mu}_H{H}"] = dict(final_p05=round(np.quantile(eq[:, -1], .05), 1), final_p50=round(np.median(eq[:, -1]), 1),
                                  P_final_lt0=round((eq[:, -1] < 0).mean(), 3),
                                  maxDD_p50=round(np.median(dd), 1), maxDD_p95=round(np.quantile(dd, .95), 1),
                                  maxDD_p99=round(np.quantile(dd, .99), 1))
# losing streaks
L = (R < 0).astype(int); best = cur = 0
for x in L:
    cur = cur + 1 if x else 0; best = max(best, cur)
out["longest_losing_streak_hist"] = int(best)
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, "s06_dd_killswitch.json"), "w"), indent=1)
