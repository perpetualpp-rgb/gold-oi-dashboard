"""Spread-corrected buy-stop trigger (so_sim long_trig=1) vs the engine's ASK trigger. IS only.
1) validation: so_sim(long_trig=0) == engine.run trade by trade on several configs;
2) sweep long_trig x buf_k x exits x timings."""
import sys
import os
import itertools
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config, params_key, zero_cost_D  # noqa
from so_sim import run_so  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))


def validate():
    cfgs = [E.Params(), E.Params(buf_k=0.1), E.Params(sl_k=0.5, tp_r=2.0), E.Params(buf_atr=0.1, sl_ref=1, sl_k=0.5),
            E.Params(**TIMINGS["T2_ldn7-8"]), E.Params(**TIMINGS["T3_ldn8-13"], tp_r=1.0)]
    for p in cfgs:
        a = E.run(p, end=E.IS_END)
        b = run_so(p, long_trig=0)
        same = (len(a) == len(b) and np.allclose(a[["day", "dir", "i_entry", "i_exit"]].values,
                                                  b[["day", "dir", "i_entry", "i_exit"]].values)
                and np.allclose(a.pnl.values, b.pnl.values))
        print("validate", json.dumps({k: v for k, v in p.to_dict().items() if E.Params().to_dict()[k] != v}),
              len(a), len(b), "IDENTICAL" if same else "DIFF")
        assert same


def main():
    D()
    validate()
    rows = []
    EXITS = {"sl1W": dict(sl_k=1.0), "sl0.5W": dict(sl_k=0.5), "sl1W_tp1": dict(sl_k=1.0, tp_r=1.0),
             "sl1W_tp2": dict(sl_k=1.0, tp_r=2.0)}
    for (tn, tm), lt, bk, (en, ex) in itertools.product(TIMINGS.items(), [0, 1], [0, 0.05, 0.1, 0.2],
                                                         EXITS.items()):
        p = E.Params(**tm, **ex, buf_k=bk)
        t = run_so(p, long_trig=lt)
        r = full_summ(t)
        r.update(timing=tn, long_trig=lt, buf_k=bk, exit=en)
        log_config("s08", params_key(p) + f"lt{lt}", r)
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s08_results.csv"), index=False)
    cols = ["timing", "exit", "buf_k", "long_trig", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos", "L_n",
            "L_avg", "S_n", "S_avg", "maxDD_R"]
    print(df[cols].to_string(index=False))
    piv = df.pivot_table(index=["timing", "exit", "buf_k"], columns="long_trig", values="avg_R")
    piv["diff"] = piv[1] - piv[0]
    print(piv.round(4).to_string())
    print("mean improvement from spread-corrected trigger:", round(piv["diff"].mean(), 4),
          "share improved:", round((piv["diff"] > 0).mean(), 3))


if __name__ == "__main__":
    main()
