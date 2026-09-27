"""Custom simulator: BREAK-THEN-RETEST entry (trade WITH the break, but on a pullback limit order).

Per London day, entry window [range_end, entry_end):
  1. a BREAK: BID high >= range high + pen*W (up) or BID low <= range low - pen*W (down);
     the most recent break side is the armed side.
  2. from the NEXT bar on (lpen = USD the price must trade through the limit, 0 = touch), a limit order at edge + off*W in the break direction (buy limit at
     rh + off*W filled when ASK low <= it; sell limit at rl - off*W filled when BID high >= it).
     off < 0 = deeper pullback inside the range. Filled at the limit price (no slip).
  3. stop: sl_mode 0 = sl_k*W from entry; 1 = opposite edge -/+ sbuf*W; 2 = range midpoint -/+ sbuf*W.
     (risk floored at 0.3 USD). target: tp_r*risk (0 = none).  time exit as engine.py.
Execution rules as engine.py (entry bar: stop only; SL before TP; stop fills at worse of level/open + slip;
longs exit on BID, shorts on ASK; commission 0.07/oz). One trade per day.
"""
import numpy as np
import pandas as pd
from numba import njit

from common import E


@njit(cache=True)
def _sim(bo, bh, bl, bc, ao, ah, al, ac, i_re, i_ee, i_ex, rh, rl, ok, ex_close,
         pen, off, sl_mode, sl_k, sbuf, tp_r, commission, slip, max_wait, lpen):
    nd = len(i_re)
    out = np.full((nd, 8), np.nan)
    k = 0
    for d in range(nd):
        if not ok[d]:
            continue
        W = rh[d] - rl[d]
        if W <= 0:
            continue
        up_b = rh[d] + pen * W
        dn_b = rl[d] - pen * W
        lim_l = rh[d] + off * W
        lim_s = rl[d] - off * W
        brk = 0
        brk_i = -1
        pos = 0
        entry = 0.0
        sl = 0.0
        tp = 0.0
        risk = 0.0
        ent_i = -1
        closed = False
        i = i_re[d]
        while i < i_ex[d]:
            if pos == 0:
                if i >= i_ee[d]:
                    break
                # limit fill check for the armed side (orders live from the bar after the break)
                if brk != 0 and i > brk_i and (max_wait <= 0 or i - brk_i <= max_wait):
                    if brk == 1 and al[i] <= lim_l - lpen:
                        pos = 1
                        entry = lim_l
                    elif brk == -1 and bh[i] >= lim_s + lpen:
                        pos = -1
                        entry = lim_s
                if pos != 0:
                    ent_i = i
                    if sl_mode == 0:
                        risk = sl_k * W
                    elif sl_mode == 1:
                        risk = (entry - (rl[d] - sbuf * W)) if pos == 1 else ((rh[d] + sbuf * W) - entry)
                    else:
                        mid = 0.5 * (rh[d] + rl[d])
                        risk = (entry - (mid - sbuf * W)) if pos == 1 else ((mid + sbuf * W) - entry)
                    risk = max(risk, 0.3)
                    sl = entry - pos * risk
                    tp = entry + pos * tp_r * risk if tp_r > 0 else 0.0
                    if (pos == 1 and bl[i] <= sl) or (pos == -1 and ah[i] >= sl):
                        px = sl - pos * slip
                        out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = i
                        out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pos * (px - entry) - commission
                        out[k, 7] = risk
                        k += 1
                        pos = 0
                        closed = True
                        break
                    i += 1
                    continue
                hu = bh[i] >= up_b
                hd = bl[i] <= dn_b
                if hu and not hd:
                    if brk != 1:
                        brk_i = i
                    brk = 1
                elif hd and not hu:
                    if brk != -1:
                        brk_i = i
                    brk = -1
                i += 1
                continue
            if pos == 1:
                if bl[i] <= sl:
                    px = min(sl, bo[i]) - slip
                    r = 1
                elif tp_r > 0 and bh[i] >= tp:
                    px = tp
                    r = 2
                else:
                    r = 0
                    px = 0.0
            else:
                if ah[i] >= sl:
                    px = max(sl, ao[i]) + slip
                    r = 1
                elif tp_r > 0 and al[i] <= tp:
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
                closed = True
                break
            i += 1
        if pos != 0 and not closed:
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


def run_rt(timing, pen=0.1, off=0.0, sl_mode=0, sl_k=1.0, sbuf=0.0, tp_r=0.0, commission=0.07, slip=0.05,
           max_wait=0, lpen=0.0, start=None, end=E.IS_END, D=None):
    D = D or E.load()
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close = E._windows_full(
        D, timing["range_start"], timing["range_end"], timing["entry_end"], timing["exit_time"])
    days = D["days"]
    atr = days["atr14_prev"].values.astype(float)
    ok = valid & np.isfinite(atr) & ((rh - rl) > 0)
    if start is not None:
        ok &= days.index >= pd.Timestamp(start)
    if end is not None:
        ok &= days.index <= pd.Timestamp(end)
    out = _sim(D["bo"], D["bh"], D["bl"], D["bc"], D["ao"], D["ah"], D["al"], D["ac"],
               i_re.astype(np.int64), i_ee.astype(np.int64), i_ex.astype(np.int64),
               np.nan_to_num(rh), np.nan_to_num(rl), ok, ex_close.astype(np.bool_),
               float(pen), float(off), int(sl_mode), float(sl_k), float(sbuf), float(tp_r),
               float(commission), float(slip), int(max_wait), float(lpen))
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
