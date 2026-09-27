"""Re-simulate exits for a fixed set of entries (from engine.run with max_trades=1).
Replicates engine._simulate position management exactly (validated in s04), and adds:
  max_hold  : minutes after entry -> market exit at the open of the first bar at/after that time
  ts_min/ts_thr : time-stop: at the first bar at/after entry+ts_min, exit at its open if the
                  unrealised R (exit side, at that open) is below ts_thr
"""
import numpy as np
from numba import njit


@njit(cache=True)
def sim(bo, bh, bl, bc, ao, ah, al, ac, lmin, i_ent, pos_a, entry_a, risk_a, iend_a, exclose_a,
        tp_r, be_r, trail_r, max_hold, ts_min, ts_thr, commission, slip):
    n = len(i_ent)
    R = np.empty(n)
    reason = np.empty(n, np.int64)
    iexit = np.empty(n, np.int64)
    for k in range(n):
        i0 = i_ent[k]; pos = pos_a[k]; entry = entry_a[k]; risk = risk_a[k]; iend = iend_a[k]
        sl = entry - pos * risk
        tp = entry + pos * tp_r * risk if tp_r > 0 else 0.0
        best = entry
        be_done = False
        px = 0.0
        rs = 0
        t0 = lmin[i0]
        # entry bar: stop only
        if (pos == 1 and bl[i0] <= sl) or (pos == -1 and ah[i0] >= sl):
            px = sl - pos * slip
            rs = 1
            iexit[k] = i0
        else:
            i = i0 + 1
            ts_done = ts_min <= 0
            while i < iend:
                el = lmin[i] - t0
                if max_hold > 0 and el >= max_hold:
                    px = (bo[i] - slip) if pos == 1 else (ao[i] + slip)
                    rs = 5
                    break
                if not ts_done and el >= ts_min:
                    ts_done = True
                    ur = pos * (((bo[i] - slip) if pos == 1 else (ao[i] + slip)) - entry) / risk
                    if ur < ts_thr:
                        px = (bo[i] - slip) if pos == 1 else (ao[i] + slip)
                        rs = 6
                        break
                if pos == 1:
                    if bl[i] <= sl:
                        px = min(sl, bo[i]) - slip
                        rs = 1 if sl < entry else 3
                    elif tp_r > 0 and bh[i] >= tp:
                        px = tp
                        rs = 2
                    elif bh[i] > best:
                        best = bh[i]
                else:
                    if ah[i] >= sl:
                        px = max(sl, ao[i]) + slip
                        rs = 1 if sl > entry else 3
                    elif tp_r > 0 and al[i] <= tp:
                        px = tp
                        rs = 2
                    elif al[i] < best:
                        best = al[i]
                if rs != 0:
                    break
                gain = pos * (best - entry) / risk
                if be_r > 0 and not be_done and gain >= be_r:
                    be_done = True
                    if pos == 1:
                        sl = max(sl, entry + 0.05)
                    else:
                        sl = min(sl, entry - 0.05)
                if trail_r > 0 and (be_r <= 0 or be_done):
                    if pos == 1:
                        sl = max(sl, best - trail_r * risk)
                    else:
                        sl = min(sl, best + trail_r * risk)
                i += 1
            iexit[k] = i
            if rs == 0:
                if exclose_a[k]:
                    j = iend - 1
                    px = (bc[j] - slip) if pos == 1 else (ac[j] + slip)
                else:
                    j = iend
                    px = (bo[j] - slip) if pos == 1 else (ao[j] + slip)
                rs = 4
                iexit[k] = j
        R[k] = (pos * (px - entry) - commission) / risk
        reason[k] = rs
    return R, reason, iexit
