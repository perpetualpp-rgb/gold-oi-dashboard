"""Check B: intraday momentum / breakout follow-through in spot gold, IS 2014-2021 only.

Literature claims checked:
  - Gao, Han, Li & Zhou (2018 JFE): first half-hour return (incl. overnight) predicts last half-hour (SPY).
  - Baltussen, Da, Lammers & Martens (2021 JFE): rest-of-day return predicts last 30 min in 60+ futures,
    incl. COMEX gold (pit hours 08:20-13:30 ET); weaker in commodities (pooled R2 ~0.1%).
  - Zarattini & Aziz (2023), Zarattini, Barbon & Aziz (2024): opening-range breakouts follow through, mostly
    when opening activity is abnormally high (relative volume); 5-min ORB >> 30/60-min ORB.
  - Osler (2003, 2005): stop-loss clusters beyond levels -> cascades (continuation) vs take-profit
    clusters -> reversals. A 'stop-hunt' market would show race probabilities < 0.5 after a break.
Output: out_s03_momentum.txt
"""
import numpy as np
import pandas as pd

from common import ols, tstat

T = pd.read_parquet("out/daytable.parquet")
lines = []
P = lines.append
COST_USD = 0.47     # engine round trip ~ spread 0.30 + commission 0.07 + 2 x slip 0.05


def lr(a, b):
    return np.log(T[b] / T[a])


def reg_block(title, y, x, cond=None, cond_name=None):
    b, t, r2, n = ols(y.values, x.values)
    s = np.sign(x) * y
    s = s[np.isfinite(s)]
    by = (np.sign(x) * y).groupby(T["year"]).mean()
    P(f"{title}: slope={b:.3f} t={t:.2f} R2={r2*100:.2f}% n={n} | timing sign(x)*y: mean={s.mean()*1e4:.2f}bps "
      f"t={tstat(s):.2f} hit={np.mean(s > 0):.3f} yrs+={int((by > 0).sum())}/8")
    if cond is not None:
        q = pd.qcut(cond, 3, labels=["low", "mid", "high"])
        for lab in ["low", "mid", "high"]:
            m = (q == lab).values
            b, t, r2, n = ols(y.values[m], x.values[m])
            s = (np.sign(x) * y)[m]
            s = s[np.isfinite(s)]
            P(f"    {cond_name} {lab:>4}: slope={b:.3f} t={t:.2f} R2={r2*100:.2f}% n={n} timing mean={s.mean()*1e4:.2f}bps t={tstat(s):.2f}")


P("Check B1: Gao et al. / Baltussen et al. intraday momentum on spot gold, COMEX pit clock (ET)")
y = lr("ny1300", "ny1330")                       # last half hour of the pit session
reg_block("r_last(13:00-13:30ET) ~ r_ONFH(prev 13:30 -> 08:50ET)", y, lr("ny1330_prev", "ny0850"),
          T["relact_ny"], "NY first-30min relative range")
reg_block("r_last ~ r_ROD(prev 13:30 -> 13:00ET)", y, lr("ny1330_prev", "ny1300"),
          T["relact_ny"], "NY first-30min relative range")
reg_block("r_last ~ r_first30(08:20-08:50ET)", y, lr("ny0820", "ny0850"))
reg_block("r(08:50-13:30ET) ~ r_first30(08:20-08:50ET)", lr("ny0850", "ny1330"), lr("ny0820", "ny0850"),
          T["relact_ny"], "NY first-30min relative range")

P("\nCheck B2: London-clock momentum")
reg_block("r(07:30-20:00) ~ r(07:00-07:30)", lr("p0730", "p2000"), lr("p0700", "p0730"),
          T["relact_lon"], "London first-30min relative range")
reg_block("r(08:00-20:00) ~ r(07:00-08:00)", lr("p0800", "p2000"), lr("p0700", "p0800"))
reg_block("r(07:00-20:00) ~ r(00:00-07:00) [Asian drift continues?]", lr("p0700", "p2000"), lr("p0000", "p0700"))
reg_block("r(13:00-20:00) ~ r(07:00-13:00) [London -> NY]", lr("p1300", "p2000"), lr("p0700", "p1300"))


def race_table(tag, label, extra_masks=()):
    P(f"\nCheck B3 [{label}]: race from the broken level, gross (no costs). P(win|resolved) vs 0.5 under a "
      f"random walk; ft = dir*(P(20:00)-level)/W; cost/W = {COST_USD}/W")
    base = T[T[f"{tag}_dir"] != 0].copy()
    masks = [("all", np.ones(len(base), bool)), ("long", base[f"{tag}_dir"].values == 1),
             ("short", base[f"{tag}_dir"].values == -1)] + [(n, f(base)) for n, f in extra_masks]
    rows = []
    for name, m in masks:
        x = base[m]
        row = dict(subset=name, n=len(x))
        for k in (0.5, 1.0, 2.0):
            rc = x[f"{tag}_race{k}"]
            res = rc[rc != 0]
            p = ((res == 1).sum() + 0.5 * (res == 0.5).sum()) / max(len(res), 1)
            z = (p - 0.5) / np.sqrt(0.25 / max(len(res), 1))
            row[f"P{k}"] = round(p, 3)
            row[f"z{k}"] = round(z, 2)
            row[f"res{k}"] = len(res)
        ft = x[f"{tag}_ft"]
        row["ft_mean"] = round(ft.mean(), 3)
        row["ft_t"] = round(tstat(ft.values), 2)
        row["ft_med"] = round(ft.median(), 3)
        row["cost_W"] = round((COST_USD / x[f"{tag}_W"]).mean(), 3)
        by = ft.groupby(x["year"]).mean()
        row["ft_yrs+"] = int((by > 0).sum())
        rows.append(row)
    P(pd.DataFrame(rows).to_string(index=False))
    # by year for P1.0
    x = base
    rc = x[f"{tag}_race1.0"]
    g = pd.DataFrame({"y": x["year"], "rc": rc, "d": x[f"{tag}_dir"], "ft": x[f"{tag}_ft"]})
    g = g[g["rc"] != 0]
    py = g.groupby(["y"]).apply(lambda s: ((s.rc == 1).sum() + 0.5 * (s.rc == 0.5).sum()) / len(s))
    P("  P1.0 by year: " + ", ".join(f"{y}:{v:.3f}" for y, v in py.items()))


race_table("asia", "Asian range 00-07 London, breaks 07-12, exit 20:00 (engine default session)", [
    ("brk 07:00-07:59", lambda b: b["asia_brk_min"].values < 480),
    ("brk 08:00-11:59", lambda b: b["asia_brk_min"].values >= 480),
    ("brk>=07:30 all", lambda b: b["asia_brk_min"].values >= 450),
    ("brk>=07:30 & relact_lon high tercile", lambda b: (b["asia_brk_min"].values >= 450) &
     (b["relact_lon"].values > np.nanquantile(T["relact_lon"], 2 / 3))),
    ("brk>=07:30 & relact_lon low tercile", lambda b: (b["asia_brk_min"].values >= 450) &
     (b["relact_lon"].values < np.nanquantile(T["relact_lon"], 1 / 3))),
])
race_table("lonam", "London-morning range 07-13, breaks 13-17 London (NY open), exit 20:00", [
    ("brk 13:00-13:59", lambda b: b["lonam_brk_min"].values < 840),
    ("brk 14:00-16:59", lambda b: b["lonam_brk_min"].values >= 840),
    ("relact_ny high tercile (LOOK-AHEAD for brk<08:50ET)", lambda b: b["relact_ny"].values > np.nanquantile(T["relact_ny"], 2 / 3)),
    ("brk>=14:00 all", lambda b: b["lonam_brk_min"].values >= 840),
    ("brk>=14:00 & relact_ny high tercile", lambda b: (b["lonam_brk_min"].values >= 840) &
     (b["relact_ny"].values > np.nanquantile(T["relact_ny"], 2 / 3))),
    ("brk>=14:00 & relact_ny low tercile", lambda b: (b["lonam_brk_min"].values >= 840) &
     (b["relact_ny"].values < np.nanquantile(T["relact_ny"], 1 / 3))),
])

open("out_s03_momentum.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
