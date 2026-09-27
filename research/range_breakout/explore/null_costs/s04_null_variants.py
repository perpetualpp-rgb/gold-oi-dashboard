"""Null tests for the cost-study base configs at default costs and frictionless (spread_k=0, comm 0,
slip 0). Same configs as s03 (not new configs; VAL already counted there)."""
import numpy as np
import pandas as pd
import common as C
import null as N

E = C.E
D = E.load()
D0 = C.spread_scaled(D, 0.0)
BASES = {
    "default": E.Params(),
    "tight_sl0.5_tp2": E.Params(sl_k=0.5, tp_r=2.0),
    "fade_tp1": E.Params(entry_mode=2, tp_r=1.0),
    "wide_sl2": E.Params(sl_k=2.0),
}
rows, dirrows = [], []
for name, p in BASES.items():
    for lab, pp, Dx in (("default_costs", p, D),
                        ("frictionless", E.Params(**{**p.to_dict(), "commission": 0.0, "slip": 0.0}), D0)):
        res = N.null_test(pp, n_perm=10000, seed=11, D=Dx)
        rows += N.summary_rows(res, f"{name} | {lab}")
        for per in ("IS", "VAL"):
            b = res[per]
            for side in ("long_trades", "short_trades"):
                x = b[side]
                dirrows.append(dict(config=name, costs=lab, period=per,
                                    break_dir="up (long)" if side == "long_trades" else "down (short)",
                                    n=x["n"], R_breakout_dir=x["actual"], R_opposite=x["opposite"],
                                    diff=x["diff"], t_diff=x["t_diff"]))
df = pd.DataFrame(rows)
dd = pd.DataFrame(dirrows)
print(C.fmt_table(df))
print()
print(C.fmt_table(dd.round(4)))
df.to_csv(C.os.path.join(C.HERE, "out_null_variants.csv"), index=False)
dd.to_csv(C.os.path.join(C.HERE, "out_null_variants_bydir.csv"), index=False)

# random-time null, default at both cost levels
for lab, pp, Dx in (("default_costs", E.Params(), D), ("frictionless", E.Params(commission=0.0, slip=0.0), D0)):
    rt = N.null_time_test(pp, n_perm=200, seed=3, D=Dx)
    print("random-time null", lab, {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in rt.items()})
