import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import pandas as pd
import engine as E
pd.set_option("display.width", 200)
D = E.load()
p = E.Params()
sp = E.split(p)
for k, v in sp.items():
    print(k, v)
t = E.run(p, end=E.VAL_END)
for lab, sub in (("IS", t[t.date <= E.IS_END]), ("VAL", t[t.date > E.IS_END])):
    for d, nm in ((1, "long"), (-1, "short")):
        s = E.stats(sub[sub.dir == d])
        print(lab, nm, {k: s[k] for k in ("n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R")})
print(E.by_year(t).to_string())
