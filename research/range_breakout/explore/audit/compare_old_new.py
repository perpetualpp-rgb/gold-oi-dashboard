"""Old (HEAD) vs fixed engine on IS/VAL, plus cost sensitivity. Never runs past VAL_END."""
import sys, os, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import numpy as np, pandas as pd
import engine as E
old_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("engine_old", old_path)
O = importlib.util.module_from_spec(spec); spec.loader.exec_module(O)
D = E.load()
Dold = {k: v for k, v in D.items() if k != "_win_cache"}

def row(t, lab):
    out = {}
    for name, sub in (("IS", t[t.date <= E.IS_END]), ("VAL", t[(t.date > E.IS_END)])):
        s = E.stats(sub)
        out[name] = f"n={s['n']} avgR={s['avg_R']:+.4f} t={s['t_stat']:+.2f} PF={s['PF']:.3f} DD={s['maxDD_R']}"
    return f"{lab:34s} IS: {out['IS']}\n{'':34s} VAL: {out['VAL']}"

cfgs = {
    "default": E.Params(),
    "tp2": E.Params(tp_r=2.0),
    "max_trades2": E.Params(max_trades=2),
    "max_trades2_sl_opp": E.Params(max_trades=2, sl_ref=2),
    "trail1": E.Params(trail_r=1.0, be_r=1.0),
    "confirm15": E.Params(entry_mode=1, confirm_tf=15),
    "confirm15_mt2": E.Params(entry_mode=1, confirm_tf=15, max_trades=2),
    "fade_tp1": E.Params(entry_mode=2, tp_r=1.0),
    "trend50": E.Params(trend=50),
    "exit_21_59": E.Params(exit_time=21.9),
}
n = 0
for lab, p in cfgs.items():
    to = O.run(p, end=E.VAL_END, D=Dold); tn = E.run(p, end=E.VAL_END, D=D); n += 1
    # old engine used the global stats; recompute both with the fixed stats for a like-for-like view
    print(row(to, "OLD " + lab)); print(row(tn, "NEW " + lab))
    diff = len(tn) - len(to)
    print(f"{'':34s} trade count change {diff:+d}; old trades exiting on a later day: "
          f"{(D['lmin'][to.i_exit.values] // 1440 != D['lmin'][to.i_entry.values] // 1440).sum()}, new: "
          f"{(D['lmin'][tn.i_exit.values] // 1440 != D['lmin'][tn.i_entry.values] // 1440).sum()}")
print("configs:", n)

# cost sensitivity on default (new engine)
print("\nCOST SENSITIVITY (default Params, IS / VAL, longs|shorts IS)")
for slip in (0.05, 0.10, 0.20):
    for extra in (0.0, 0.10, 0.20):
        D2 = dict(D); D2.pop("_win_cache", None)
        if extra:
            for c in ("ao", "ah", "al", "ac"):
                D2[c] = D[c] + extra
        t = E.run(E.Params(slip=slip), end=E.VAL_END, D=D2)
        i = t[t.date <= E.IS_END]; v = t[t.date > E.IS_END]
        si, sv = E.stats(i), E.stats(v)
        sl_, ss_ = E.stats(i[i.dir == 1]), E.stats(i[i.dir == -1])
        print(f"slip={slip:.2f} spread+{extra:.2f}: IS avgR {si['avg_R']:+.4f} t {si['t_stat']:+.2f} | VAL avgR {sv['avg_R']:+.4f} t {sv['t_stat']:+.2f} | IS L {sl_['avg_R']:+.4f} S {ss_['avg_R']:+.4f}")
# median cost per trade in R
t = E.run(E.Params(), end=E.VAL_END, D=D)
i = t[t.date <= E.IS_END]
spr = (D["ao"] - D["bo"])[i.i_entry.values]
cost_usd = spr + 2 * 0.05 + 0.07
print("IS default: median risk USD", round(i.risk.median(), 2), "median round-trip cost USD", round(np.median(cost_usd), 3),
      "=> median cost in R", round(np.median(cost_usd / i.risk.values), 4), "mean", round(np.mean(cost_usd / i.risk.values), 4))
