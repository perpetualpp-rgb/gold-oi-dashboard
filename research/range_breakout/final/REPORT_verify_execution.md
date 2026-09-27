# Verification: Execution realism and implementation (MT5 retail account), IS+VAL only (2014-01-01..2023-12-31)

**Verdict: weak**

**Expected live edge:** Best estimate +0.01R per trade (plausible range -0.05R to +0.06R). The execution haircut alone is 0.02-0.045R per trade: central -0.023R, retail -0.044R, adverse -0.087R. That takes the pooled IS+VAL backtest from +0.104R to +0.06..+0.08R, and VAL from +0.020R to -0.03..+0.002R. Selection-bias shrinkage (DSR 0.18-0.35) is outside this lens, but applying it to the gross edge leaves roughly zero to +0.03R.

## Findings

- The engine reproduces the frozen PRIMARY exactly: 645 trades (IS 532 at +0.1216R, VAL 113 at +0.0202R, pooled +0.1038R). Median SL is 6.71 USD, so the modelled round trip (about 0.30 spread + 0.07 commission + 2 x 0.05 slip) costs about 0.07R. Entries fall mostly between 05:00 and 08:00 London (261 at 05-06, 133 at 06-07, 133 at 07-08); 57% of trades exit on time and 43% at the SL.
- (a) M1 spreads. Real Dukascopy spreads match the model on average in the entry window. I measured 34,000+ matched minutes on Dukascopy days before 2024 (2014 full year, plus 8-10 days a year for 2015-2023). The real/model ratio at bar open is 1.00 (p90 1.22) for 05:00-07:00 London and 0.94 (p90 1.15) for 07:00-08:00. There is NO spread spike at 07:00-08:00 London. The spike is at the NY 08:30 data minute (13:30 London, 12:30 in DST-mismatch weeks): open spread p90 is 2.3x the model and p99 3.8x (p99 up to 1.56 USD). The 21:55-23:05 rollover is p90 2.1x, but it is outside the trading window. On the primary's own entry minutes on sample days (n=46), the real/model ratio is 0.97 at the open and 1.07 on a max-of-proxies, with p90 1.24.
- (a) Tick level (Dukascopy ticks: a random 60-70% sample of the primary's entry, SL-exit and time-exit hours; 297 entries, 146 SL fills and 71 time exits measured). ENTRY: the first tick through the level fills 0.063 USD past it, against the engine's 0.050. At 250/500 ms latency the gap is 0.089/0.099 USD. It is 0.116-0.136 USD at 07-09 London against 0.07 in other hours. The excess is only +0.005R per trade. SL EXITS are the real problem: the engine fills at the SL plus 0.05, but real stop fills average 0.25-0.28 USD past the SL (median 0.04, p90 0.92, max 4.5). These are genuine price jumps: the previous tick was still 0.5-2.7 USD on the safe side. 19 of 146 SL hits happened in the NY 08:30/10:00 minutes, with 0.73 USD mean slip. TIME EXITS at 20:00 London slip only about 0.01 USD against the engine's 0.05, so the engine is conservative there. Spread on the trigger tick is 1.08x the model at entries and 1.20x at SL fills.
- (a) The tick slippage costs -0.018R per trade in net (90% bootstrap CI -0.025 to -0.011) at 250 ms latency, and -0.0215R (CI -0.030 to -0.014) at 500 ms. About 80% of it comes from SL fills on news jumps, which an M1-bar engine cannot see.
- (a) Spread sensitivity (ASK = BID + k x model; the engine ASK is exactly BID + model, checked). Pooled avg R is 0.1001 at k=1, 0.0815 at k=1.25, 0.0745 at k=1.5 and 0.0482 at k=2. For VAL the same steps give +0.017, -0.018, -0.017 and -0.053. Uniform slip 0.10 gives pooled 0.084; slip 0.20 on stop fills gives 0.065. Real vs modelled ASK on the 2014 Dukascopy days changes nothing: 38 identical trades, +0.0007R. So the constant-within-hour spread model does not bias triggers or short stop-outs. NY 08:30 spread spikes would stop out about 8-10 extra shorts in 10 years (-0.003R).
- (b) ATR from broker D1 bars. On a NY-close (GMT+2/+3) server, ATR correlates 0.998 with the London-day ATR. 614 of 645 trade days are shared: 31 dropped (avg -0.05R) and 16 added (avg +0.43R). IS rises to +0.1405 and VAL to +0.0253; this is noise from swapped trades, not an improvement. A GMT+0/+1 server has a Sunday stub D1 bar, which biases ATR14 13% low. The filters then admit 876 trades instead of 645 (only 545 shared), and VAL falls to -0.124R (IS +0.118). GMT+0 without a Sunday bar is harmless (+0.0296 VAL).
- (c) Lot size (0.01 lot = 1 oz at a 100-oz contract). SL in USD over 2014-2023: median 6.71, p95 13.84, max 24.28. As a share of price: median 0.46%, p95 0.83%, max 1.44%. Minimum equity so that 0.01 lot never exceeds the target risk, on 2014-2023 SLs: 1,384 USD at 1% risk for the p95 SL (2,428 for the max SL) and 2,767 at 0.5% (4,856 for the max). Scaled to a 3,500 USD gold price, the same thresholds become 2,897 at 1% (5,040 max) and 5,793 at 0.5% (10,080 max). Lot rounding also under-risks. At 5,000 USD and 0.5%, realised risk averages 85% of target (CV 13%); at 1,000 USD and 0.5%, 74% of trades cannot be taken at all.
- (d) Server time. On a NY+7 server (GMT+2/+3), London 00:00 is 02:00 server except on 169 of 2,594 IS+VAL days (6.5%, the US/EU DST-mismatch weeks), when it is 03:00. With hard-coded server hours, 42 trades on those days shift by -1h. On a fixed GMT+2 server without DST, every BST day shifts by +1h. The MT5 tester returns TimeGMT()==TimeCurrent(), so an EA that derives London time from TimeGMT puts every session 2-3h early. The range then spans the daily halt, and trades fall from 645 to 359. None of these errors is a systematic haircut: pooled avg R is 0.121, 0.129 and 0.148 under the three errors, and -1h or +1h on all days gives 0.136 or 0.122. The strategy is not knife-edge on the hour. The real cost is that live results stop matching the backtest trade by trade, which ruins any monitoring.
- (e) MT5 mechanics. (1) At the first tick at 05:00 London, ASK is already at or above the BID-high level (or BID at or below the low) on 3.4% of filter days, so the EA must send a market order. The nearer level is within 0.50 USD on 20% of days and within 1.00 USD on 37%, so a broker StopsLevel above 0 forces virtual stops. (2) The engine sets SL = fill minus or plus the width. If the SL is instead attached to the pending order at level minus or plus the width, the result is -0.004R, from a mean gap plus slip of 0.057 USD (p99 0.32). (3) 14 trades fell on US early-close days. On the 5 Black Fridays among them, an EA without a holiday calendar would hold the position over the weekend. The R effect happened to be +0.006, but the tail risk is unbounded by the backtest. (4) No filter day had both levels touched in the same bar. No trade was stopped on its entry bar. (5) Buy stops trigger on ASK against a BID range, and SLs on BID (long) or ASK (short): this matches MT5.
- Feed dependence. A broker's BID feed differs from HistData. On 2014, HistData and Dukascopy share only 31 of 33/38 trade days (avg R 0.39 vs 0.26). Adding independent N(0, sigma) noise to every M1 high/low (20 seeds each) gives pooled avg R 0.0995 (sd 0.006) at sigma 0.03, 0.097 (sd 0.011) at sigma 0.06 and 0.071 (sd 0.011) at sigma 0.12. At sigma 0.12 the Jaccard overlap of trade days is 0.92.
- COMBINED (s10, stacked; pooled / IS / VAL avg R). Engine: 0.1038 / 0.1216 / 0.0202. CENTRAL (Dukascopy-level spread, tick slippage at 250 ms, feed sigma 0.03, NY 08:30 spike, SL modified after fill): 0.0805 / 0.0973 (t 1.54) / 0.0017, a haircut of -0.023R. RETAIL (spread x1.25, 500 ms, sigma 0.06): 0.0595 / 0.0784 (t 1.26) / -0.0303, a haircut of -0.044R. ADVERSE (spread x1.5, 1 s, sigma 0.12, attached SL): 0.0169 / 0.0302 / -0.0466, a haircut of -0.087R. The realistic execution haircut is 0.02-0.045R per trade: 20-45% of the pooled backtest edge, and more than the whole VAL edge.

## Risks

- SL fills on macro-data jumps (NY 08:30, 10:00) cost 0.7 USD on average and up to 4.5 USD, a tail the M1 engine prices at 0.05. News-heavy years will be worse than the backtest.
- The VAL edge (+0.02R) is below the central execution haircut (-0.023R). After realistic costs VAL is flat (+0.002R, central) or negative (-0.03R, retail), so live expectancy may be zero or negative even before any selection-bias shrinkage.
- Standard (no-commission) accounts, with spreads about 1.3-1.8x the model all-in, sit between the RETAIL and ADVERSE scenarios.
- Feed and broker dependence: 5-18% of trade days change between feeds, and the width/ATR and regime filters sit on thresholds. Live P&L can diverge materially from the backtest over a year of about 60 trades.
- A GMT+0/+1 broker with Sunday D1 bars combined with iATR(D1) silently changes the strategy (ATR 13% low, +36% trades, VAL -0.12R).
- Server-time and DST bugs (hard-coded server hours, TimeGMT in the tester) do not lose money systematically, but they make the live and MT5-tester trades differ from the research engine, so monitoring and kill-switch comparisons are invalid.
- Small accounts: below about 3-6k USD at 0.5% risk (about 1.4-2.9k at 1%, depending on the gold price), 0.01-lot granularity either skips trades or forces over-risk up to 2-5% of equity on wide-range days.
- The tick sample is 60-70% of the primary's hours, drawn at random, and there are only 146 SL fills. The SL-slippage mean has a standard error of about 0.05 USD, and one NFP day contributes a lot.
- US early-close days (5 Black Fridays in 10 years) can leave a position open over the weekend if the EA has no holiday calendar.

## Guardrails

- Account type: raw/ECN with commission <= 7 USD per lot round trip and a measured average XAUUSD spread <= 0.30-0.35 USD (at gold near 2,000; scale with price) during 05:00-12:00 London. Measure it on the live account for 2 weeks before trading. Do not trade the strategy on a standard account whose all-in round trip exceeds about 0.55 USD per oz per 2,000 USD of gold price.
- Compute London time in the EA from UTC with explicit rules (UK BST: last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC; server offset for a NY-close server = 2h, or 3h during US DST). Never hard-code server hours, and never rely on TimeGMT() in the Strategy Tester. Unit-test the DST-mismatch weeks (2nd-last Sunday of March, last Sunday of October to 1st Sunday of November).
- Compute ATR14 and its 20-day mean from London-midnight daily bars built inside the EA from M1/H1 data, identical to engine._daily. Only if that is impossible, use iATR(PERIOD_D1), and then only on a GMT+2/+3 NY-close server. Never use it on a server that has Sunday D1 bars.
- Orders: buy stop exactly at the BID range high and sell stop exactly at the BID range low (no spread added), expiring at 12:00 London. If the level is already crossed at placement (about 3% of days), send a market order. If the level is within SYMBOL_TRADE_STOPS_LEVEL, use a virtual stop with a market order. After the fill, modify the SL to fill minus or plus the range width; this is worth 0.004R against an attached SL.
- Size the position on the range width. If the computed lots are below 0.01, skip the trade rather than force the minimum lot. Minimum equity: about 3,000 USD at 1% risk or 6,000 USD at 0.5% at current gold prices (at 3,500 USD gold, the p95 SL needs 2,900 and 5,800 USD). Recommended: at least 10,000 USD at 0.5%, so that rounding keeps realised risk above 90% of target.
- Flatten at 20:00 London. Keep a hard-coded US-holiday early-close calendar and close 15 minutes before the halt on those days. Never hold over a weekend.
- Execution monitoring: log fill minus level for every entry and SL. Halt and review if, over a rolling 30 fills, mean entry slip exceeds 0.15 USD, mean SL slip exceeds 0.50 USD, or the median spread at entry exceeds 1.3x the pre-trade measurement.
- Before going live, run the EA in the MT5 tester in 'Every tick based on real ticks' mode on the broker's own history for 2022-2023. Require at least 90% of trade days to match the engine, with the same direction, before any live money.
- Performance kill switch: stop if cumulative R falls below -15R (the IS maxDD was 16.1R), or if the rolling 100-trade mean is below -0.05R. Given the expected edge of about 0.01-0.03R, treat live trading as an experiment at minimum risk (0.25-0.5%).
- Optional: a VPS with under 50 ms latency to the broker. Pending stops are server-side, but market orders, first-tick orders and SL modifications depend on client latency.

## Engine/data notes

- Stop exits: the engine fills at the SL plus 0.05 (or at the bar open on a gap) whenever the SL is crossed inside an M1 bar. Ticks show that SLs hit by news jumps fill 0.7 USD past the level on average (max 4.5). The overall mean SL slip is 0.25-0.28 USD against 0.05 assumed, about -0.015R per trade that the M1 engine cannot represent.
- Time exits: the engine's 0.05 slip is conservative. The real fill at the first tick after 20:00 London is about 0.01 USD away from the bar-open quote (+0.004R per trade in the strategy's favour).
- The spread model is constant within each London hour, so max_spread never binds, and news-minute spikes (NY 08:30 p90 2.3x, p99 3.8x) are absent. On the 2014 Dukascopy real-vs-model ASK check this does not change any trade, and the spike effect on shorts is about -0.003R.
- The engine anchors SL to the actual fill (including gap and slip). An MT5 pending order with an attached SL anchors to the level, so the EA must modify the SL after the fill; otherwise -0.004R.
- Feed dependence: the strategy's trade set depends on the exact BID highs and lows of the HistData feed (2014 against Dukascopy: 31 common days of 33/38). The filters sit on thresholds, so a broker feed changes 2-8% of trade days.
- The first bar of the entry window can be at or beyond the level (3.4% of filter days). The engine fills at max(level, ASK open) + slip, which in MT5 must be a market order because a buy stop below Ask is rejected.
- The early-close handling (ex_close) is correct in the engine, but it assumes the EA knows the holiday calendar; MT5 session info does not provide it reliably.
- Research pitfall for the MT5 port: TimeGMT()==TimeCurrent() in the Strategy Tester, so any GMT-based London clock is wrong in backtests; the sessions land 2-3h early.
- Disclosure: data_cache/spread_model.csv contains 2024-2026 spread rows, which I saw when printing the file header. I did not use them. xcommon.spread_model() slices to <=2023, and all price data was loaded with engine.load(until=VAL_END). Tick downloads were restricted to hours before 2024.

## Full report

EXECUTION REALISM: summary for the PRIMARY re5_w030_a20_W1.00 (IS+VAL only)

The backtest overstates what a retail MT5 account would get by about 0.02-0.045R per trade. That is 20-45% of the pooled IS+VAL edge (+0.104R) and more than the entire VAL edge (+0.020R). Most of it comes from something the M1-bar engine cannot see: stop-loss fills that land on macro-data price jumps. It does not come from the spread model, which matches real Dukascopy spreads well.

Scripts and outputs are in /home/user/gold-oi-dashboard/research/range_breakout/final/verify_execution/ (xcommon.py, s00-s10 *.py, *.json, *.csv, *.log). Ticks are cached in ticks/. The engine was not modified; the tests pass (26).

(a) Spread and slippage
- M1 spreads (s01_spread_minutes.py, s01_spread.json, s01_spread_buckets.csv). The data are the Dukascopy BID+ASK sample days before 2024. The real/model spread ratio at bar open is 1.00 for 05-07 London (p90 1.22), 0.94 for 07-08 (p90 1.15) and 0.95 for 08-12. There is no 07:00-08:00 London spike. The spike is at the NY 08:30 minute (13:30 London): p90 2.3x and p99 3.8x the model. At the primary's own entry minutes on sample days the ratio is 0.97-1.07 (p90 1.24). Replaying 2014 on Dukascopy BID with real ASK against modelled ASK gives the same 38 trades and a difference of +0.0007R (s06).
- Ticks (s02a/b/c): 297 entries, 146 SL fills, 71 time exits.

| Fill type | Real fill vs level | Engine assumption | Effect |
|---|---|---|---|
| Entry, 0 ms | 0.063 USD | 0.05 | |
| Entry, 250 ms | 0.089 USD | 0.05 | |
| Entry, 250 ms, 07-09 London | 0.12 USD | 0.05 | |
| SL fill | 0.25-0.28 USD mean; p90 0.92; max 4.5 | 0.05 | 19 of 146 SLs hit in the NY 08:30/10:00 minutes, at 0.73 USD mean; genuine jumps, the previous tick was still safely on the other side |
| Time exit | about 0.01 USD | 0.05 | engine is conservative here |

- Net slippage component: -0.018R at 250 ms (90% CI -0.025 to -0.011) and -0.0215R at 500 ms.
- Spread scaling (s07; the engine ASK is exactly BID + model):

| Spread multiplier k | Pooled avg R | VAL avg R |
|---|---|---|
| 1 | 0.100 | 0.017 |
| 1.25 | 0.082 | -0.018 |
| 1.5 | 0.075 | -0.017 |
| 2 | 0.048 | -0.053 |

- Other cost variants: uniform slip 0.10 gives 0.084; slip 0.20 on stop fills gives 0.065. NY 08:30 spread spikes stopping out shorts cost about -0.003R.

(b) Broker D1 ATR (s03)
- NY-close (GMT+2/+3) D1 bars: ATR correlates 0.998 with the London-day ATR. 614 of 645 days are shared, and the result is IS +0.1405 / VAL +0.0253. This is not a haircut; the change is noise from 47 swapped trades.
- A GMT+0/+1 server with Sunday D1 bars puts ATR 13% low. Trades rise to 876, and the result is IS +0.118 / VAL -0.124. This is a dangerous implementation trap.
- Best practice: build London-day bars inside the EA.

(c) Minimum lot (s04; 0.01 lot = 1 oz)
- SL in USD: median 6.71, p95 13.84, max 24.28. As a share of price: median 0.46%, p95 0.83%, max 1.44%.
- Minimum equity so the p95 SL fits at 0.01 lot: 1,384 USD at 1% and 2,767 at 0.5% on 2014-2023 prices. Scaled to 3,500 USD gold: 2,897 and 5,793. The max SL needs up to 10,080 at 0.5%.
- Lot rounding under-risks: at 5k USD and 0.5%, realised risk averages 85% of target.
- Recommendation: at least 10k USD at 0.5%, and skip trades below 0.01 lot rather than forcing the minimum.

(d) Server time and DST (s05)
- On a NY+7 server, 169 of 2,594 days (6.5%) have London 00:00 at server 03:00 instead of 02:00.

| EA error | What goes wrong | Pooled avg R |
|---|---|---|
| Hard-coded server hours | 42 trades shift by -1h | 0.121 |
| Fixed GMT+2 server without DST | every BST day shifts by +1h | 0.129 |
| TimeGMT() in the MT5 tester (it equals server time) | sessions land 2-3h early, range spans the halt, n falls to 359 | 0.148 |

- None of these is a systematic loss; ±1h on all days gives 0.136 / 0.122. The damage is that live and tester results stop matching the research trades.
- The EA must compute London time from UTC with explicit UK and US DST rules.

(e) MT5 mechanics (s08, s09)
- Buy stops trigger on ASK against a BID range, and SLs on BID (long) or ASK (short): this matches MT5.
- The level is already crossed at 05:00 London on 3.4% of filter days, so the EA must send a market order. The nearer level is within 0.50 USD on 20% of days, so StopsLevel above 0 forces virtual stops.
- The engine anchors the SL to the fill. An attached pending-order SL costs -0.004R, so the EA should modify the SL after the fill.
- 14 trades fell on early-close days, 5 of them Black Fridays, which a naive EA would hold over the weekend.
- No filter day had both levels in one bar, and there were no entry-bar stop-outs.
- Feed dependence: noise of 0.03, 0.06 and 0.12 USD on M1 highs/lows gives pooled 0.0995, 0.097 and 0.071. HistData and Dukascopy in 2014 share only 31 of 33/38 trade days.

Combined (s10, stacked, pooled / IS / VAL)

| Scenario | Pooled | IS | VAL | Haircut |
|---|---|---|---|---|
| Engine | 0.1038 | 0.1216 | 0.0202 | — |
| CENTRAL (Dukascopy spread, tick slippage at 250 ms, feed noise 0.03, spike, SL modified after fill) | 0.0805 | 0.0973 (t 1.54) | 0.0017 | -0.023R |
| CENTRAL + NY-close ATR | 0.094 | | | |
| RETAIL (spread x1.25, 500 ms, feed noise 0.06) | 0.0595 | 0.0784 | -0.0303 | -0.044R |
| ADVERSE (spread x1.5, 1 s, feed noise 0.12, attached SL) | 0.0169 | 0.0302 | -0.0466 | -0.087R |

Verdict from this lens: WEAK. After realistic execution, the edge is statistically indistinguishable from zero (IS t about 1.3-1.5) and VAL is flat to negative. My best live estimate is +0.01R per trade (range -0.05 to +0.06). If traded at all, it should be only on a raw/ECN account with a correctly built EA: London clock from UTC, London-day ATR, SL modified after fill, and a holiday calendar. Use small risk, fill-quality monitoring and the kill switches listed under guardrails.
