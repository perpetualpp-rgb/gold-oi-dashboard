"""Statistical-validity lens for the frozen PRIMARY (IS+VAL only; data loaded with until=VAL_END).
Outputs: trades_primary.csv, trades_fallback.csv, s01_core.json"""
import json, os, sys
import numpy as np, pandas as pd
from statistics import NormalDist
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common import E, data  # noqa

nd = NormalDist()
cand = json.load(open(os.path.join(HERE, "..", "candidates.json")))["candidates"]
D = data()
assert D["index"].max() < pd.Timestamp("2024-01-01", tz="UTC")

def P(d):
    return E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})

days = D["days"].index
out = {}
TR = {}
for lab in ("primary", "fallback"):
    t = E.run(P(cand[lab]), end=E.VAL_END, D=D)
    t = t[t.date <= E.VAL_END]
    t.to_csv(os.path.join(HERE, f"trades_{lab}.csv"), index=False)
    TR[lab] = t

def stationary_idx(nd_, nb, block, rng):
    idx = np.empty((nb, nd_), dtype=np.int64)
    p = 1.0 / block
    for b in range(nb):
        new = rng.random(nd_) < p; new[0] = True
        st = rng.integers(0, nd_, nd_)
        # vectorised: position = start of current block + offset
        blk = np.cumsum(new) - 1
        bstart = st[np.flatnonzero(new)]
        first = np.flatnonzero(new)
        off = np.arange(nd_) - first[blk]
        idx[b] = (bstart[blk] + off) % nd_
    return idx

def day_series(t, lo, hi):
    dd = days[(days >= pd.Timestamp(lo)) & (days <= pd.Timestamp(hi))]
    S = np.zeros(len(dd)); N = np.zeros(len(dd))
    ix = np.searchsorted(dd.values, t.date.values)
    m = (t.date >= pd.Timestamp(lo)) & (t.date <= pd.Timestamp(hi))
    np.add.at(S, ix[m.values], t.R.values[m.values]); np.add.at(N, ix[m.values], 1)
    return S, N

periods = {"IS": ("2014-01-01", E.IS_END), "VAL": ("2022-01-01", E.VAL_END), "POOLED": ("2014-01-01", E.VAL_END)}
rng = np.random.default_rng(12345)
NB = 20000
for lab, t in TR.items():
    res = {}
    for per, (lo, hi) in periods.items():
        S, N = day_series(t, lo, hi)
        m = S.sum() / N.sum()
        R = t.R.values[(t.date >= lo).values & (t.date <= hi).values]
        r = dict(n=int(N.sum()), avg_R=round(m, 4), sd_R=round(R.std(ddof=1), 3),
                 se_iid=round(R.std(ddof=1) / np.sqrt(len(R)), 4), t_iid=round(m / (R.std(ddof=1) / np.sqrt(len(R))), 2))
        for block in (1, 5, 10, 20, 60):
            idx = stationary_idx(len(S), NB if block == 10 else 5000, block, rng)
            bm = S[idx].sum(1) / np.maximum(N[idx].sum(1), 1)
            r[f"b{block}"] = dict(ci90=[round(np.quantile(bm, .05), 4), round(np.quantile(bm, .95), 4)],
                                  se=round(bm.std(ddof=1), 4), P_gt0=round((bm > 0).mean(), 4))
        res[per] = r
    out[lab] = res
    print(lab, json.dumps(res, indent=0))

# ---------------- tail / year dependence (primary) --------------------------------------------
t = TR["primary"]
tail = {}
for per, (lo, hi) in periods.items():
    R = np.sort(t.R.values[(t.date >= lo).values & (t.date <= hi).values])[::-1]
    rr = {"max_R": round(R[0], 2), "top5": [round(x, 2) for x in R[:5]]}
    for k in (1, 3, 5, 10, 20, 30):
        rr[f"drop_top{k}"] = round(R[k:].mean(), 4)
    for c in (2, 3, 4):
        rr[f"winsor{c}R"] = round(np.minimum(R, c).mean(), 4)
    # share of total R from top 5% of trades
    k5 = max(1, int(0.05 * len(R)))
    rr["share_total_from_top5pct"] = round(R[:k5].sum() / R.sum(), 2) if R.sum() > 0 else None
    rr["median_R"] = round(np.median(R), 3)
    # how many top trades to remove to push avg <= 0
    cs = R.sum() - np.cumsum(R)
    rr["n_top_to_zero"] = int(np.argmax(cs <= 0) + 1) if (cs <= 0).any() else None
    tail[per] = rr
out["primary_tails"] = tail
yr = t.groupby(t.date.dt.year).R.agg(["size", "mean", "sum"]).round(3)
out["primary_by_year"] = yr.reset_index().to_dict("records")
drops = {}
isR = t[t.date <= E.IS_END]
allR = t
for y in sorted(t.date.dt.year.unique()):
    a = isR[isR.date.dt.year != y].R; b = allR[allR.date.dt.year != y].R
    drops[int(y)] = dict(IS_wo=round(a.mean(), 4), IS_t_wo=round(a.mean() / a.std(ddof=1) * np.sqrt(len(a)), 2),
                         POOLED_wo=round(b.mean(), 4), POOLED_t_wo=round(b.mean() / b.std(ddof=1) * np.sqrt(len(b)), 2))
a = isR[~isR.date.dt.year.isin([2014, 2020, 2021])].R
drops["IS_wo_2014_2020_2021"] = dict(avg=round(a.mean(), 4), t=round(a.mean() / a.std(ddof=1) * np.sqrt(len(a)), 2), n=len(a))
a = isR[~isR.date.dt.year.isin([2015, 2020])].R
drops["IS_wo_2015_2020"] = dict(avg=round(a.mean(), 4), t=round(a.mean() / a.std(ddof=1) * np.sqrt(len(a)), 2), n=len(a))
a = isR[~isR.date.dt.year.isin([2014])].R
drops["IS_wo_2014"] = dict(avg=round(a.mean(), 4), t=round(a.mean() / a.std(ddof=1) * np.sqrt(len(a)), 2), n=len(a))
out["primary_drop_year"] = drops
# month concentration
mo = t.groupby(t.date.dt.to_period("M")).R.sum().sort_values(ascending=False)
out["primary_top_months"] = {str(k): round(v, 2) for k, v in mo.head(8).items()}
out["primary_top_trades"] = t.sort_values("R", ascending=False).head(12)[["date", "dir", "R", "width", "atr"]].assign(date=lambda x: x.date.astype(str)).round(3).to_dict("records")
# direction split per period
out["primary_dir"] = {per: {("long" if d == 1 else "short"): dict(n=int(((t.dir == d) & (t.date >= lo) & (t.date <= hi)).sum()), avg=round(t.R[(t.dir == d) & (t.date >= lo) & (t.date <= hi)].mean(), 4)) for d in (1, -1)} for per, (lo, hi) in periods.items()}
json.dump(out, open(os.path.join(HERE, "s01_core.json"), "w"), indent=1, default=str)
print(json.dumps({k: out[k] for k in ("primary_tails", "primary_by_year", "primary_drop_year", "primary_top_months", "primary_top_trades", "primary_dir")}, indent=1, default=str))
