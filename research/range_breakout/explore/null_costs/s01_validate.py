"""Validate that the null re-walker reproduces engine.run exactly when the direction is not randomised.
IS+VAL only (end = VAL_END). These runs are validation of code, not strategy configs."""
import time
import numpy as np
import null as N
E = N.E

D = E.load()
cases = {
    "default": E.Params(),
    "sl0.5_tp2": E.Params(sl_k=0.5, tp_r=2.0),
    "tp1": E.Params(tp_r=1.0),
    "be1_trail1": E.Params(be_r=1.0, trail_r=1.0),
    "trail0.5": E.Params(trail_r=0.5),
    "max_trades2": E.Params(max_trades=2),
    "max2_tp1.5": E.Params(max_trades=2, tp_r=1.5, sl_k=0.7),
    "confirm15": E.Params(entry_mode=1, confirm_tf=15),
    "confirm5_max2": E.Params(entry_mode=1, confirm_tf=5, max_trades=2),
    "fade_tp1": E.Params(entry_mode=2, tp_r=1.0),
    "fade_atr_pen": E.Params(entry_mode=2, sl_ref=1, sl_k=0.5, tp_r=1.5, limit_pen=0.05),
    "atr_stop": E.Params(sl_ref=1, sl_k=0.5, tp_r=2.0),
    "opp_edge": E.Params(sl_ref=2, buf_k=0.1),
    "trend200": E.Params(trend=200, max_w_atr=0.8),
    "evening": E.Params(range_start=-6, range_end=-2.5, entry_end=3, exit_time=8),
    "exit2154": E.Params(exit_time=21.9),
    "ny": E.Params(range_start=7, range_end=13.5, entry_end=17, exit_time=21.5, tp_r=1.5),
    "costs0": E.Params(commission=0, slip=0),
}
t0 = time.time()
allok = True
for k, p in cases.items():
    n, mx, bad = N.validate(p, D=D)
    allok &= bad == 0
    print(f"{k:16s} n={n:5d}  max|dR|={mx:.2e}  mismatches={bad}")
# a spread-scaled dataset as well
D2 = dict(D)
D2.pop("_win_cache", None)
for c in "ohlc":
    D2["a" + c] = D["b" + c] + 2.0 * (D["a" + c] - D["b" + c])
n, mx, bad = N.validate(E.Params(sl_k=0.5, tp_r=2.0), D=D2)
allok &= bad == 0
print(f"{'spread x2':16s} n={n:5d}  max|dR|={mx:.2e}  mismatches={bad}")
print("ALL OK" if allok else "MISMATCH FOUND", f"({time.time()-t0:.1f}s)")
