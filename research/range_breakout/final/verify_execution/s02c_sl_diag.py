"""Diagnose large tick SL slippage: is it a genuine price jump (previous tick still on the safe side of
the SL) or a feed offset (Dukascopy already beyond the SL at the window start)? Also: HistData vs
Dukascopy M1 feed offset at the trigger minute, and NY-time of the SL hits."""
from xcommon import *
import s02b_tick_slippage as T  # noqa  (re-runs s02b; cheap)
S = pd.read_csv("s02b_tick_fills.csv")
D = data()
t = pd.read_csv("trades_primary.csv"); t["t_exit"] = pd.to_datetime(t.t_exit, utc=True); t["t_entry"] = pd.to_datetime(t.t_entry, utc=True)
rows = []
for kind in ("entry", "sl"):
    x = S[S.kind == kind]
    for r in x.itertuples():
        tr = t[t.date == r.date].iloc[0]
        tt0 = (tr.t_exit if kind == "sl" else tr.t_entry)
        w = T.window(tt0 - pd.Timedelta(minutes=5), tt0 + pd.Timedelta(minutes=2))
        tt, ask, bid = w
        px = (bid if tr.dir == 1 else ask) if kind == "sl" else (ask if tr.dir == 1 else bid)
        k = np.searchsorted(tt, r.trig_ms)
        lvl = (tr.entry - tr.dir * tr.risk) if kind == "sl" else tr.level
        sgn = -tr.dir if kind == "sl" else tr.dir         # +1: trigger when px >= lvl
        first_in_window = k == np.searchsorted(tt, (tt0 - pd.Timedelta(minutes=5)).value // 10**6)
        prev_dist = sgn * (lvl - px[k - 1]) if k > 0 else np.nan     # >0: previous tick still safe
        gap_ms = tt[k] - tt[k - 1] if k > 0 else np.nan
        # feed offset: Dukascopy BID at the trigger minute vs HistData BID bar (close) of that minute
        m = pd.Timestamp(r.trig_ms, unit="ms", tz="UTC").floor("min")
        i = np.searchsorted(D["index"], m)
        sel = (tt >= m.value // 10**6) & (tt < m.value // 10**6 + 60000)
        off = bid[sel][-1] - D["bc"][i] if sel.any() and i < len(D["bc"]) and D["index"][i] == m else np.nan
        ny = pd.Timestamp(r.trig_ms, unit="ms", tz="UTC").tz_convert("America/New_York")
        rows.append(dict(kind=kind, date=r.date, dir=tr.dir, slip0=r.slip_0, prev_dist=prev_dist, gap_ms=gap_ms,
                         first_in_window=bool(first_in_window), feed_off=off, ny_hm=ny.hour + ny.minute / 60,
                         risk=tr.risk))
Q = pd.DataFrame(rows)
Q.to_csv("s02c_diag.csv", index=False)
pd.set_option("display.width", 200)
for kind in ("entry", "sl"):
    q = Q[Q.kind == kind]
    print(kind, "n", len(q), "first tick of window already beyond:", int(q.first_in_window.sum()),
          " |feed offset| median %.3f p90 %.3f" % (q.feed_off.abs().median(), q.feed_off.abs().quantile(.9)))
    big = q[q.slip0 > 0.3].sort_values("slip0", ascending=False)
    print(big.round(3).to_string())
    clean = q[~q.first_in_window]
    print("  excluding window-start triggers: n", len(clean), "mean slip0 %.3f median %.3f" % (clean.slip0.mean(), clean.slip0.median()))
    print("  NY 08:25-08:45 or 09:55-10:05 hits:", int(((q.ny_hm.between(8.4, 8.75)) | (q.ny_hm.between(9.9, 10.1))).sum()),
          "mean slip there %.3f" % q[(q.ny_hm.between(8.4, 8.75)) | (q.ny_hm.between(9.9, 10.1))].slip0.mean())
