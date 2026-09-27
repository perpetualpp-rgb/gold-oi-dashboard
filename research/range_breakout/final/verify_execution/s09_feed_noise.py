"""(e) Broker feed != HistData feed. Each broker's BID highs/lows differ by cents and by spike wicks, which
moves the range edges, ATR, the width/ATR filter and the regime filter. Perturb every M1 bar's high and low
independently: high += e_h, low -= e_l, e ~ N(0, sigma) (then high >= max(open, close), low <= min(open,
close) enforced), ASK shifted identically; 20 seeds per sigma. Report avg R distribution and trade-day
overlap with the engine. Reference: HistData vs Dukascopy 2014 (s05_duka_2014.json): 31 common days of
33/38, avg R 0.39 vs 0.26; |feed offset| p90 0.10-0.12 USD at trigger minutes (s02c)."""
from xcommon import *
D = data()
p = params("primary")
ref = E.run(p, end=E.VAL_END, D=D)
spr = {c: D["a" + c] - D["b" + c] for c in ("o", "h", "l", "c")}
res = {}
for sigma in (0.03, 0.06, 0.12):
    rows = []
    for seed in range(20):
        rng = np.random.default_rng(seed)
        n = len(D["bh"])
        bh = np.maximum(D["bh"] + rng.normal(0, sigma, n), np.maximum(D["bo"], D["bc"]))
        bl = np.minimum(D["bl"] - rng.normal(0, sigma, n), np.minimum(D["bo"], D["bc"]))
        d = {k: v for k, v in D.items() if k not in ("_win_cache", "days")}
        d["bh"], d["bl"] = bh, bl
        d["ah"], d["al"] = bh + spr["h"], bl + spr["l"]
        d["days"] = E._daily(d)
        t = E.run(p, end=E.VAL_END, D=d)
        isv = t[t.date <= E.IS_END].R; va = t[t.date > E.IS_END].R
        common = len(set(t.date) & set(ref.date))
        rows.append(dict(seed=seed, n=len(t), IS=isv.mean(), VAL=va.mean(), ALL=t.R.mean(),
                         jacc=common / len(set(t.date) | set(ref.date))))
    X = pd.DataFrame(rows)
    res[sigma] = dict(n_mean=round(X.n.mean(), 1), IS_mean=round(X.IS.mean(), 4), IS_min=round(X.IS.min(), 4), IS_max=round(X.IS.max(), 4),
                      VAL_mean=round(X.VAL.mean(), 4), ALL_mean=round(X.ALL.mean(), 4), ALL_sd=round(X.ALL.std(), 4),
                      ALL_min=round(X.ALL.min(), 4), ALL_max=round(X.ALL.max(), 4), jaccard_mean=round(X.jacc.mean(), 3))
    print(sigma, res[sigma], flush=True)
res["engine"] = dict(IS=round(ref[ref.date <= E.IS_END].R.mean(), 4), ALL=round(ref.R.mean(), 4), n=len(ref))
json.dump({str(k): v for k, v in res.items()}, open("s09_feed_noise.json", "w"), indent=1)
