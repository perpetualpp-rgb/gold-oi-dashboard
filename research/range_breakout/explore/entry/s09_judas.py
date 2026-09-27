"""Direct test of the 'Judas swing' hypothesis: is the EARLY London break (07:00-09:00) of the Asian range a
false move that reverses? (a) gross diagnostic by hour of the first break; (b) breakout vs fade vs
failed-break reversal restricted to early entry windows (entry_end 8, 9, 10). IS only."""
import sys
import os
import itertools
import json
import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config, eval_is  # noqa
from fb_sim import run_fb  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))


@njit(cache=True)
def first_break(bh, bl, bc, i_re, i_ee, i_ex, rh, rl, ok):
    nd = len(i_re)
    ie = np.full(nd, -1)
    s = np.zeros(nd, np.int64)
    hold = np.full(nd, np.nan)      # BID close before exit - edge, in W, no stop
    stop1 = np.full(nd, np.nan)     # with 1W stop behind the edge (gross, W units)
    opp = np.zeros(nd, np.int64)    # opposite edge touched later (before exit)
    back_mid = np.zeros(nd, np.int64)  # back to the midpoint before exit
    for d in range(nd):
        if not ok[d]:
            continue
        W = rh[d] - rl[d]
        for i in range(i_re[d], i_ee[d]):
            hu = bh[i] >= rh[d]
            hd = bl[i] <= rl[d]
            if hu and hd:
                break
            if hu or hd:
                ie[d] = i
                s[d] = 1 if hu else -1
                break
        if ie[d] < 0:
            continue
        L = rh[d] if s[d] == 1 else rl[d]
        last = i_ex[d] - 1
        hold[d] = s[d] * (bc[last] - L) / W
        st = L - s[d] * W
        res = np.nan
        for i in range(ie[d] + 1, i_ex[d]):
            if s[d] == 1:
                if bl[i] <= st:
                    res = -1.0
                    break
            else:
                if bh[i] >= st:
                    res = -1.0
                    break
        if np.isnan(res):
            res = hold[d]
        stop1[d] = res
        mid = 0.5 * (rh[d] + rl[d])
        for i in range(ie[d] + 1, i_ex[d]):
            if (s[d] == 1 and bl[i] <= mid) or (s[d] == -1 and bh[i] >= mid):
                back_mid[d] = 1
            if (s[d] == 1 and bl[i] <= rl[d]) or (s[d] == -1 and bh[i] >= rh[d]):
                opp[d] = 1
                break
    return ie, s, hold, stop1, opp, back_mid


def main():
    Dd = D()
    days = Dd["days"].index
    isd = (days >= pd.Timestamp("2014-01-01")) & (days <= pd.Timestamp(E.IS_END))
    lines = []
    for tn in ("T0_asia0-7", "T1_asia0-8"):
        tm = TIMINGS[tn]
        i_rs, i_re, i_ee, i_ex, rh, rl, valid, exc = E._windows_full(Dd, tm["range_start"], tm["range_end"],
                                                                      tm["entry_end"], tm["exit_time"])
        ok = valid & isd & ~exc
        ie, s, hold, stop1, opp, bm = first_break(Dd["bh"], Dd["bl"], Dd["bc"], i_re.astype(np.int64),
                                                  i_ee.astype(np.int64), i_ex.astype(np.int64),
                                                  np.nan_to_num(rh), np.nan_to_num(rl), ok)
        log_config("s09_diag", tn, dict(n=int((ie >= 0).sum())))
        sel = ie >= 0
        lmin = Dd["lmin"][ie[sel]]
        hour = (lmin % 1440) // 60
        df = pd.DataFrame(dict(hour=hour, dir=s[sel], hold=hold[sel], stop1=stop1[sel], opp=opp[sel],
                               mid=bm[sel]))
        g = df.groupby("hour").agg(n=("hold", "size"), hold_W=("hold", "mean"), stop1_W=("stop1", "mean"),
                                   p_back_mid=("mid", "mean"), p_opp_edge=("opp", "mean"))
        g["stop1_t"] = df.groupby("hour")["stop1"].apply(lambda x: x.mean() / x.std() * np.sqrt(len(x)))
        allrow = pd.DataFrame(dict(n=[len(df)], hold_W=[df.hold.mean()], stop1_W=[df.stop1.mean()],
                                   p_back_mid=[df.mid.mean()], p_opp_edge=[df.opp.mean()],
                                   stop1_t=[df.stop1.mean() / df.stop1.std() * np.sqrt(len(df))]), index=["all"])
        g = pd.concat([g, allrow])
        lines.append(f"\n{tn}: first break of the range, by London hour of the break (gross, W units)\n")
        lines.append(g.round(3).to_string())
    # (b) early entry windows at T0
    tm = TIMINGS["T0_asia0-7"]
    rows = []
    for ee in (8.0, 9.0, 10.0, 12.0):
        t0 = dict(tm, entry_end=ee)
        for name, kw in (("breakout sl1W", dict(entry_mode=0)),
                         ("breakout slOpp", dict(entry_mode=0, sl_ref=2)),
                         ("fade sl1W none", dict(entry_mode=2, sl_k=1.0)),
                         ("fade sl1W opp", dict(entry_mode=2, sl_k=1.0, tp_r=1.0)),
                         ("fade sl0.5W mid", dict(entry_mode=2, sl_k=0.5, tp_r=1.0)),
                         ("fade sl0.5W opp", dict(entry_mode=2, sl_k=0.5, tp_r=2.0)),
                         ("fade buf0.2 sl0.5W opp", dict(entry_mode=2, sl_k=0.5, buf_k=0.2, tp_r=2.4))):
            r, _ = eval_is("s09", E.Params(**t0, **kw))
            r.update(entry_end=ee, mech=name)
            rows.append(r)
        for pen, tf, tg in itertools.product((0.0, 0.1, 0.2), (5, 15), ("mid", "opp", "none")):
            kw = dict(pen=pen, tf=tf, stop_mode=0, sbuf=0.1, tgt_mode={"none": 0, "mid": 1, "opp": 2}[tg])
            t = run_fb(t0, **kw)
            r = full_summ(t)
            r.update(entry_end=ee, mech=f"failed-break pen{pen} M{tf} {tg}")
            log_config("s09_fb", json.dumps(t0) + json.dumps(kw), r)
            rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s09_results.csv"), index=False)
    cols = ["entry_end", "mech", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos", "L_avg", "S_avg"]
    lines.append("\nT0 (range 00-07) with early entry cut-offs\n")
    lines.append(df[cols].to_string(index=False))
    out = "\n".join(lines)
    open(os.path.join(HERE, "s09_judas.txt"), "w").write(out)
    print(out)


if __name__ == "__main__":
    main()
