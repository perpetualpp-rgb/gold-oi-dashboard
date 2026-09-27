"""(e) Engine execution assumptions vs what MT5 does. IS+VAL, primary.
 1. Order placement at the 05:00 London bar: pending stops must be >= SYMBOL_TRADE_STOPS_LEVEL away from
    the current price (buy stop above Ask, sell stop below Bid). Distance at the first tick of the window.
 2. SL anchoring: engine puts SL = fill -/+ width (EA must modify SL after the fill). If the EA instead
    attaches SL = level -/+ width to the pending order, risk grows by the gap+slip. Re-walk both.
 3. Early-close (US holiday) days: engine flattens at the last bar before the halt; a naive EA that only
    closes at 20:00 London holds to the next session open (SL server-side still active).
 4. Both levels touched in the first touching bar: engine skips the day; an EA takes the first tick.
 5. Entry-bar convention: only SL checked on the entry bar (conservative) - count trades stopped on
    the entry bar."""
from xcommon import *
import null as N
D = data()
p = params("primary")
t = E.run(p, end=E.VAL_END, D=D)
i_rs, i_re, i_ee, i_ex, rh, rl, valid, exc = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
res = {}
# ---- 1. placement distance on days that pass the filters (days with a trade or not)
p_nf = params("primary")
# rebuild filter mask as engine does
days = D["days"]; atr = days["atr14_prev"].values; width = rh - rl
ma = pd.Series(atr).rolling(20, min_periods=12).mean().values
mask = valid & np.isfinite(atr) & (width > 0) & (width / atr >= 0.3) & np.isfinite(ma) & (atr <= ma) & (days.index.dayofweek < 5)
mask &= days.index <= pd.Timestamp(E.VAL_END)
j = i_re[mask]
dl = rh[mask] - D["ao"][j]         # buy stop distance above ASK at 05:00 open
ds = D["bo"][j] - rl[mask]         # sell stop distance below BID
dmin = np.minimum(dl, ds)
res["placement"] = dict(filter_days=int(mask.sum()),
                        share_level_already_crossed=round(float((dmin <= 0).mean()), 4),
                        share_within_010=round(float((dmin < 0.10).mean()), 4),
                        share_within_030=round(float((dmin < 0.30).mean()), 4),
                        share_within_050=round(float((dmin < 0.50).mean()), 4),
                        share_within_100=round(float((dmin < 1.00).mean()), 4),
                        first_bar_trades=int((t.i_entry.values == i_re[t.day.values]).sum()))
# ---- 2. SL anchoring
level = np.where(t.dir == 1, rh[t.day], rl[t.day])
extra = t.dir.values * (t.entry.values - level)             # gap + slip beyond the level
w_eng = N.walk(p, t, t.dir.values, D)
assert np.allclose(w_eng.R.values, t.R.values)
t2 = t.copy(); t2["risk"] = t.risk + extra
w_anch = N.walk(p, t2, t.dir.values, D)
R_anch = w_anch.pnl / t.risk                                 # sized on planned width
res["sl_anchoring"] = dict(mean_extra_usd=round(float(extra.mean()), 4), p99_extra=round(float(np.quantile(extra, .99)), 3),
                           R_engine=round(t.R.mean(), 4), R_attached_SL=round(float(R_anch.mean()), 4),
                           delta=round(float(R_anch.mean() - t.R.mean()), 4))
# ---- 3. early-close days
ec = t[exc[t.day.values]].copy()
nxt = i_ex[ec.day.values]                                    # first bar at/after 20:00 = next session open
px_naive = np.where(ec.dir == 1, D["bo"][nxt] - p.slip, D["ao"][nxt] + p.slip)
sl = ec.entry - ec.dir * ec.risk
# if the reopen gaps through the stop, the server-side SL fills at the open anyway (same price)
R_naive = (ec.dir * (px_naive - ec.entry) - p.commission) / ec.risk
res["early_close"] = dict(n=len(ec), R_engine_sum=round(ec.R.sum(), 2), R_naive_hold_sum=round(float(R_naive.sum()), 2),
                          delta_avgR_all=round(float((R_naive.sum() - ec.R.sum()) / len(t)), 4),
                          dates=[str(d.date()) for d in ec.date])
# ---- 4. both levels in one bar (engine skips the day)
lvl_l, lvl_s = rh, rl
both = 0; first_touch = 0
for d in np.where(mask)[0]:
    a, b = i_re[d], min(i_ee[d], i_ex[d])
    hl = D["ah"][a:b] >= lvl_l[d]; hs = D["bl"][a:b] <= lvl_s[d]
    k = np.where(hl | hs)[0]
    if len(k):
        first_touch += 1
        if hl[k[0]] and hs[k[0]]:
            both += 1
res["both_levels_same_bar"] = dict(days_with_touch=first_touch, both_same_bar=both)
# ---- 5. entry-bar stop-outs
eb = t[(t.reason == "sl") & (t.i_exit == t.i_entry)]
res["entry_bar_stopouts"] = dict(n=len(eb), share=round(len(eb) / len(t), 4))
print(json.dumps(res, indent=1, default=str))
json.dump(res, open("s08_mt5_mechanics.json", "w"), indent=1, default=str)
