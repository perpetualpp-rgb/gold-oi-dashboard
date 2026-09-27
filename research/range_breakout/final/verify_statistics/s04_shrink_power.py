"""Shrinkage estimates of the OOS avg_R of the PRIMARY, family-level (selection-light) evidence,
neighbour stability, and live-sample power analysis. IS/VAL only."""
import json, os
import numpy as np, pandas as pd
from statistics import NormalDist
HERE = os.path.dirname(os.path.abspath(__file__))
nd = NormalDist()
cf = json.load(open(os.path.join(HERE, "broad_family_configs.json")))
cfgs, IP = cf["configs"], cf["i_primary"]
out = {}
Z = {p: np.load(os.path.join(HERE, f"broad_family_S_{p}.npz")) for p in ("IS", "VAL")}

def tstat(x):
    x = x[np.isfinite(x)]
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x))

# ---- family-level: equal-weight average of per-config daily R (per trade-day avg across configs) ----
fam = {}
for per in ("IS", "VAL"):
    S, N = Z[per]["S"].astype(float), Z[per]["N"].astype(float)
    n = N.sum(1); keep = n >= (100 if per == "IS" else 25)
    m = S[keep].sum(1) / n[keep]
    # per-day family P&L in "R per trade" units: each config's daily R scaled by its 1/avg trades per day
    rate = n[keep] / S.shape[1]
    daily = (S[keep] / rate[:, None]).mean(0)  # expected R per config-trade, per day
    dates = pd.to_datetime(Z[per]["dates"])
    yr = pd.Series(daily, index=dates).groupby(dates.year).mean()
    # block-robust t: Newey-West lag 10
    x = daily - daily.mean(); T = len(x); g0 = (x @ x) / T
    lr = g0 + 2 * sum((1 - L / 11) * (x[L:] @ x[:-L]) / T for L in range(1, 11))
    fam[per] = dict(n_cfg=int(keep.sum()), mean_cfg_avgR=round(m.mean(), 4), median_cfg_avgR=round(np.median(m), 4),
                    frac_pos=round((m > 0).mean(), 3), family_portfolio_avgR=round(daily.mean(), 4),
                    family_portfolio_t_NW=round(daily.mean() / np.sqrt(lr / T), 2),
                    by_year={int(k): round(v, 4) for k, v in yr.items()})
    # family without 2014
    if per == "IS":
        k = dates.year != 2014
        xx = daily[k] - daily[k].mean(); T2 = len(xx); g0 = (xx @ xx) / T2
        lr2 = g0 + 2 * sum((1 - L / 11) * (xx[L:] @ xx[:-L]) / T2 for L in range(1, 11))
        fam[per]["wo2014_avgR"] = round(daily[k].mean(), 4); fam[per]["wo2014_t_NW"] = round(daily[k].mean() / np.sqrt(lr2 / T2), 2)
out["family_level"] = fam
print(json.dumps(fam, indent=1))

# ---- neighbours of the primary (one knob changed) -----------------------------------------
def stats_cfg(j, per):
    S, N = Z[per]["S"][j].astype(float), Z[per]["N"][j].astype(float)
    return N.sum(), S.sum() / max(N.sum(), 1)
P0 = cfgs[IP]
nb = []
for j, c in enumerate(cfgs):
    diff = [k for k in set(c) | set(P0) if c.get(k, None) != P0.get(k, None)
            and not (k in ("comp_n",) )]
    if 1 <= len(diff) <= 2 and (len(diff) == 1 or set(diff) <= {"range_start", "range_end", "entry_end", "comp_n", "comp_max", "comp_min", "atr_regime_n", "atr_regime_max"}):
        nI, mI = stats_cfg(j, "IS"); nV, mV = stats_cfg(j, "VAL")
        nb.append(dict(change={k: c.get(k) for k in diff}, IS_n=int(nI), IS_avgR=round(mI, 4), VAL_n=int(nV), VAL_avgR=round(mV, 4)))
out["neighbours"] = nb
for r in nb: print(r)

# ---- shrinkage ---------------------------------------------------------------------------------
tp = pd.read_csv(os.path.join(HERE, "trades_primary.csv"), parse_dates=["date"])
core = json.load(open(os.path.join(HERE, "s01_core.json")))
inf = json.load(open(os.path.join(HERE, "s03_inference.json")))
xIS, seIS = core["primary"]["IS"]["avg_R"], core["primary"]["IS"]["b10"]["se"]
xV, seV = core["primary"]["VAL"]["avg_R"], core["primary"]["VAL"]["b10"]["se"]
xP, seP = core["primary"]["POOLED"]["avg_R"], core["primary"]["POOLED"]["b10"]["se"]
sh = {}
# (1) skeptical normal priors centred at 0
for tau in (0.03, 0.05, 0.10):
    for lab, x, se in (("IS", xIS, seIS), ("POOLED", xP, seP)):
        w = tau ** 2 / (tau ** 2 + se ** 2); pm = w * x; ps = np.sqrt(w) * se
        sh[f"prior_N(0,{tau})_{lab}"] = dict(post_mean=round(pm, 4), post_sd=round(ps, 4), P_gt0=round(1 - nd.cdf(-pm / ps), 3))
# (2) prior centred on the broad family (mean cfg avg_R in IS), tau from split-half signal variance
S, N = Z["IS"]["S"].astype(float), Z["IS"]["N"].astype(float)
dates = pd.to_datetime(Z["IS"]["dates"]); h1 = dates <= "2017-12-31"
nA, nB = N[:, h1].sum(1), N[:, ~h1].sum(1); k = (nA >= 60) & (nB >= 60)
mA, mB = S[:, h1].sum(1)[k] / nA[k], S[:, ~h1].sum(1)[k] / nB[k]
cov_signal = np.cov(mA, mB)[0, 1]          # cross-half covariance = variance of persistent config effects
mu0 = fam["IS"]["mean_cfg_avgR"]
tau_f = np.sqrt(max(cov_signal, 1e-8))
for lab, x, se in (("IS", xIS, seIS), ("POOLED", xP, seP)):
    w = tau_f ** 2 / (tau_f ** 2 + se ** 2); pm = mu0 + w * (x - mu0); ps = np.sqrt(w) * se
    sh[f"EB_family_prior_{lab}"] = dict(mu0=round(mu0, 4), tau=round(tau_f, 4), weight_on_data=round(w, 3),
                                        post_mean=round(pm, 4), post_sd=round(ps, 4), P_gt0=round(1 - nd.cdf(-pm / ps), 3))
# the family mean itself is inflated by construction (round-1 knowledge): also use prior mean 0 with tau_f
for lab, x, se in (("IS", xIS, seIS), ("POOLED", xP, seP)):
    w = tau_f ** 2 / (tau_f ** 2 + se ** 2); pm = w * x; ps = np.sqrt(w) * se
    sh[f"EB_prior_mean0_tau_family_{lab}"] = dict(tau=round(tau_f, 4), post_mean=round(pm, 4), P_gt0=round(1 - nd.cdf(-pm / ps), 3))
# (3) IS->VAL regression and selection-decay ratios (s03)
sh["IS_to_VAL_regression_pred"] = inf["IS_to_VAL_decay"]["pred_VAL_primary"]
sh["decay_ratio_IS_t_1.8_2.2_to_VAL"] = round(inf["IS_to_VAL_decay"]["IS_t_1.8_2.2"]["VAL_mean"] / inf["IS_to_VAL_decay"]["IS_t_1.8_2.2"]["IS_mean"], 3)
sh["decay_ratio_split_half_t_1.5_2.5"] = [inf["IS_split_half_decay"][k]["t_1.5_2.0"]["ratio"] for k in inf["IS_split_half_decay"]]
# (4) Posterior after VAL: EB-shrunk IS as prior, VAL as data
pr = sh["EB_prior_mean0_tau_family_IS"]["post_mean"]; prs = np.sqrt(tau_f ** 2 * seIS ** 2 / (tau_f ** 2 + seIS ** 2))
w = prs ** -2 / (prs ** -2 + seV ** -2); pm = w * pr + (1 - w) * xV; ps = (prs ** -2 + seV ** -2) ** -0.5
sh["EB_IS_then_VAL_update"] = dict(post_mean=round(pm, 4), post_sd=round(ps, 4), P_gt0=round(1 - nd.cdf(-pm / ps), 3))
out["shrinkage"] = sh
out["tau_family_split_half"] = round(tau_f, 4)
print(json.dumps(sh, indent=1))

# ---- power ---------------------------------------------------------------------------------
R = tp.R.values; sd = R.std(ddof=1); tpy = 60.0
za, zb = nd.inv_cdf(0.95), nd.inv_cdf(0.80)
pw = {"sd_R": round(sd, 3), "assumed_trades_per_year": tpy}
rng = np.random.default_rng(3)
for mu in (0.12, 0.10, 0.06, 0.04, 0.02):
    n_an = ((za + zb) * sd / mu) ** 2
    # simulation with the empirical (fat right tail) distribution shifted to mean mu, one-sided t test at 5%
    base = R - R.mean() + mu
    def power(n, reps=3000):
        s = base[rng.integers(0, len(base), (reps, n))]
        t = s.mean(1) / (s.std(1, ddof=1) / np.sqrt(n))
        return (t > za).mean()
    lo, hi = 20, 200000
    while hi / lo > 1.05:
        mid = int(np.sqrt(lo * hi))
        if power(min(mid, 60000), 1500 if mid < 5000 else 400) >= 0.8: hi = mid
        else: lo = mid
    pw[f"mu={mu}"] = dict(n_analytic=int(n_an), years_analytic=round(n_an / tpy, 1), n_sim_empirical=int(hi), years_sim=round(hi / tpy, 1))
# distinguishing mu=0.12 from mu=0.04 (IS claim vs shrunk), one-sided
n_d = ((za + zb) * sd / 0.08) ** 2
pw["distinguish_0.12_vs_0.04"] = dict(n=int(n_d), years=round(n_d / tpy, 1))
# what can 1 / 2 / 3 years of live trading detect (80% power, one-sided 5%)?
pw["MDE_by_years"] = {y: round((za + zb) * sd / np.sqrt(y * tpy), 3) for y in (1, 2, 3, 5, 10)}
# SPRT (Wald) H0 mu=0 vs H1 mu=0.06, alpha 0.05 beta 0.2: expected sample sizes under normal approx
mu1 = 0.06; A = np.log(0.8 / 0.05); B = np.log(0.2 / 0.95)
llr_step = lambda mu: (mu1 * mu - mu1 ** 2 / 2) / sd ** 2
pw["SPRT_0_vs_0.06"] = dict(E_n_if_mu0=int(round(B / llr_step(0))), E_n_if_mu0p06=int(round(A / llr_step(mu1))),
                            years_if_mu0=round(B / llr_step(0) / tpy, 1), years_if_mu0p06=round(A / llr_step(mu1) / tpy, 1))
out["power"] = pw
print(json.dumps(pw, indent=1))
json.dump(out, open(os.path.join(HERE, "s04_shrink_power.json"), "w"), indent=1, default=float)
