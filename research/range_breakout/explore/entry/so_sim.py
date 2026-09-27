"""Custom stop-entry simulator = engine.py entry_mode 0, max_trades 1 path, plus one extra knob:

  long_trig: 0 = engine behaviour: buy stop at rh+buf triggers on ASK high (i.e. when BID is still up to one
                 spread BELOW the BID range high);
             1 = 'spread-corrected' buy stop: triggers when BID high >= rh+buf (the break is on the same price
                 series as the range), filled at max(level + spread, ASK open) + slip. In MT5 this is a buy stop
                 at rh + buf + current spread, or a market buy when BID crosses the level.
  long_add / short_add: extra USD added to the long / short level (asymmetric buffers).
With long_trig=0 and adds 0 it reproduces engine.run trade by trade (checked in s08_spread_fix.py).
Stops/targets/BE/trail are not needed here: sl = sl_k*W (or ATR) from entry, optional tp_r, time exit.
"""
import numpy as np
import pandas as pd
from numba import njit

from common import E


@njit(cache=True)
def _sim(bo, bh, bl, bc, ao, ah, al, ac, d_re, d_ee, d_ex, rh, rl, allow_l, allow_s, buf, sl_dist, tp_r,
         commission, slip, ex_close, long_trig, long_add, short_add):
    nd = len(d_re)
    out = np.full((nd, 9), np.nan)
    k = 0
    for d in range(nd):
        if d_re[d] < 0 or d_ex[d] <= d_re[d]:
            continue
        lvl_l = rh[d] + buf[d] + long_add
        lvl_s = rl[d] - buf[d] - short_add
        armed_l = allow_l[d]
        armed_s = allow_s[d]
        if not (armed_l or armed_s):
            continue
        pos = 0
        entry = 0.0
        ent_i = -1
        sl = 0.0
        tp = 0.0
        risk = 0.0
        i = d_re[d]
        closed = False
        while i < d_ex[d]:
            if pos == 0:
                if i >= d_ee[d]:
                    break
                if long_trig == 0:
                    hit_l = armed_l and ah[i] >= lvl_l
                else:
                    hit_l = armed_l and bh[i] >= lvl_l
                hit_s = armed_s and bl[i] <= lvl_s
                if hit_l and hit_s:
                    break
                if hit_l:
                    pos = 1
                    if long_trig == 0:
                        entry = max(lvl_l, ao[i]) + slip
                    else:
                        entry = max(lvl_l + (ao[i] - bo[i]), ao[i]) + slip
                elif hit_s:
                    pos = -1
                    entry = min(lvl_s, bo[i]) - slip
                if pos == 0:
                    i += 1
                    continue
                ent_i = i
                risk = sl_dist[d]
                sl = entry - pos * risk
                tp = entry + pos * tp_r * risk if tp_r > 0 else 0.0
                if (pos == 1 and bl[i] <= sl) or (pos == -1 and ah[i] >= sl):
                    px = sl - pos * slip
                    out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = i
                    out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pos * (px - entry) - commission
                    out[k, 7] = risk; out[k, 8] = 1
                    k += 1
                    pos = 0
                    closed = True
                    break
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
                out[k, 7] = risk; out[k, 8] = r
                k += 1
                pos = 0
                closed = True
                break
            i += 1
        if pos != 0 and not closed:
            if ex_close[d]:
                j = d_ex[d] - 1
                px = (bc[j] - slip) if pos == 1 else (ac[j] + slip)
            else:
                j = min(d_ex[d], len(bo) - 1)
                px = (bo[j] - slip) if pos == 1 else (ao[j] + slip)
            out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = j
            out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pos * (px - entry) - commission
            out[k, 7] = risk; out[k, 8] = 4
            k += 1
    return out[:k]


def run_so(p, long_trig=0, long_add=0.0, short_add=0.0, start=None, end=E.IS_END, D=None):
    """p: engine.Params (entry_mode 0, max_trades 1, sl_ref 0/1; no be/trail, no trend/comp filters)."""
    assert p.entry_mode == 0 and p.max_trades == 1 and p.sl_ref in (0, 1)
    assert p.be_r == 0 and p.trail_r == 0 and p.trend == 0 and p.comp_n == 0 and not p.skip_nfp
    D = D or E.load()
    days = D["days"]
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close = E._windows_full(D, p.range_start, p.range_end,
                                                                      p.entry_end, p.exit_time)
    width = rh - rl
    atr = days["atr14_prev"].values.astype(float)
    if p.range_end < 0:
        atr = np.r_[np.nan, atr[:-1]]
    mask = valid & np.isfinite(atr) & (width > 0)
    wa = width / atr
    mask &= (wa >= p.min_w_atr) & (wa <= p.max_w_atr)
    mask &= np.array(p.dow_mask, dtype=bool)[days.index.dayofweek.values]
    if start is not None:
        mask &= days.index >= pd.Timestamp(start)
    if end is not None:
        mask &= days.index <= pd.Timestamp(end)
    buf = p.buf_k * width + p.buf_atr * np.nan_to_num(atr)
    sl_dist = p.sl_k * width if p.sl_ref == 0 else p.sl_k * np.nan_to_num(atr)
    sl_dist = np.maximum(np.nan_to_num(sl_dist), 0.3)
    out = _sim(D["bo"], D["bh"], D["bl"], D["bc"], D["ao"], D["ah"], D["al"], D["ac"],
               np.where(mask, i_re, -1).astype(np.int64), i_ee.astype(np.int64), i_ex.astype(np.int64),
               np.nan_to_num(rh), np.nan_to_num(rl), mask.copy(), mask.copy(), np.nan_to_num(buf), sl_dist,
               float(p.tp_r), float(p.commission), float(p.slip), ex_close.astype(np.bool_), int(long_trig),
               float(long_add), float(short_add))
    t = pd.DataFrame(out, columns=["day", "dir", "i_entry", "i_exit", "entry", "exit", "pnl", "risk", "reason"])
    if len(t) == 0:
        return t
    for c in ("day", "dir", "i_entry", "i_exit", "reason"):
        t[c] = t[c].astype(np.int64)
    t["date"] = days.index[t["day"].values]
    t["t_entry"] = D["index"][t["i_entry"].values]
    t["R"] = t["pnl"] / t["risk"]
    t["width"] = width[t["day"].values]
    t["reason"] = t["reason"].map({1: "sl", 2: "tp", 3: "trail", 4: "time"})
    return t
