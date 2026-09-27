"""Combined realistic haircut for the primary, IS+VAL. Stacks, per scenario:
  spread k (ASK = BID + k * model), feed noise sigma (s09 method, 10 seeds), tick-measured excess
  slippage over the engine's 0.05 (s02b, latency L; entry by London bucket 07-09 / other, SL exits,
  time exits), SL attached to the pending order or modified after fill (s08), NY 08:30 spread-spike
  stop-outs of shorts (s07), and the D1-ATR source (London days vs NY-close broker bars, s03).
Also a bootstrap (tick rows resampled) CI for the slippage component."""
from xcommon import *
import null as N
D = data()
F = pd.read_csv("s02b_tick_fills.csv")
F["bucket"] = np.where((F.hour_ldn >= 7) & (F.hour_ldn < 9), "open", "other")
spr = {c: D["a" + c] - D["b" + c] for c in ("o", "h", "l", "c")}


def excess_table(L, Fs=F):
    ex = Fs[f"slip_{L}"] - Fs.engine_slip
    g = Fs.assign(ex=ex)
    ent = g[g.kind == "entry"].groupby("bucket").ex.mean().to_dict()
    ent_all = g[g.kind == "entry"].ex.mean()
    return dict(entry_open=ent.get("open", ent_all), entry_other=ent.get("other", ent_all),
                sl=g[g.kind == "sl"].ex.mean(), time=g[g.kind == "time"].ex.mean())


def make_D(k=1.0, sigma=0.0, seed=0):
    if k == 1.0 and sigma == 0:
        return D
    d = {kk: v for kk, v in D.items() if kk not in ("_win_cache", "days")}
    bh, bl = D["bh"], D["bl"]
    if sigma > 0:
        rng = np.random.default_rng(seed); n = len(bh)
        bh = np.maximum(bh + rng.normal(0, sigma, n), np.maximum(D["bo"], D["bc"]))
        bl = np.minimum(bl - rng.normal(0, sigma, n), np.minimum(D["bo"], D["bc"]))
    d["bh"], d["bl"] = bh, bl
    d["ao"] = D["bo"] + k * spr["o"]; d["ac"] = D["bc"] + k * spr["c"]
    d["ah"] = bh + k * spr["h"]; d["al"] = bl + k * spr["l"]
    d["days"] = E._daily(d)
    return d


def ny_mask(d, p):
    """NY-close broker ATR filter mask (same construction as s03)."""
    idx = d["index"]; days = d["days"].index
    ny = idx.tz_convert("America/New_York").tz_localize(None)
    s = pd.DataFrame({"d": (ny + pd.Timedelta(hours=7)).normalize(), "h": d["bh"], "l": d["bl"], "c": d["bc"]})
    g = s.groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    g = g[g.index.dayofweek < 5]
    pc = g["c"].shift(1)
    tr = np.maximum(g["h"] - g["l"], np.maximum((g["h"] - pc).abs(), (g["l"] - pc).abs()))
    atr = tr.rolling(14).mean(); m20 = atr.rolling(20, min_periods=12).mean()
    pos = np.searchsorted(atr.index.values, days.values, side="left") - 1
    a = np.where(pos >= 0, atr.values[np.maximum(pos, 0)], np.nan)
    m = np.where(pos >= 0, m20.values[np.maximum(pos, 0)], np.nan)
    *_, rh, rl, valid, _ = E._windows_full(d, p.range_start, p.range_end, p.entry_end, p.exit_time)
    return np.isfinite(a) & np.isfinite(m) & ((rh - rl) / a >= 0.3) & (a <= m)


def run_one(k, sigma, seed, L, attached, spike, atr_src):
    p = params("primary")
    d = make_D(k, sigma, seed)
    if atr_src == "ny":
        p0 = params("primary", min_w_atr=0.0, atr_regime_n=0)
        t = E.run(p0, end=E.VAL_END, D=d)
        t = t[ny_mask(d, p)[t.day.values]].reset_index(drop=True)
    else:
        t = E.run(p, end=E.VAL_END, D=d)
    R = t.R.values.copy()
    if attached:
        i_rs, i_re, *_ = E._windows_full(d, p.range_start, p.range_end, p.entry_end, p.exit_time)
        _, _, _, _, rh, rl, _, _ = E._windows_full(d, p.range_start, p.range_end, p.entry_end, p.exit_time)
        lvl = np.where(t.dir == 1, rh[t.day], rl[t.day])
        t2 = t.copy(); t2["risk"] = t.risk + t.dir * (t.entry - lvl)
        R = (N.walk(p, t2, t.dir.values, d).pnl / t.risk).values
    if L is not None:
        X = excess_table(L)
        he = t.t_entry.dt.tz_convert("Europe/London").dt.hour.values
        ent = np.where((he >= 7) & (he < 9), X["entry_open"], X["entry_other"])
        ext = np.where(t.reason.values == "sl", X["sl"], np.where(t.reason.values == "time", X["time"], 0.0))
        R = R - (ent + ext) / t.risk.values
    R = R - spike
    t = t.assign(R=R)
    o = {}
    for per, sel in (("IS", t.date <= E.IS_END), ("VAL", t.date > E.IS_END), ("ALL", t.date > "2000")):
        x = t[sel].R
        o[per] = (len(x), x.mean(), x.mean() / x.std() * np.sqrt(len(x)))
    return o


def scen(name, k=1.0, sigma=0.0, L=None, attached=False, spike=0.0, atr_src="london", seeds=10):
    ss = range(seeds) if sigma > 0 else [0]
    outs = [run_one(k, sigma, s, L, attached, spike, atr_src) for s in ss]
    r = {per: dict(n=round(np.mean([o[per][0] for o in outs]), 1), avg_R=round(np.mean([o[per][1] for o in outs]), 4),
                   t=round(np.mean([o[per][2] for o in outs]), 2)) for per in ("IS", "VAL", "ALL")}
    print(f"{name:70s} IS {r['IS']['avg_R']:+.4f} (t {r['IS']['t']:.2f})  VAL {r['VAL']['avg_R']:+.4f}  ALL {r['ALL']['avg_R']:+.4f} n {r['ALL']['n']}", flush=True)
    return r

res = {"tick_rows": F.kind.value_counts().to_dict()}
for L in (0, 250, 500, 1000):
    res[f"excess_usd_L{L}"] = {k: round(v, 4) for k, v in excess_table(L).items()}
print(json.dumps({k: v for k, v in res.items()}, indent=1))
# bootstrap the slippage component (tick rows resampled within kind), effect on ALL avg R at L=250 & 500
base_t = E.run(params("primary"), end=E.VAL_END, D=D)
he = base_t.t_entry.dt.tz_convert("Europe/London").dt.hour.values
rng = np.random.default_rng(0)
for L in (250, 500):
    eff = []
    for b in range(2000):
        Fb = pd.concat([g.sample(len(g), replace=True, random_state=int(rng.integers(1 << 31))) for _, g in F.groupby("kind")])
        X = excess_table(L, Fb)
        ent = np.where((he >= 7) & (he < 9), X["entry_open"], X["entry_other"])
        ext = np.where(base_t.reason.values == "sl", X["sl"], np.where(base_t.reason.values == "time", X["time"], 0.0))
        eff.append(-((ent + ext) / base_t.risk.values).mean())
    eff = np.array(eff)
    res[f"slip_component_R_L{L}"] = dict(mean=round(eff.mean(), 4), ci90=[round(np.quantile(eff, .05), 4), round(np.quantile(eff, .95), 4)])
    print("slippage component L", L, res[f"slip_component_R_L{L}"])

S = {}
S["engine"] = scen("engine (k1, slip .05)")
S["ticks_L250"] = scen("tick slippage L=250ms only", L=250)
S["ticks_L500"] = scen("tick slippage L=500ms only", L=500)
S["attached_SL"] = scen("SL attached to pending order only", attached=True)
S["ny_atr"] = scen("NY-close D1 ATR only", atr_src="ny")
S["feed_03"] = scen("feed noise sigma .03 only", sigma=0.03)
S["central"] = scen("CENTRAL: k1.0, ticks L250, feed .03, spike .003, SL mod after fill", k=1.0, sigma=0.03, L=250, spike=0.003)
S["central_ny"] = scen("CENTRAL + NY-close ATR", k=1.0, sigma=0.03, L=250, spike=0.003, atr_src="ny")
S["retail"] = scen("RETAIL: k1.25, ticks L500, feed .06, spike .003", k=1.25, sigma=0.06, L=500, spike=0.003)
S["adverse"] = scen("ADVERSE: k1.5, ticks L1000, feed .12, spike .003, attached SL", k=1.5, sigma=0.12, L=1000, spike=0.003, attached=True)
res["scenarios"] = S
json.dump(res, open("s10_combined.json", "w"), indent=1, default=str)
