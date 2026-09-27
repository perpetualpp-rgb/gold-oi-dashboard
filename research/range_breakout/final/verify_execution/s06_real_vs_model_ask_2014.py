"""(a/e) Isolate the spread MODEL: on the 2014 Dukascopy days (full daily BID+ASK coverage to 2014-10-24),
run the primary with (i) Dukascopy BID + real Dukascopy ASK and (ii) the same BID + modelled ASK
(BID + spread_model[year, London hour], exactly how the engine's ASK parquet is built). The difference
is what the constant-within-hour spread misses: spread-driven extra triggers of buy stops, spread spikes
that hit short stops, and wider spreads at exits. Also (iii) real ASK with the spread scaled by 1.5 and
by 2 around the real mid (a wider retail broker)."""
from xcommon import *
import glob
M = spread_model()


def side(sd):
    fr = []
    for p in sorted(glob.glob(os.path.join(RAW, f"XAUUSD_{sd}_2014*.npy"))):
        x = raw_side(pd.Timestamp(os.path.basename(p)[-12:-4]), sd)
        if x is not None:
            fr.append(x)
    o = pd.concat(fr).sort_index()
    o = o[~((o.volume <= 0) & (o.high == o.low))]
    return o[~o.index.duplicated()]

bid, ask = side("BID"), side("ASK")
idx = bid.index.intersection(ask.index)
bid, ask = bid.loc[idx], ask.loc[idx]
spr = ask.close - bid.close
ok = (spr >= 0) & (spr < 5)
bid, ask, idx = bid[ok], ask[ok], idx[ok]
local = idx.tz_convert("Europe/London").tz_localize(None)
lmin = local.values.astype("datetime64[m]").astype(np.int64)
mod = np.array([M.at[2014, h] for h in local.hour])


def mk(ao, ah, al, ac):
    d = dict(index=idx, lmin=lmin, bo=bid.open.values, bh=bid.high.values, bl=bid.low.values, bc=bid.close.values,
             ao=ao, ah=ah, al=al, ac=ac)
    d["days"] = E._daily(d)
    return d

b = bid
variants = {
    "real_ask": mk(ask.open.values, ask.high.values, ask.low.values, ask.close.values),
    "model_ask": mk(b.open.values + mod, b.high.values + mod, b.low.values + mod, b.close.values + mod),
}
for k in (1.5, 2.0):
    so, sh, sl_, sc = (ask.open - b.open).values, (ask.high - b.high).values, (ask.low - b.low).values, (ask.close - b.close).values
    variants[f"real_ask_x{k}"] = mk(b.open.values + k * so, b.high.values + k * sh, b.low.values + k * sl_, b.close.values + k * sc)
    variants[f"model_ask_x{k}"] = mk(b.open.values + k * mod, b.high.values + k * mod, b.low.values + k * mod, b.close.values + k * mod)
res = {}
T = {}
for lab in ("primary", "fallback"):
    p = params(lab)
    p0 = params(lab, min_w_atr=0.0, atr_regime_n=0)      # also the unfiltered 00-05 breakout (more trades)
    for pl, pp in ((lab, p), (lab + "_nofilter", p0)):
        if pl == "fallback_nofilter":
            continue
        for k, Dv in variants.items():
            t = E.run(pp, start="2014-02-01", end="2014-10-23", D=Dv)
            T[(pl, k)] = t
            res[f"{pl}|{k}"] = dict(n=len(t), avg_R=round(t.R.mean(), 4), sum_R=round(t.R.sum(), 2),
                                   long_n=int((t.dir == 1).sum()), short_n=int((t.dir == -1).sum()),
                                   sl_n=int((t.reason == "sl").sum()))
        a, m = T[(pl, "real_ask")], T[(pl, "model_ask")]
        mm = a.merge(m, on="date", how="outer", suffixes=("_r", "_m"))
        both = mm.dropna(subset=["R_r", "R_m"])
        res[f"{pl}|diff"] = dict(common=len(both), only_real=int(mm.R_m.isna().sum()), only_model=int(mm.R_r.isna().sum()),
                                 diff_dir=int((both.dir_r != both.dir_m).sum()),
                                 common_meanR_real=round(both.R_r.mean(), 4), common_meanR_model=round(both.R_m.mean(), 4),
                                 common_mean_diff=round((both.R_r - both.R_m).mean(), 4),
                                 exit_reason_changed=int((both.reason_r != both.reason_m).sum()))
for k, v in res.items():
    print(k, v)
json.dump(res, open("s06_real_vs_model_ask_2014.json", "w"), indent=1)
