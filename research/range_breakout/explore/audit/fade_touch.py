import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np, pandas as pd
import engine as E
D = E.load()
t = E.run(E.Params(entry_mode=2, tp_r=1.0), end=E.IS_END)
i = t.i_entry.values
pen = np.where(t.dir == -1, D["bh"][i] - t.entry, t.entry - D["al"][i])
print("fade IS fills:", len(t), "penetration quantiles USD", np.percentile(pen, [0, 10, 25, 50]).round(3))
for thr in (0.0, 0.02, 0.05, 0.10):
    s = t[pen >= thr] if thr > 0 else t
    print(f"fills with pen>={thr}: {len(s)}  avgR (fills kept, same exits) {s.R.mean():+.4f}  vs touch-only fills avgR {t[pen < thr].R.mean() if thr>0 else float('nan'):+.4f}")
# reversal: how often the same-bar reversal is used now
t2 = E.run(E.Params(max_trades=2), end=E.IS_END)
g = t2.groupby("day")
two = g.filter(lambda x: len(x) == 2)
same = two.groupby("day").apply(lambda x: x.i_entry.iloc[1] == x.i_exit.iloc[0]).sum()
print("max_trades=2 IS: days with 2 trades", two.day.nunique(), "of which reversal in the same bar", same)
# skipped days where both levels were hit in the same M1 bar (mode 0 default)
i_rs, i_re, i_ee, i_ex, rh, rl, valid = E._windows(D, 0, 7, 12, 20)
cnt = 0
for d in np.where(valid & (D["days"].index <= E.IS_END))[0]:
    a, b = i_re[d], i_ee[d]
    hl = D["ah"][a:b] >= rh[d]; hs = D["bl"][a:b] <= rl[d]
    fl = np.argmax(hl) if hl.any() else 10**9; fs = np.argmax(hs) if hs.any() else 10**9
    if fl == fs and fl < 10**9:
        cnt += 1
print("IS days skipped because both edges hit in the first-touch bar:", cnt)
