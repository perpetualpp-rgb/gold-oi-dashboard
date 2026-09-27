"""Descriptive statistics (no trading, no costs), IS days only (2014-01-01..2021-12-31).

1. Intraday drift profile: mean BID return per London hour (USD and bp), t-stat, and cumulative path.
   This is the control for the long/short asymmetry: if London/NY hours drift down, breakout shorts
   profit from drift, not from the breakout.
2. Asian range break study for ranges 00-07 and 00-05 London:
   - does BID break the range during London (range_end..16:00)? which side first? time of first break
   - does the opposite side also break later (before 16:00 / 20:00) = "double break" / false break
   - follow-through from the break level to the 16:00 and 20:00 price, in units of range width (gross)
   - benchmark: the unconditional move over the same clock interval on all days (drift control)
   - by hour of first break, split up/down
3. Volatility profile by 5-minute slot around known events (AM fix 10:30, COMEX 13:20, US data 13:30,
   PM fix 15:00).
Output: out/descriptive.txt (+ csvs)
"""
import numpy as np
import pandas as pd

from common import E, data, OUT, md_table

D = data()
days = D["days"].index
lmin = D["lmin"]
bo, bh, bl, bc = D["bo"], D["bh"], D["bl"], D["bc"]
base = days.values.astype("datetime64[m]").astype(np.int64)
is_day = (days >= pd.Timestamp("2014-01-01")) & (days <= pd.Timestamp(E.IS_END)) & (days.dayofweek < 5)
IS_IDX = np.where(is_day)[0]
out_lines = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out_lines.append(s)


def idx_at(hours):
    """first bar index at/after base+hours, and whether it is within 30 min (market open)."""
    t = base + int(round(hours * 60))
    i = np.searchsorted(lmin, t)
    ok = (i < len(lmin)) & (lmin[np.minimum(i, len(lmin) - 1)] - t < 30)
    return i, ok


def px_at(hours):
    i, ok = idx_at(hours)
    v = np.where(ok & is_day, bo[np.minimum(i, len(bo) - 1)], np.nan)   # IS days only
    return v


# ------------------------------------------------------------------ 1. hourly drift profile (IS)
P("## 1. Intraday drift profile, IS 2014-2021, BID open at each London hour")
H = np.arange(0, 22)   # 00..21 (22:00-23:00 is the daily halt)
px = np.vstack([px_at(h) for h in list(H) + [22]]).T  # day x 23
px = px[IS_IDX]
ret = np.diff(px, axis=1)                    # hour h -> h+1
lvl = px[:, :-1]
bp = ret / lvl * 1e4
rows = []
for k, h in enumerate(H):
    r = ret[:, k]
    r = r[np.isfinite(r)]
    b = bp[:, k]
    b = b[np.isfinite(b)]
    rows.append(dict(hour=f"{h:02d}-{h + 1:02d}", n=len(r), mean_usd=r.mean(), t=r.mean() / r.std(ddof=1) * np.sqrt(len(r)),
                     mean_bp=b.mean(), sd_bp=b.std(ddof=1), up_frac=(r > 0).mean()))
hd = pd.DataFrame(rows)
hd["cum_bp"] = hd["mean_bp"].cumsum()
P(md_table(hd))
hd.to_csv(f"{OUT}/hourly_drift_is.csv", index=False)

# by year: 07->20 London move and 20->07 (overnight via prev day) move
p07, p20, p00 = px_at(7), px_at(20), px_at(0)
p12, p16 = px_at(12), px_at(16)
yrs = days.year.values
rows = []
for y in range(2014, 2022):
    m = is_day & (yrs == y)
    def mv(a, b):
        r = (b[m] - a[m]) / a[m] * 1e4
        r = r[np.isfinite(r)]
        return r.mean(), r.mean() / r.std(ddof=1) * np.sqrt(len(r))
    a1, t1 = mv(p00, p07)
    a2, t2 = mv(p07, p12)
    a3, t3 = mv(p12, p20)
    a4, t4 = mv(p07, p20)
    rows.append(dict(year=y, bp_00_07=a1, t_00_07=t1, bp_07_12=a2, t_07_12=t2, bp_12_20=a3, t_12_20=t3,
                     bp_07_20=a4, t_07_20=t4))
yd = pd.DataFrame(rows)
P("\n### Session drift by year (mean bp per day, BID)")
P(md_table(yd, 2))

# ------------------------------------------------------------------ 2. Asian range break study
atr = D["days"]["atr14_prev"].values


def break_study(rs, re_, lon_end=16.0, late=20.0, tag=""):
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, _ = E._windows_full(D, rs, re_, lon_end, late)
    i16, ok16 = idx_at(lon_end)
    i20, ok20 = idx_at(late)
    recs = []
    for j in IS_IDX:
        if not valid[j] or not ok16[j] or not ok20[j]:
            continue
        a, b1, b2 = i_re[j], i16[j], i20[j]
        hi, lo = bh[a:b2], bl[a:b2]
        w = rh[j] - rl[j]
        up = np.nonzero(hi > rh[j])[0]
        dn = np.nonzero(lo < rl[j])[0]
        fu = up[0] if len(up) else 10 ** 9
        fd = dn[0] if len(dn) else 10 ** 9
        first = min(fu, fd)
        lon_n = b1 - a
        rec = dict(j=j, year=days[j].year, w=w, w_atr=w / atr[j] if atr[j] > 0 else np.nan,
                   p_re=bo[a], p16=bo[b1], p20=bo[b2], rh=rh[j], rl=rl[j])
        if first >= lon_n:
            rec["side"] = 0     # no break during London window
        elif fu == fd:
            rec["side"] = 9     # both in the same bar
        else:
            side = 1 if fu < fd else -1
            rec["side"] = side
            ib = a + first
            rec["brk_min"] = (lmin[ib] - base[j]) / 60.0
            lvl = rh[j] if side == 1 else rl[j]
            rec["ft16"] = side * (bo[b1] - lvl) / w
            rec["ft20"] = side * (bo[b2] - lvl) / w
            # unconditional control: drift over the same clock interval (open of break bar -> 16/20)
            rec["move16_from_brkbar"] = side * (bo[b1] - bo[ib]) / w
            rec["move20_from_brkbar"] = side * (bo[b2] - bo[ib]) / w
            other = fd if side == 1 else fu
            rec["other16"] = other < lon_n
            rec["other20"] = other < (b2 - a)
            # did it reach +1 width beyond the level before the other side broke (before 20:00)?
            if side == 1:
                tgt = np.nonzero(hi[first:] >= rh[j] + w)[0]
            else:
                tgt = np.nonzero(lo[first:] <= rl[j] - w)[0]
            t1 = first + tgt[0] if len(tgt) else 10 ** 9
            rec["hit1w_before_other"] = t1 < other
        recs.append(rec)
    df = pd.DataFrame(recs)
    for c in ("other16", "other20", "hit1w_before_other"):
        df[c] = df[c].astype(float)      # object bool+NaN column -> float (NaN on no-break days)
    n = len(df)
    P(f"\n## 2. Range break study {tag}: range {rs:g}-{re_:g}, London window to {lon_end:g}:00, late {late:g}:00, IS days={n}")
    vc = df["side"].value_counts()
    P(f"no break by {lon_end:g}:00: {vc.get(0, 0) / n:.1%} | up first: {vc.get(1, 0) / n:.1%} | down first: "
      f"{vc.get(-1, 0) / n:.1%} | both same bar: {vc.get(9, 0) / n:.1%}")
    rows = []
    for side, nm in ((1, "up-first"), (-1, "down-first"), (None, "all breaks")):
        s = df[df.side == side] if side else df[df.side.isin([1, -1])]
        rows.append(dict(
            group=nm, n=len(s),
            med_break_time=s.brk_min.median(),
            other_side_by16=s.other16.mean(), other_side_by20=s.other20.mean(),
            hit_1w_before_other=s.hit1w_before_other.mean(),
            ft16_mean=s.ft16.mean(), ft16_pos=(s.ft16 > 0).mean(), ft16_t=s.ft16.mean() / s.ft16.std() * np.sqrt(len(s)),
            ft20_mean=s.ft20.mean(), ft20_pos=(s.ft20 > 0).mean(), ft20_t=s.ft20.mean() / s.ft20.std() * np.sqrt(len(s)),
            ctrl20_from_bar=s.move20_from_brkbar.mean()))
    P(md_table(pd.DataFrame(rows)))
    # control: unconditional average signed drift over the same interval on ALL days (not only break days)
    # in width units, for a long and a short held from the re hour to 20:00
    allw = df.w.values
    uncond = (df.p20 - df.p_re) / allw
    P(f"control: unconditional (all days) move {re_:g}:00->{late:g}:00 in width units: mean {uncond.mean():+.3f} "
      f"(t {uncond.mean() / uncond.std() * np.sqrt(len(uncond)):.2f}); so a random long earns {uncond.mean():+.3f}, "
      f"a random short {-uncond.mean():+.3f} before costs")
    # by hour of first break
    b = df[df.side.isin([1, -1])].copy()
    b["hr"] = np.floor(b.brk_min).astype(int)
    rows = []
    for hr, g in b.groupby("hr"):
        r = dict(hour=hr, n=len(g))
        for side, nm in ((1, "up"), (-1, "dn")):
            s = g[g.side == side]
            r[f"{nm}_n"] = len(s)
            r[f"{nm}_ft20"] = s.ft20.mean() if len(s) else np.nan
            r[f"{nm}_t"] = s.ft20.mean() / s.ft20.std() * np.sqrt(len(s)) if len(s) > 2 else np.nan
            r[f"{nm}_dbl20"] = s.other20.mean() if len(s) else np.nan
        rows.append(r)
    P(f"\nby hour of first break (ft20 = follow-through from level to {late:g}:00, width units, gross)")
    P(md_table(pd.DataFrame(rows)))
    # by year
    rows = []
    for y, g in b.groupby("year"):
        rows.append(dict(year=y, n=len(g), up_share=(g.side == 1).mean(),
                         up_ft20=g[g.side == 1].ft20.mean(), dn_ft20=g[g.side == -1].ft20.mean(),
                         dbl20=g.other20.mean()))
    P("\nby year")
    P(md_table(pd.DataFrame(rows)))
    # end-of-day location relative to the range
    s = df[df.side.isin([1, -1])]
    loc20 = np.where(s.p20 > s.rh, "above", np.where(s.p20 < s.rl, "below", "inside"))
    ct = pd.crosstab(s.side.map({1: "up-first", -1: "down-first"}), loc20, normalize="index").round(3)
    P(f"\nlocation of {late:g}:00 price vs range, by first-break side")
    P(md_table(ct.reset_index()))
    df.to_csv(f"{OUT}/breaks_{tag}.csv", index=False)
    return df


b07 = break_study(0, 7, 16, 20, tag="asian00-07")
b05 = break_study(0, 5, 16, 20, tag="asian00-05")
b_lon = break_study(8, 13, 16, 20, tag="london08-13")   # NY session variant: London-morning range

# ------------------------------------------------------------------ 3. volatility profile around events
P("\n## 3. Mean absolute 5-minute BID move (USD), IS, around gold event times (London clock)")
day_of = lmin // 1440
mod = lmin % 1440
isbar = (D["index"] >= pd.Timestamp("2014-01-01", tz="UTC")) & (D["index"] < pd.Timestamp("2022-01-01", tz="UTC"))
slot = mod // 5
c = pd.Series(bc[isbar])
r5 = pd.DataFrame({"slot": slot[isbar], "absret": np.abs(np.r_[np.nan, np.diff(bc[isbar])]),
                   "ret": np.r_[np.nan, np.diff(bc[isbar])]})
g = r5.groupby("slot").agg(abs1m=("absret", "mean"), drift1m=("ret", "mean"), n=("ret", "size"))
g["abs5m_sum"] = g.abs1m * 5
g["time"] = [f"{(s * 5) // 60:02d}:{(s * 5) % 60:02d}" for s in g.index]
sel = [s for s in g.index if (s * 5) // 60 in (6, 7, 8, 10, 12, 13, 14, 15, 16, 20)]
P(md_table(g.loc[sel, ["time", "n", "abs1m", "drift1m"]].reset_index(drop=True), 4))
g.to_csv(f"{OUT}/vol_profile_5min_is.csv")

with open(f"{OUT}/descriptive.txt", "w") as f:
    f.write("\n".join(out_lines))
