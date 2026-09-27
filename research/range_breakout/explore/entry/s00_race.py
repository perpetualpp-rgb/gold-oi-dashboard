"""Gross (cost-free) race diagnostic: after the FIRST touch of a range edge in the entry window,
does price travel b range-widths further before coming back a range-widths (momentum), or the
reverse (false break / stop hunt)?

M[a][b] = mean PnL (in range widths W) of a breakout entered exactly at the touched edge
(+buffer), stop a*W behind the entry, target b*W beyond (b=inf -> time exit). BID prices both ways,
no costs, entry bar ignored, both levels in one later bar -> counted as half/half (neutral).
A fade with stop a' and target b' earns exactly -M[b'][a'] (in W) gross.
Under a driftless random walk every cell is 0.  IS only.
"""
import sys
import os
import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, log_config, md  # noqa: E402

A = np.array([0.25, 0.5, 0.75, 1.0, 1.5, 2.0])
B = np.array([0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 1e9])


@njit(cache=True)
def race(bh, bl, bc, bo, i_re, i_ee, i_ex, rh, rl, ok, bufw, A, B):
    nd = len(i_re)
    na, nb = len(A), len(B)
    res = np.full((nd, na, nb), np.nan)
    dirn = np.zeros(nd, np.int64)
    ext = np.full(nd, np.nan)      # close at exit - entry, in W (no stop)
    for d in range(nd):
        if not ok[d]:
            continue
        W = rh[d] - rl[d]
        if W <= 0:
            continue
        up = rh[d] + bufw * W
        dn = rl[d] - bufw * W
        ie = -1
        s = 0
        for i in range(i_re[d], i_ee[d]):
            hu = bh[i] >= up
            hd = bl[i] <= dn
            if hu and hd:
                break
            if hu:
                ie = i; s = 1
                break
            if hd:
                ie = i; s = -1
                break
        if ie < 0:
            continue
        L = up if s == 1 else dn
        dirn[d] = s
        last = i_ex[d] - 1
        ext[d] = s * (bc[last] - L) / W
        for ia in range(na):
            for ib in range(nb):
                stop = L - s * A[ia] * W
                tgt = L + s * B[ib] * W
                out = np.nan
                for i in range(ie + 1, i_ex[d]):
                    if s == 1:
                        hs = bl[i] <= stop
                        ht = bh[i] >= tgt
                    else:
                        hs = bh[i] >= stop
                        ht = bl[i] <= tgt
                    if hs and ht:
                        out = 0.5 * (B[ib] - A[ia])
                        break
                    if hs:
                        out = -A[ia]
                        break
                    if ht:
                        out = B[ib]
                        break
                if np.isnan(out):
                    out = s * (bc[last] - L) / W
                res[d, ia, ib] = out
    return res, dirn, ext


def main():
    Dd = D()
    days = Dd["days"].index
    isd = (days >= pd.Timestamp("2014-01-01")) & (days <= pd.Timestamp(E.IS_END))
    lines = []
    for tn, tm in TIMINGS.items():
        i_rs, i_re, i_ee, i_ex, rh, rl, valid, exc = E._windows_full(
            Dd, tm["range_start"], tm["range_end"], tm["entry_end"], tm["exit_time"])
        ok = valid & isd & ~exc
        for bufw in (0.0, 0.1, 0.3):
            res, dirn, ext = race(Dd["bh"], Dd["bl"], Dd["bc"], Dd["bo"], i_re.astype(np.int64),
                                  i_ee.astype(np.int64), i_ex.astype(np.int64), np.nan_to_num(rh),
                                  np.nan_to_num(rl), ok, bufw, A, B)
            log_config("s00_race", f"{tn} buf{bufw}", dict(n=int((dirn != 0).sum())))
            sel = dirn != 0
            yrs = days.year.values
            lines.append(f"\n### {tn}  buffer {bufw} W   (break days: {sel.sum()}, up {int((dirn==1).sum())}, "
                         f"down {int((dirn==-1).sum())})")
            e = ext[sel]
            el, es = ext[dirn == 1], ext[dirn == -1]
            lines.append(f"No stop, hold to exit: mean {e.mean():+.3f} W (se {e.std()/np.sqrt(len(e)):.3f}), "
                         f"up-breaks {el.mean():+.3f}, down-breaks {es.mean():+.3f}")
            # matrix of gross mean PnL in W (all, then long/short), t-stat
            for lab, m in (("ALL", sel), ("UP", dirn == 1), ("DOWN", dirn == -1)):
                M = np.nanmean(res[m], axis=0)
                S = np.nanstd(res[m], axis=0) / np.sqrt(m.sum())
                df = pd.DataFrame(M, index=[f"stop {a}" for a in A],
                                  columns=[f"tgt {b}" if b < 1e8 else "tgt none" for b in B]).round(3)
                lines.append(f"\n{lab}: breakout gross mean PnL in W (rows stop a, cols target b)\n")
                lines.append(md(df))
                if lab == "ALL":
                    T = pd.DataFrame(M / S, index=df.index, columns=df.columns).round(1)
                    lines.append("\nt-stats\n")
                    lines.append(md(T))
                    # per-year sign for a few cells
                    yl = []
                    for (ia, ib) in ((3, 7), (3, 3), (1, 1), (0, 1)):
                        g = pd.Series(res[m][:, ia, ib], index=yrs[m]).groupby(level=0).mean()
                        yl.append(f"stop {A[ia]}/tgt {B[ib] if B[ib] < 1e8 else 'none'}: years>0 "
                                  f"{int((g > 0).sum())}/8  " + " ".join(f"{v:+.2f}" for v in g.values))
                    lines.append("\n" + "\n".join("- " + x for x in yl))
    out = "\n".join(lines)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "s00_race_tables.txt"), "w") as f:
        f.write(out)
    print(out)


if __name__ == "__main__":
    main()
