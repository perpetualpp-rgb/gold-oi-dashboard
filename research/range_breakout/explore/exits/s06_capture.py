"""Which exit captures the MFE best? Default stop (1 x width), same entries for every exit, IS only.
Configs here are all already in the s02 grid (except tstop, counted in s04), so nothing new is logged.
Also: MFE of the breakout direction vs the mirror (opposite) direction on mid prices."""
import numpy as np
import pandas as pd
import common as C
import engine as E
from exitsim import sim

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
D = C.data()
p = E.Params()
t = C.run_is(p, log=False)
w = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
iend, exc = w[3][t.day.values].astype(np.int64), w[7][t.day.values].astype(np.bool_)
M = pd.read_parquet(C.OUT + "/s01_mfe.parquet")
assert len(M) == len(t) and np.allclose(M.R.values, t.R.values)
mfe = M.mfe_stop.values
EX = [("time 20:00 only", {}), ("TP 1R", dict(tp=1.0)), ("TP 1.5R", dict(tp=1.5)), ("TP 2R", dict(tp=2.0)),
      ("TP 3R", dict(tp=3.0)), ("trail 1R", dict(tr=1.0)), ("trail 1.5R", dict(tr=1.5)), ("trail 2R", dict(tr=2.0)),
      ("BE 0.5R", dict(be=0.5)), ("BE 1R + trail 1.5R", dict(be=1.0, tr=1.5)), ("BE 1R + trail 1R", dict(be=1.0, tr=1.0)),
      ("tstop 120m <0R", dict(tsm=120, tst=0.0))]
rows = []
big = mfe >= 1.0
for nm, kw in EX:
    R, rs, _ = sim(D["bo"], D["bh"], D["bl"], D["bc"], D["ao"], D["ah"], D["al"], D["ac"], D["lmin"],
                   t.i_entry.values.astype(np.int64), t.dir.values.astype(np.int64), t.entry.values, t.risk.values,
                   iend, exc, kw.get("tp", 0.0), kw.get("be", 0.0), kw.get("tr", 0.0), 0, kw.get("tsm", 0), kw.get("tst", 0.0), 0.07, 0.05)
    rows.append(dict(exit=nm, avg_R=R.mean().round(4), t=round(R.mean() / R.std(ddof=1) * np.sqrt(len(R)), 2),
                     capture_all=round(R.sum() / mfe.sum(), 3),
                     avgR_when_MFE_ge1=R[big].mean().round(3), capture_MFE_ge1=round(R[big].sum() / mfe[big].sum(), 3),
                     avgR_when_MFE_lt1=R[~big].mean().round(3),
                     giveback_winners=round((mfe[R > 0] - R[R > 0]).mean(), 3), win=round((R > 0).mean(), 3),
                     skew=round(C.skew(R), 2), p95=round(np.quantile(R, .95), 2), p99=round(np.quantile(R, .99), 2)))
X = pd.DataFrame(rows)
print(f"trades {len(t)}, mean MFE before stop {mfe.mean():.3f}R, share with MFE>=1R {big.mean():.3f}")
print(X.to_string(index=False))
X.to_csv(C.OUT + "/s06_capture.csv", index=False)

# mirror MFE on mid prices: breakout direction vs opposite direction, same entry bar, same 1R
bo, bh, bl, bc, ao, ah, al, ac = (D[k] for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
mh, ml, mc = (bh + ah) / 2, (bl + al) / 2, (bc + ac) / 2
res = []
for r, ie in zip(t.itertuples(), iend):
    i0, pos, risk = r.i_entry, r.dir, r.risk
    sp = ao[i0] - bo[i0]
    em = (r.entry - 0.05 - sp / 2) if pos == 1 else (r.entry + 0.05 + sp / 2)
    up = (np.r_[mc[i0], mh[i0 + 1:ie]] - em) / risk
    dn = (em - np.r_[mc[i0], ml[i0 + 1:ie]]) / risk
    f, a = (up, dn) if pos == 1 else (dn, up)
    def mfe_before(f, a):
        h = np.nonzero(a >= 1.0)[0]
        j = h[0] if len(h) else len(a)
        return max(0.0, f[:j].max()) if j > 0 else 0.0
    res.append((pos, mfe_before(f, a), mfe_before(a, f), f.max(), a.max()))
Q = pd.DataFrame(res, columns=["dir", "mfe_dir", "mfe_mirror", "maxfav_nostop", "maxadv_nostop"])
print("\nmid-price MFE before a 1R stop: breakout direction vs mirror direction")
for d_, nm in ((0, "all"), (1, "long"), (-1, "short")):
    q = Q if d_ == 0 else Q[Q.dir == d_]
    diff = q.mfe_dir - q.mfe_mirror
    print(f"{nm:5s} mean dir {q.mfe_dir.mean():.3f}  mirror {q.mfe_mirror.mean():.3f}  diff {diff.mean():+.3f} (t {diff.mean() / diff.std() * np.sqrt(len(q)):.2f})"
          f"  median dir {q.mfe_dir.median():.2f} mirror {q.mfe_mirror.median():.2f}  | no-stop max fav {q.maxfav_nostop.mean():.3f} vs max adv {q.maxadv_nostop.mean():.3f}")
Q.to_csv(C.OUT + "/s06_mirror.csv", index=False)
