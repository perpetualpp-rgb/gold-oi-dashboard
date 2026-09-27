"""Plateau checks around the two best IS cells found on this axis. IS only.
C: break-then-retest (rt_sim) at T0 (and same grid at T1);  D: failed-break reversal (fb_sim) at T3."""
import sys
import os
import itertools
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config  # noqa
from rt_sim import run_rt  # noqa
from fb_sim import run_fb  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    D()
    rows = []
    for tn, pen, off, sk in itertools.product(["T0_asia0-7", "T1_asia0-8"], [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
                                              [0.05, 0.0, -0.05, -0.1, -0.15], [0.75, 1.0, 1.25]):
        kw = dict(pen=pen, off=off, sl_mode=0, sl_k=sk, tp_r=0.0)
        t = run_rt(TIMINGS[tn], **kw)
        r = full_summ(t)
        r.update(timing=tn, **kw)
        log_config("s10_rt", tn + json.dumps(kw, sort_keys=True), r)
        rows.append(r)
    C = pd.DataFrame(rows)
    C.to_csv(os.path.join(HERE, "s10_retest_plateau.csv"), index=False)
    for tn in ["T0_asia0-7", "T1_asia0-8"]:
        for sk in [0.75, 1.0, 1.25]:
            s = C[(C.timing == tn) & (C.sl_k == sk)]
            print(tn, "retest sl_k", sk, "avg_R rows pen, cols off")
            print(s.pivot(index="pen", columns="off", values="avg_R").round(3).to_string())
    s = C[(C.timing == "T0_asia0-7") & (C.sl_k == 1.0)]
    print(s.pivot(index="pen", columns="off", values="t_stat").round(2).to_string())
    print(s.pivot(index="pen", columns="off", values="yrs_pos").to_string())
    rows = []
    for pen, tf, sb, tg, rec in itertools.product([0.3, 0.4, 0.5, 0.6, 0.75], [30, 60], [0.05, 0.1, 0.2],
                                                  ["1R", "1.5R", "2R", "opp"], [0.0, 0.1]):
        kw = dict(pen=pen, tf=tf, stop_mode=0, sbuf=sb, rec=rec,
                  tgt_mode=2 if tg == "opp" else 3, tp_r=0.0 if tg == "opp" else float(tg[:-1]))
        t = run_fb(TIMINGS["T3_ldn8-13"], **kw)
        r = full_summ(t)
        r.update(tg=tg, **kw)
        log_config("s10_fb", "T3" + json.dumps(kw, sort_keys=True), r)
        rows.append(r)
    Dd = pd.DataFrame(rows)
    Dd.to_csv(os.path.join(HERE, "s10_fb_plateau.csv"), index=False)
    for tf in (30, 60):
        s = Dd[(Dd.tf == tf) & (Dd.rec == 0) & (Dd.sbuf == 0.1)]
        print("T3 failed-break tf", tf, "sbuf 0.1 rec 0: avg_R rows pen cols target")
        print(s.pivot(index="pen", columns="tg", values="avg_R").round(3).to_string())
        print(s.pivot(index="pen", columns="tg", values="n").to_string())
    print("T3 failed-break plateau grid: share avg_R>0", round((Dd.avg_R > 0).mean(), 3), "median avg_R",
          round(Dd.avg_R.median(), 4), "max t", Dd.t_stat.max())


if __name__ == "__main__":
    main()
