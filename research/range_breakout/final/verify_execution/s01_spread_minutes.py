"""(a) Real Dukascopy BID/ASK M1 spreads (sample days < 2024) vs the modelled spread (year x London hour).
Spread proxies per minute: open (ASK open - BID open), close, and 'hi' = ASK high - BID high,
'lo' = ASK low - BID low (the spread around the bar's extremes, where stop orders trigger).
Buckets of London clock minutes; ratio real/model per minute. Also: spread at the primary's actual
entry and exit minutes on the sample days (the engine trades on HistData days; the Dukascopy sample
days are matched by timestamp)."""
from xcommon import *
M = spread_model()
R = raw_pairs()
loc = R.index.tz_convert("Europe/London")
R["y"] = R.index.year
R["hl"] = loc.hour
R["mod"] = [M.at[y, h] for y, h in zip(R.y, R.hl)]
R["tod"] = loc.hour * 60 + loc.minute
R["s_open"] = R.open_a - R.open_b
R["s_close"] = R.close_a - R.close_b
R["s_hi"] = R.high_a - R.high_b
R["s_lo"] = R.low_a - R.low_b
R["s_max"] = R[["s_open", "s_close", "s_hi", "s_lo"]].max(axis=1)
R["rng"] = R.high_b - R.low_b
R["date"] = loc.date
print("sample days per year (both sides):", R.groupby("y").date.nunique().to_dict())

# New York 08:30 (US data) in London clock is 13:30 except in US/EU DST-mismatch weeks (12:30).
ny = R.index.tz_convert("America/New_York")
R["ny_tod"] = ny.hour * 60 + ny.minute
buckets = {
    "00:00-05:00 (range)": (R.tod < 300),
    "05:00-07:00": (R.tod >= 300) & (R.tod < 420),
    "07:00-07:05": (R.tod >= 420) & (R.tod < 425),
    "07:00-08:00": (R.tod >= 420) & (R.tod < 480),
    "08:00-08:05": (R.tod >= 480) & (R.tod < 485),
    "08:00-12:00": (R.tod >= 480) & (R.tod < 720),
    "NY 08:30 minute (13:30 Ldn)": (R.ny_tod == 510),
    "NY 08:29-08:35": (R.ny_tod >= 509) & (R.ny_tod < 516),
    "NY 10:00 minute": (R.ny_tod == 600),
    "19:55-20:05 (time exit)": (R.tod >= 1195) & (R.tod < 1205),
    "20:00 minute": (R.tod == 1200),
    "21:55-23:05 (rollover)": (R.tod >= 1315) & (R.tod < 1385),
}
rows = []
for per, pm in (("2014", R.y == 2014), ("2015-2023", R.y >= 2015), ("all<2024", R.y > 0)):
    for k, m in buckets.items():
        x = R[m & pm]
        if len(x) == 0:
            continue
        r = dict(period=per, bucket=k, n=len(x), model=x["mod"].mean())
        for c in ("s_open", "s_hi", "s_max"):
            r[f"{c}_med"] = x[c].median(); r[f"{c}_p90"] = x[c].quantile(.9); r[f"{c}_p99"] = x[c].quantile(.99)
        r["ratio_open_mean"] = (x.s_open / x["mod"]).mean()
        r["ratio_open_p90"] = (x.s_open / x["mod"]).quantile(.9)
        r["ratio_max_p90"] = (x.s_max / x["mod"]).quantile(.9)
        rows.append(r)
T = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(T.round(3).to_string())
T.round(4).to_csv("s01_spread_buckets.csv", index=False)

# spread on 'breakout-like' minutes in the entry window: top-5% bar ranges 05-12 London
w = R[(R.tod >= 300) & (R.tod < 720)].copy()
thr = w.groupby("y").rng.transform(lambda s: s.quantile(.95))
big = w[w.rng >= thr]
print("\nentry window 05-12, top-5%% range minutes: real/model  open mean %.3f p90 %.3f | max-proxy mean %.3f p90 %.3f  n=%d" % (
    (big.s_open / big["mod"]).mean(), (big.s_open / big["mod"]).quantile(.9),
    (big.s_max / big["mod"]).mean(), (big.s_max / big["mod"]).quantile(.9), len(big)))

# spread at the primary's (and fallback's) trade minutes that fall on sample days
out = {}
for lab in ("primary", "fallback"):
    t = pd.read_csv(f"trades_{lab}.csv", parse_dates=["t_entry", "t_exit", "date"])
    for side, col in (("entry", "t_entry"), ("exit", "t_exit")):
        ts = pd.to_datetime(t[col], utc=True)
        hit = ts.isin(R.index)
        x = R.loc[ts[hit]]
        d = dict(n=int(hit.sum()), model_mean=float(x["mod"].mean()), open_mean=float(x.s_open.mean()),
                 open_p90=float(x.s_open.quantile(.9)), max_mean=float(x.s_max.mean()),
                 max_p90=float(x.s_max.quantile(.9)),
                 ratio_open_mean=float((x.s_open / x["mod"]).mean()), ratio_max_mean=float((x.s_max / x["mod"]).mean()),
                 ratio_max_p90=float((x.s_max / x["mod"]).quantile(.9)))
        if side == "exit":
            sl = (t.reason[hit.values] == "sl").values
            d["sl_exits_n"] = int(sl.sum())
            d["sl_ratio_max_mean"] = float((x.s_max / x["mod"])[sl].mean()) if sl.any() else None
        out[f"{lab}_{side}"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}
print(json.dumps(out, indent=1))
json.dump({"buckets": T.round(4).to_dict("records"), "trade_minutes": out,
           "entry_window_top5pct_ratio_open_mean": round(float((big.s_open / big["mod"]).mean()), 4),
           "entry_window_top5pct_ratio_max_p90": round(float((big.s_max / big["mod"]).quantile(.9)), 4)},
          open("s01_spread.json", "w"), indent=1)
