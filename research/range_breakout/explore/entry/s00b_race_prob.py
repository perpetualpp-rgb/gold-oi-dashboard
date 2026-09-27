"""Probability view of the race diagnostic: after the first touch of a range edge, P(price goes +b*W beyond
before coming back a*W) among resolved cases, vs the driftless random-walk value a/(a+b). IS only, gross."""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, log_config  # noqa
from s00_race import race  # noqa

A = np.array([0.25, 0.5, 1.0])
B = np.array([0.25, 0.5, 1.0])
Dd = D()
days = Dd["days"].index
isd = (days >= pd.Timestamp("2014-01-01")) & (days <= pd.Timestamp(E.IS_END))
rows = []
for tn, tm in TIMINGS.items():
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, exc = E._windows_full(Dd, tm["range_start"], tm["range_end"],
                                                                  tm["entry_end"], tm["exit_time"])
    ok = valid & isd & ~exc
    res, dirn, ext = race(Dd["bh"], Dd["bl"], Dd["bc"], Dd["bo"], i_re.astype(np.int64), i_ee.astype(np.int64),
                          i_ex.astype(np.int64), np.nan_to_num(rh), np.nan_to_num(rl), ok, 0.0, A, B)
    sel = dirn != 0
    for ia, a in enumerate(A):
        for ib, b in enumerate(B):
            x = res[sel, ia, ib]
            win = (x == b).sum() + 0.5 * (x == 0.5 * (b - a)).sum() * (a != b)
            loss = (x == -a).sum() + 0.5 * (x == 0.5 * (b - a)).sum() * (a != b)
            if a == b:
                win = (x == b).sum() + 0.5 * (x == 0).sum() * 0   # ties impossible to separate from time exits
                loss = (x == -a).sum()
            p = win / (win + loss)
            se = np.sqrt(p * (1 - p) / (win + loss))
            rows.append(dict(timing=tn, back_a=a, beyond_b=b, resolved=int(win + loss), p_beyond_first=round(p, 3),
                             rw=round(a / (a + b), 3), z=round((p - a / (a + b)) / se, 1),
                             W_med=round(float(np.median((rh - rl)[sel])), 2)))
df = pd.DataFrame(rows)
df.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "s00b_race_prob.csv"), index=False)
print(df.to_string(index=False))
