"""Primary/fallback trades on IS+VAL with the frozen params; adds level, gap, spread info."""
from xcommon import *
D = data()
for lab in ("primary", "fallback"):
    p = params(lab)
    t = E.run(p, end=E.VAL_END, D=D)
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, exc = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
    t["level"] = np.where(t.dir == 1, rh[t.day], rl[t.day])
    t["gap_usd"] = t.dir * (t.entry - t.level) - p.slip          # fill beyond level due to bar-open gap
    t["spread_model_entry"] = D["ao"][t.i_entry] - D["bo"][t.i_entry]
    t["ex_close"] = exc[t.day]
    loc = t.t_entry.dt.tz_convert("Europe/London")
    t["entry_hm"] = loc.dt.hour + loc.dt.minute / 60
    t["first_bar"] = t.i_entry == i_re[t.day]
    t["period"] = np.where(t.date <= E.IS_END, "IS", "VAL")
    t.to_csv(f"trades_{lab}.csv", index=False)
    print(lab, len(t), t.groupby("period").R.agg(["count", "mean"]).round(4).to_dict())
    print(" risk USD quantiles", t.risk.quantile([.05, .25, .5, .75, .95]).round(2).to_dict())
    print(" gap>0 share", (t.gap_usd > 1e-9).mean().round(3), "mean gap", t.gap_usd.mean().round(4),
          "first-bar entries", t.first_bar.sum(), "ex_close", t.ex_close.sum())
    print(" reasons", t.reason.value_counts().to_dict())
    print(" entry hour hist", pd.cut(t.entry_hm, [5, 6, 7, 8, 9, 10, 11, 12], right=False).value_counts().sort_index().to_dict())
