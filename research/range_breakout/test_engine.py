"""Synthetic-price tests for engine.py execution rules. Run: python3 -m pytest -q test_engine.py"""
import numpy as np
import pandas as pd

import engine as E

SPREAD = 0.2


def make_D(day_paths, start="2024-01-08"):
    """day_paths: list of callables f(minute_of_day)->(o,h,l,c) BID, minutes 0..1259 (00:00-21:00 London, winter=UTC)."""
    idx, rows = [], []
    days = pd.bdate_range(start, periods=len(day_paths))
    for d, f in zip(days, day_paths):
        for m in range(0, 21 * 60):
            idx.append(pd.Timestamp(d, tz="UTC") + pd.Timedelta(minutes=m))
            rows.append(f(m))
    idx = pd.DatetimeIndex(idx)
    a = np.array(rows, dtype=float)
    lmin = idx.tz_convert("Europe/London").tz_localize(None).values.astype("datetime64[m]").astype(np.int64)
    D = dict(index=idx, lmin=lmin,
             bo=a[:, 0], bh=a[:, 1], bl=a[:, 2], bc=a[:, 3],
             ao=a[:, 0] + SPREAD, ah=a[:, 1] + SPREAD, al=a[:, 2] + SPREAD, ac=a[:, 3] + SPREAD)
    g = pd.DataFrame(index=days)
    g["atr14_prev"] = 10.0
    g["close_prev"] = 2000.0
    for n in (20, 50, 100, 200):
        g[f"sma{n}_prev"] = 1990.0  # uptrend
    D["days"] = g
    E._WIN_CACHE.clear()
    return D


def flat_range(m):
    # Asian range 1995..2005 (00:00-07:00), oscillating
    if m < 7 * 60:
        return (2000, 2005, 1995, 2000) if m % 60 == 0 else (2000, 2001, 1999, 2000)
    return None


def path_up_tp(m):
    r = flat_range(m)
    if r:
        return r
    if m < 8 * 60:
        return (2000, 2001, 1999, 2000)
    if m == 8 * 60:
        return (2000, 2006, 2000, 2006)        # breakout: ask high 2006.2 >= 2005
    if m < 10 * 60:
        return (2006, 2007, 2005.5, 2006.5)
    return (2030, 2031, 2029, 2030)           # far beyond TP


def path_up_sl(m):
    r = flat_range(m)
    if r:
        return r
    if m == 8 * 60:
        return (2000, 2006, 2000, 2006)
    if 8 * 60 < m < 9 * 60:
        return (2006, 2006.5, 2005, 2005.5)
    if m >= 9 * 60:
        return (1990, 1991, 1980, 1985)       # through the stop
    return (2000, 2001, 1999, 2000)


def path_time_exit(m):
    r = flat_range(m)
    if r:
        return r
    if m == 8 * 60:
        return (2000, 2006, 2000, 2006)
    if m > 8 * 60:
        return (2008, 2009, 2007, 2008)
    return (2000, 2001, 1999, 2000)


def P(**kw):
    base = dict(range_start=0, range_end=7, entry_end=12, exit_time=20, sl_ref=0, sl_k=1.0, tp_r=1.0,
                commission=0.0, slip=0.0)
    base.update(kw)
    return E.Params(**base)


def test_long_tp():
    D = make_D([path_up_tp])
    t = E.run(P(), D=D)
    assert len(t) == 1
    r = t.iloc[0]
    assert r.dir == 1
    assert abs(r.entry - 2005.0) < 1e-9          # buy stop at range high 2005 hit via ask
    assert r.reason == "tp"
    assert abs(r.R - 1.0) < 1e-9                  # risk = width 10, TP = 1R


def test_long_sl_gap_fill():
    D = make_D([path_up_sl])
    t = E.run(P(tp_r=0), D=D)
    r = t.iloc[0]
    assert r.reason == "sl"
    # stop 1995, bar opens 1990 -> gap fill at 1990 => -15/10 = -1.5R
    assert abs(r.exit - 1990) < 1e-9 and abs(r.R + 1.5) < 1e-9


def test_time_exit_on_bid():
    D = make_D([path_time_exit])
    t = E.run(P(tp_r=0), D=D)
    r = t.iloc[0]
    assert r.reason == "time"
    assert abs(r.exit - 2008) < 1e-9             # BID open of the 20:00 bar
    assert r.t_exit.hour == 20


def test_costs_reduce_pnl():
    # time exit: entry slip + exit slip + commission all hit PnL
    D = make_D([path_time_exit])
    t0 = E.run(P(tp_r=0), D=D)
    t1 = E.run(P(tp_r=0, commission=0.07, slip=0.05), D=D)
    assert abs((t0.pnl.iloc[0] - t1.pnl.iloc[0]) - 0.17) < 1e-9


def test_no_entry_after_cutoff():
    D = make_D([path_up_tp])
    t = E.run(P(entry_end=8.0), D=D)              # breakout bar is 08:00 -> excluded
    assert len(t) == 0


def test_trend_filter_blocks_long():
    D = make_D([path_up_tp])
    D["days"][[c for c in D["days"].columns if c.startswith("sma")]] = 2010.0  # downtrend
    t = E.run(P(trend=20), D=D)
    assert len(t) == 0


def test_confirm_mode_enters_next_bar_open():
    D = make_D([path_up_tp])
    t = E.run(P(entry_mode=1, confirm_tf=15), D=D)
    r = t.iloc[0]
    # 08:14 bar (15-min block close) closes 2006.5 > 2005 -> entry at 08:15 ask open 2006.2
    assert r.t_entry.hour == 8 and r.t_entry.minute == 15
    assert abs(r.entry - 2006.2) < 1e-9


def test_range_uses_only_range_window():
    D = make_D([path_up_tp])
    i_rs, i_re, *_ , rh, rl, valid = E._windows(D, 0, 7, 12, 20)
    assert rh[0] == 2005 and rl[0] == 1995 and valid[0]


def test_fade_sells_upper_break():
    D = make_D([path_up_sl])
    t = E.run(P(entry_mode=2), D=D)
    r = t.iloc[0]
    assert r.dir == -1 and abs(r.entry - 2005) < 1e-9     # sell limit at range high, touched by BID
    assert r.reason == "tp" and abs(r.R - 1.0) < 1e-9     # TP 1R = 1995
