"""Finalists on IS: by-year, long/short, cost stress (slip 0.10, spread +0.10, both)."""
import numpy as np
import pandas as pd
import common as C
import engine as E

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
D = C.data()
DS = C.cost_stressed(0.10)
FIN = {
    "F0_default": E.Params(),
    "F1_W1_trail2": E.Params(trail_r=2.0),
    "F2_ATR0.75_BE1_trail1.5_x21": E.Params(sl_ref=1, sl_k=0.75, be_r=1.0, trail_r=1.5, exit_time=21.0),
    "F3_ATR1.5_timeexit": E.Params(sl_ref=1, sl_k=1.5),
}
cols = ["n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R", "yrs_pos", "L_n", "L_avg_R", "L_t", "S_n", "S_avg_R", "S_t", "skew"]
rows, yrs = [], {}
for nm, p in FIN.items():
    for cost, pp, DD in (("base", p, D), ("slip0.10", E.Params(**{**p.to_dict(), "slip": 0.10}), D),
                         ("spread+0.10", p, DS), ("both", E.Params(**{**p.to_dict(), "slip": 0.10}), DS)):
        log = not (cost == "base")           # base configs already counted in s02/s05
        if nm == "F0_default" and cost != "base":
            log = True
        t = C.run_is(pp, D=DD, tag=f"s07_{nm}_{cost}", log=log)
        d = C.full_summ(t)
        rows.append(dict(cfg=nm, cost=cost, **{c: d[c] for c in cols}))
        if cost == "base":
            yrs[nm] = t.groupby(t.date.dt.year).R.mean().round(3)
X = pd.DataFrame(rows)
print(X.to_string(index=False))
Y = pd.DataFrame(yrs)
print("\nIS avg_R by year (base costs)")
print(Y.to_string())
X.to_csv(C.OUT + "/s07_finalists_is.csv", index=False)
Y.to_csv(C.OUT + "/s07_finalists_is_years.csv")
