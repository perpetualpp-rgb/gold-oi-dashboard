"""Session range-breakout backtest engine for XAUUSD on Dukascopy M1 BID/ASK bars.

Conventions (kept deliberately conservative):
- Session times are London local clock (DST-aware). A "day" is a London calendar date, Mon-Fri.
- The range is built from BID highs/lows (what an MT4/MT5 chart shows).
- Buy stops trigger on ASK high, sell stops on BID low (MT execution model). Fills are at the
  worse of the level and the bar open (gaps), plus `slip`.
- Longs exit on BID, shorts on ASK. Stops fill at the worse of stop level and bar open, minus `slip`.
- If SL and TP are both inside one M1 bar, SL is assumed first. On the entry bar only SL is checked.
- Take-profit fills exactly at the TP price (no favourable gap fill).
- If both breakout levels are touched in the same bar before a position exists, the day is skipped.
- Time exit: market order at the open of the first bar at/after `exit_time`. If the market is closed at
  `exit_time` (US-holiday early close, Friday close, exit_time inside the daily halt), the position is
  flattened at the close of the last bar before `exit_time` (an EA does this with the broker's holiday
  calendar) instead of being carried to the next session's open.
- max_trades=2 (stop orders): the opposite stop order stays armed; if a stop-out and the opposite
  level happen in the same M1 bar, the reversal fills in that bar (price moves through both levels).
- Commission is charged per ounce round trip (7 USD/lot = 0.07 USD/oz).
- Every filter uses only information available before the entry window opens (prior days, or the
  range itself which is complete when the window opens). If range_end < 0 (the entry window opens on
  the previous evening), daily features are taken one more day back, because the previous London day
  is not finished yet.
"""
import os
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data_cache")

# Split used everywhere. Holdout must not be used for design decisions.
IS_END = "2021-12-31"      # in-sample: 2014-01-01 .. 2021-12-31
VAL_END = "2023-12-31"     # validation: 2022-01-01 .. 2023-12-31
# holdout: 2024-01-01 .. end of data

_DATA = None


def load(force=False):
    """Return dict of aligned numpy arrays + London local minute clock."""
    global _DATA
    if _DATA is not None and not force:
        return _DATA
    bid = pd.read_parquet(os.path.join(CACHE, "XAUUSD_M1_BID.parquet"))
    ask = pd.read_parquet(os.path.join(CACHE, "XAUUSD_M1_ASK.parquet"))
    idx = bid.index.intersection(ask.index)
    bid, ask = bid.loc[idx], ask.loc[idx]
    # drop obviously broken quotes (negative spread or absurd spread)
    spr = ask["close"] - bid["close"]
    ok = (spr >= 0) & (spr < 5.0)
    bid, ask, idx = bid[ok], ask[ok], idx[ok]
    local = idx.tz_convert("Europe/London").tz_localize(None)
    lmin = (local.values.astype("datetime64[m]").astype(np.int64))  # minutes since epoch, London clock
    _DATA = dict(
        index=idx,
        lmin=lmin,
        bo=bid["open"].values, bh=bid["high"].values, bl=bid["low"].values, bc=bid["close"].values,
        ao=ask["open"].values, ah=ask["high"].values, al=ask["low"].values, ac=ask["close"].values,
    )
    _DATA["days"] = _daily(_DATA)
    return _DATA


def _daily(d):
    """Daily (London date) OHLC from BID, used for ATR / trend filters (always shifted by 1 day)."""
    day = d["lmin"] // 1440
    s = pd.DataFrame({"day": day, "o": d["bo"], "h": d["bh"], "l": d["bl"], "c": d["bc"]})
    g = s.groupby("day").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    g.index = pd.to_datetime(g.index * 86400, unit="s")
    g = g[g.index.dayofweek < 5]
    pc = g["c"].shift(1)
    tr = np.maximum(g["h"] - g["l"], np.maximum((g["h"] - pc).abs(), (g["l"] - pc).abs()))
    g["atr14_prev"] = tr.rolling(14).mean().shift(1)
    g["close_prev"] = g["c"].shift(1)
    for n in (20, 50, 100, 200):
        g[f"sma{n}_prev"] = g["c"].rolling(n).mean().shift(1)
    return g


@dataclass
class Params:
    # session definition, hours on London clock relative to the day's 00:00 (negative = previous evening)
    range_start: float = 0.0
    range_end: float = 7.0
    entry_end: float = 12.0      # no new entries at/after this time
    exit_time: float = 20.0      # flat at this time
    # entry
    entry_mode: int = 0          # 0 = stop order at level, 1 = bar-close confirmation on `confirm_tf` minutes,
                                 # 2 = fade: limit order AGAINST the break at the level (use sl_ref 0/1, max_trades 1)
    confirm_tf: int = 15
    buf_k: float = 0.0           # buffer beyond range edge = buf_k * range width + buf_atr * ATR
    buf_atr: float = 0.0
    # stop / target (distances measured from the entry price)
    sl_ref: int = 0              # 0 = range width, 1 = ATR14(prev), 2 = opposite range edge (+ buffer)
    sl_k: float = 1.0
    tp_r: float = 0.0            # take profit in R (0 = none)
    be_r: float = 0.0            # move stop to entry once price reaches be_r * R (0 = off)
    trail_r: float = 0.0         # trail stop at best - trail_r * R, active after be_r reached (or immediately if be_r=0)
    max_trades: int = 1          # 2 = allow one stop-and-reverse (opposite order stays armed)
    # filters
    min_w_atr: float = 0.0       # range width / ATR14 bounds
    max_w_atr: float = 99.0
    comp_n: int = 0              # compression filter: width / median(width of prior comp_n days)
    comp_max: float = 99.0
    comp_min: float = 0.0
    trend: int = 0               # 0 off; N = trade only in direction of prev close vs SMA(N)
    trend_mode: int = 0          # 0 = trend-following only, 1 = counter-trend only
    dow_mask: tuple = (1, 1, 1, 1, 1)   # Mon..Fri
    skip_nfp: bool = False       # skip first Friday of month
    # costs
    commission: float = 0.07     # USD per oz round trip
    slip: float = 0.05           # USD per stop/market fill
    max_spread: float = 1.0      # skip entry if spread at trigger bar open exceeds this
                                 # (NB: ASK is BID + an hourly median spread model, so this rarely binds)
    limit_pen: float = 0.0       # fade limits fill only if price trades this far (USD) through the level
                                 # (0 = fill on touch, as MT5 does; >0 = conservative queue/touch check)

    def to_dict(self):
        return asdict(self)


@njit(cache=True)
def _simulate(bo, bh, bl, bc, ao, ah, al, ac, lmin,
              d_rs, d_re, d_ee, d_ex, rh, rl, atr, allow_l, allow_s,
              entry_mode, confirm_tf, buf, sl_dist, tp_r, be_r, trail_r, max_trades,
              commission, slip, max_spread, sl_ref_opp, ex_close, limit_pen):
    nd = len(d_rs)
    # each side can be traded at most once per day (armed_l / armed_s), so <= 2 trades per day
    out = np.full((nd * 2, 9), np.nan)
    k = 0
    for d in range(nd):
        if d_re[d] < 0 or d_ex[d] <= d_re[d]:
            continue
        lvl_l = rh[d] + buf[d]
        lvl_s = rl[d] - buf[d]
        armed_l = allow_l[d]
        armed_s = allow_s[d]
        if not (armed_l or armed_s):
            continue
        trades = 0
        pos = 0
        entry = 0.0
        sl = 0.0
        tp = 0.0
        risk = 0.0
        best = 0.0
        be_done = False
        pend = 0          # bar-close confirmation: pending direction to open at next bar open
        ent_i = -1
        i = d_re[d]
        redo = False      # re-scan the current bar for the opposite stop order after a stop-out
        while i < d_ex[d]:
            again = redo
            redo = False
            if pos == 0:
                if trades >= max_trades or i >= d_ee[d]:
                    if pend == 0:
                        break
                spread_now = ao[i] - bo[i]
                if pend != 0:
                    if spread_now <= max_spread:
                        pos = pend
                        entry = (ao[i] + slip) if pos == 1 else (bo[i] - slip)
                    pend = 0
                elif entry_mode == 0:
                    hit_l = armed_l and ah[i] >= lvl_l
                    hit_s = armed_s and bl[i] <= lvl_s
                    if hit_l and hit_s:
                        break
                    if hit_l:
                        pos = 1
                        entry = max(lvl_l, ao[i]) + slip
                    elif hit_s:
                        pos = -1
                        entry = min(lvl_s, bo[i]) - slip
                    if pos != 0 and spread_now > max_spread:
                        pos = 0
                        break
                elif entry_mode == 2:
                    # fade: sell limit at the upper level (BID touch), buy limit at the lower level (ASK touch)
                    hit_up = armed_s and bh[i] >= lvl_l + limit_pen
                    hit_dn = armed_l and al[i] <= lvl_s - limit_pen
                    if hit_up and hit_dn:
                        break
                    if hit_up:
                        pos = -1
                        entry = lvl_l
                    elif hit_dn:
                        pos = 1
                        entry = lvl_s
                    if pos != 0 and spread_now > max_spread:
                        pos = 0
                        break
                else:
                    if (lmin[i] + 1) % confirm_tf == 0 and i + 1 < d_ex[d] and i + 1 < d_ee[d]:
                        if armed_l and bc[i] > lvl_l:
                            pend = 1
                        elif armed_s and bc[i] < lvl_s:
                            pend = -1
                    i += 1
                    continue
                if pos == 0:
                    i += 1
                    continue
                # position opened on bar i
                trades += 1
                ent_i = i
                if sl_ref_opp:
                    if pos == 1:
                        risk = entry - (rl[d] - buf[d])
                    else:
                        risk = (rh[d] + buf[d]) - entry
                    risk = max(risk, 0.1)
                else:
                    risk = sl_dist[d]
                sl = entry - pos * risk
                tp = entry + pos * tp_r * risk if tp_r > 0 else 0.0
                best = entry
                be_done = False
                if pos == 1:
                    armed_l = False
                else:
                    armed_s = False
                # entry bar: only the stop is checked
                if (pos == 1 and bl[i] <= sl) or (pos == -1 and ah[i] >= sl):
                    px = sl - pos * slip
                    pnl = pos * (px - entry) - commission
                    out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = i
                    out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pnl; out[k, 7] = risk; out[k, 8] = 1
                    k += 1
                    pos = 0
                    if max_trades < 2 or trades >= max_trades:
                        break
                    if not again and entry_mode != 2:
                        redo = True
                        continue
                i += 1
                continue
            # manage open position on bar i
            if pos == 1:
                # stop first (conservative)
                if bl[i] <= sl:
                    px = min(sl, bo[i]) - slip
                    reason = 1 if sl < entry else 3
                elif tp_r > 0 and bh[i] >= tp:
                    px = tp
                    reason = 2
                else:
                    px = 0.0
                    reason = 0
                    fav = bh[i]
                    if fav > best:
                        best = fav
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
                    fav = al[i]
                    if fav < best:
                        best = fav
            if reason != 0:
                pnl = pos * (px - entry) - commission
                out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = i
                out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pnl; out[k, 7] = risk; out[k, 8] = reason
                k += 1
                pos = 0
                if max_trades < 2 or trades >= max_trades:
                    break
                # stop-out: price is moving toward the opposite level, so that stop order can fill in
                # this bar. Bar-close mode may also signal at this bar's close. Not after a TP (the
                # bar's low/high may precede the TP) and not for limit orders (fade).
                if not again and ((entry_mode == 0 and reason != 2) or entry_mode == 1):
                    redo = True
                    continue
                i += 1
                continue
            # stop adjustments use the bar's close-side extreme (applied from next bar)
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
        if pos != 0:
            if ex_close[d]:
                # market closed at exit_time: flatten at the close of the session's last bar
                i = d_ex[d] - 1
                px = (bc[i] - slip) if pos == 1 else (ac[i] + slip)
            else:
                i = d_ex[d]
                if i >= len(bo):
                    i = len(bo) - 1
                px = (bo[i] - slip) if pos == 1 else (ao[i] + slip)
            pnl = pos * (px - entry) - commission
            out[k, 0] = d; out[k, 1] = pos; out[k, 2] = ent_i; out[k, 3] = i
            out[k, 4] = entry; out[k, 5] = px; out[k, 6] = pnl; out[k, 7] = risk; out[k, 8] = 4
            k += 1
    return out[:k]


_WIN_CACHE = {}          # kept for backward compatibility; the live cache is stored inside each D
EXIT_GAP_TOL = 30        # minutes: if the first bar at/after exit_time is later than this, the
                         # market was closed at exit_time -> flatten at the previous bar's close


def _windows(D, rs, re_, ee, ex):
    """Bar-index windows per London day. Returns (i_rs, i_re, i_ee, i_ex, rh, rl, valid).
    Range = bars with London time in [rs, re_) (BID high/low); entries from the bar at i_re."""
    return _windows_full(D, rs, re_, ee, ex)[:7]


def _windows_full(D, rs, re_, ee, ex):
    cache = D.setdefault("_win_cache", {})   # per dataset, so two datasets never share windows
    key = (rs, re_, ee, ex)
    if key in cache:
        return cache[key]
    days = D["days"].index
    base = (days.values.astype("datetime64[m]").astype(np.int64))
    lmin = D["lmin"]
    t_rs = base + int(round(rs * 60))
    t_re = base + int(round(re_ * 60))
    t_ee = base + int(round(ee * 60))
    t_ex = base + int(round(ex * 60))
    i_rs = np.searchsorted(lmin, t_rs)
    i_re = np.searchsorted(lmin, t_re)
    i_ee = np.searchsorted(lmin, t_ee)
    i_ex = np.searchsorted(lmin, t_ex)
    ex_close = (i_ex >= len(lmin)) | (lmin[np.minimum(i_ex, len(lmin) - 1)] - t_ex > EXIT_GAP_TOL)
    n = len(days)
    rh = np.full(n, np.nan)
    rl = np.full(n, np.nan)
    bh, bl = D["bh"], D["bl"]
    valid = np.zeros(n, dtype=bool)
    for j in range(n):
        a, b = i_rs[j], i_re[j]
        # need a reasonably complete range: at least 60% of expected minutes
        if b - a >= 0.6 * (re_ - rs) * 60 and i_ex[j] > i_re[j] and i_re[j] < len(lmin):
            # the bar at i_re must be on the same session (not a weekend gap)
            if lmin[i_re[j]] - t_re[j] < 30:
                rh[j] = bh[a:b].max()
                rl[j] = bl[a:b].min()
                valid[j] = True
    res = (i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close)
    cache[key] = res
    return res


def run(p: Params, start=None, end=None, D=None):
    """Backtest. Returns trades DataFrame (one row per trade)."""
    D = D or load()
    if p.entry_mode == 2 and p.sl_ref == 2:
        raise ValueError("entry_mode=2 (fade) needs sl_ref 0 or 1: the 'opposite edge' is the fade's "
                         "entry level, which gives a zero-distance stop")
    days = D["days"]
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close = _windows_full(D, p.range_start, p.range_end,
                                                                      p.entry_end, p.exit_time)
    width = rh - rl
    # daily features are "as of the end of the previous London day". If the entry window opens
    # before midnight (range_end < 0) that day is still running, so go one more day back.
    lag = 1 if p.range_end < 0 else 0

    def feat(col):
        v = days[col].values.astype(float)
        return np.r_[np.full(lag, np.nan), v[:len(v) - lag]] if lag else v

    atr = feat("atr14_prev")
    mask = valid & np.isfinite(atr) & (width > 0)
    wa = width / atr
    mask &= (wa >= p.min_w_atr) & (wa <= p.max_w_atr)
    if p.comp_n > 0:
        med = pd.Series(width).rolling(p.comp_n, min_periods=max(5, p.comp_n // 2)).median().shift(1).values
        ratio = width / med
        mask &= np.isfinite(ratio) & (ratio <= p.comp_max) & (ratio >= p.comp_min)
    dow = days.index.dayofweek.values
    mask &= np.array(p.dow_mask, dtype=bool)[dow]
    if p.skip_nfp:
        nfp = (dow == 4) & (days.index.day.values <= 7)
        mask &= ~nfp
    if start is not None:
        mask &= days.index >= pd.Timestamp(start)
    if end is not None:
        mask &= days.index <= pd.Timestamp(end)
    allow_l = mask.copy()
    allow_s = mask.copy()
    if p.trend > 0:
        cp, sma = feat("close_prev"), feat(f"sma{p.trend}_prev")
        ok = np.isfinite(cp) & np.isfinite(sma)       # no trend defined yet -> no trade
        allow_l &= ok
        allow_s &= ok
        up = cp > sma
        if p.trend_mode == 0:
            allow_l &= up
            allow_s &= ~up
        else:
            allow_l &= ~up
            allow_s &= up
    buf = p.buf_k * width + p.buf_atr * np.nan_to_num(atr)
    if p.sl_ref == 0:
        sl_dist = p.sl_k * width
    elif p.sl_ref == 1:
        sl_dist = p.sl_k * np.nan_to_num(atr)
    else:
        sl_dist = np.zeros_like(width)
    sl_dist = np.maximum(np.nan_to_num(sl_dist), 0.3)
    out = _simulate(D["bo"], D["bh"], D["bl"], D["bc"], D["ao"], D["ah"], D["al"], D["ac"], D["lmin"],
                    i_rs.astype(np.int64), np.where(mask, i_re, -1).astype(np.int64), i_ee.astype(np.int64),
                    i_ex.astype(np.int64), np.nan_to_num(rh), np.nan_to_num(rl), np.nan_to_num(atr),
                    allow_l, allow_s, p.entry_mode, p.confirm_tf, np.nan_to_num(buf), sl_dist,
                    p.tp_r, p.be_r, p.trail_r, p.max_trades, p.commission, p.slip, p.max_spread,
                    p.sl_ref == 2, ex_close.astype(np.bool_), float(p.limit_pen))
    cols = ["day", "dir", "i_entry", "i_exit", "entry", "exit", "pnl", "risk", "reason"]
    t = pd.DataFrame(out, columns=cols)
    if len(t) == 0:
        return t
    for c in ("day", "dir", "i_entry", "i_exit", "reason"):
        t[c] = t[c].astype(np.int64)
    t["date"] = days.index[t["day"].values]
    t["t_entry"] = D["index"][t["i_entry"].values]
    t["t_exit"] = D["index"][np.minimum(t["i_exit"].values, len(D["index"]) - 1)]
    t["R"] = t["pnl"] / t["risk"]
    t["width"] = width[t["day"].values]
    t["atr"] = atr[t["day"].values]
    t["reason"] = t["reason"].map({1: "sl", 2: "tp", 3: "trail", 4: "time"})
    return t


def stats(t, label=""):
    """Summary metrics in R units (risk-normalised; 1R = planned stop distance)."""
    if t is None or len(t) == 0:
        return dict(label=label, n=0)
    R = t["R"].values
    daily = t.groupby("date")["R"].sum()
    eq = np.cumsum(R)
    dd = (np.maximum.accumulate(np.r_[0.0, eq])[1:] - eq).max()     # peak includes the 0 start
    years = max((t["date"].max() - t["date"].min()).days / 365.25, 0.5)
    wins, losses = R[R > 0].sum(), -R[R < 0].sum()
    sd = R.std(ddof=1) if len(R) > 1 else np.nan
    return dict(
        label=label,
        n=len(R),
        trades_per_year=round(len(R) / years, 1),
        win_rate=round((R > 0).mean(), 3),
        avg_R=round(R.mean(), 4),
        total_R=round(R.sum(), 1),
        PF=round(wins / losses, 3) if losses > 0 else np.inf,
        t_stat=round(R.mean() / sd * np.sqrt(len(R)), 2) if sd and sd > 0 else np.nan,
        # per-trading-day R, annualised with the number of days that actually had trades per year
        sharpe_ann=round(daily.mean() / daily.std(ddof=1) * np.sqrt(len(daily) / years), 2)
        if len(daily) > 2 else np.nan,
        maxDD_R=round(dd, 1),
        avg_win_R=round(R[R > 0].mean(), 3) if (R > 0).any() else 0,
        avg_loss_R=round(R[R < 0].mean(), 3) if (R < 0).any() else 0,
        usd_per_oz=round(t["pnl"].sum(), 1),
    )


def by_year(t):
    if len(t) == 0:
        return pd.DataFrame()
    g = t.groupby(t["date"].dt.year)["R"]
    return pd.DataFrame({"n": g.size(), "win": g.apply(lambda r: (r > 0).mean()).round(3),
                         "avg_R": g.mean().round(3), "sum_R": g.sum().round(1)})


def split(p: Params, D=None):
    """Stats on in-sample and validation only. Never touches the holdout."""
    D = D or load()
    t = run(p, end=VAL_END, D=D)
    if len(t) == 0:
        return {"IS": dict(n=0), "VAL": dict(n=0)}
    return {"IS": stats(t[t["date"] <= IS_END], "IS"), "VAL": stats(t[t["date"] > IS_END], "VAL")}


def holdout(p: Params, D=None):
    D = D or load()
    t = run(p, start="2024-01-01", D=D)
    return stats(t, "HOLDOUT"), t
