"""Bar-close confirmation entries (entry_mode 1) with buffers, 3 exit geometries, 4 timings. IS only."""
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
    "sl1W_tp1": dict(sl_ref=0, sl_k=1.0, tp_r=1.0),
}
TF = [5, 15, 30, 60]
BUF_K = [0, 0.1, 0.2, 0.3]
BUF_ATR = [0, 0.1]


def main():
    D()
    rows = []
    for (tn, tm), (en, ex), tf, bk, ba in itertools.product(TIMINGS.items(), EXITS.items(), TF, BUF_K, BUF_ATR):
        p = E.Params(**tm, **ex, entry_mode=1, confirm_tf=tf, buf_k=bk, buf_atr=ba)
        r, _ = eval_is("s02", p)
        r.update(timing=tn, exit=en, tf=tf, buf_k=bk, buf_atr=ba)
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s02_results.csv"), index=False)
    cols = ["tf", "buf_k", "buf_atr", "n", "avg_R", "t_stat", "PF", "win_rate", "yrs_pos", "L_avg", "S_avg",
            "maxDD_R", "cost_R"]
    out = []
    for tn in TIMINGS:
        for en in EXITS:
            sub = df[(df.timing == tn) & (df.exit == en)]
            out.append(f"\n### {tn} / {en}\n")
            out.append(md(sub[cols], index=False))
    open(os.path.join(HERE, "s02_confirm_tables.txt"), "w").write("\n".join(out))
    print(df.groupby(["timing", "exit"])[["avg_R", "t_stat"]].agg(["mean", "max"]).round(3).to_string())
    for tn in TIMINGS:
        for en in ["sl1W", "slOpp"]:
            s = df[(df.timing == tn) & (df.exit == en) & (df.buf_atr == 0)]
            print(tn, en)
            print(s.pivot(index="tf", columns="buf_k", values="avg_R").round(3).to_string())
    top = df[df.n >= 150].sort_values("t_stat", ascending=False).head(20)
    print(top[["timing", "exit"] + cols].to_string(index=False))


if __name__ == "__main__":
    main()
