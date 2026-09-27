"""(a) Tick-level stop-fill slippage for the primary's IS+VAL trades (Dukascopy ticks, random sample of
hours fetched by s02a). For each trade with the needed hour(s):
  entry: level = range edge (HistData BID). Trigger = first tick in the entry minute window
         [entry minute - 5 min, entry minute + 2 min) with ASK >= level (long) / BID <= level (short).
         fill(L) = the quote on the first tick at/after trigger + L ms (L = 0 is the trigger tick itself,
         i.e. a zero-latency server-side stop). slip(L) = dir * (fill - level). Engine assumed
         slip = max(level, bar open) - level + 0.05.
  SL exit: same on the stop price (engine SL = engine fill -/+ risk): BID <= SL (long) / ASK >= SL (short).
  Also: real spread on the trigger tick vs the model spread for that hour.
Only 2014-2023 hours are used."""
from xcommon import *
import lzma
M = spread_model()
TD = os.path.join(HERE, "ticks")
dt_ = np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"), ("av", ">f4"), ("bv", ">f4")])
_cache = {}


def ticks(h):
    if h in _cache:
        return _cache[h]
    p = os.path.join(TD, f"{h:%Y%m%d%H}.bi5")
    if not os.path.exists(p):
        _cache[h] = None; return None
    raw = open(p, "rb").read()
    if not raw:
        _cache[h] = None; return None
    a = np.frombuffer(lzma.decompress(raw), dtype=dt_)
    tt = np.int64(h.value // 10**6) + a["ms"].astype(np.int64)          # epoch ms
    o = (tt, a["ask"].astype(float) / 1e3, a["bid"].astype(float) / 1e3)
    _cache[h] = o; return o


def window(t0, t1):
    hs = pd.date_range(t0.floor("h"), t1.floor("h"), freq="h")
    parts = [ticks(h) for h in hs]
    if any(x is None for x in parts):
        return None
    return tuple(np.concatenate([x[i] for x in parts]) for i in range(3))

LAT = [0, 100, 250, 500, 1000, 2000]


def measure(ts, side_px, dir_trig, level, pay_dir, t0, t1):
    """dir_trig: +1 trigger when px >= level, -1 when px <= level. pay_dir: +1 if higher fill is worse."""
    tt, ask, bid = ts
    px = ask if side_px == "ask" else bid
    sel = (tt >= t0.value // 10**6) & (tt < t1.value // 10**6)
    k = np.where(sel & ((px >= level) if dir_trig == 1 else (px <= level)))[0]
    if len(k) == 0:
        return None
    k = k[0]
    out = {"trig_ms": int(tt[k]), "spread_trig": ask[k] - bid[k]}
    for L in LAT:
        j = np.searchsorted(tt, tt[k] + L)
        if j >= len(tt):
            return None
        out[f"slip_{L}"] = pay_dir * (px[j] - level)
    return out

rows = []
t = pd.read_csv("trades_primary.csv")
for c in ("t_entry", "t_exit"):
    t[c] = pd.to_datetime(t[c], utc=True)
for r in t.itertuples():
    if r.t_entry >= CUT:
        continue
    # entry
    t0, t1 = r.t_entry - pd.Timedelta(minutes=5), r.t_entry + pd.Timedelta(minutes=2)
    w = window(t0, t1)
    hl = r.t_entry.tz_convert("Europe/London").hour
    if w is not None:
        m = measure(w, "ask" if r.dir == 1 else "bid", r.dir, r.level, r.dir, t0, t1)
        if m is not None:
            m.update(kind="entry", date=r.date, dir=r.dir, risk=r.risk, hour_ldn=hl,
                     engine_slip=r.dir * (r.entry - r.level), model_spread=M.at[r.t_entry.year, hl],
                     early_min=(r.t_entry.value // 10**6 - m["trig_ms"]) / 60000)
            rows.append(m)
    if r.reason == "sl":
        sl = r.entry - r.dir * r.risk
        t0, t1 = r.t_exit - pd.Timedelta(minutes=5), r.t_exit + pd.Timedelta(minutes=2)
        w = window(t0, t1)
        hx = r.t_exit.tz_convert("Europe/London").hour
        if w is not None:
            # long SL: BID <= sl (dir_trig -1), worse = lower fill -> pay_dir -1 ; short SL: ASK >= sl
            m = measure(w, "bid" if r.dir == 1 else "ask", -r.dir, sl, -r.dir, t0, t1)
            if m is not None:
                m.update(kind="sl", date=r.date, dir=r.dir, risk=r.risk, hour_ldn=hx,
                         engine_slip=-r.dir * (r.exit - sl), model_spread=M.at[r.t_exit.year, hx],
                         early_min=(r.t_exit.value // 10**6 - m["trig_ms"]) / 60000)
                rows.append(m)
    if r.reason == "time" and not r.ex_close:
        t0 = r.t_exit                                 # 20:00 London bar; market order at its first tick
        w = window(t0, t0 + pd.Timedelta(minutes=1))
        if w is not None:
            tt, ask, bid = w
            k0 = np.searchsorted(tt, t0.value // 10**6)
            if k0 < len(tt):
                m = {"trig_ms": int(tt[k0]), "spread_trig": ask[k0] - bid[k0]}
                q_eng = r.exit + r.dir * 0.05          # engine quote before its slip (BID open long / model ASK open short)
                for L in LAT:
                    j = np.searchsorted(tt, tt[k0] + L)
                    j = min(j, len(tt) - 1)
                    fill = bid[j] if r.dir == 1 else ask[j]
                    m[f"slip_{L}"] = r.dir * (q_eng - fill)      # >0 = worse than the engine's quote
                hx = t0.tz_convert("Europe/London").hour
                m.update(kind="time", date=r.date, dir=r.dir, risk=r.risk, hour_ldn=hx, engine_slip=0.05,
                         model_spread=M.at[t0.year, hx], early_min=0.0)
                rows.append(m)
S = pd.DataFrame(rows)
S.to_csv("s02b_tick_fills.csv", index=False)
print("measured fills:", S.kind.value_counts().to_dict(), " trade-hours available:", len(_cache))
pd.set_option("display.width", 220)
cols = [f"slip_{L}" for L in LAT] + ["engine_slip", "spread_trig", "model_spread"]
for kind in ("entry", "sl", "time"):
    x = S[S.kind == kind]
    if len(x) == 0:
        continue
    print(f"\n{kind}: n={len(x)}")
    print(x[cols].describe(percentiles=[.5, .75, .9, .95]).round(3).to_string())
    x = x.assign(lo=np.where((x.hour_ldn >= 7) & (x.hour_ldn < 9), "07-09 London", "other"))
    print(x.groupby("lo")[cols].mean().round(3).to_string())
    print("  mean excess slip vs engine (L=0, 250, 500 ms), in USD and in R:")
    for L in (0, 250, 500, 1000):
        ex = x[f"slip_{L}"] - x.engine_slip
        print(f"   L={L:4d}ms  USD {ex.mean():+.4f} (se {ex.std()/np.sqrt(len(ex)):.4f})  R {(ex / x.risk).mean():+.4f}")
    print("  trigger minute differs from engine (|early_min|>1):", (x.early_min.abs() > 1).mean().round(3))
summary = {}
for kind in ("entry", "sl", "time"):
    x = S[S.kind == kind]
    if len(x):
        summary[kind] = {"n": len(x), **{f"mean_slip_{L}ms": round(x[f"slip_{L}"].mean(), 4) for L in LAT},
                         **{f"p90_slip_{L}ms": round(x[f"slip_{L}"].quantile(.9), 4) for L in LAT},
                         "engine_slip_mean": round(x.engine_slip.mean(), 4),
                         **{f"excess_R_{L}ms": round(((x[f"slip_{L}"] - x.engine_slip) / x.risk).mean(), 4) for L in LAT},
                         "spread_trig_mean": round(x.spread_trig.mean(), 4), "model_spread_mean": round(x.model_spread.mean(), 4),
                         "spread_trig_p90": round(x.spread_trig.quantile(.9), 4)}
json.dump(summary, open("s02b_tick_slippage.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
