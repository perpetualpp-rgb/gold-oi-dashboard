"""FADE (entry_mode 2): limit order against the break at range edge +/- buffer.
sl_k x tp_r x buf_k x buf_atr on 4 timings (range-width stops), plus ATR stops on T0. IS only."""
import sys
import os
import itertools
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, eval_is, md  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SL_K = [0.25, 0.5, 0.75, 1.0]
TP_R = [0, 0.5, 1.0, 1.5, 2.0]
BUF_K = [0, 0.05, 0.1, 0.2, 0.3, 0.5]
BUF_ATR = [0, 0.1]


def main():
    D()
    rows = []
    for (tn, tm), sk, tp, bk, ba in itertools.product(TIMINGS.items(), SL_K, TP_R, BUF_K, BUF_ATR):
        p = E.Params(**tm, entry_mode=2, sl_ref=0, sl_k=sk, tp_r=tp, buf_k=bk, buf_atr=ba)
        r, _ = eval_is("s04", p)
        r.update(timing=tn, sl="W", sl_k=sk, tp_r=tp, buf_k=bk, buf_atr=ba)
        rows.append(r)
    tm = TIMINGS["T0_asia0-7"]
    for sk, tp, bk in itertools.product([0.1, 0.2, 0.3, 0.5], [0.5, 1.0, 2.0], [0, 0.1, 0.3]):
        p = E.Params(**tm, entry_mode=2, sl_ref=1, sl_k=sk, tp_r=tp, buf_k=bk)
        r, _ = eval_is("s04", p)
        r.update(timing="T0_asia0-7", sl="ATR", sl_k=sk, tp_r=tp, buf_k=bk, buf_atr=0)
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s04_results.csv"), index=False)
    cols = ["sl", "sl_k", "tp_r", "buf_k", "buf_atr", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos",
            "L_avg", "S_avg", "maxDD_R", "cost_R"]
    out = []
    for tn in TIMINGS:
        sub = df[df.timing == tn]
        out.append(f"\n### {tn}\n")
        out.append(md(sub[cols], index=False))
    open(os.path.join(HERE, "s04_fade_tables.txt"), "w").write("\n".join(out))
    print(df.groupby(["timing", "sl"])[["avg_R", "t_stat"]].agg(["mean", "max", "min"]).round(3).to_string())
    print("share of fade configs with avg_R>0:", (df.avg_R > 0).mean().round(3))
    for tn in TIMINGS:
        s = df[(df.timing == tn) & (df.sl == "W") & (df.buf_atr == 0) & (df.buf_k == 0)]
        print(tn, "buf 0: avg_R rows sl_k, cols tp_r")
        print(s.pivot(index="sl_k", columns="tp_r", values="avg_R").round(3).to_string())
        s = df[(df.timing == tn) & (df.sl == "W") & (df.buf_atr == 0) & (df.sl_k == 0.5)]
        print(tn, "sl_k 0.5: avg_R rows buf_k, cols tp_r")
        print(s.pivot(index="buf_k", columns="tp_r", values="avg_R").round(3).to_string())
    top = df[df.n >= 150].sort_values("t_stat", ascending=False).head(20)
    print(top[["timing"] + cols].to_string(index=False))


if __name__ == "__main__":
    main()
