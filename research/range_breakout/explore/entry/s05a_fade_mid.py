"""Fade limit at the range edge (+buffer) with the target at the range MIDPOINT or the OPPOSITE EDGE.
With sl_ref=0 and buf = buf_k*W, a target at the midpoint is exactly tp_r = (buf_k+0.5)/sl_k and at the
opposite edge tp_r = (buf_k+1)/sl_k (TP distance measured from the limit price = edge+buf). IS only."""
import sys
import os
import itertools
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import E, D, TIMINGS, eval_is  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    D()
    rows = []
    for (tn, tm), sk, bk, tgt, pen in itertools.product(TIMINGS.items(), [0.25, 0.5, 0.75, 1.0],
                                                        [0, 0.1, 0.2, 0.3, 0.5], ["mid", "opp"], [0.0, 0.05]):
        tp = (bk + (0.5 if tgt == "mid" else 1.0)) / sk
        p = E.Params(**tm, entry_mode=2, sl_ref=0, sl_k=sk, tp_r=tp, buf_k=bk, limit_pen=pen)
        r, _ = eval_is("s05a", p)
        r.update(timing=tn, sl_k=sk, buf_k=bk, target=tgt, tp_r=round(tp, 3), limit_pen=pen)
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "s05a_results.csv"), index=False)
    print("configs:", len(df), " share avg_R>0:", (df.avg_R > 0).mean())
    for tn in TIMINGS:
        for tgt in ("mid", "opp"):
            s = df[(df.timing == tn) & (df.target == tgt) & (df.limit_pen == 0)]
            print(tn, tgt, "avg_R rows sl_k cols buf_k")
            print(s.pivot(index="sl_k", columns="buf_k", values="avg_R").round(3).to_string())
    cols = ["timing", "target", "sl_k", "buf_k", "tp_r", "limit_pen", "n", "avg_R", "t_stat", "PF", "win_rate",
            "yrs_pos", "L_avg", "S_avg"]
    print(df.sort_values("t_stat", ascending=False).head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
