"""Synthetic tests for null.py. Run: cd explore/null_costs && python3 -m pytest -q test_null.py"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import test_engine as TE  # noqa: E402
import null as N  # noqa: E402

E = N.E


def test_same_direction_reproduces_engine():
    D = TE.make_D([TE.path_up_tp, TE.path_up_sl, TE.path_time_exit])
    for p in (TE.P(), TE.P(tp_r=0), TE.P(tp_r=0, slip=0.05, commission=0.07)):
        t = E.run(p, D=D)
        w = N.walk(p, t, t["dir"].values, D)
        assert np.allclose(w["R"].values, t["R"].values, atol=1e-12)


def test_flip_of_breakout_long_is_short_at_bid_minus_slip():
    # path_up_tp: buy stop at 2005 (ASK), spread 0.2 -> flipped short sells BID 2004.8 - slip
    D = TE.make_D([TE.path_up_tp])
    p = TE.P(tp_r=0, slip=0.05, commission=0.0)
    t = E.run(p, D=D)
    assert t.iloc[0].dir == 1 and abs(t.iloc[0].entry - 2005.05) < 1e-9
    px = N.entry_prices(p, t, -t["dir"].values, D)
    assert abs(px[0] - (2005.0 - TE.SPREAD - 0.05)) < 1e-9
    # short with risk 10 from 2004.75: stop at 2014.75, later bars at 2030 -> stopped (gap fill at ASK open)
    w = N.walk(p, t, -t["dir"].values, D)
    assert w.iloc[0].reason == 1
    assert abs(w.iloc[0].exit - (2030 + TE.SPREAD + 0.05)) < 1e-9


def test_fade_flip_pays_spread_but_no_entry_slip():
    D = TE.make_D([TE.path_up_sl])
    p = TE.P(entry_mode=2, tp_r=1.0, slip=0.05)
    t = E.run(p, D=D)
    assert t.iloc[0].dir == -1 and abs(t.iloc[0].entry - 2005) < 1e-9
    px = N.entry_prices(p, t, -t["dir"].values, D)
    assert abs(px[0] - (2005 + TE.SPREAD)) < 1e-9


def test_null_test_rejects_holdout():
    try:
        N.null_test(E.Params(), end="2024-06-30", D=TE.make_D([TE.path_up_tp]))
    except ValueError:
        return
    raise AssertionError("null_test must refuse end dates in the holdout")
