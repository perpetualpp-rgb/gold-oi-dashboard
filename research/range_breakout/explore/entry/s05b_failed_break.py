"""Failed-breakout reversal (Judas swing / turtle soup) sweep with fb_sim, 4 timings. IS only."""
import sys
import os
import itertools
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config, zero_cost_D  # noqa: E402
from fb_sim import run_fb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STOPS = {"ext+0.1W": dict(stop_mode=0, sbuf=0.1), "ext+0.25W": dict(stop_mode=0, sbuf=0.25),
         "fix0.5W": dict(stop_mode=1, stop_k=0.5), "fix1W": dict(stop_mode=1, stop_k=1.0)}
TGTS = {"none": dict(tgt_mode=0), "mid": dict(tgt_mode=1), "opp": dict(tgt_mode=2), "1.5R": dict(tgt_mode=3, tp_r=1.5)}


def main():
    D()
    rows = []
    for (tn, tm), pen, rec, tf, (sn, so), (gn, go) in itertools.product(
            TIMINGS.items(), [0.0, 0.1, 0.2, 0.3, 0.5], [0.0, 0.25], [1, 5, 15, 60], STOPS.items(), TGTS.items()):
        kw = dict(pen=pen, rec=rec, tf=tf, **so, **go)
        t = run_fb(tm, **kw)
        r = full_summ(t)
        r.update(timing=tn, pen=pen, rec=rec, tf=tf, stop=sn, tgt=gn)
        log_config("s05b", tn + json.dumps(kw, sort_keys=True), r)
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s05b_results.csv"), index=False)
    print("configs", len(df), "share avg_R>0", round((df.avg_R > 0).mean(), 3),
          "share t>2", round((df.t_stat > 2).mean(), 3))
    print(df.groupby(["timing", "tgt"])[["avg_R", "t_stat"]].agg(["mean", "max"]).round(3).to_string())
    print(df.groupby(["timing", "stop"])[["avg_R", "t_stat"]].agg(["mean", "max"]).round(3).to_string())
    print(df.groupby(["timing", "pen"])[["avg_R", "t_stat"]].agg(["mean", "max"]).round(3).to_string())
    cols = ["timing", "pen", "rec", "tf", "stop", "tgt", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos",
            "L_avg", "S_avg", "cost_R"]
    print(df[df.n >= 150].sort_values("t_stat", ascending=False).head(20)[cols].to_string(index=False))
    # gross (no spread, no commission, no slip) for a representative subset
    Z = zero_cost_D()
    g = []
    for (tn, tm), pen, (sn, so), (gn, go) in itertools.product(TIMINGS.items(), [0.0, 0.2], STOPS.items(),
                                                                [("mid", dict(tgt_mode=1)), ("none", dict(tgt_mode=0))]):
        kw = dict(pen=pen, rec=0.0, tf=15, **so, **go)
        t = run_fb(tm, commission=0.0, slip=0.0, D=Z, **kw)
        r = full_summ(t)
        r.update(timing=tn, pen=pen, stop=sn, tgt=gn, gross=True)
        log_config("s05b_gross", tn + json.dumps(kw, sort_keys=True), r)
        g.append(r)
    g = pd.DataFrame(g)
    g.to_csv(os.path.join(HERE, "s05b_gross.csv"), index=False)
    print("GROSS (zero spread/commission/slip), tf=15 rec=0")
    print(g[["timing", "pen", "stop", "tgt", "n", "avg_R", "t_stat", "yrs_pos", "L_avg", "S_avg"]].to_string(index=False))


if __name__ == "__main__":
    main()
