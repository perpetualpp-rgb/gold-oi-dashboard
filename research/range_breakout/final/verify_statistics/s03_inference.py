"""Reality check on the broad family, N_eff, DSR, Harvey-Liu haircut, shrinkage, power. IS/VAL only."""
import json, os, sys
import numpy as np, pandas as pd
from statistics import NormalDist
HERE = os.path.dirname(os.path.abspath(__file__))
nd = NormalDist(); EM = 0.5772156649
cf = json.load(open(os.path.join(HERE, "broad_family_configs.json")))
IP, IF = cf["i_primary"], cf["i_fallback"]
out = {}

def boot_counts(n, nb, block, seed):
    rng = np.random.default_rng(seed); C = np.zeros((nb, n), np.float32)
    for b in range(nb):
        new = rng.random(n) < 1 / block; new[0] = True
        first = np.flatnonzero(new); blk = np.cumsum(new) - 1
        st = rng.integers(0, n, len(first))
        idx = (st[blk] + np.arange(n) - first[blk]) % n
        C[b] = np.bincount(idx, minlength=n)
    return C

def emax(N):  # expected max of N iid N(0,1) (Bailey-LdP approximation)
    return 0.0 if N <= 1 else (1 - EM) * nd.inv_cdf(1 - 1 / N) + EM * nd.inv_cdf(1 - 1 / (N * np.e))

def solve_N(target, f):
    lo, hi = 1.0, 1e9
    for _ in range(200):
        mid = np.sqrt(lo * hi)
        lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
    return mid

res = {}
for per in ("IS", "VAL"):
    z = np.load(os.path.join(HERE, f"broad_family_S_{per}.npz"))
    S, N = z["S"].astype(np.float64), z["N"].astype(np.float64)
    n = N.sum(1); keep = n >= (100 if per == "IS" else 25)
    m = np.where(n > 0, S.sum(1) / np.maximum(n, 1), np.nan)
    C = boot_counts(S.shape[1], 2000, 10, 7 if per == "IS" else 8).astype(np.float64)
    bs = C @ S.T; bn = C @ N.T
    bm = bs / np.maximum(bn, 1)
    se = bm.std(0, ddof=1)
    t = m / se
    ts = (bm - m) / se
    mx = np.nanmax(np.where(keep, ts, -np.inf), axis=1)
    q95 = float(np.quantile(mx, .95)); mmean = float(mx.mean())
    # per-trade SR for DSR V
    res[per] = dict(S=S, N=N, m=m, se=se, t=t, keep=keep, n=n)
    rank = int((t[keep] > t[IP]).sum() + 1)
    d = dict(n_configs=int(keep.sum()), primary_avg_R=round(m[IP], 4), primary_t_boot=round(t[IP], 3),
             primary_rank=rank, fallback_t_boot=round(t[IF], 3), fallback_rank=int((t[keep] > t[IF]).sum() + 1),
             best_t=round(float(np.nanmax(t[keep])), 3), maxt_q95=round(q95, 3), maxt_mean=round(mmean, 3),
             p_family_primary=round((1 + (mx >= t[IP]).sum()) / (1 + len(mx)), 4),
             p_family_fallback=round((1 + (mx >= t[IF]).sum()) / (1 + len(mx)), 4),
             p_family_best=round((1 + (mx >= np.nanmax(t[keep])).sum()) / (1 + len(mx)), 4),
             frac_configs_t_gt_1_96=round(float((t[keep] > 1.96).mean()), 4),
             frac_configs_avgR_gt0=round(float((m[keep] > 0).mean()), 4),
             N_eff_from_q95=round(np.log(0.95) / np.log(nd.cdf(q95)), 1),
             N_eff_from_mean_max=round(solve_N(mmean, emax), 1))
    out[f"broad_family_{per}"] = d
    print(per, d, flush=True)

# ---- IS->VAL decay and split-half decay within IS --------------------------------------------
I, V = res["IS"], res["VAL"]
k = I["keep"] & V["keep"]
x, y = I["m"][k], V["m"][k]
b = np.polyfit(x, y, 1)
dec = {"slope_VAL_on_IS": round(b[0], 3), "intercept": round(b[1], 4), "pred_VAL_primary": round(np.polyval(b, I["m"][IP]), 4),
       "corr": round(np.corrcoef(x, y)[0, 1], 3)}
for lo_t, hi_t in ((1.5, 2.0), (1.8, 2.2), (2.0, 2.5), (2.5, 9)):
    s = k & (I["t"] >= lo_t) & (I["t"] < hi_t)
    dec[f"IS_t_{lo_t}_{hi_t}"] = dict(n_cfg=int(s.sum()), IS_mean=round(I["m"][s].mean(), 4), VAL_mean=round(V["m"][s].mean(), 4),
                                     VAL_frac_pos=round((V["m"][s] > 0).mean(), 3)) if s.sum() else None
out["IS_to_VAL_decay"] = dec
# split-half within IS: 2014-17 -> 2018-21 and reverse
zi = np.load(os.path.join(HERE, "broad_family_S_IS.npz")); dts = pd.to_datetime(zi["dates"])
h1 = dts <= "2017-12-31"
sh = {}
for a, bb, lab in ((h1, ~h1, "A_2014_17->B_2018_21"), (~h1, h1, "B_2018_21->A_2014_17")):
    na, nb_ = I["N"][:, a].sum(1), I["N"][:, bb].sum(1)
    ma, mb = I["S"][:, a].sum(1) / np.maximum(na, 1), I["S"][:, bb].sum(1) / np.maximum(nb_, 1)
    kk = (na >= 60) & (nb_ >= 60)
    sa = np.array([I["S"][j, a][I["N"][j, a] > 0].std(ddof=1) if kk[j] else np.nan for j in range(len(na))])
    ta = ma / (sa / np.sqrt(np.maximum(na, 1)))
    bh = np.polyfit(ma[kk], mb[kk], 1)
    r = dict(slope=round(bh[0], 3), corr=round(np.corrcoef(ma[kk], mb[kk])[0, 1], 3))
    for lo_t, hi_t in ((1.5, 2.0), (2.0, 2.5), (2.5, 9)):
        s = kk & (ta >= lo_t) & (ta < hi_t)
        r[f"t_{lo_t}_{hi_t}"] = dict(n_cfg=int(s.sum()), sel_mean=round(ma[s].mean(), 4), other_mean=round(mb[s].mean(), 4),
                                     ratio=round(mb[s].mean() / ma[s].mean(), 3)) if s.sum() else None
    r["primary_first"] = round(ma[IP], 4); r["primary_second"] = round(mb[IP], 4)
    sh[lab] = r
out["IS_split_half_decay"] = sh
print(json.dumps({"dec": dec, "sh": sh}, indent=1), flush=True)

# ---- DSR with honest N ----------------------------------------------------------------------
tp = pd.read_csv(os.path.join(HERE, "trades_primary.csv"), parse_dates=["date"])
def dsr(R, N, V):
    T = len(R); sr = R.mean() / R.std(ddof=1); d_ = R - R.mean()
    g3 = (d_ ** 3).mean() / (d_ ** 2).mean() ** 1.5; g4 = (d_ ** 4).mean() / (d_ ** 2).mean() ** 2
    sr0 = np.sqrt(V) * emax(N)
    zz = (sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return dict(N=round(N, 1), V=round(V, 6), SR=round(sr, 4), SR0=round(sr0, 4), DSR=round(nd.cdf(zz), 4))
kI = I["keep"]
sr_x = I["m"][kI] / np.array([I["S"][j][I["N"][j] > 0].std(ddof=1) for j in np.flatnonzero(kI)])
Vx = float(np.var(sr_x, ddof=1))
out["sr_cross_sectional"] = dict(V=round(Vx, 6), sd=round(np.sqrt(Vx), 4), mean=round(sr_x.mean(), 4), max=round(sr_x.max(), 4))
dsr_rows = []
Neff_q = out["broad_family_IS"]["N_eff_from_q95"]; Neff_m = out["broad_family_IS"]["N_eff_from_mean_max"]
for per, R in (("IS", tp.R[tp.date <= "2021-12-31"].values), ("POOLED", tp.R.values)):
    for lab, Nn, Vv in (("N=1", 1, 1 / len(R)), ("N_eff_grid24_participation=2.3", 2.3, 1 / len(R)),
                        ("N_eff_grid24_maxt~12", 12, 1 / len(R)), ("N_eff_broad_meanmax", Neff_m, 1 / len(R)),
                        ("N_eff_broad_q95", Neff_q, 1 / len(R)), ("N=12960 raw broad", 12960, 1 / len(R)),
                        ("N=20000 raw round1", 20000, 1 / len(R)),
                        ("V=xsect broad, N_eff_meanmax", Neff_m, Vx), ("V=xsect broad, N=12960", 12960, Vx)):
        r = dsr(R, Nn, Vv); r.update(case=lab, period=per); dsr_rows.append(r)
out["DSR"] = dsr_rows
for r in dsr_rows: print(r)

# ---- Harvey-Liu haircut (annualised on trades/yr) -------------------------------------------
def haircut(R, years, Ns, rank=1):
    sr = R.mean() / R.std(ddof=1); tpy = len(R) / years; sra = sr * np.sqrt(tpy); tt = sra * np.sqrt(years)
    p = 2 * (1 - nd.cdf(tt)); rows = []
    for Nn in Ns:
        cN = sum(1 / i for i in range(1, int(Nn) + 1))
        for meth, pa in (("Bonferroni", min(1, Nn * p)), ("Holm_rank1", min(1, Nn * p)), ("BHY_rank1", min(1, Nn * cN * p))):
            ta = nd.inv_cdf(1 - pa / 2) if pa < 1 else 0.0
            rows.append(dict(N=Nn, method=meth, SR_ann=round(sra, 3), p=round(p, 4), p_adj=round(pa, 4),
                             SR_ann_haircut=round(ta / np.sqrt(years), 3), haircut=round(1 - ta / tt, 3)))
    return rows
Ns = [12, 24, 50, int(round(Neff_m)), int(round(Neff_q)), 200, 1000, 12960]
out["haircut_IS"] = haircut(tp.R[tp.date <= "2021-12-31"].values, 8.0, Ns)
out["haircut_POOLED"] = haircut(tp.R.values, 10.0, Ns)
for r in out["haircut_POOLED"]: print("HL pooled", r)
for r in out["haircut_IS"]: print("HL IS", r)
json.dump(out, open(os.path.join(HERE, "s03_inference.json"), "w"), indent=1, default=float)
