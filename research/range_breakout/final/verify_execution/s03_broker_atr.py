"""(b) ATR14 from broker D1 bars instead of London-day bars.
Variants:
  london   : engine (London-midnight days, Sunday evening bars dropped)
  ny_close : GMT+2/+3 server (NY 17:00 close), 5 bars/week, as most MT5 gold brokers
  gmt0_sun : GMT+0 server with a separate Sunday D1 bar (Sunday 22/23:00 UTC open -> short Sunday bar)
  gmt0_nosun: GMT+0 server without Sunday bar (Sunday ticks merged into Monday)
ATR = SMA14 of true range (MT5 iATR), value of the last COMPLETED broker bar before the London day's
05:00 entry window; atr regime = ATR <= mean(ATR over last 20 broker bars incl. current), min_periods 12.
Filters applied post hoc on the primary's unfiltered trades (max_trades=1: days are independent)."""
from xcommon import *
from features import run_mask
D = data()
days = D["days"].index
idx = D["index"]


def broker_atr(bday, keep_sun=False):
    s = pd.DataFrame({"d": bday, "h": D["bh"], "l": D["bl"], "c": D["bc"]})
    g = s.groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"), n=("h", "size"))
    if not keep_sun:
        g = g[g.index.dayofweek < 5]
    else:
        g = g[g.index.dayofweek != 5]
    pc = g["c"].shift(1)
    tr = np.maximum(g["h"] - g["l"], np.maximum((g["h"] - pc).abs(), (g["l"] - pc).abs()))
    atr = tr.rolling(14).mean()
    # bar that is complete at London 05:00 of day d: broker bars whose END <= that moment.
    # For NY-close and GMT0 servers, the bar dated d-1 (and for GMT0 w/ Sunday: Sunday bar for Monday) ends
    # before 05:00 London d; bar d is still open. So use the last bar with date < d.
    a = atr.copy()
    pos = np.searchsorted(a.index.values, days.values, side="left") - 1   # last broker bar dated < d
    val = np.where(pos >= 0, a.values[np.maximum(pos, 0)], np.nan)
    m20 = atr.rolling(20, min_periods=12).mean()
    mval = np.where(pos >= 0, m20.values[np.maximum(pos, 0)], np.nan)
    return val, mval

ny = idx.tz_convert("America/New_York").tz_localize(None)
utc = idx.tz_localize(None)
V = {}
V["ny_close"] = broker_atr((ny + pd.Timedelta(hours=7)).normalize())
V["gmt0_sun"] = broker_atr(utc.normalize(), keep_sun=True)
sun2mon = utc.normalize() + pd.to_timedelta((utc.dayofweek == 6).astype(int), unit="D")
V["gmt0_nosun"] = broker_atr(sun2mon)
atr_l = D["days"]["atr14_prev"].values
V["london"] = (atr_l, pd.Series(atr_l).rolling(20, min_periods=12).mean().values)

p = params("primary")
p0 = params("primary", min_w_atr=0.0, atr_regime_n=0)
*_, rh, rl, valid, _ = E._windows_full(D, p.range_start, p.range_end, p.entry_end, p.exit_time)
width = rh - rl
base = E.run(p0, end=E.VAL_END, D=D)
ref = E.run(p, end=E.VAL_END, D=D)
res = {}
masks = {}
for k, (a, m) in V.items():
    ok = np.isfinite(a) & np.isfinite(m) & (width / a >= 0.3) & (a <= m)
    masks[k] = ok
    t = run_mask(p0, ok, D, end=E.VAL_END)
    r = {}
    for per, sel in (("IS", t.date <= E.IS_END), ("VAL", t.date > E.IS_END)):
        x = t[sel]; st = E.stats(x)
        r[per] = dict(n=st["n"], avg_R=st["avg_R"], t=st["t_stat"], PF=st["PF"])
    common = set(t.date) & set(ref.date)
    r["days_vs_engine"] = dict(n=len(t), engine_n=len(ref), common=len(common),
                               only_here=len(set(t.date) - set(ref.date)), only_engine=len(set(ref.date) - set(t.date)))
    ok_is = (days <= E.IS_END) & np.isfinite(a) & np.isfinite(atr_l)
    r["corr_atr_vs_london_IS"] = round(float(np.corrcoef(a[ok_is], atr_l[ok_is])[0, 1]), 4)
    r["mean_ratio_atr_vs_london"] = round(float(np.nanmean(a[ok_is] / atr_l[ok_is])), 4)
    res[k] = r
    print(k, json.dumps(r))
chk = run_mask(p0, masks["london"], D, end=E.VAL_END)
print("london post-hoc reproduces engine:", len(chk) == len(ref) and np.allclose(chk.R.values, ref.R.values))
# trades that differ: R of the swapped trades
t_ny = run_mask(p0, masks["ny_close"], D, end=E.VAL_END)
only_eng = ref[~ref.date.isin(t_ny.date)]; only_ny = t_ny[~t_ny.date.isin(ref.date)]
res["ny_close_swap"] = dict(dropped_n=len(only_eng), dropped_avgR=round(only_eng.R.mean(), 4),
                            added_n=len(only_ny), added_avgR=round(only_ny.R.mean(), 4))
print(res["ny_close_swap"])
json.dump(res, open("s03_broker_atr.json", "w"), indent=1)
