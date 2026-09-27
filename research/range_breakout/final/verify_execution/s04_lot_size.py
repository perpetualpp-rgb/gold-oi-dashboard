"""(c) Minimum lot (0.01 lot = 1 oz at a 100-oz contract) vs the primary's SL in USD/oz.
Per trade: lots = floor(equity * f / (SL_usd * 100) / step) * step, step 0.01. If lots < 0.01 the EA
must either skip the trade or take 0.01 lot and over-risk. Reported for IS+VAL SL sizes and a price-
scaled projection (SL scales roughly with price: SL/price quantiles applied to a 2,000 and 3,500 USD
gold price; no 2024+ data is read, the prices are just round numbers)."""
from xcommon import *
t = pd.read_csv("trades_primary.csv", parse_dates=["date"])
D = data()
t["price"] = D["bo"][t.i_entry]
t["sl_pct"] = t.risk / t.price * 100
q = [0.05, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0]
out = {"sl_usd_quantiles": t.risk.quantile(q).round(2).to_dict(),
       "sl_pct_price_quantiles": t.sl_pct.quantile(q).round(4).to_dict(),
       "sl_usd_by_year_median": t.groupby(t.date.dt.year).risk.median().round(2).to_dict(),
       "sl_usd_by_year_p95": t.groupby(t.date.dt.year).risk.quantile(.95).round(2).to_dict()}
for P in (2000, 3500):
    out[f"sl_usd_at_price_{P}"] = (t.sl_pct.quantile(q) / 100 * P).round(2).to_dict()
print(json.dumps(out, indent=1, default=str))
# account-size table: USD loss at 1R with 0.01 lot = SL_usd * 1 oz
rows = []
for scen, sl in (("IS+VAL actual", t.risk.values),
                 ("price 2000 (scaled)", t.sl_pct.values / 100 * 2000),
                 ("price 3500 (scaled)", t.sl_pct.values / 100 * 3500)):
    for f in (0.005, 0.01):
        need_all = sl.max() / f          # equity so that 0.01 lot never exceeds f
        need_95 = np.quantile(sl, .95) / f
        need_med = np.median(sl) / f
        for eq in (1000, 2500, 5000, 10000, 25000):
            lots = np.floor(eq * f / (sl * 100) / 0.01 + 1e-9) * 0.01
            skip = (lots < 0.01).mean()
            lots_force = np.maximum(lots, 0.01)
            real_risk = lots_force * 100 * sl / eq       # realised risk fraction with forced 0.01 min
            ok = lots >= 0.01
            under = (lots[ok] * 100 * sl[ok] / eq / f)   # rounding-down under-risk ratio
            rows.append(dict(scenario=scen, risk=f, equity=eq, skip_share=round(skip, 3),
                             forced_min_risk_p95=round(np.quantile(real_risk, .95) * 100, 2),
                             forced_min_risk_max=round(real_risk.max() * 100, 2),
                             rounding_realised_over_target_mean=round(under.mean(), 3) if ok.any() else None,
                             rounding_cv=round(under.std() / under.mean(), 3) if ok.sum() > 2 else None))
        print(f"{scen} risk {f:.1%}: equity for 0.01 lot at median SL {need_med:,.0f}, at p95 SL {need_95:,.0f}, max SL {need_all:,.0f}")
        out[f"min_equity_{scen}_{f}"] = dict(median=round(need_med), p95=round(need_95), max=round(need_all))
T = pd.DataFrame(rows)
print(T.to_string())
T.to_csv("s04_lot_table.csv", index=False)
json.dump(out, open("s04_lot_size.json", "w"), indent=1, default=str)
