"""VAL (2022-01-01..2023-12-31) for the finalists. 6 VAL configs: F0-F3 net + 2 zero-cost diagnostics.
Never touches 2024+ (end=E.VAL_END)."""
import numpy as np
import pandas as pd
import common as C
import engine as E

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
D = C.data()
D0 = C.cost_stressed(0.0)
for k in ("ao", "ah", "al", "ac"):
    D0[k] = D["b" + k[1]].copy()
VAL = {
    "F0_default": (E.Params(), D),
    "F1_W1_trail2": (E.Params(trail_r=2.0), D),
    "F2_ATR0.75_BE1_trail1.5_x21": (E.Params(sl_ref=1, sl_k=0.75, be_r=1.0, trail_r=1.5, exit_time=21.0), D),
    "F3_ATR1.5_timeexit": (E.Params(sl_ref=1, sl_k=1.5), D),
    "G0_default_GROSS": (E.Params(commission=0.0, slip=0.0), D0),
    "G3_ATR1.5_timeexit_GROSS": (E.Params(sl_ref=1, sl_k=1.5, commission=0.0, slip=0.0), D0),
}
cols = ["n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R", "L_n", "L_avg_R", "L_t", "S_n", "S_avg_R", "S_t", "skew"]
rows = []
for nm, (p, DD) in VAL.items():
    t = C.run_val(p, D=DD, tag=f"s08_{nm}")
    assert t.date.max() <= pd.Timestamp(E.VAL_END) and t.date.min() >= pd.Timestamp("2022-01-01")
    d = C.full_summ(t, years=[2022, 2023])
    y = t.groupby(t.date.dt.year).R.mean().round(3)
    rows.append(dict(cfg=nm, **{c: d[c] for c in cols}, y2022=y.get(2022), y2023=y.get(2023)))
X = pd.DataFrame(rows)
print(X.to_string(index=False))
X.to_csv(C.OUT + "/s08_val.csv", index=False)
