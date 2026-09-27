"""Custom simulator: FAILED-BREAKOUT REVERSAL ("Judas swing" / turtle soup).

Setup per London day (entry window [range_end, entry_end)):
  1. a BREAK: BID high >= range high + pen*W (up-break) or BID low <= range low - pen*W (down-break);
  2. then a RECLAIM: a bar closing on a `tf`-minute boundary with BID close back inside the range by
     at least rec*W (close <= high - rec*W after an up-break, >= low + rec*W after a down-break);
  3. enter AGAINST the break at the next bar open (short at BID open - slip / long at ASK open + slip).
Stop: stop_mode 0 = beyond the break extreme (session BID high/low since range end) + sbuf*W;
      stop_mode 1 = fixed stop_k*W from entry.  (floored at 0.3 USD like engine.py)
Target: tgt_mode 0 none, 1 = range midpoint, 2 = opposite edge, 3 = tp_r * risk.
Execution rules copied from engine.py: entry bar checks only the stop; stop first when SL and TP in one
bar; stops fill at the worse of level and bar open (+slip); TP exact; longs exit on BID, shorts on ASK;
time exit at the open of the first bar at/after exit_time (or the last bar close if the market is closed);
commission 0.07/oz round trip. One trade per day. If the reversal target (tgt 1/2) is already beyond the
entry price, the day is skipped.
`side`: 0 both, 1 only fade up-breaks (shorts), -1 only fade down-breaks (longs).
"""
import numpy as np
import pandas as pd
from numba import njit

from common import E


@njit(cache=True)
def _sim(bo, bh, bl, bc, ao, ah, al, ac, lmin, i_re, i_ee, i_ex, rh, rl, ok, ex_close,
         pen, rec, tf, stop_mode, sbuf, stop_k, tgt_mode, tp_r, commission, slip, side, max_bars_after_break):
    nd = len(i_re)
    out = np.full((nd, 8), np.nan)
    k = 0
    for d in range(nd):
        if not ok[d]:
            continue
        W = rh[d] - rl[d]
        if W <= 0:
            continue
        up_lvl = rh[d] + pen * W
        dn_lvl = rl[d] - pen * W
        brk = 0          # last break side: 1 up, -1 down
        brk_i = -1
        hi = -1e18
        lo = 1e18
        pend = 0
        pos = 0
        entry = 0.0
        sl = 0.0
        tp = 0.0
        risk = 0.0
        ent_i = -1
        i = i_re[d]
        done = False
        while i < i_ex[d]:
            if pos == 0:
                if pend != 0:
                    # open at this bar's open
                    pos = pend
                    pend = 0
                    if pos == 1:
                        entry = ao[i] + slip
                        if stop_mode == 0:
                            sl = lo - sbuf * W
                        else:
                            sl = entry - stop_k * W
                        risk = max(entry - sl, 0.3)
                        sl = entry - risk
                        if tgt_mode == 1:
                            tp = 0.5 * (rh[d] + rl[d])
                        elif tgt_mode == 2:
                            tp = rh[d]
                        elif tgt_mode == 3:
                            tp = entry + tp_r * risk
                        if (tgt_mode == 1 or tgt_mode == 2) and tp <= entry:
                            pos = 0
                            done = True
                            break
                    else:
                        entry = bo[i] - slip
                        if stop_mode == 0:
                            sl = hi + sbuf * W
                        else:
                            sl = entry + stop_k * W
                        risk = max(sl - entry, 0.3)
                        sl = entry + risk
                        if tgt_mode == 1:
                            tp = 0.5 * (rh[d] + rl[d])
                        elif tgt_mode == 2:
                            tp = rl[d]
                        elif tgt_mode == 3:
                            tp = entry - tp_r * risk
                        if (tgt_mode == 1 or tgt_mode == 2) and tp >= entry:
                            pos = 0
                            done = True
                            break
                    ent_i = i
                    # entry bar: stop only
                    if (pos == 1 and bl[i] <= sl) or (pos == -1 and ah[i] >= sl):
                        px = sl - pos * slip
                        out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = i
                        out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pos * (px - entry) - commission
                        out[k, 7] = risk
                        k += 1
                        pos = 0
                        done = True
                        break
                    i += 1
                    continue
                if i >= i_ee[d]:
                    break
                # track session extremes and breaks
                if bh[i] > hi:
                    hi = bh[i]
                if bl[i] < lo:
                    lo = bl[i]
                hu = bh[i] >= up_lvl
                hd = bl[i] <= dn_lvl
                if hu and not hd:
                    if brk != 1:
                        brk_i = i
                    brk = 1
                elif hd and not hu:
                    if brk != -1:
                        brk_i = i
                    brk = -1
                # reclaim signal at a tf-bar close (not in the same bar as the break extreme only if tf==1)
                if brk != 0 and (lmin[i] + 1) % tf == 0 and i + 1 < i_ee[d] and i + 1 < i_ex[d]:
                    if max_bars_after_break <= 0 or i - brk_i <= max_bars_after_break:
                        if brk == 1 and side >= 0 and bc[i] <= rh[d] - rec * W:
                            pend = -1
                        elif brk == -1 and side <= 0 and bc[i] >= rl[d] + rec * W:
                            pend = 1
                i += 1
                continue
            # manage position
            if pos == 1:
                if bl[i] <= sl:
                    px = min(sl, bo[i]) - slip
                    r = 1
                elif tgt_mode > 0 and bh[i] >= tp:
                    px = tp
                    r = 2
                else:
                    r = 0
                    px = 0.0
            else:
                if ah[i] >= sl:
                    px = max(sl, ao[i]) + slip
                    r = 1
                elif tgt_mode > 0 and al[i] <= tp:
                    px = tp
                    r = 2
                else:
                    r = 0
                    px = 0.0
            if r != 0:
                out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = i
                out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pos * (px - entry) - commission
                out[k, 7] = risk
                k += 1
                pos = 0
                done = True
                break
            i += 1
        if pos != 0 and not done:
            if ex_close[d]:
                j = i_ex[d] - 1
                px = (bc[j] - slip) if pos == 1 else (ac[j] + slip)
            else:
                j = min(i_ex[d], len(bo) - 1)
                px = (bo[j] - slip) if pos == 1 else (ao[j] + slip)
            out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = j
            out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pos * (px - entry) - commission
            out[k, 7] = risk
            k += 1
    return out[:k]


def run_fb(timing, pen=0.0, rec=0.0, tf=15, stop_mode=0, sbuf=0.1, stop_k=1.0, tgt_mode=1, tp_r=1.0,
           commission=0.07, slip=0.05, side=0, max_bars=0, start=None, end=E.IS_END, D=None):
    D = D or E.load()
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close = E._windows_full(
        D, timing["range_start"], timing["range_end"], timing["entry_end"], timing["exit_time"])
    days = D["days"]
    atr = days["atr14_prev"].values.astype(float)
    ok = valid & np.isfinite(atr) & ((rh - rl) > 0)     # same universe as engine.run default
    if start is not None:
        ok &= days.index >= pd.Timestamp(start)
    if end is not None:
        ok &= days.index <= pd.Timestamp(end)
    out = _sim(D["bo"], D["bh"], D["bl"], D["bc"], D["ao"], D["ah"], D["al"], D["ac"], D["lmin"],
               i_re.astype(np.int64), i_ee.astype(np.int64), i_ex.astype(np.int64),
               np.nan_to_num(rh), np.nan_to_num(rl), ok, ex_close.astype(np.bool_),
               float(pen), float(rec), int(tf), int(stop_mode), float(sbuf), float(stop_k), int(tgt_mode),
               float(tp_r), float(commission), float(slip), int(side), int(max_bars))
    t = pd.DataFrame(out, columns=["day", "dir", "i_entry", "i_exit", "entry", "exit", "pnl", "risk"])
    if len(t) == 0:
        return t
    for c in ("day", "dir", "i_entry", "i_exit"):
        t[c] = t[c].astype(np.int64)
    t["date"] = days.index[t["day"].values]
    t["t_entry"] = D["index"][t["i_entry"].values]
    t["R"] = t["pnl"] / t["risk"]
    t["width"] = (rh - rl)[t["day"].values]
    return t
