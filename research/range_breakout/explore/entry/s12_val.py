"""VAL (2022-01-01..2023-12-31) check of the finalists. 7 configs in total. Never touches 2024+:
engine runs use end=VAL_END, custom sims start=2022-01-01 end=VAL_END."""
import sys
import os
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config, zero_cost_D  # noqa
from rt_sim import run_rt  # noqa
from fb_sim import run_fb  # noqa
from s11_finalists_is import FIN  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
VS, VE = "2022-01-01", E.VAL_END


def main():
    D()
    rows = []
    for name, (kind, tn, kw) in FIN.items():
        tm = TIMINGS[tn]
        if kind == "rt":
            t = run_rt(tm, start=VS, end=VE, **kw)
        elif kind == "fb":
            t = run_fb(tm, start=VS, end=VE, **kw)
        else:
            t = E.run(E.Params(**tm, **kw), end=VE)
            t = t[t.date > E.IS_END]
        assert t.date.max() <= pd.Timestamp(VE)
        r = full_summ(t)
        log_config("s12_VAL", name, r)
        rows.append(dict(name=name, **r))
        print(name, E.by_year(t).to_dict())
    # gross (zero spread / commission / slip): does the with-the-break gross edge persist in VAL?
    Z = zero_cost_D()
    for name, kw in (("GROSS stop default T0", dict()), ("GROSS fade sl1W tp1R T0", dict(entry_mode=2, tp_r=1.0))):
        p = E.Params(**kw, commission=0.0, slip=0.0)
        t = E.run(p, end=VE, D=Z)
        t = t[t.date > E.IS_END]
        r = full_summ(t)
        log_config("s12_VAL", name, r)
        rows.append(dict(name=name, **r))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s12_val_results.csv"), index=False)
    print(df[["name", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos", "trades_per_year", "maxDD_R",
              "L_n", "L_avg", "S_n", "S_avg"]].to_string(index=False))
    print("VAL configs checked:", len(df))


if __name__ == "__main__":
    main()
