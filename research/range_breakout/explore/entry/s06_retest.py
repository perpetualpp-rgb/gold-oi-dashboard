"""Break-then-retest limit entries WITH the break (rt_sim), 4 timings. IS only (+ gross check)."""
import sys
import os
import itertools
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config, zero_cost_D  # noqa: E402
from rt_sim import run_rt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STOPS = {"0.5W": dict(sl_mode=0, sl_k=0.5), "1W": dict(sl_mode=0, sl_k=1.0),
         "opp": dict(sl_mode=1, sbuf=0.0), "mid": dict(sl_mode=2, sbuf=0.0)}


def main():
    D()
    rows = []
    for (tn, tm), pen, off, (sn, so), tp in itertools.product(
            TIMINGS.items(), [0.0, 0.1, 0.2, 0.3, 0.5], [0.1, 0.0, -0.1, -0.25], STOPS.items(), [0.0, 1.5]):
        if off > pen:
            continue
        kw = dict(pen=pen, off=off, tp_r=tp, **so)
        t = run_rt(tm, **kw)
        r = full_summ(t)
        r.update(timing=tn, pen=pen, off=off, stop=sn, tp_r=tp)
        log_config("s06", tn + json.dumps(kw, sort_keys=True), r)
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s06_results.csv"), index=False)
    print("configs", len(df), "share avg_R>0", round((df.avg_R > 0).mean(), 3))
    print(df.groupby(["timing", "stop"])[["avg_R", "t_stat"]].agg(["mean", "max"]).round(3).to_string())
    print(df.groupby(["timing", "off"])[["avg_R", "t_stat"]].agg(["mean", "max"]).round(3).to_string())
    cols = ["timing", "pen", "off", "stop", "tp_r", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos",
            "L_avg", "S_avg", "maxDD_R", "cost_R"]
    print(df[df.n >= 150].sort_values("t_stat", ascending=False).head(20)[cols].to_string(index=False))
    Z = zero_cost_D()
    g = []
    for (tn, tm), pen, off in itertools.product(TIMINGS.items(), [0.1, 0.3], [0.0, -0.25]):
        kw = dict(pen=pen, off=off, sl_mode=0, sl_k=1.0, tp_r=0.0)
        t = run_rt(tm, commission=0.0, slip=0.0, D=Z, **kw)
        r = full_summ(t)
        r.update(timing=tn, pen=pen, off=off)
        log_config("s06_gross", tn + json.dumps(kw, sort_keys=True), r)
        g.append(r)
    g = pd.DataFrame(g)
    print("GROSS, stop 1W, no target")
    print(g[["timing", "pen", "off", "n", "avg_R", "t_stat", "yrs_pos", "L_avg", "S_avg"]].to_string(index=False))
    g.to_csv(os.path.join(HERE, "s06_gross.csv"), index=False)


if __name__ == "__main__":
    main()
