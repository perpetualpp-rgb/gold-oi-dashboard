"""Stop entries (entry_mode 0) with buffers, 4 exit geometries, 4 session timings. IS only."""
import sys
import os
import itertools
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, eval_is, md  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXITS = {
    "sl1W": dict(sl_ref=0, sl_k=1.0),
    "slOpp": dict(sl_ref=2, sl_k=1.0),
    "sl0.5W": dict(sl_ref=0, sl_k=0.5),
    "sl1W_tp1": dict(sl_ref=0, sl_k=1.0, tp_r=1.0),
}
BUF_K = [0, 0.05, 0.1, 0.2, 0.3, 0.5]
BUF_ATR = [0, 0.05, 0.1, 0.2]


def main():
    D()
    rows = []
    for (tn, tm), (en, ex), bk, ba in itertools.product(TIMINGS.items(), EXITS.items(), BUF_K, BUF_ATR):
        p = E.Params(**tm, **ex, entry_mode=0, buf_k=bk, buf_atr=ba)
        r, _ = eval_is("s01", p)
        r.update(timing=tn, exit=en, buf_k=bk, buf_atr=ba)
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s01_results.csv"), index=False)
    out = []
    cols = ["buf_k", "buf_atr", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos", "L_avg", "S_avg", "maxDD_R",
            "cost_R"]
    for tn in TIMINGS:
        for en in EXITS:
            sub = df[(df.timing == tn) & (df.exit == en)]
            out.append(f"\n### {tn} / {en}\n")
            out.append(md(sub[cols], index=False))
            piv = sub.pivot(index="buf_k", columns="buf_atr", values="avg_R")
            out.append("\navg_R pivot (rows buf_k, cols buf_atr)\n")
            out.append(md(piv.round(4)))
    txt = "\n".join(out)
    open(os.path.join(HERE, "s01_stop_buffers_tables.txt"), "w").write(txt)
    # compact summary
    print(df.groupby(["timing", "exit"])[["avg_R", "t_stat"]].agg(["mean", "max"]).round(3).to_string())
    top = df[df.n >= 150].sort_values("t_stat", ascending=False).head(25)
    print(top[["timing", "exit"] + cols].to_string(index=False))


if __name__ == "__main__":
    main()
