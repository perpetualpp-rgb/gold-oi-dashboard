"""Is the 2014 outlier (primary +0.65R/trade, 27R of 65R IS) a HistData artefact? Re-run the primary on
real Dukascopy BID/ASK M1 (data_cache/raw, 2014-01..2014-10 daily coverage) and compare trade by trade
with the HistData-based engine data over the same dates. Read-only on the cache."""
import glob, json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common import E, data  # noqa
RAW = os.path.join(E.CACHE, "raw")

def load_side(side):
    fr = []
    for p in sorted(glob.glob(os.path.join(RAW, f"XAUUSD_{side}_2014*.npy"))):
        rec = np.load(p)
        if len(rec) == 0: continue
        day = pd.Timestamp(os.path.basename(p)[-12:-4], tz="UTC")
        idx = day + pd.to_timedelta(rec[:, 0].astype(np.int64), unit="s")
        fr.append(pd.DataFrame({"open": rec[:, 1] / 1e3, "close": rec[:, 2] / 1e3, "low": rec[:, 3] / 1e3,
                                "high": rec[:, 4] / 1e3, "volume": rec[:, 5]}, index=idx))
    o = pd.concat(fr).sort_index()
    o = o[~((o.volume <= 0) & (o.high == o.low))]
    return o[~o.index.duplicated()]

bid, ask = load_side("BID"), load_side("ASK")
idx = bid.index.intersection(ask.index)
bid, ask = bid.loc[idx], ask.loc[idx]
spr = ask.close - bid.close; ok = (spr >= 0) & (spr < 5)
bid, ask, idx = bid[ok], ask[ok], idx[ok]
local = idx.tz_convert("Europe/London").tz_localize(None)
Dd = dict(index=idx, lmin=local.values.astype("datetime64[m]").astype(np.int64),
          bo=bid.open.values, bh=bid.high.values, bl=bid.low.values, bc=bid.close.values,
          ao=ask.open.values, ah=ask.high.values, al=ask.low.values, ac=ask.close.values)
Dd["days"] = E._daily(Dd)
last = pd.Timestamp("2014-10-25")  # daily Dukascopy coverage ends 2014-10-24
cand = json.load(open(os.path.join(HERE, "..", "candidates.json")))["candidates"]
res = {"duka_last_day": str(last.date())}
Dh = data()
for lab in ("primary", "fallback"):
    p = E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in cand[lab].items()})
    td = E.run(p, start="2014-02-01", end=last - pd.Timedelta(days=1), D=Dd)
    th = E.run(p, start="2014-02-01", end=last - pd.Timedelta(days=1), D=Dh)
    m = th.merge(td, on="date", how="outer", suffixes=("_hd", "_dk"))
    same_dir = (m.dir_hd == m.dir_dk).sum()
    res[lab] = dict(hist_n=len(th), hist_avgR=round(th.R.mean(), 4), hist_sumR=round(th.R.sum(), 2),
                    duka_n=len(td), duka_avgR=round(td.R.mean(), 4), duka_sumR=round(td.R.sum(), 2),
                    common_days=int((m.dir_hd.notna() & m.dir_dk.notna()).sum()),
                    same_dir=int(same_dir), corr_R_common=round(m[["R_hd", "R_dk"]].dropna().corr().iloc[0, 1], 3),
                    avg_spread_duka_entry=round(float(np.nanmean(Dd["ao"][td.i_entry.values] - Dd["bo"][td.i_entry.values])), 3),
                    avg_spread_hist_entry=round(float(np.nanmean(Dh["ao"][th.i_entry.values] - Dh["bo"][th.i_entry.values])), 3))
    big = m.sort_values("R_hd", ascending=False).head(6)[["date", "dir_hd", "R_hd", "dir_dk", "R_dk"]]
    res[lab]["top_hist_trades_vs_duka"] = big.assign(date=big.date.astype(str)).round(3).to_dict("records")
print(json.dumps(res, indent=1, default=str))
json.dump(res, open(os.path.join(HERE, "s05_duka_2014.json"), "w"), indent=1, default=str)
