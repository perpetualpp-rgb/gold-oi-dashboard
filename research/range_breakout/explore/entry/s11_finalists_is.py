"""IS detail for the finalists: by-year, long/short, cost stress (slip 0.10 and spread +0.10), limit fill
with 0.05 USD penetration, and the same rule at the other timings. IS only."""
import sys
import os
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, full_summ, log_config, wide_spread_D  # noqa
from rt_sim import run_rt  # noqa
from fb_sim import run_fb  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))

FIN = {
    "C_retest_T0": ("rt", "T0_asia0-7", dict(pen=0.3, off=0.0, sl_mode=0, sl_k=1.0, tp_r=0.0)),
    "D_failbrk_T3": ("fb", "T3_ldn8-13", dict(pen=0.5, rec=0.0, tf=60, stop_mode=0, sbuf=0.1, tgt_mode=3, tp_r=1.5)),
    "B_stop_buf0.05_T0": ("eng", "T0_asia0-7", dict(buf_k=0.05)),
    "F_fade_T0": ("eng", "T0_asia0-7", dict(entry_mode=2, sl_k=1.0, tp_r=1.0)),
    "G_failbrk_T0": ("fb", "T0_asia0-7", dict(pen=0.1, rec=0.0, tf=15, stop_mode=0, sbuf=0.1, tgt_mode=1)),
}


def run_any(kind, timing, kw, D_=None, slip=0.05, **extra):
    tm = TIMINGS[timing]
    if kind == "rt":
        return run_rt(tm, slip=slip, D=D_, **kw, **extra)
    if kind == "fb":
        return run_fb(tm, slip=slip, D=D_, **kw)
    return E.run(E.Params(**tm, **kw, slip=slip), end=E.IS_END, D=D_)


def main():
    Dn = D()
    Wd = wide_spread_D(0.10)
    rows = []
    for name, (kind, tn, kw) in FIN.items():
        t = run_any(kind, tn, kw)
        r = full_summ(t)
        print(f"\n== {name} {kind} {tn} {json.dumps(kw)}")
        print("IS", {k: r[k] for k in ("n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos", "trades_per_year",
                                       "maxDD_R", "L_n", "L_avg", "L_t", "S_n", "S_avg", "S_t")})
        print(E.by_year(t).T.to_string())
        rows.append(dict(name=name, variant="base", **r))
        for vn, kws in (("slip0.10", dict(slip=0.10)), ("spread+0.10", dict(D_=Wd)),
                        ("slip0.10+spread0.10", dict(slip=0.10, D_=Wd))):
            tt = run_any(kind, tn, kw, **kws)
            rr = full_summ(tt)
            log_config("s11_stress", name + vn, rr)
            rows.append(dict(name=name, variant=vn, **rr))
        if kind == "rt":
            tt = run_any(kind, tn, kw, lpen=0.05)
            rr = full_summ(tt)
            log_config("s11_stress", name + "lpen0.05", rr)
            rows.append(dict(name=name, variant="limit pen 0.05", **rr))
        for tn2 in TIMINGS:
            if tn2 == tn:
                continue
            tt = run_any(kind, tn2, kw)
            rr = full_summ(tt)
            log_config("s11_timing", name + tn2, rr)
            rows.append(dict(name=name, variant="timing " + tn2, **rr))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s11_results.csv"), index=False)
    print(df[["name", "variant", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos", "L_avg", "S_avg",
              "maxDD_R"]].to_string(index=False))


if __name__ == "__main__":
    main()
