"""VAL (2022-01-01..2023-12-31) check for the timing finalists. Base costs only. Each config is logged
with stage=VAL in out/configs_log.csv. Never runs past E.VAL_END.
Output: out/val_check.txt
"""
import pandas as pd

from common import E, data, summarize, OUT, md_table, _log

D = data()
FIN = {
    "F1 asia00-05 ee12 ex20": E.Params(range_start=0, range_end=5, entry_end=12, exit_time=20),
    "F2 asia00-0530 ee07 ex21": E.Params(range_start=0, range_end=5.5, entry_end=7, exit_time=21),
    "F3 range02-09 ee12 ex20": E.Params(range_start=2, range_end=9, entry_end=12, exit_time=20),
}
rows, lines = [], []
for name, p in FIN.items():
    _log("val", p, "VAL")
    t = E.run(p, start="2022-01-01", end=E.VAL_END, D=D)
    assert t.date.max() <= pd.Timestamp(E.VAL_END)
    s = summarize(t)
    rows.append(dict(config=name, **s))
    yb = E.by_year(t)
    yl = t[t.dir == 1].groupby(t.date.dt.year).R.mean().rename("L_avg")
    ys = t[t.dir == -1].groupby(t.date.dt.year).R.mean().rename("S_avg")
    lines.append(f"\n{name}\n" + md_table(pd.concat([yb, yl, ys], axis=1).reset_index().rename(columns={"date": "year"}), 3))
df = pd.DataFrame(rows)[["config", "n", "avg_R", "win_rate", "PF", "t_stat", "trades_per_year", "maxDD_R",
                         "L_n", "L_avg", "L_t", "S_n", "S_avg", "S_t", "yrs_pos"]]
txt = md_table(df, 4) + "\n" + "\n".join(lines)
print(txt)
with open(f"{OUT}/val_check.txt", "w") as f:
    f.write(txt)
