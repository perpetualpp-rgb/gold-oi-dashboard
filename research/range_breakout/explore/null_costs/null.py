"""Null models for the range-breakout engine (reusable).

Main entry point
----------------
    null_test(params, n_perm=200, seed=0, D=None, end=engine.VAL_END)

Takes the trades that engine.run(params) produces, keeps each trade's ENTRY BAR (time), risk distance
(R size), SL/TP/BE/trail/exit rules and costs, and re-simulates it in BOTH directions:

    R_same : the trade as the engine took it          (reproduces engine.run exactly, see validate())
    R_flip : the opposite direction at the same moment

Because each trade's outcome in a given direction is deterministic, a random-direction permutation
is just a per-trade coin flip between R_same and R_flip; no re-walking per permutation is needed,
so n_perm can be large (10 000 costs < 1 s).

Nulls reported (per period IS / VAL and per actual direction):
  * coin     : each trade long or short with p = 0.5 (iid). Removes gold's drift from the null mean.
  * shuffle  : the trade directions are permuted across trades (the number of longs and shorts is
               kept), so the null has the same net long exposure as the strategy. This is the
               cleaner test of "does the breakout direction carry information", given the drift.
  * always_long / always_short at the same entry times.
p-values are one-sided, P(null avg_R >= actual avg_R), with the (1 + #>=) / (1 + n_perm) correction.

How the opposite-direction entry is priced
------------------------------------------
Let q be the quote the engine filled on (ASK for a long, BID for a short), i.e. entry -/+ entry slip.
The opposite trade trades the other side of the same quote at the same moment, paying the same spread
and the same slip:  orig long  -> short at q - spread - slip_e ;  orig short -> long at q + spread + slip_e
(slip_e = params.slip for stop / confirm entries, 0 for fade limit entries). The risk distance is the
original trade's risk (for sl_ref=2 the 'opposite edge' is not defined for the flipped side, so the
same USD distance is used). Entry-bar rule is the engine's: only the stop is checked on the entry bar.

Each trade is walked independently from its entry bar to the day's exit (for max_trades=2 the flipped
first trade may overlap the second trade of that day; the second trade is kept as its own entry time).

Secondary null
--------------
    null_time_test(params, n_perm=200, ...) : on the same trade days, enter at a RANDOM bar of the
    entry window [range_end, entry_end) at market (bar open, ASK+slip long / BID-slip short) with a
    random direction and the same risk distance/exit rules. Tests whether the breakout moment itself
    (volatility at the break) matters, not only the direction.
"""
import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import engine as E  # noqa: E402


# ------------------------------------------------------------------------------------------------
# bar walker (mirrors engine._simulate position management exactly)
# ------------------------------------------------------------------------------------------------
@njit(cache=True)
def _walk_one(pos, i0, entry, risk, iex, exclose, bo, bh, bl, bc, ao, ah, al, ac,
              tp_r, be_r, trail_r, commission, slip):
    """Returns (pnl, exit_px, exit_idx, reason) reason: 1 sl, 2 tp, 3 trail/BE stop, 4 time."""
    sl = entry - pos * risk
    tp = entry + pos * tp_r * risk if tp_r > 0 else 0.0
    best = entry
    be_done = False
    # entry bar: only the stop is checked
    if (pos == 1 and bl[i0] <= sl) or (pos == -1 and ah[i0] >= sl):
        px = sl - pos * slip
        return pos * (px - entry) - commission, px, i0, 1
    i = i0 + 1
    while i < iex:
        if pos == 1:
            if bl[i] <= sl:
                px = min(sl, bo[i]) - slip
                reason = 1 if sl < entry else 3
            elif tp_r > 0 and bh[i] >= tp:
                px = tp
                reason = 2
            else:
                px = 0.0
                reason = 0
                if bh[i] > best:
                    best = bh[i]
        else:
            if ah[i] >= sl:
                px = max(sl, ao[i]) + slip
                reason = 1 if sl > entry else 3
            elif tp_r > 0 and al[i] <= tp:
                px = tp
                reason = 2
            else:
                px = 0.0
                reason = 0
                if al[i] < best:
                    best = al[i]
        if reason != 0:
            return pos * (px - entry) - commission, px, i, reason
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
    if exclose:
        i = iex - 1
        px = (bc[i] - slip) if pos == 1 else (ac[i] + slip)
    else:
        i = iex
        if i >= len(bo):
            i = len(bo) - 1
        px = (bo[i] - slip) if pos == 1 else (ao[i] + slip)
    return pos * (px - entry) - commission, px, i, 4


@njit(cache=True)
def _walk_many(pos, i0, entry, risk, iex, exclose, bo, bh, bl, bc, ao, ah, al, ac,
               tp_r, be_r, trail_r, commission, slip):
    n = len(pos)
    pnl = np.empty(n)
    pxo = np.empty(n)
    iout = np.empty(n, dtype=np.int64)
    rsn = np.empty(n, dtype=np.int64)
    for k in range(n):
        a, b, c, d = _walk_one(pos[k], i0[k], entry[k], risk[k], iex[k], exclose[k],
                               bo, bh, bl, bc, ao, ah, al, ac, tp_r, be_r, trail_r, commission, slip)
        pnl[k] = a
        pxo[k] = b
        iout[k] = c
        rsn[k] = d
    return pnl, pxo, iout, rsn


def _day_windows(p, D):
    """(i_re, i_ee, i_ex, ex_close) per engine day index for these session hours."""
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close = E._windows_full(D, p.range_start, p.range_end,
                                                                       p.entry_end, p.exit_time)
    return i_re, i_ee, i_ex, ex_close


def walk(p, trades, dirs, D=None, entries=None):
    """Re-simulate `trades` (engine.run output) with direction `dirs` (+1/-1 per trade) from each
    trade's entry bar. `entries` overrides entry prices (default: engine price for the same
    direction, mirrored quote for the opposite direction). Returns DataFrame pnl, exit, i_exit, reason, R."""
    D = D or E.load()
    _, _, i_ex, ex_close = _day_windows(p, D)
    day = trades["day"].values.astype(np.int64)
    i0 = trades["i_entry"].values.astype(np.int64)
    dirs = np.asarray(dirs, dtype=np.int64)
    if entries is None:
        entries = entry_prices(p, trades, dirs, D)
    risk = trades["risk"].values.astype(float)
    pnl, px, iout, rsn = _walk_many(dirs, i0, np.asarray(entries, float), risk,
                                    i_ex[day].astype(np.int64), ex_close[day].astype(np.bool_),
                                    D["bo"], D["bh"], D["bl"], D["bc"], D["ao"], D["ah"], D["al"], D["ac"],
                                    float(p.tp_r), float(p.be_r), float(p.trail_r),
                                    float(p.commission), float(p.slip))
    return pd.DataFrame({"pnl": pnl, "exit": px, "i_exit": iout, "reason": rsn, "R": pnl / risk},
                        index=trades.index)


def entry_prices(p, trades, dirs, D):
    """Engine entry price when dirs == trade dir; mirrored quote (other side, same spread and slip)
    when flipped."""
    slip_e = 0.0 if p.entry_mode == 2 else p.slip
    i0 = trades["i_entry"].values.astype(np.int64)
    spr = D["ao"][i0] - D["bo"][i0]
    e = trades["entry"].values.astype(float)
    od = trades["dir"].values.astype(np.int64)
    q = e - od * slip_e                       # quote the engine filled on (ASK long, BID short)
    flip_px = np.where(od == 1, q - spr - slip_e, q + spr + slip_e)
    return np.where(np.asarray(dirs) == od, e, flip_px)


def both_ways(p, D=None, start=None, end=E.VAL_END, trades=None):
    """engine.run trades plus R_same (re-walked) and R_flip (opposite direction, same moment)."""
    D = D or E.load()
    t = E.run(p, start=start, end=end, D=D) if trades is None else trades
    if len(t) == 0:
        return t
    t = t.copy()
    od = t["dir"].values
    s = walk(p, t, od, D)
    f = walk(p, t, -od, D)
    t["R_same"] = s["R"].values
    t["R_flip"] = f["R"].values
    t["reason_flip"] = f["reason"].values
    t["R_long"] = np.where(od == 1, t["R_same"], t["R_flip"])
    t["R_short"] = np.where(od == -1, t["R_same"], t["R_flip"])
    return t


def validate(p, D=None, end=E.VAL_END, tol=1e-9):
    """Check the re-walker reproduces engine.run (same direction). Returns (n, max|dR|, n_mismatch)."""
    D = D or E.load()
    t = E.run(p, end=end, D=D)
    if len(t) == 0:
        return 0, 0.0, 0
    s = walk(p, t, t["dir"].values, D)
    rmap = {"sl": 1, "tp": 2, "trail": 3, "time": 4}
    dR = np.abs(s["R"].values - t["R"].values)
    bad = (dR > tol) | (s["i_exit"].values != t["i_exit"].values) | \
          (s["reason"].values != t["reason"].map(rmap).values) | (np.abs(s["exit"].values - t["exit"].values) > tol)
    return len(t), float(dR.max()), int(bad.sum())


# ------------------------------------------------------------------------------------------------
# permutation nulls
# ------------------------------------------------------------------------------------------------
def _perm_block(Rs, Rf, od, n_perm, rng):
    """coin + shuffle null distributions of avg_R."""
    n = len(Rs)
    if n == 0:
        return {}
    actual = Rs.mean()
    # coin: each trade independently keeps (Rs) or flips (Rf) its direction with p=0.5
    coin = np.empty(n_perm)
    shuf = np.empty(n_perm)
    RL = np.where(od == 1, Rs, Rf)
    RS = np.where(od == -1, Rs, Rf)
    nL = int((od == 1).sum())
    chunk = max(1, int(2e7 // max(n, 1)))
    for a in range(0, n_perm, chunk):
        b = min(n_perm, a + chunk)
        m = rng.random((b - a, n)) < 0.5
        coin[a:b] = np.where(m, Rs, Rf).mean(axis=1)
        # shuffle: random set of nL trades are long, rest short
        keys = rng.random((b - a, n))
        rank = np.argsort(np.argsort(keys, axis=1), axis=1)
        isL = rank < nL
        shuf[a:b] = np.where(isL, RL, RS).mean(axis=1)

    def summ(x):
        return dict(mean=float(x.mean()), sd=float(x.std(ddof=1)), q05=float(np.quantile(x, 0.05)),
                    q50=float(np.quantile(x, 0.5)), q95=float(np.quantile(x, 0.95)),
                    p=float((1 + (x >= actual - 1e-12).sum()) / (1 + len(x))),
                    z=float((actual - x.mean()) / x.std(ddof=1)) if x.std(ddof=1) > 0 else np.nan)
    # analytic check (coin): mean of (Rs+Rf)/2, var = sum((Rs-Rf)^2/4)/n^2
    d = (Rs - Rf) / 2
    z_an = d.sum() / np.sqrt((d ** 2).sum()) if (d ** 2).sum() > 0 else np.nan
    return dict(n=n, n_long=nL, n_short=n - nL, actual=float(actual),
                always_long=float(RL.mean()), always_short=float(RS.mean()),
                coin=summ(coin), shuffle=summ(shuf), z_coin_analytic=float(z_an),
                _coin=coin, _shuffle=shuf)


def null_test(params, n_perm=200, seed=0, D=None, end=E.VAL_END, trades=None, periods=None,
              keep_dist=False):
    """Random-direction null at the breakout entry times.

    params  : engine.Params
    n_perm  : number of permutations (coin and shuffle each)
    end     : last date (default engine.VAL_END; never pass a date >= 2024-01-01)
    periods : dict name -> (start, end) date strings; default IS and VAL
    Returns dict: {'trades': DataFrame with R_same/R_flip/R_long/R_short, 'IS': {...}, 'VAL': {...}}
    Each period block has n, actual avg_R, always_long, always_short, coin{mean,sd,q05,q50,q95,p,z},
    shuffle{...}, and per-direction sub-blocks 'long_trades' / 'short_trades'
    (actual vs the opposite trade at the same moment).
    """
    if pd.Timestamp(end) >= pd.Timestamp("2024-01-01"):
        raise ValueError("holdout is sealed: end must be < 2024-01-01")
    D = D or E.load()
    t = both_ways(params, D=D, end=end, trades=trades)
    if periods is None:
        periods = {"IS": (None, E.IS_END), "VAL": ("2022-01-01", E.VAL_END)}
    rng = np.random.default_rng(seed)
    res = {"trades": t}
    for name, (a, b) in periods.items():
        sub = t
        if len(sub) and a is not None:
            sub = sub[sub["date"] >= pd.Timestamp(a)]
        if len(sub) and b is not None:
            sub = sub[sub["date"] <= pd.Timestamp(b)]
        if len(sub) == 0:
            res[name] = dict(n=0)
            continue
        od = sub["dir"].values
        blk = _perm_block(sub["R_same"].values, sub["R_flip"].values, od, n_perm, rng)
        for dname, dv in (("long_trades", 1), ("short_trades", -1)):
            m = od == dv
            if m.sum() > 1:
                rs, rf = sub["R_same"].values[m], sub["R_flip"].values[m]
                dd = rs - rf
                blk[dname] = dict(n=int(m.sum()), actual=float(rs.mean()), opposite=float(rf.mean()),
                                  diff=float(dd.mean()),
                                  t_diff=float(dd.mean() / dd.std(ddof=1) * np.sqrt(len(dd))))
        if not keep_dist:
            blk.pop("_coin")
            blk.pop("_shuffle")
        res[name] = blk
    return res


def summary_rows(res, label=""):
    """Flatten null_test output into table rows."""
    rows = []
    for per in ("IS", "VAL"):
        b = res.get(per, {})
        if not b or b.get("n", 0) == 0:
            continue
        rows.append(dict(config=label, period=per, n=b["n"], nL=b["n_long"], nS=b["n_short"],
                         actual=round(b["actual"], 4),
                         always_long=round(b["always_long"], 4), always_short=round(b["always_short"], 4),
                         coin_mean=round(b["coin"]["mean"], 4), coin_sd=round(b["coin"]["sd"], 4),
                         coin_q95=round(b["coin"]["q95"], 4), p_coin=round(b["coin"]["p"], 4),
                         shuf_mean=round(b["shuffle"]["mean"], 4), shuf_q95=round(b["shuffle"]["q95"], 4),
                         p_shuffle=round(b["shuffle"]["p"], 4),
                         L_minus_opp=round(b.get("long_trades", {}).get("diff", np.nan), 4),
                         S_minus_opp=round(b.get("short_trades", {}).get("diff", np.nan), 4)))
    return rows


# ------------------------------------------------------------------------------------------------
# random-time null
# ------------------------------------------------------------------------------------------------
def null_time_test(params, n_perm=200, seed=0, D=None, end=E.VAL_END, trades=None, periods=None):
    """On the strategy's trade days (one entry per day, first trade of the day), enter at a random bar
    of [range_end, entry_end) at market (ASK open + slip / BID open - slip), random direction, same
    risk distance and exit rules and costs. Returns per-period null distribution of avg_R."""
    if pd.Timestamp(end) >= pd.Timestamp("2024-01-01"):
        raise ValueError("holdout is sealed")
    D = D or E.load()
    t = E.run(params, end=end, D=D) if trades is None else trades
    t = t.drop_duplicates("day", keep="first")
    i_re, i_ee, i_ex, ex_close = _day_windows(params, D)
    day = t["day"].values.astype(np.int64)
    lo = i_re[day].astype(np.int64)
    hi = np.minimum(i_ee[day], i_ex[day]).astype(np.int64)        # entries strictly before hi
    risk = t["risk"].values.astype(float)
    if periods is None:
        periods = {"IS": (None, E.IS_END), "VAL": ("2022-01-01", E.VAL_END)}
    rng = np.random.default_rng(seed)
    n = len(t)
    Rm = np.empty((n_perm, n))
    for k in range(n_perm):
        ib = lo + np.floor(rng.random(n) * np.maximum(hi - lo, 1)).astype(np.int64)
        dirs = np.where(rng.random(n) < 0.5, 1, -1).astype(np.int64)
        ent = np.where(dirs == 1, D["ao"][ib] + params.slip, D["bo"][ib] - params.slip)
        pnl, _, _, _ = _walk_many(dirs, ib, ent, risk, i_ex[day].astype(np.int64),
                                  ex_close[day].astype(np.bool_),
                                  D["bo"], D["bh"], D["bl"], D["bc"], D["ao"], D["ah"], D["al"], D["ac"],
                                  float(params.tp_r), float(params.be_r), float(params.trail_r),
                                  float(params.commission), float(params.slip))
        Rm[k] = pnl / risk
    out = {}
    for name, (a, b) in periods.items():
        m = np.ones(n, bool)
        if a is not None:
            m &= t["date"].values >= np.datetime64(pd.Timestamp(a))
        if b is not None:
            m &= t["date"].values <= np.datetime64(pd.Timestamp(b))
        if m.sum() == 0:
            continue
        x = Rm[:, m].mean(axis=1)
        act = t["R"].values[m].mean()
        out[name] = dict(n=int(m.sum()), actual_first_trade=float(act), mean=float(x.mean()),
                         sd=float(x.std(ddof=1)), q05=float(np.quantile(x, .05)), q95=float(np.quantile(x, .95)),
                         p=float((1 + (x >= act).sum()) / (1 + n_perm)))
    return out


# ------------------------------------------------------------------------------------------------
# family-wise tests (multiple testing over a searched family of configs)
# ------------------------------------------------------------------------------------------------
def _family_frames(configs, D, start, end):
    fr = {}
    for name, v in configs.items():
        p, tr = (v if isinstance(v, tuple) else (v, None))
        t = both_ways(p, D=D, start=start, end=end, trades=tr)
        if len(t) and tr is not None:
            if start is not None:
                t = t[t["date"] >= pd.Timestamp(start)]
            t = t[t["date"] <= pd.Timestamp(end)]
        if len(t) > 2:
            fr[name] = t
    return fr


def family_null(configs, n_perm=2000, seed=0, D=None, start=None, end=E.IS_END, chunk=250):
    """Direction-information test with a family-wise (single-step max-z) correction.

    configs : dict name -> Params  or  name -> (Params, trades)   (trades = engine.run output, possibly
              filtered post hoc by a day mask; None = engine.run(Params))
    Per config, d_i = (R_same_i - R_flip_i) / 2 and z = sum(d) / sqrt(sum(d^2)) (the random-direction
    null of avg_R, centred and scaled; = the analytic coin z). Under the null each d_i has a random sign.
    ONE coin per DATE is shared by all configs, which keeps the cross-config dependence. Returns raw
    and family-adjusted p = P(max over configs of null z >= observed z).
    NB: this tests whether the chosen DIRECTION beats a random one at the same moments. It does not
    test net profitability (use family_bootstrap for that).
    """
    if pd.Timestamp(end) >= pd.Timestamp("2024-01-01"):
        raise ValueError("holdout is sealed")
    D = D or E.load()
    fr = _family_frames(configs, D, start, end)
    dates = np.unique(np.concatenate([f["date"].values for f in fr.values()]))
    names = list(fr)
    dd = {n: ((fr[n]["R_same"].values - fr[n]["R_flip"].values) / 2) for n in names}
    didx = {n: np.searchsorted(dates, fr[n]["date"].values) for n in names}
    obs = np.array([dd[n].sum() / np.sqrt((dd[n] ** 2).sum()) for n in names])
    rng = np.random.default_rng(seed)
    null = np.empty((n_perm, len(names)))
    for a in range(0, n_perm, chunk):
        b = min(n_perm, a + chunk)
        sgn = np.where(rng.random((b - a, len(dates))) < 0.5, 1.0, -1.0)
        for j, n in enumerate(names):
            null[a:b, j] = (sgn[:, didx[n]] * dd[n]).sum(axis=1) / np.sqrt((dd[n] ** 2).sum())
    mx = null.max(axis=1)
    rows = []
    for j, n in enumerate(names):
        rows.append(dict(config=n, n=len(fr[n]), avg_R=fr[n]["R_same"].mean(), dir_info_R=dd[n].mean(),
                         z=obs[j], p_raw=(1 + (null[:, j] >= obs[j]).sum()) / (1 + n_perm),
                         p_family=(1 + (mx >= obs[j]).sum()) / (1 + n_perm)))
    out = pd.DataFrame(rows).sort_values("z", ascending=False).reset_index(drop=True)
    out.attrs["max_null_q95"] = float(np.quantile(mx, 0.95))
    out.attrs["n_configs"] = len(names)
    return out


def family_bootstrap(configs, n_boot=2000, block=10, seed=0, D=None, start=None, end=E.IS_END):
    """Net-profitability test with a family-wise correction (White's reality check, studentised,
    single-step max-t): H0 for each config is 'true avg_R <= 0'. Dates (the union over configs) are
    resampled jointly with a stationary bootstrap (mean block `block` trading days), so the cross-config
    and serial dependence are kept. t* = (avgR* - avgR) / se_boot; p_family = P(max t* >= t_obs)."""
    if pd.Timestamp(end) >= pd.Timestamp("2024-01-01"):
        raise ValueError("holdout is sealed")
    D = D or E.load()
    fr = {}
    for name, v in configs.items():
        p, tr = (v if isinstance(v, tuple) else (v, None))
        t = E.run(p, start=start, end=end, D=D) if tr is None else tr
        t = t[t["date"] <= pd.Timestamp(end)]
        if start is not None:
            t = t[t["date"] >= pd.Timestamp(start)]
        if len(t) > 2:
            fr[name] = t
    names = list(fr)
    dates = np.unique(np.concatenate([fr[n]["date"].values for n in names]))
    nd = len(dates)
    S = np.zeros((len(names), nd))
    Nn = np.zeros((len(names), nd))
    for j, n in enumerate(names):
        ix = np.searchsorted(dates, fr[n]["date"].values)
        np.add.at(S[j], ix, fr[n]["R"].values)
        np.add.at(Nn[j], ix, 1.0)
    rng = np.random.default_rng(seed)
    # stationary bootstrap index matrix
    idx = np.empty((n_boot, nd), dtype=np.int64)
    pstart = 1.0 / block
    for b in range(n_boot):
        new = rng.random(nd) < pstart
        new[0] = True
        starts = rng.integers(0, nd, nd)
        pos = np.empty(nd, dtype=np.int64)
        cur = 0
        for i in range(nd):
            cur = starts[i] if new[i] else (cur + 1) % nd
            pos[i] = cur
        idx[b] = pos
    obs_m = S.sum(axis=1) / Nn.sum(axis=1)
    boot_m = np.empty((n_boot, len(names)))
    for j in range(len(names)):
        boot_m[:, j] = S[j][idx].sum(axis=1) / np.maximum(Nn[j][idx].sum(axis=1), 1)
    se = boot_m.std(axis=0, ddof=1)
    t_obs = obs_m / se
    t_star = (boot_m - obs_m) / se
    mx = t_star.max(axis=1)
    rows = []
    for j, n in enumerate(names):
        rows.append(dict(config=n, n=int(Nn[j].sum()), avg_R=obs_m[j], t_boot=t_obs[j],
                         p_raw=(1 + (t_star[:, j] >= t_obs[j]).sum()) / (1 + n_boot),
                         p_family=(1 + (mx >= t_obs[j]).sum()) / (1 + n_boot)))
    out = pd.DataFrame(rows).sort_values("t_boot", ascending=False).reset_index(drop=True)
    out.attrs["max_t_q95"] = float(np.quantile(mx, 0.95))
    out.attrs["n_configs"] = len(names)
    return out
