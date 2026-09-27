"""Parameter-stability of the frozen primary (and fallback) on IS / VAL only.

1. One-at-a-time: every continuous knob of the primary at -20/-10/+10/+20 % (clock times: range_start
   additive +/-0.5/1 h = 10/20 % of the 5 h range; other clock times multiplicative).
2. Switching on knobs that are off in the primary (buffers, TP, BE, trail, max width, 2 trades, entry
   confirmation, trend) -- structural neighbours, reported separately.
3. Joint: 200 random draws with every design knob perturbed simultaneously, U(-10%,+10%) and U(-20%,+20%).
Outputs: s02_oat.csv, s02_structural.csv, s02_joint_{primary,fallback}_{10,20}.csv, s02_perturb.json
"""
import os
import numpy as np
import pandas as pd

from rcommon import E, data, cand_params, tstat, dump, HERE

D = data()
C = cand_params()


def ev(p):
    t = E.run(p, end=E.VAL_END, D=D)
    if len(t) == 0:
        return dict(IS_n=0, IS_avg=np.nan, IS_t=np.nan, VAL_n=0, VAL_avg=np.nan, VAL_t=np.nan)
    a = t[t.date <= E.IS_END].R.values
    b = t[t.date > E.IS_END].R.values
    yrs = t[t.date <= E.IS_END].groupby(t.date.dt.year).R.sum()
    return dict(IS_n=len(a), IS_avg=round(a.mean(), 4), IS_t=round(tstat(a), 2), IS_yrs_pos=int((yrs > 0).sum()),
                VAL_n=len(b), VAL_avg=round(b.mean(), 4) if len(b) else np.nan,
                VAL_t=round(tstat(b), 2) if len(b) > 2 else np.nan,
                ALL_avg=round(t.R.mean(), 4), ALL_t=round(tstat(t.R.values), 2))


def mk(base, **kw):
    return E.Params(**{**base.to_dict(), **kw})


res = {}
prim = C["primary"]
base_ev = ev(prim)
print("primary", base_ev)
res["primary_base"] = base_ev

# ---------------- 1. one at a time ----------------
rows = []
knobs = {
    "range_start": [(-1.0, "-20%(-1h)"), (-0.5, "-10%(-0.5h)"), (0.5, "+10%(+0.5h)"), (1.0, "+20%(+1h)")],
}
mult = ["range_end", "entry_end", "exit_time", "sl_k", "min_w_atr", "atr_regime_n", "atr_regime_max",
        "commission", "slip", "max_spread"]
for k, lst in knobs.items():
    for v, lab in lst:
        rows.append(dict(knob=k, change=lab, value=getattr(prim, k) + v, **ev(mk(prim, **{k: getattr(prim, k) + v}))))
for k in mult:
    for f in (0.8, 0.9, 1.1, 1.2):
        v = getattr(prim, k) * f
        if k == "atr_regime_n":
            v = int(round(v))
        rows.append(dict(knob=k, change=f"{(f - 1) * 100:+.0f}%", value=v, **ev(mk(prim, **{k: v}))))
oat = pd.DataFrame(rows)
oat.to_csv(os.path.join(HERE, "s02_oat.csv"), index=False)
print(oat.to_string(index=False))
res["oat"] = oat.to_dict(orient="records")
d = oat[~oat.knob.isin(["commission", "slip", "max_spread"])]
res["oat_summary"] = dict(n=len(d), IS_min=d.IS_avg.min(), IS_max=d.IS_avg.max(), IS_frac_pos=(d.IS_avg > 0).mean(),
                          VAL_min=d.VAL_avg.min(), VAL_max=d.VAL_avg.max(), VAL_frac_pos=(d.VAL_avg > 0).mean(),
                          IS_frac_below_half_base=(d.IS_avg < base_ev["IS_avg"] / 2).mean(),
                          worst_IS=d.loc[d.IS_avg.idxmin(), ["knob", "change", "IS_avg", "VAL_avg"]].to_dict(),
                          worst_VAL=d.loc[d.VAL_avg.idxmin(), ["knob", "change", "IS_avg", "VAL_avg"]].to_dict())
print(res["oat_summary"])

# ---------------- 2. structural neighbours (knobs that are off in the primary) ----------------
srows = []
for lab, kw in (("buf_k=0.05", dict(buf_k=0.05)), ("buf_k=0.10", dict(buf_k=0.10)),
                ("buf_atr=0.02", dict(buf_atr=0.02)), ("buf_atr=0.05", dict(buf_atr=0.05)),
                ("tp_r=3", dict(tp_r=3.0)), ("tp_r=5", dict(tp_r=5.0)), ("tp_r=8", dict(tp_r=8.0)),
                ("be_r=2", dict(be_r=2.0)), ("be_r=3", dict(be_r=3.0)), ("trail_r=3", dict(trail_r=3.0)),
                ("max_w_atr=1.5", dict(max_w_atr=1.5)), ("max_w_atr=1.0", dict(max_w_atr=1.0)),
                ("max_trades=2", dict(max_trades=2)), ("entry_mode=1 (15m close)", dict(entry_mode=1)),
                ("sl_ref=1 sl_k=0.35 (ATR stop, ~same size)", dict(sl_ref=1, sl_k=0.35)),
                ("sl_ref=2 (opposite edge)", dict(sl_ref=2)),
                ("trend=100 with", dict(trend=100)), ("skip_nfp", dict(skip_nfp=True)),
                ("no regime filter (=w0.30 only)", dict(atr_regime_n=0)),
                ("no width filter (regime only)", dict(min_w_atr=0.0)),
                ("no filters", dict(min_w_atr=0.0, atr_regime_n=0))):
    srows.append(dict(variant=lab, **ev(mk(prim, **kw))))
st = pd.DataFrame(srows)
st.to_csv(os.path.join(HERE, "s02_structural.csv"), index=False)
print(st.to_string(index=False))
res["structural"] = st.to_dict(orient="records")

# ---------------- 3. joint random perturbations ----------------
JK = ["range_start", "range_end", "entry_end", "exit_time", "sl_k", "min_w_atr", "atr_regime_n", "atr_regime_max"]


def draw(base, rng, s):
    kw = {}
    for k in JK:
        b = getattr(base, k)
        if k == "range_start":
            v = b + rng.uniform(-1, 1) * s * 5.0            # s=0.2 -> +/-1 h (20 % of the 5 h range)
        else:
            v = b * (1 + rng.uniform(-s, s))
        if k == "atr_regime_n":
            if b == 0:
                v = 0
            else:
                v = int(round(v))
        if k == "atr_regime_max" and base.atr_regime_n == 0:
            v = b
        kw[k] = v
    # keep windows sane
    kw["entry_end"] = max(kw["entry_end"], kw["range_end"] + 1.0)
    return kw


joint = {}
for cname in ("primary", "fallback"):
    base = C[cname]
    be = ev(base)
    for s in (0.10, 0.20):
        rng = np.random.default_rng(12345 + int(s * 100))
        rows = []
        for i in range(200):
            kw = draw(base, rng, s)
            rows.append(dict(**{k: round(v, 4) if isinstance(v, float) else v for k, v in kw.items()},
                             **ev(mk(base, **kw))))
        df = pd.DataFrame(rows)
        df.to_csv(os.path.join(HERE, f"s02_joint_{cname}_{int(s * 100)}.csv"), index=False)
        q = lambda x: {f"q{int(p * 100):02d}": round(float(np.nanquantile(x, p)), 4) for p in (0.05, 0.25, 0.5, 0.75, 0.95)}
        # linear sensitivity: standardised deltas -> avg_R
        X = np.column_stack([(df[k] - getattr(base, k)) / (np.std(df[k]) + 1e-12) for k in JK
                             if np.std(df[k]) > 0])
        ks = [k for k in JK if np.std(df[k]) > 0]
        X1 = np.column_stack([np.ones(len(df)), X])
        sens = {}
        for per in ("IS_avg", "VAL_avg"):
            y = df[per].values
            ok = np.isfinite(y)
            beta = np.linalg.lstsq(X1[ok], y[ok], rcond=None)[0]
            sens[per] = {k: round(float(b), 4) for k, b in zip(ks, beta[1:])}
        joint[f"{cname}_{int(s * 100)}"] = dict(
            base=be, IS=q(df.IS_avg), VAL=q(df.VAL_avg), ALL=q(df.ALL_avg),
            IS_frac_pos=round(float((df.IS_avg > 0).mean()), 3), VAL_frac_pos=round(float((df.VAL_avg > 0).mean()), 3),
            ALL_frac_pos=round(float((df.ALL_avg > 0).mean()), 3),
            IS_frac_ge_base=round(float((df.IS_avg >= be["IS_avg"]).mean()), 3),
            VAL_frac_ge_base=round(float((df.VAL_avg >= be["VAL_avg"]).mean()), 3),
            IS_frac_t_gt2=round(float((df.IS_t > 2).mean()), 3),
            IS_frac_gt_0p05=round(float((df.IS_avg > 0.05).mean()), 3),
            VAL_frac_gt_0p05=round(float((df.VAL_avg > 0.05).mean()), 3),
            corr_IS_VAL=round(float(df[["IS_avg", "VAL_avg"]].corr().iloc[0, 1]), 3),
            mean_IS_n=round(float(df.IS_n.mean()), 1), sensitivity_per_1sd=sens)
        print(cname, s, joint[f"{cname}_{int(s * 100)}"])
res["joint"] = joint
dump(res, "s02_perturb.json")
