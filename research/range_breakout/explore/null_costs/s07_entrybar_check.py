"""How often is a trade stopped on its entry bar (engine rule: only SL checked, conservatively), for the
actual breakout side vs the flipped side? (default config, IS; not a new config)"""
import numpy as np, pandas as pd
import common as C, null as N
E = C.E
D = E.load()
p = E.Params()
t = E.run(p, end=E.IS_END, D=D)
f = N.walk(p, t, -t["dir"].values, D)
same_eb = ((t.reason == "sl") & (t.i_exit == t.i_entry))
flip_eb = ((f.reason == 1) & (f.i_exit.values == t.i_entry.values))
print("entry-bar stop-outs: actual", int(same_eb.sum()), " flipped", int(flip_eb.sum()), "of", len(t))
# drop days where either side was stopped on the entry bar and recompute direction info
m = ~(same_eb.values | flip_eb.values)
tb = N.both_ways(p, D=D, end=E.IS_END, trades=t)
d = (tb.R_same - tb.R_flip) / 2
print("dir info all:", round(d.mean(), 4), " excl entry-bar stop days:", round(d[m].mean(), 4),
      " z:", round(d.sum() / np.sqrt((d**2).sum()), 2), round(d[m].sum() / np.sqrt((d[m]**2).sum()), 2))
# time-in-trade and hold
print("median bars held actual:", int((t.i_exit - t.i_entry).median()), " flipped:", int(np.median(f.i_exit.values - t.i_entry.values)))
