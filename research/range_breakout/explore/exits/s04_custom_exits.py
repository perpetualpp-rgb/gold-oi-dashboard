"""Custom exits not expressible in engine.Params: holding-time caps and time-stops; plus exit_time
9-13 through the engine; plus by-year gross vs net of the default. IS only."""
import numpy as np
import pandas as pd
import common as C
import engine as E
from exitsim import sim

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
D = C.data()
D0 = C.cost_stressed(0.0)
for k in ("ao", "ah", "al", "ac"):
    D0[k] = D["b" + k[1]].copy()
out = []
def pr(s=""):
    print(s); out.append(str(s))

def entries(p, DD, log=True, tag=""):
    t = C.run_is(p, D=DD, tag=tag, log=log)
    w = E._windows_full(DD, p.range_start, p.range_end, p.entry_end, p.exit_time)
    return t, w[3][t.day.values].astype(np.int64), w[7][t.day.values].astype(np.bool_)

def resim(t, iend, exc, DD, tp=0.0, be=0.0, tr=0.0, mh=0, tsm=0, tst=0.0, comm=0.07, slip=0.05, risk=None):
    rk = t.risk.values if risk is None else risk
    return sim(DD["bo"], DD["bh"], DD["bl"], DD["bc"], DD["ao"], DD["ah"], DD["al"], DD["ac"], DD["lmin"],
               t.i_entry.values.astype(np.int64), t.dir.values.astype(np.int64), t.entry.values, rk,
               iend, exc, tp, be, tr, mh, tsm, tst, comm, slip)

# ---- 1. validation against the engine (configs already counted in s02 -> log=False)
pr("## validation of exitsim vs engine (max |dR|)")
for kw in [dict(), dict(tp_r=2.0), dict(be_r=1.0, trail_r=1.5), dict(trail_r=0.5), dict(tp_r=1.0, be_r=0.5),
           dict(sl_ref=1, sl_k=0.75, be_r=1.0, trail_r=1.5, exit_time=21.0), dict(exit_time=14.0, trail_r=2.0)]:
    p = E.Params(**kw)
    t, iend, exc = entries(p, D, log=False)
    R, rs, ix = resim(t, iend, exc, D, p.tp_r, p.be_r, p.trail_r)
    pr(f"{kw}: n={len(t)} max|dR|={np.abs(R - t.R.values).max():.2e} exit-bar mismatches={(ix != t.i_exit.values).sum()}")

def summ_R(R, t, rs=None):
    tt = t.copy(); tt["R"] = R
    d = C.full_summ(tt) if rs is None else C.full_summ(tt.assign(reason=pd.Series(rs).map({1: "sl", 2: "tp", 3: "trail", 4: "time", 5: "time", 6: "time"}).values))
    return d

cols = ["n", "avg_R", "win_rate", "PF", "t_stat", "maxDD_R", "yrs_pos", "L_avg_R", "L_t", "S_avg_R", "S_t", "skew"]
rows = []
# ---- 2. holding-time caps and time stops, default stop (W1) and ATR0.75 stop, net + gross
for stop_name, base in (("W1.0", E.Params()), ("ATR0.75", E.Params(sl_ref=1, sl_k=0.75))):
    tN, iN, eN = entries(base, D, log=False)
    tG, iG, eG = entries(E.Params(**{**base.to_dict(), "commission": 0.0, "slip": 0.0}), D0, log=False)
    specs = [("hold", dict(mh=h)) for h in (15, 30, 60, 120, 180, 240, 360)]
    specs += [("tstop", dict(tsm=m, tst=th)) for m in (15, 30, 60, 120) for th in (0.0, 0.25)]
    specs += [("hold+trail2", dict(mh=h, tr=2.0)) for h in (120, 240)]
    for fam, kw in specs:
        for mode, t, ie, ex, DD, cm, sl in (("net", tN, iN, eN, D, 0.07, 0.05), ("gross", tG, iG, eG, D0, 0.0, 0.0)):
            C._log("s04_" + mode, base, f"IS custom {fam} {kw}")
            R, rs, _ = resim(t, ie, ex, DD, comm=cm, slip=sl, **kw)
            d = summ_R(R, t, rs)
            rows.append(dict(stop=stop_name, family=fam, spec=str(kw), mode=mode, **{c: d[c] for c in cols}))
X = pd.DataFrame(rows)
X.to_csv(C.OUT + "/s04_custom.csv", index=False)
W = X[X["mode"] == "net"].merge(X[X["mode"] == "gross"][["stop", "spec", "avg_R", "t_stat"]], on=["stop", "spec"], suffixes=("", "_g"))
pr("\n## holding caps / time stops (net, with gross avg_R_g / t_g)")
pr(W.drop(columns="mode").to_string(index=False))

# ---- 3. early clock exits via the engine
pr("\n## engine exit_time 9..13 (default stop, no TP), net and gross")
r2 = []
for ex in (9.0, 10.0, 11.0, 12.0, 13.0):
    p = E.Params(exit_time=ex)
    dn = C.full_summ(C.run_is(p, tag="s04_exitT"))
    dg = C.full_summ(C.run_is(E.Params(exit_time=ex, commission=0.0, slip=0.0), D=D0, tag="s04_exitT_gross"))
    r2.append(dict(exit_time=ex, **{c: dn[c] for c in cols}, avg_R_g=dg["avg_R"], t_g=dg["t_stat"]))
pr(pd.DataFrame(r2).to_string(index=False))

# ---- 4. by-year net vs gross for the default
pr("\n## default config by year: net vs gross (IS)")
tn = C.run_is(E.Params(), log=False)
tg = C.run_is(E.Params(commission=0.0, slip=0.0), D=D0, log=False)
by = pd.DataFrame({"n": tn.groupby(tn.date.dt.year).R.size(), "net_avgR": tn.groupby(tn.date.dt.year).R.mean().round(3),
                   "gross_avgR": tg.groupby(tg.date.dt.year).R.mean().round(3),
                   "gross_L": tg[tg.dir == 1].groupby(tg[tg.dir == 1].date.dt.year).R.mean().round(3),
                   "gross_S": tg[tg.dir == -1].groupby(tg[tg.dir == -1].date.dt.year).R.mean().round(3)})
pr(by.to_string())
with open(C.OUT + "/s04_custom.txt", "w") as f:
    f.write("\n".join(out))
