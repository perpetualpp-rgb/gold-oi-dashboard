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
            r = f(m)
            if r is None:          # missing bar (market closed / data hole)
                continue
            idx.append(pd.Timestamp(d, tz="UTC") + pd.Timedelta(minutes=m))
            rows.append(r)
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


# ---------------------------------------------------------------------------------------------
# Audit regression tests (explore/audit/REPORT.md)
# ---------------------------------------------------------------------------------------------

def _early_close(path, close_min=18 * 60 + 30):
    """Same path, but the market closes early (US holiday) at close_min."""
    return lambda m: None if m >= close_min else path(m)


def far_away(m):
    return (2100, 2101, 2099, 2100)                 # next session trades far away


def test_time_exit_on_early_close_day_exits_same_session():
    # Friday with a US-holiday early close at 18:30; exit_time 20:00 has no bar. The position must be
    # flattened at the close of the last bar of the session, not at the next session's open (Monday).
    D = make_D([_early_close(path_time_exit), far_away], start="2024-01-12")   # Fri, Mon
    t = E.run(P(tp_r=0), D=D)
    assert len(t) == 1
    r = t.iloc[0]
    assert r.reason == "time"
    assert r.t_exit.date() == pd.Timestamp("2024-01-12").date()
    assert r.t_exit.hour == 18 and r.t_exit.minute == 29
    assert abs(r.exit - 2008) < 1e-9                 # BID close of the 18:29 bar


def test_time_exit_short_on_early_close_uses_ask_close():
    def path_dn(m):
        r = flat_range(m)
        if r:
            return r
        if m == 8 * 60:
            return (2000, 2000, 1994, 1994)
        if m > 8 * 60:
            return (1992, 1993, 1991, 1992)
        return (2000, 2001, 1999, 2000)
    D = make_D([_early_close(path_dn), far_away], start="2024-01-12")
    t = E.run(P(tp_r=0, slip=0.05), D=D)
    r = t.iloc[0]
    assert r.reason == "time" and r.dir == -1
    assert abs(r.exit - (1992 + SPREAD + 0.05)) < 1e-9


def test_maxdd_counts_drawdown_from_start():
    t = pd.DataFrame({"R": [-1.0, -1.0, 0.5], "pnl": [-1.0, -1.0, 0.5],
                      "date": pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])})
    assert E.stats(t)["maxDD_R"] == 2.0


def test_sharpe_annualised_by_trading_days_not_252():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2016-01-01", "2019-12-31")[::5]          # ~52 trade days per year
    R = rng.normal(0.1, 1.0, len(dates))
    t = pd.DataFrame({"R": R, "pnl": R, "date": dates})
    years = (dates[-1] - dates[0]).days / 365.25
    expected = R.mean() / R.std(ddof=1) * np.sqrt(len(dates) / years)
    assert abs(E.stats(t)["sharpe_ann"] - round(expected, 2)) < 0.011


def test_trend_filter_with_undefined_sma_trades_nothing():
    D = make_D([path_up_tp])
    D["days"]["sma200_prev"] = np.nan                 # not enough history yet
    assert len(E.run(P(trend=200, trend_mode=0), D=D)) == 0
    assert len(E.run(P(trend=200, trend_mode=1), D=D)) == 0


def test_fade_with_opposite_edge_stop_is_rejected():
    D = make_D([path_up_sl])
    try:
        E.run(P(entry_mode=2, sl_ref=2), D=D)
    except ValueError:
        return
    raise AssertionError("fade + sl_ref=2 gives a zero-distance stop and must be rejected")


def path_reverse(m):
    r = flat_range(m)
    if r:
        return r
    if m == 8 * 60:
        return (2000, 2006, 2000, 2006)               # long at 2005, stop 1995
    if m < 8 * 60:
        return (2000, 2001, 1999, 2000)
    if 8 * 60 < m < 9 * 60:
        return (2006, 2006.5, 2005, 2005.5)
    if m == 9 * 60:
        return (2000, 2000, 1985, 1986)               # through the stop AND the sell-stop at 1995
    return (1986, 1987, 1984, 1985)


def test_reversal_fills_on_the_same_bar_as_the_stop():
    D = make_D([path_reverse])
    t = E.run(P(tp_r=0, max_trades=2), D=D)
    assert len(t) == 2
    lg, sh = t.iloc[0], t.iloc[1]
    assert lg.dir == 1 and lg.reason == "sl" and abs(lg.exit - 1995) < 1e-9
    # the opposite sell stop at 1995 is armed and is crossed in the same 09:00 bar
    assert sh.dir == -1 and sh.t_entry == lg.t_exit and abs(sh.entry - 1995) < 1e-9


def test_confirm_mode_respects_entry_cutoff():
    D = make_D([path_up_tp])
    # signal at the close of the 08:00-08:14 block would fill at 08:15 = entry_end -> not allowed
    t = E.run(P(entry_mode=1, confirm_tf=15, entry_end=8.25), D=D)
    assert len(t) == 0


def test_range_excludes_bar_at_range_end():
    def path(m):
        if m == 7 * 60:
            return (2000, 2050, 1950, 2000)           # huge bar exactly at range_end
        return path_up_tp(m)
    D = make_D([path])
    *_, rh, rl, valid = E._windows(D, 0, 7, 12, 20)
    assert rh[0] == 2005 and rl[0] == 1995


def test_daily_filters_not_from_unfinished_day_when_range_ends_before_midnight():
    # range 18:00-20:00 of the previous evening: entries start before day d-1 is complete, so the
    # "previous day" ATR/SMA of day d (which include d-1's full daily bar) must not be used.
    def evening(m):
        if 18 * 60 <= m < 20 * 60:
            return (2000, 2005, 1995, 2000) if m % 30 == 0 else (2000, 2001, 1999, 2000)
        if m == 20 * 60 + 30:
            return (2000, 2006, 2000, 2006)          # breakout 20:30
        if m > 20 * 60 + 30:
            return (2006, 2007, 2005.5, 2006.5)
        return (2000, 2001, 1999, 2000)
    D = make_D([evening, evening, evening])
    D["days"]["atr14_prev"] = [10.0, 20.0, 30.0]
    t = E.run(P(range_start=-6, range_end=-4, entry_end=-3.1, exit_time=-3, tp_r=0), D=D)
    assert len(t) == 2                                # days 1 and 2 (their evening is on day 0 / 1)
    for _, r in t.iterrows():
        assert r.atr == {1: 10.0, 2: 20.0}[r.day]


def lower(m):
    o, h, l, c = path_up_tp(m)
    return (o - 100, h - 100, l - 100, c - 100)


def test_window_cache_is_per_dataset():
    D1 = make_D([path_up_tp])
    D2 = make_D([lower])
    E.run(P(), D=D1)                                  # caches windows for D1 without clearing
    *_, rh2, rl2, _ = E._windows(D2, 0, 7, 12, 20)
    assert rh2[0] == 1905 and rl2[0] == 1895


def test_fade_limit_penetration_requirement():
    # path_up_sl: BID high reaches 2006 on the 08:00 bar -> 1.0 through the 2005 sell limit
    D = make_D([path_up_sl])
    assert len(E.run(P(entry_mode=2, limit_pen=0.5), D=D)) == 1
    t = E.run(P(entry_mode=2, limit_pen=0.5), D=D)
    assert abs(t.iloc[0].entry - 2005) < 1e-9                  # still filled at the limit price
    t = E.run(P(entry_mode=2, limit_pen=1.5), D=D)             # 08:00 high is only 1.0 through;
    assert t.iloc[0].t_entry.minute == 1                         # the 08:01 bar (2006.5) fills it
    t = E.run(P(entry_mode=2, limit_pen=1.6), D=D)              # upper limit never traded 1.6 through
    assert (t.dir == -1).sum() == 0
