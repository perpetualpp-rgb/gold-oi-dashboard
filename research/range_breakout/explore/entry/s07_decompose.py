"""Gross edge vs costs for the main entry mechanics (engine.run on a zero-spread copy with commission=0,
slip=0), plus a cost stress (slip 0.10, spread +0.10). IS only. Also gross/net by range-width quintile
for the default stop entry (diagnostic: costs are ~fixed USD, the gross edge scales with W)."""
import sys
import os
import itertools
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config, zero_cost_D, wide_spread_D, md, params_key  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
MECH = {
    "stop buf0": dict(entry_mode=0),
    "stop buf_k0.1": dict(entry_mode=0, buf_k=0.1),
    "stop buf_k0.3": dict(entry_mode=0, buf_k=0.3),
    "stop buf_atr0.1": dict(entry_mode=0, buf_atr=0.1),
    "stop slOpp": dict(entry_mode=0, sl_ref=2),
    "confirm M15": dict(entry_mode=1, confirm_tf=15),
    "confirm M60": dict(entry_mode=1, confirm_tf=60),
    "stop&reverse": dict(entry_mode=0, max_trades=2),
    "fade sl1W tp1R": dict(entry_mode=2, sl_k=1.0, tp_r=1.0),
    "fade sl0.5W tp=mid": dict(entry_mode=2, sl_k=0.5, tp_r=1.0),
    "fade sl0.25W tp=mid": dict(entry_mode=2, sl_k=0.25, tp_r=2.0),
}


def main():
    Dn = D()
    Z = zero_cost_D()
    Wd = wide_spread_D(0.10)
    rows = []
    for (tn, tm), (mn, mk) in itertools.product(TIMINGS.items(), MECH.items()):
        p = E.Params(**tm, **mk)
        net = full_summ(E.run(p, end=E.IS_END, D=Dn))
        gp = E.Params(**{**p.to_dict(), "commission": 0.0, "slip": 0.0})
        gross = full_summ(E.run(gp, end=E.IS_END, D=Z))
        sp = E.Params(**{**p.to_dict(), "slip": 0.10})
        stress = full_summ(E.run(sp, end=E.IS_END, D=Wd))
        for tag, r in (("net", net), ("gross", gross), ("stress", stress)):
            log_config("s07_" + tag, params_key(p), r)
        rows.append(dict(timing=tn, mech=mn, n=int(net["n"]), gross_R=gross["avg_R"], gross_t=gross["t_stat"],
                         gross_L=gross["L_avg"], gross_S=gross["S_avg"], net_R=net["avg_R"], net_t=net["t_stat"],
                         cost_R=round(gross["avg_R"] - net["avg_R"], 4), stress_R=stress["avg_R"],
                         net_yrs=net["yrs_pos"]))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s07_results.csv"), index=False)
    print(df.to_string(index=False))
    open(os.path.join(HERE, "s07_decompose_tables.txt"), "w").write(md(df, index=False))
    # width quintiles for the default stop entry, T0
    for tn in ("T0_asia0-7", "T1_asia0-8"):
        p = E.Params(**TIMINGS[tn])
        tn_ = E.run(p, end=E.IS_END, D=Dn)
        tg = E.run(E.Params(**{**p.to_dict(), "commission": 0.0, "slip": 0.0}), end=E.IS_END, D=Z)
        m = tn_.merge(tg[["day", "dir", "R"]], on=["day", "dir"], suffixes=("", "_g"))
        m["q"] = pd.qcut(m["width"], 5)
        g = m.groupby("q", observed=True).agg(n=("R", "size"), W_med=("width", "median"), gross_R=("R_g", "mean"),
                                              net_R=("R", "mean"))
        g["cost_R"] = g.gross_R - g.net_R
        print(tn, "default stop entry by range-width quintile (USD)")
        print(g.round(3).to_string())


if __name__ == "__main__":
    main()
