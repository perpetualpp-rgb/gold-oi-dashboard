"""(a) Null baselines for the default breakout: random direction at the same entry times,
always-long / always-short, random entry time. IS and VAL (default = 1 VAL config)."""
import numpy as np
import pandas as pd
import common as C
import null as N

E = C.E
pd.set_option("display.width", 250)
D = E.load()

p = E.Params()
C.log_config("default", p, True, "null test IS+VAL")
res = N.null_test(p, n_perm=10000, seed=1, D=D, keep_dist=True)
res200 = N.null_test(p, n_perm=200, seed=2, D=D)
rows = N.summary_rows(res, "default n_perm=10000") + N.summary_rows(res200, "default n_perm=200")
df = pd.DataFrame(rows)
print(C.fmt_table(df))
for per in ("IS", "VAL"):
    b = res[per]
    print(per, "z_coin_analytic", round(b["z_coin_analytic"], 2), "perm z", round(b["coin"]["z"], 2),
          "long_trades", {k: round(v, 4) for k, v in b["long_trades"].items()},
          "short_trades", {k: round(v, 4) for k, v in b["short_trades"].items()})

t = res["trades"]
# per year: actual, always long, always short, coin mean, direction info (actual - coin mean)
t["year"] = t["date"].dt.year
g = t.groupby("year")
yr = pd.DataFrame({
    "n": g.size(),
    "nL": g["dir"].apply(lambda d: (d == 1).sum()),
    "actual": g["R_same"].mean(),
    "always_long": g["R_long"].mean(),
    "always_short": g["R_short"].mean(),
    "coin_mean": g.apply(lambda x: ((x["R_same"] + x["R_flip"]) / 2).mean()),
})
yr["dir_info"] = yr["actual"] - yr["coin_mean"]
# per-year coin p-value
rng = np.random.default_rng(5)
pv = {}
for y, x in g:
    rs, rf = x["R_same"].values, x["R_flip"].values
    m = rng.random((10000, len(rs))) < 0.5
    null = np.where(m, rs, rf).mean(axis=1)
    pv[y] = (1 + (null >= rs.mean()).sum()) / 10001
yr["p_coin"] = pd.Series(pv)
print(C.fmt_table(yr.reset_index().round(4)))

# random-time null
rt = N.null_time_test(p, n_perm=200, seed=3, D=D)
print("random-time null:", {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in rt.items()})

# exit reason mix: same vs flipped
for per, m in (("IS", t["date"] <= E.IS_END), ("VAL", t["date"] > E.IS_END)):
    sub = t[m]
    print(per, "reason same:", sub["reason"].value_counts().to_dict(),
          " flipped:", pd.Series(sub["reason_flip"]).map({1: "sl", 2: "tp", 3: "trail", 4: "time"}).value_counts().to_dict())

np.save(C.os.path.join(C.HERE, "out_null_default_IS_coin.npy"), res["IS"]["_coin"])
np.save(C.os.path.join(C.HERE, "out_null_default_VAL_coin.npy"), res["VAL"]["_coin"])
yr.to_csv(C.os.path.join(C.HERE, "out_null_default_by_year.csv"))
df.to_csv(C.os.path.join(C.HERE, "out_null_default.csv"), index=False)
