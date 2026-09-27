"""(a) Re-run the primary (IS+VAL) under realistic spread/slippage models.
Spread: ASK = BID + k * model spread (k = 1, 1.25 (p90 real/model at the entry minutes), 1.5, 2), rebuilt
from the engine arrays (the engine's ASK is BID + model exactly, checked below).
Slippage (time-of-day dependent): engine run with slip=0; then per trade
   R = (pnl - slip_entry(t_entry) - slip_exit(reason, t_exit)) / risk.
The SL price is set from the zero-slip entry (difference < 0.2 USD vs slipped entry, negligible).
News spike at NY 08:30 (13:30 London): shorts still open with SL within X USD above the ASK high of the
08:30 NY minute are counted as stopped by a spread spike (X = excess real spread at p90 / p99)."""
from xcommon import *
D = data()
M = spread_model()
loc = D["index"].tz_convert("Europe/London")
modsp = M.values[D["index"].year.values - 2014, loc.hour.values]
chk = np.abs((D["ao"] - D["bo"]) - modsp)
print("engine ASK == BID + model: max abs diff", chk.max().round(6), "share>1e-6", (chk > 1e-6).mean().round(5))
spr = D["ao"] - D["bo"]   # use the engine's actual spread array (identical up to rounding)


def with_spread(k, extra=None):
    add = (k - 1.0) * spr + (0 if extra is None else extra)
    d = dict(D)
    d = {kk: v for kk, v in D.items() if kk != "_win_cache"}
    for c in ("ao", "ah", "al", "ac"):
        d[c] = D[c] + add
    return d


def run_scn(k=1.0, slip_fn=None, lab="primary", extra=None):
    p = params(lab, slip=0.0)
    Dk = D if (k == 1.0 and extra is None) else with_spread(k, extra)
    t = E.run(p, end=E.VAL_END, D=Dk)
    le = t.t_entry.dt.tz_convert("Europe/London")
    lx = t.t_exit.dt.tz_convert("Europe/London")
    he = le.dt.hour + le.dt.minute / 60
    hx = lx.dt.hour + lx.dt.minute / 60
    se, sx = slip_fn(he.values, hx.values, t.reason.values)
    t["R"] = (t.pnl - se - sx) / t.risk
    return t


def summ(t):
    o = {}
    for per, sel in (("IS", t.date <= E.IS_END), ("VAL", t.date > E.IS_END), ("ALL", t.date > "2000")):
        x = t[sel].R
        o[per] = dict(n=len(x), avg_R=round(x.mean(), 4), t=round(x.mean() / x.std() * np.sqrt(len(x)), 2))
    return o


def const(se, sx_sl, sx_time):
    return lambda he, hx, rs: (np.full(len(he), se), np.where(rs == "sl", sx_sl, sx_time))


def london_open(se_open, se_other, sx_sl_open, sx_sl_other, sx_time):
    def f(he, hx, rs):
        se = np.where((he >= 7) & (he < 8.5), se_open, se_other)
        sx = np.where(rs == "sl", np.where((hx >= 7) & (hx < 8.5), sx_sl_open, sx_sl_other), sx_time)
        return se, sx
    return f

scn = {
    "engine (k1, slip .05/.05)": (1.0, const(.05, .05, .05)),
    "k1.25 slip .05": (1.25, const(.05, .05, .05)),
    "k1.5 slip .05": (1.5, const(.05, .05, .05)),
    "k2.0 slip .05": (2.0, const(.05, .05, .05)),
    "k1 slip .10 all": (1.0, const(.10, .10, .10)),
    "k1 slip .20 stops, .05 time": (1.0, const(.20, .20, .05)),
    "k1 LDN-open slip .20, other .10, SL .15, time .05": (1.0, london_open(.20, .10, .20, .15, .05)),
    "k1.25 LDN-open slip .20, other .10, SL .15, time .05": (1.25, london_open(.20, .10, .20, .15, .05)),
    "k1.5 slip .20 stops, .10 time": (1.5, const(.20, .20, .10)),
    "k1 slip 0 (frictionless slip)": (1.0, const(0, 0, 0)),
}
res = {}
for name, (k, f) in scn.items():
    t = run_scn(k, f)
    res[name] = summ(t)
    print(f"{name:55s}", res[name])
ref = run_scn(1.0, const(.05, .05, .05))
e = E.run(params("primary"), end=E.VAL_END, D=D)
print("post-hoc slip vs engine slip=.05: n", len(ref), len(e), "mean R diff", (ref.R.values - e.R.values).mean().round(5) if len(ref) == len(e) else "n differs")

# NY 08:30 spike exposure: shorts open at the NY 08:30 minute
ny = D["index"].tz_convert("America/New_York")
nym = (ny.hour * 60 + ny.minute).values
t = e.copy()
spk = []
for r in t.itertuples():
    if r.dir != -1:
        continue
    a, b = r.i_entry, r.i_exit
    seg = np.arange(a + 1, b)
    j = seg[nym[seg] == 510] if len(seg) else seg
    if len(j) == 0:
        continue
    j = j[0]
    sl = r.entry + r.risk
    spk.append(dict(date=r.date, dist=sl - D["ah"][j], R=r.R, risk=r.risk))
S = pd.DataFrame(spk)
out = {"shorts_open_at_NY0830": len(S)}
for x in (0.3, 0.5, 1.0, 1.3):
    hit = S[(S.dist > 0) & (S.dist < x)]
    # stopped at SL (-1R minus costs ~ -1.05R) instead of their actual R
    dR = ((-1.05) - hit.R).sum() / len(e)
    out[f"within_{x}"] = dict(n=len(hit), sum_R_actual=round(hit.R.sum(), 2), delta_avgR_all_trades=round(dR, 4))
print(out)
res["ny0830_spike"] = out
json.dump(res, open("s07_cost_scenarios.json", "w"), indent=1, default=str)
