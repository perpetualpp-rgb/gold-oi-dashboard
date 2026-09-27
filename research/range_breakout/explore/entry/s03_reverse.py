"""Stop-and-reverse (max_trades=2): stop / confirm entries, buffers, exits, 4 timings. IS only.
Also reports the SECOND trade of the day (the reversal after a failed break) on its own."""
import sys
import os
import itertools
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, eval_is, md, summ, years_pos  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXITS = {
    "sl1W": dict(sl_ref=0, sl_k=1.0),
    "sl0.5W": dict(sl_ref=0, sl_k=0.5),
    "slOpp": dict(sl_ref=2, sl_k=1.0),
}
MODES = {"stop": dict(entry_mode=0), "conf15": dict(entry_mode=1, confirm_tf=15)}
BUF_K = [0, 0.1, 0.2, 0.3]
BUF_ATR = [0, 0.1]


def main():
    D()
    rows = []
    for (tn, tm), (mn, mo), (en, ex), bk, ba in itertools.product(TIMINGS.items(), MODES.items(), EXITS.items(),
                                                                  BUF_K, BUF_ATR):
        p = E.Params(**tm, **mo, **ex, max_trades=2, buf_k=bk, buf_atr=ba)
        r, t = eval_is("s03", p)
        # first vs second trade of the day
        t = t.sort_values(["day", "i_entry"])
        rank = t.groupby("day").cumcount()
        t1, t2 = t[rank == 0], t[rank == 1]
        s1, s2 = summ(t1), summ(t2)
        r.update(timing=tn, mode=mn, exit=en, buf_k=bk, buf_atr=ba,
                 first_n=s1.get("n", 0), first_avg=s1.get("avg_R", np.nan), first_t=s1.get("t_stat", np.nan),
                 rev_n=s2.get("n", 0), rev_avg=s2.get("avg_R", np.nan), rev_t=s2.get("t_stat", np.nan),
                 rev_yrs=years_pos(t2))
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s03_results.csv"), index=False)
    cols = ["mode", "exit", "buf_k", "buf_atr", "n", "avg_R", "t_stat", "PF", "yrs_pos", "L_avg", "S_avg",
            "first_avg", "rev_n", "rev_avg", "rev_t", "rev_yrs"]
    out = []
    for tn in TIMINGS:
        sub = df[df.timing == tn]
        out.append(f"\n### {tn}\n")
        out.append(md(sub[cols], index=False))
    open(os.path.join(HERE, "s03_reverse_tables.txt"), "w").write("\n".join(out))
    print(df.groupby(["timing", "mode", "exit"])[["avg_R", "t_stat", "rev_avg", "rev_t"]].agg(["mean", "max"])
          .round(3).to_string())
    top = df[df.n >= 150].sort_values("t_stat", ascending=False).head(15)
    print(top[["timing"] + cols].to_string(index=False))
    top = df[df.rev_n >= 150].sort_values("rev_t", ascending=False).head(10)
    print(top[["timing"] + cols].to_string(index=False))


if __name__ == "__main__":
    main()
