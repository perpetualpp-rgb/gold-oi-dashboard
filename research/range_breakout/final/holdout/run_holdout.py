"""ONE-SHOT HOLDOUT evaluation (2024-01-01 .. end of data) of the frozen candidates.

Candidates are loaded ONLY from final/candidates.json (sha256 recorded). Only primary, fallback and the
baseline are run on the holdout (plus cost-stress variants of the same three configs). Nothing here is
used to change parameters. engine.py is not modified; null.py's holdout guard is respected by calling
its lower-level helpers (both_ways/_perm_block) directly with the holdout trades.
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(FINAL, ".."))
for p in (ROOT, os.path.join(ROOT, "explore", "null_costs")):
    if p not in sys.path:
        sys.path.insert(0, p)
import engine as E  # noqa: E402
import null as NL  # noqa: E402

pd.set_option("display.width", 250)
HO_START = "2024-01-01"


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ---------------------------------------------------------------- 0. provenance
cand_path = os.path.join(FINAL, "candidates.json")
assert os.path.exists(cand_path), "final/candidates.json missing"
cand_sha = sha(cand_path)
C = json.load(open(cand_path))
eng_sha = {f: sha(os.path.join(ROOT, f)) for f in ("engine.py", "test_engine.py")}
eng_match = eng_sha == C["engine_sha256"]
print("candidates.json sha256:", cand_sha)
print("engine sha256:", eng_sha, "matches frozen:", eng_match)
assert eng_match, "engine.py differs from the frozen engine"


def P(d):
    return E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})


CANDS = {k: P(C["candidates"][k]) for k in ("primary", "fallback", "baseline")}
D = E.load()
last_bar = D["index"].max()
print("data last bar (UTC):", last_bar)

KEYS = ("n", "trades_per_year", "win_rate", "avg_R", "total_R", "t_stat", "PF", "sharpe_ann", "maxDD_R",
        "avg_win_R", "avg_loss_R", "usd_per_oz")


def st(t):
    s = E.stats(t)
    return {k: (float(s[k]) if k in s and s[k] is not None else None) for k in KEYS} if len(t) else {"n": 0}


def tstat(R):
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 1 else float("nan")


def with_spread(D, add):
    D2 = {k: v for k, v in D.items() if k != "_win_cache"}
    for c in ("ao", "ah", "al", "ac"):
        D2[c] = D[c] + add
    return D2


D_sp = with_spread(D, 0.10)
D_gross = {k: v for k, v in D.items() if k != "_win_cache"}
for c in "ohlc":
    D_gross["a" + c] = D["b" + c]


def stat_boot_idx(nd, n_boot, block, rng):
    idx = np.empty((n_boot, nd), dtype=np.int64)
    for b in range(n_boot):
        new = rng.random(nd) < 1.0 / block
        new[0] = True
        starts = rng.integers(0, nd, nd)
        cur = 0
        for i in range(nd):
            cur = starts[i] if new[i] else (cur + 1) % nd
            idx[b, i] = cur
    return idx


def daily_SN(t):
    g = t.groupby("date")["R"]
    return g.sum().values, g.size().values.astype(float)


def boot_mean_ci(t, n_boot=5000, block=10, seed=0):
    """Stationary (date-block) bootstrap of avg_R per trade."""
    S, N = daily_SN(t)
    idx = stat_boot_idx(len(S), n_boot, block, np.random.default_rng(seed))
    m = S[idx].sum(1) / N[idx].sum(1)
    return m


def predictive(t_ref, n_target_trades, n_boot=5000, block=10, seed=0, centre=None):
    """Distribution of avg_R over a sample of ~n_target_trades trades drawn from t_ref's process
    (stationary bootstrap over t_ref trade dates, drawing dates until the trade count is reached)."""
    S, N = daily_SN(t_ref)
    if centre is not None:          # shift every trade so the reference mean equals `centre`
        S = S - N * (S.sum() / N.sum() - centre)
    nd = len(S)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        s = n = 0.0
        cur = rng.integers(nd)
        while n < n_target_trades:
            s += S[cur]; n += N[cur]
            cur = rng.integers(nd) if rng.random() < 1.0 / block else (cur + 1) % nd
        out[b] = s / n
    return out


res = {"candidates_sha256": cand_sha, "engine_sha256": eng_sha, "engine_matches_frozen": eng_match,
       "data_last_bar_utc": str(last_bar), "holdout_start": HO_START}

# ---------------------------------------------------------------- 1. reproduce IS/VAL (sanity)
repro = {}
for name, p in CANDS.items():
    t = E.run(p, end=E.VAL_END, D=D)
    isv = C["is_val_stats"][name]
    a = E.stats(t[t.date <= E.IS_END]); b = E.stats(t[t.date > E.IS_END])
    repro[name] = dict(IS_n=a["n"], IS_avg_R=a["avg_R"], VAL_n=b["n"], VAL_avg_R=b["avg_R"],
                       frozen_IS=(isv["IS"]["n"], isv["IS"]["avg_R"]), frozen_VAL=(isv["VAL"]["n"], isv["VAL"]["avg_R"]),
                       match=(a["n"] == isv["IS"]["n"] and abs(a["avg_R"] - isv["IS"]["avg_R"]) < 1e-4 and
                              b["n"] == isv["VAL"]["n"] and abs(b["avg_R"] - isv["VAL"]["avg_R"]) < 1e-4))
print("IS/VAL reproduction:", json.dumps(repro, default=str))
res["isval_reproduction"] = repro

# ---------------------------------------------------------------- 2. holdout runs
HO, ISVAL = {}, {}
for name, p in CANDS.items():
    s_h, t = E.holdout(p, D=D)
    t_alt = E.run(p, start=HO_START, D=D)
    assert len(t) == len(t_alt) and np.allclose(t.R.values, t_alt.R.values)
    HO[name] = t
    ISVAL[name] = E.run(p, end=E.VAL_END, D=D)
    t.to_csv(os.path.join(HERE, f"trades_holdout_{name}.csv"), index=False)

for name, p in CANDS.items():
    t = HO[name]
    r = {"HOLDOUT": st(t), "HOLDOUT_long": st(t[t.dir == 1]), "HOLDOUT_short": st(t[t.dir == -1])}
    r["exit_reasons"] = t.reason.value_counts().to_dict()
    by = E.by_year(t)
    by["L_n"] = t[t.dir == 1].groupby(t.date.dt.year).size()
    by["L_avg_R"] = t[t.dir == 1].groupby(t.date.dt.year).R.mean().round(3)
    by["S_n"] = t[t.dir == -1].groupby(t.date.dt.year).size()
    by["S_avg_R"] = t[t.dir == -1].groupby(t.date.dt.year).R.mean().round(3)
    by["t"] = t.groupby(t.date.dt.year).R.apply(lambda x: round(tstat(x.values), 2))
    r["by_year"] = by.reset_index().rename(columns={"date": "year"}).to_dict(orient="records")
    # top-k removed
    Rs = np.sort(t.R.values)[::-1]
    r["top5_removed_avg_R"] = float(Rs[5:].mean())
    r["top10_removed_avg_R"] = float(Rs[10:].mean())
    # cost stress
    stress = {}
    pd_ = p.to_dict()
    for lab, pp, DD in (("default", p, D),
                        ("slip0.10", E.Params(**{**pd_, "slip": 0.10}), D),
                        ("spread+0.10", p, D_sp),
                        ("slip0.10+spread+0.10", E.Params(**{**pd_, "slip": 0.10}), D_sp),
                        ("gross(no costs)", E.Params(**{**pd_, "slip": 0.0, "commission": 0.0}), D_gross)):
        ts = E.run(pp, start=HO_START, D=DD)
        stress[lab] = dict(n=len(ts), avg_R=round(float(ts.R.mean()), 4), t=round(tstat(ts.R.values), 2),
                           total_R=round(float(ts.R.sum()), 1))
    r["cost_stress"] = stress
    # random-direction null on the holdout (1000 perms), same method as null.null_test
    bw = NL.both_ways(p, D=D, trades=t)
    assert np.allclose(bw.R_same.values, t.R.values), "re-walker does not reproduce engine"
    blk = NL._perm_block(bw.R_same.values, bw.R_flip.values, bw.dir.values, 1000, np.random.default_rng(1))
    blk.pop("_coin"); blk.pop("_shuffle")
    for dname, dv in (("long_trades", 1), ("short_trades", -1)):
        m = bw.dir.values == dv
        dd = bw.R_same.values[m] - bw.R_flip.values[m]
        blk[dname] = dict(n=int(m.sum()), actual=float(bw.R_same.values[m].mean()),
                          opposite=float(bw.R_flip.values[m].mean()), diff=float(dd.mean()), t_diff=tstat(dd))
    r["null_test"] = blk
    # bootstrap CI of the holdout mean itself
    bm = boot_mean_ci(t, seed=11)
    r["holdout_boot_ci90"] = [float(np.quantile(bm, .05)), float(np.quantile(bm, .95))]
    r["holdout_boot_p_le0"] = float((bm <= 0).mean())
    # ------------- expectation from IS/VAL
    ti = ISVAL[name]
    tIS, tVAL = ti[ti.date <= E.IS_END], ti[ti.date > E.IS_END]
    nH = len(t)
    exp = {}
    for lab, ref in (("IS", tIS), ("IS+VAL", ti)):
        mref = float(ref.R.mean())
        bmr = boot_mean_ci(ref, seed=3)
        pr = predictive(ref, nH, seed=5)
        pr0 = predictive(ref, nH, seed=7, centre=0.0)
        obs = float(t.R.mean())
        exp[lab] = dict(n_ref=len(ref), mean_ref=mean_ref if (mean_ref := mref) else mref,
                        sd_ref=float(ref.R.std(ddof=1)), se_ref_boot=float(bmr.std(ddof=1)),
                        ref_ci90=[float(np.quantile(bmr, .05)), float(np.quantile(bmr, .95))],
                        pred_n=nH,
                        pred_ci90_if_edge_as_ref=[float(np.quantile(pr, .05)), float(np.quantile(pr, .95))],
                        pred_ci95_if_edge_as_ref=[float(np.quantile(pr, .025)), float(np.quantile(pr, .975))],
                        pctile_of_holdout_in_pred=float((pr <= obs).mean()),
                        pred_ci90_if_zero_edge=[float(np.quantile(pr0, .05)), float(np.quantile(pr0, .95))],
                        pctile_of_holdout_in_zero_edge=float((pr0 <= obs).mean()))
    r["expectation"] = exp
    res[name] = r

    print(f"\n=================== {name}: {pd_}")
    print(pd.DataFrame({k: r[k] for k in ("HOLDOUT", "HOLDOUT_long", "HOLDOUT_short")}).T.to_string())
    print(by.to_string())
    print("exit reasons:", r["exit_reasons"], "| top5 removed", round(r["top5_removed_avg_R"], 4),
          "top10 removed", round(r["top10_removed_avg_R"], 4))
    print(pd.DataFrame(stress).T.to_string())
    print("null coin:", {k: round(v, 4) for k, v in blk["coin"].items()},
          "\nnull shuffle:", {k: round(v, 4) for k, v in blk["shuffle"].items()},
          "\nalways_long", round(blk["always_long"], 4), "always_short", round(blk["always_short"], 4),
          "\nlong_trades", blk["long_trades"], "\nshort_trades", blk["short_trades"])
    print("holdout boot CI90", r["holdout_boot_ci90"], "P(mean<=0)", r["holdout_boot_p_le0"])
    for lab, e in exp.items():
        print(lab, json.dumps({k: (np.round(v, 4).tolist() if isinstance(v, (list, float)) else v) for k, v in e.items()}))

# ---------------------------------------------------------------- 3. filter activity & market regime
i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close = E._windows_full(D, 0.0, 5.0, 12.0, 20.0)
days = D["days"]
atr = days["atr14_prev"].values.astype(float)
w5 = rh - rl
ma20 = pd.Series(atr).rolling(20, min_periods=12).mean().values
_, i_re7, _, _, rh7, rl7, valid7, _ = E._windows_full(D, 0.0, 7.0, 12.0, 20.0)
w7 = rh7 - rl7
yr = days.index.year.values
wa5 = w5 / atr
ok5 = valid & np.isfinite(atr) & (w5 > 0)
pass_w030 = ok5 & (wa5 >= 0.30)
pass_w035 = ok5 & (wa5 >= 0.35)
pass_reg = np.isfinite(ma20) & (atr <= ma20)
# spread (ASK-BID, modelled) over the entry window bars 05:00-12:00 London, per day
spr = D["ao"] - D["bo"]
cs = np.r_[0.0, np.cumsum(spr)]
ent_spr = np.where(valid, (cs[np.maximum(i_ee, i_re)] - cs[i_re]) / np.maximum(i_ee - i_re, 1), np.nan)
close = days["c"].values
rows = []
for y in range(2014, 2027):
    m = (yr == y)
    mv = m & ok5
    row = dict(year=y, valid_days=int(mv.sum()),
               mean_close=round(float(np.nanmean(close[m])), 1),
               w5_mean=round(float(np.nanmean(w5[mv])), 2), atr14_mean=round(float(np.nanmean(atr[mv])), 2),
               w5_over_atr_mean=round(float(np.nanmean(wa5[mv])), 3),
               w5_over_price_bp=round(float(np.nanmean(w5[mv] / close[mv]) * 1e4), 1),
               share_w030=round(float(pass_w030[mv].mean()), 3), share_w035=round(float(pass_w035[mv].mean()), 3),
               share_regime=round(float(pass_reg[mv].mean()), 3),
               share_w030_and_regime=round(float((pass_w030 & pass_reg)[mv].mean()), 3),
               spread_entry_win=round(float(np.nanmean(ent_spr[mv])), 3))
    for name, p in CANDS.items():
        tt = pd.concat([ISVAL[name], HO[name]])
        tt = tt[tt.date.dt.year == y]
        nvalid = int((m & (valid7 if name == "baseline" else valid) & np.isfinite(atr)).sum())
        row[f"traded_share_{name}"] = round(tt.day.nunique() / max(nvalid, 1), 3)
        row[f"n_{name}"] = len(tt)
        row[f"avg_risk_{name}"] = round(float(tt.risk.mean()), 2) if len(tt) else None
        # round-trip cost in R: spread at entry bar + 2 slips + commission, relative to risk
        if len(tt):
            s_e = D["ao"][tt.i_entry.values] - D["bo"][tt.i_entry.values]
            row[f"cost_R_{name}"] = round(float(((s_e + 2 * p.slip + p.commission) / tt.risk.values).mean()), 3)
    rows.append(row)
reg = pd.DataFrame(rows)


def per_block(df, a, b):
    s = df[(df.year >= a) & (df.year <= b)]
    w = s.valid_days
    return {c: round(float(np.average(s[c].dropna(), weights=w[s[c].notna()])), 3)
            for c in df.columns if c not in ("year",) and s[c].notna().any()}


blocks = {"IS 2014-21": per_block(reg, 2014, 2021), "VAL 2022-23": per_block(reg, 2022, 2023),
          "HOLDOUT 2024-26": per_block(reg, 2024, 2026)}
reg.to_csv(os.path.join(HERE, "regime_filter_activity_by_year.csv"), index=False)
print("\n", reg.to_string(index=False))
print(pd.DataFrame(blocks).T.to_string())
res["filter_activity_by_year"] = reg.to_dict(orient="records")
res["filter_activity_blocks"] = blocks
# holdout-period valid days and period length
res["holdout_years"] = float((days.index[(days.index >= HO_START)].max() - pd.Timestamp(HO_START)).days / 365.25)

json.dump(res, open(os.path.join(HERE, "holdout_results.json"), "w"), indent=1,
          default=lambda o: o.item() if hasattr(o, "item") else str(o))
print("\nsaved", os.path.join(HERE, "holdout_results.json"))
