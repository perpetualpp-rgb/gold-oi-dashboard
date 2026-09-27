"""Kill-switch calibration on IS+VAL trades of the primary (and fallback).

The empirical trade-R distribution (IS+VAL) is re-centred to a set of true means mu and resampled with a
stationary block bootstrap over trades (mean block 10). For each rule we report P(rule fires within H
trades) and the median number of trades to fire, so the false-kill rate (mu > 0) and the detection power
(mu <= 0) can be traded off. Horizons: 130 trades (~2 years), 200 trades (~3 years).
Rules:
  roll60<X   : rolling 60-trade mean R below X (checked from trade 60)
  roll100<X  : rolling 100-trade mean R below X (from trade 100)
  DD>Y       : peak-to-trough drawdown of cumulative R above Y (CUSUM with reference 0)
  CUSUMk>h   : drawdown of (cumR - k*n), i.e. Page CUSUM for "mean below k", threshold h
Also: bootstrap distribution of max drawdown at the empirical mean (for 'DD beyond the 95th percentile').
Outputs s04_killswitch.json, s04_rules_{name}.csv
"""
import os
import numpy as np
import pandas as pd

from rcommon import E, data, cand_params, dump, HERE

D = data()
C = cand_params()
rng = np.random.default_rng(7)
NB = 4000
MB = 10


def sbb_idx(n, H, rng):
    """stationary bootstrap indices of length H from a series of length n (circular)."""
    idx = np.empty(H, dtype=np.int64)
    i = rng.integers(n)
    for k in range(H):
        if k > 0 and rng.random() < 1.0 / MB:
            i = rng.integers(n)
        else:
            i = (i + 1) % n if k > 0 else i
        idx[k] = i
    return idx


def roll_min(x, w):
    c = np.cumsum(np.c_[np.zeros((x.shape[0], 1)), x], axis=1)
    m = (c[:, w:] - c[:, :-w]) / w
    return m          # shape (B, H-w+1)


def first_hit(mask):
    """index of first True per row (np.inf if none)."""
    any_ = mask.any(axis=1)
    f = np.where(any_, mask.argmax(axis=1), np.inf)
    return f


res = {}
for name in ("primary", "fallback"):
    t = E.run(C[name], end=E.VAL_END, D=D).sort_values("t_entry")
    R = t.R.values
    mu_hat = R.mean()
    sd = R.std(ddof=1)
    tpy = len(R) / 10.0
    r = dict(n=len(R), mean=round(mu_hat, 4), sd=round(sd, 3), trades_per_year=round(tpy, 1),
             hist_maxDD=round(float((np.maximum.accumulate(np.r_[0, np.cumsum(R)])[1:] - np.cumsum(R)).max()), 1))
    Rc = R - mu_hat
    H = 200
    idx = np.stack([sbb_idx(len(R), H, rng) for _ in range(NB)])
    base = Rc[idx]                                   # (NB, H), mean ~0
    # historical realised roll stats (IS+VAL) for reference
    cs = np.cumsum(R)
    r["hist_roll60_min"] = round(float(pd.Series(R).rolling(60).mean().min()), 3)
    r["hist_roll100_min"] = round(float(pd.Series(R).rolling(100).mean().min()), 3)
    # max-DD distribution at the empirical mean and at shrunk means
    ddq = {}
    for mu in (mu_hat, 0.05, 0.0):
        x = base + mu
        c = np.cumsum(x, axis=1)
        dd = np.maximum.accumulate(np.c_[np.zeros(NB), c], axis=1)[:, 1:] - c
        for hh in (65, 130, 200):
            m = dd[:, :hh].max(axis=1)
            ddq[f"mu{mu:.3f}_H{hh}"] = {f"q{q}": round(float(np.quantile(m, q / 100)), 1) for q in (50, 75, 90, 95, 99)}
    r["maxDD_quantiles"] = ddq
    # roll-window distributions at mu_hat and 0.05: 5th pct of the min over H
    rows = []
    mus = [round(mu_hat, 3), 0.10, 0.05, 0.02, 0.0, -0.05, -0.10]
    rules = [("roll60<", 60, x) for x in (-0.15, -0.20, -0.25, -0.30)] + \
            [("roll100<", 100, x) for x in (-0.05, -0.10, -0.15, -0.20)] + \
            [("DD>", 0.0, y) for y in (15, 20, 25, 30)] + \
            [("CUSUM0.05>", 0.05, h) for h in (15, 20, 25)] + \
            [("roll60<-0.25|DD>25", None, None), ("roll100<-0.10|DD>25", None, None),
             ("roll100<-0.15|DD>30", None, None)]
    for mu in mus:
        x = base + mu
        c = np.cumsum(x, axis=1)
        cache = {}
        for rule, a, b in rules:
            if rule.startswith("roll") and "|" not in rule:
                m = roll_min(x, a)
                hit = m < b
                f = first_hit(hit) + a              # trade number at which it fires
            elif rule.startswith("DD>") or rule.startswith("CUSUM"):
                cc = c - a * np.arange(1, H + 1)
                dd = np.maximum.accumulate(np.c_[np.zeros(NB), cc], axis=1)[:, 1:] - cc
                f = first_hit(dd > b) + 1
            else:
                parts = rule.split("|")
                fs = []
                for p_ in parts:
                    if p_.startswith("roll"):
                        w = int(p_[4:p_.index("<")]); th = float(p_[p_.index("<") + 1:])
                        fs.append(first_hit(roll_min(x, w) < th) + w)
                    else:
                        y = float(p_[3:])
                        dd = np.maximum.accumulate(np.c_[np.zeros(NB), c], axis=1)[:, 1:] - c
                        fs.append(first_hit(dd > y) + 1)
                f = np.minimum(*fs)
            rows.append(dict(mu=mu, rule=rule + ("" if b is None else f"{b:g}"), thr=b, P_fire_130=round(float((f <= 130).mean()), 3),
                             P_fire_200=round(float((f <= 200).mean()), 3),
                             med_trades_to_fire=float(np.median(f[np.isfinite(f)])) if np.isfinite(f).any() else np.nan))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, f"s04_rules_{name}.csv"), index=False)
    piv = df.pivot_table(index="rule", columns="mu", values="P_fire_200", sort=False)
    piv130 = df.pivot_table(index="rule", columns="mu", values="P_fire_130", sort=False)
    print(name, r)
    print("P(fire within 200 trades)\n", piv.to_string())
    print("P(fire within 130 trades)\n", piv130.to_string())
    r["P_fire_200"] = piv.reset_index().to_dict(orient="records")
    r["P_fire_130"] = piv130.reset_index().to_dict(orient="records")
    # quantiles of the rolling-60/100 mean at a single point in time (marginal) under mu_hat and 0.05
    for mu in (mu_hat, 0.05):
        x = base + mu
        for w in (60, 100):
            m = roll_min(x, w)[:, -1]
            r[f"marginal_roll{w}_mu{mu:.3f}"] = {f"q{q}": round(float(np.quantile(m, q / 100)), 3) for q in (1, 5, 10, 50)}
    print({k: v for k, v in r.items() if k.startswith("marginal")})
    res[name] = r
dump(res, "s04_killswitch.json")
