import sys, os, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import numpy as np, pandas as pd
import engine as E
spec = importlib.util.spec_from_file_location("engine_old2", sys.argv[1])
O = importlib.util.module_from_spec(spec); spec.loader.exec_module(O)
D = E.load(); Dold = {k: v for k, v in D.items() if k != "_win_cache"}
for lab, p in (("trend200", E.Params(trend=200)),
               ("evening rng -6..-2, trend20, min_w_atr .3", E.Params(range_start=-6, range_end=-2, entry_end=3, exit_time=6, trend=20, min_w_atr=0.3))):
    for nm, mod, dd in (("OLD", O, Dold), ("NEW", E, D)):
        t = mod.run(p, end=E.IS_END, D=dd)
        s = E.stats(t); L = E.stats(t[t.dir == 1]); S = E.stats(t[t.dir == -1])
        print(f"{nm} {lab}: IS n={s['n']} avgR={s['avg_R']:+.4f} t={s['t_stat']:+.2f} | long n={L['n']} short n={S['n']} | 2014 trades long/short: "
              f"{((t.date.dt.year == 2014) & (t.dir == 1)).sum()}/{((t.date.dt.year == 2014) & (t.dir == -1)).sum()}")
