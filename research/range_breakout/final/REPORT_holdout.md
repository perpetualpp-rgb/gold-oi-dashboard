# Holdout (2024-01-01 .. 2026-09-18), one-shot

candidates.json hash verified: True

**Verdict:** NOT CONFIRMED (inconclusive, leaning negative for the filter hypothesis).

The PRIMARY made +0.053R per trade on 210 holdout trades: t 0.67, direction-null p 0.23, bootstrap P(mean <= 0) 0.24, PF 1.12, with one of three years negative. That is statistically indistinguishable from zero and from the IS estimate, and no better than the unfiltered baseline (+0.050R) over the same period. The primary's specific claim, that wide Asian ranges in a calm ATR regime add gross edge, did not replicate: the gross excess over the baseline was +0.13R in IS and is -0.01R in the holdout.

The FALLBACK did better: +0.073R, t 1.26, direction null p 0.013, all three years positive, robust to the specified cost stresses. Its net profitability is still not significant (P(mean <= 0) about 0.09). Most of its margin comes from costs being about 0.03R instead of about 0.065R in IS, and it becomes a near-unfiltered strategy in 2025-26 because the width filter passes about 60% of days. Switching from the primary to the fallback because of this holdout would turn the holdout into a selection set, so it is no longer an independent confirmation.

Neither candidate has a demonstrated edge that survives realistic, volatility-scaled costs. Only a small-size forward/demo test with real broker spreads, slippage and commission is justified, not live capital on the strength of the backtest. No parameter changes are proposed from the holdout.

## Results

### PRIMARY re5_w030_a20_W1.00

- stats: `{"period": "2024-01-01..2026-09-18 (2.71 y)", "n": 210, "trades_per_year": 77.6, "win_rate": 0.457, "avg_R": 0.0534, "total_R": 11.2, "t_stat": 0.67, "PF": 1.12, "sharpe_ann": 0.41, "maxDD_R": 16.5, "avg_win_R": 1.09, "avg_loss_R": -0.819, "usd_per_oz": 36.9, "exit_reasons": {"time": 128, "sl": 82}, "top5_removed_avg_R": -0.032, "top10_removed_avg_R": -0.091, "boot_ci90_avg_R": [-0.076, 0.177], "boot_P_mean_le_0": 0.237, "gross_avg_R": 0.0707, "cost_R_per_trade": 0.034}`
- by year: 2024: n 57, avg_R +0.161, sum +9.2R, t 0.94 (L 38 @ +0.107, S 19 @ +0.269); 2025: n 89, avg_R -0.080, sum -7.2R, t -0.75 (L 37 @ +0.117, S 52 @ -0.220); 2026 YTD (to 18 Sep): n 64, avg_R +0.143, sum +9.2R, t 0.98 (L 30 @ -0.083, S 34 @ +0.343)
- long/short: long n 105 avg_R +0.056 (t 0.54); short n 105 avg_R +0.051 (t 0.42). Opposite direction at the same moment: longs -0.100, shorts -0.022.
- cost stress: default +0.0534 (t 0.67); slip 0.10 +0.0495; spread +0.10 +0.0521; both +0.0482 (t 0.61); gross (no costs) +0.0707. At the IS-average cost in R (0.080R instead of the holdout's 0.034R) the net would be about -0.009R.
- null: coin p=0.226 (null mean -0.002, sd 0.071, q95 +0.110, z 0.78); shuffle p=0.207. 1000 perms, seed 1.

### FALLBACK re5_w035_nor_W1.00

- stats: `{"period": "2024-01-01..2026-09-18 (2.71 y)", "n": 324, "trades_per_year": 119.7, "win_rate": 0.503, "avg_R": 0.0733, "total_R": 23.8, "t_stat": 1.26, "PF": 1.191, "sharpe_ann": 0.77, "maxDD_R": 14.1, "avg_win_R": 0.908, "avg_loss_R": -0.772, "usd_per_oz": 717.5, "exit_reasons": {"time": 219, "sl": 105}, "top5_removed_avg_R": 0.012, "top10_removed_avg_R": -0.026, "boot_ci90_avg_R": [-0.014, 0.162], "boot_P_mean_le_0": 0.085, "gross_avg_R": 0.0936, "cost_R_per_trade": 0.028}`
- by year: 2024: n 82, avg_R +0.068, sum +5.6R, t 0.56 (L 46 @ -0.036, S 36 @ +0.202); 2025: n 146, avg_R +0.018, sum +2.7R, t 0.21 (L 78 @ +0.108, S 68 @ -0.084); 2026 YTD: n 96, avg_R +0.161, sum +15.5R, t 1.56 (L 47 @ +0.173, S 49 @ +0.150)
- long/short: long n 171 avg_R +0.087 (t 1.19); short n 153 avg_R +0.058 (t 0.63). Opposite direction: longs -0.150, shorts -0.148.
- cost stress: default +0.0733 (t 1.26); slip 0.10 +0.0701; spread +0.10 +0.0721; both +0.0689 (t 1.19); gross +0.0936. At the IS-average cost in R (0.065R) the net would be about +0.029R.
- null: coin p=0.013 (null mean -0.037, sd 0.053, q95 +0.048, z 2.10); shuffle p=0.013.

### BASELINE (range 00-07, no filters, engine default)

- stats: `{"period": "2024-01-01..2026-09-18 (2.71 y)", "n": 572, "trades_per_year": 211, "win_rate": 0.469, "avg_R": 0.0505, "total_R": 28.9, "t_stat": 1.06, "PF": 1.121, "sharpe_ann": 0.64, "maxDD_R": 21.8, "usd_per_oz": 1031.1, "top10_removed_avg_R": -0.023, "boot_ci90_avg_R": [-0.026, 0.126], "boot_P_mean_le_0": 0.14, "gross_avg_R": 0.0833, "cost_R_per_trade": 0.037}`
- by year: 2024: n 229, +0.095 (t 1.06); 2025: n 213, -0.053 (t -0.78); 2026 YTD: n 130, +0.142 (t 1.72)
- long/short: long n 325 +0.106 (t 1.66); short n 247 -0.022 (t -0.31)
- cost stress: default +0.0505; slip 0.10 +0.0426; spread +0.10 +0.0417; both +0.0338 (t 0.71); gross +0.0833. At the IS cost in R (0.090) the net would be about -0.007R.
- null: coin p=0.008; shuffle p=0.008

## Filter activity

Share of valid London days traded (IS 2014-21 / VAL 2022-23 / holdout 2024-26, with yearly values 2024, 2025, 2026). Primary: 0.260 / 0.220 / 0.299 (0.220, 0.345, 0.346). Fallback: 0.311 / 0.285 / 0.462 (0.317, 0.566, 0.519). Baseline: 0.892 / 0.928 / 0.815 (0.884, 0.826, 0.703).

Filter pass rates (range 00-05) for IS / VAL / holdout. w/ATR >= 0.30: 0.514 / 0.441 / 0.663, and 0.76-0.80 in 2025-26. w/ATR >= 0.35: 0.359 / 0.315 / 0.533, and 0.63 in 2025-26. ATR-regime (ATR14_prev <= its 20-day mean): 0.555 / 0.524 / 0.518. Both primary filters together: 0.288 / 0.245 / 0.332.

Market regime (IS mean -> 2024 / 2025 / 2026):
- Gold close: 1397 -> 2389 / 3447 / 4558.
- 00-05 range width in USD: 6.3 -> 11.7 / 26.5 / 56.4.
- ATR14: 18.1 -> 32.7 / 58.8 / 127.5.
- Width/ATR: 0.351 -> 0.349 / 0.454 / 0.452.
- Width in basis points of price: 44 -> 48 / 75 / 123.
- Modelled spread over 05-12 London: 0.30 -> 0.37 / 0.57 / 0.61 USD.
- Real Dukascopy sample days agree with the spread model, which was calibrated on them: 2024 0.36, 2025 0.58, 2026 0.62 USD.
- Average risk (1R) for the primary: 6.9 USD IS -> 13.5 / 26.2 / 48.1.
- Round-trip cost per primary trade in R: 0.080 IS, 0.062 VAL, then 0.046 / 0.034 / 0.019.

Data coverage in the holdout is normal (median 1200 M1 bars per 00-20 session, at most 1.1% of days short).

In short, 2025-26 is a very different regime: gold roughly 3x the IS price, about 4x the volatility, and Asian ranges wider relative to ATR. The width filters stopped being selective (the fallback trades about 55% of days instead of 31%), and fixed-USD costs shrank to about 1/2 to 1/4 of their IS size in R.

## Comparison to expectation

What IS/VAL predicted per trade, with the 90% range of the stationary-bootstrap mean (mean block 10 days, 5000 resamples):
- Primary: IS +0.122R (90% CI +0.025..+0.221, se 0.060), VAL +0.020, IS+VAL +0.104 (CI +0.018..+0.194).
- Fallback: IS +0.132 (CI +0.046..+0.214), IS+VAL +0.115.
- Baseline: IS +0.008, IS+VAL +0.004.

Predictive intervals for a holdout of the realised size were built by stationary bootstrap from the IS trade process, with the same number of trades as the holdout.

Primary (n=210):
- If the true edge equals IS, the 90% interval is -0.033..+0.291. The realised +0.053 sits at the 25th percentile, so it is INSIDE (IS+VAL reference: 30th percentile).
- If the true edge is zero, the 90% interval is -0.148..+0.166. The realised value sits at the 72nd percentile, also inside.
- The holdout has too little power (se about 0.075R) to tell the IS edge from no edge.

Fallback (n=324):
- If the edge equals IS, the 90% interval is +0.018..+0.248 and the realised +0.073 is at the 19th percentile, inside (IS+VAL: 28th percentile).
- If the edge is zero, the 90% interval is -0.113..+0.113 and the realised value is at the 85th percentile.

Baseline: the realised +0.050 is at the 77th percentile of its own IS predictive, better than its IS.

Three points below the headline numbers:
1. The filter's gross excess did not replicate. Primary gross minus baseline gross was +0.135R in IS and is -0.013R in the holdout. For the fallback it went from +0.105 to +0.010. The gross edge fell from 0.233 to 0.071 (primary) and from 0.203 to 0.094 (fallback). The unfiltered breakout's gross follow-through held up (IS 0.099, VAL 0.058, holdout 0.083). The primary did no better than the naive baseline in the holdout (net +0.053 vs +0.050).
2. The positive net holdout numbers owe a lot to costs falling in R terms. Costs are fixed in USD (spread about 0.4-0.6, slip 0.05, commission 0.07 per oz) while 1R grew 4-7x. At IS-level cost in R, the primary would be about -0.009R, the fallback about +0.029R and the baseline about -0.007R. The requested stresses (+0.10 slip or spread) are tiny next to a 27-48 USD risk, so they barely move the results. Real slippage in 2025-26 volatility is probably larger than 0.05 USD.
3. The primary depends on its tail: removing its top 10 trades gives -0.091R. It lost in 2025 (-0.080), driven by shorts (-0.220), and its holdout drawdown (16.5R in 2.7 years) matches its whole 8-year IS drawdown (16.1R).

Pooled for information only (not a test): the primary over IS+VAL+holdout is about +0.091R per trade.

This is consistent with the pre-holdout skeptical prior. The DSR of 0.18-0.35 for N_eff 50-200, the family p of 0.161 and the VAL result near zero all pointed to a heavily shrunk true edge, and the holdout lands between zero and the IS estimate.

## Full report

HOLDOUT REPORT: XAUUSD Asian-range breakout. This was the one and only holdout look, 2024-01-01..2026-09-18 (last bar 2026-09-18 20:58 UTC, 2.71 years).

Provenance
- final/candidates.json exists. sha256 = 8c821e7b1ea817d9b214ba5b70df52d4bb23ccf45b585c06bccfebd13896c1b7.
- The candidates were loaded only from that file, and nothing was re-derived or changed.
- engine.py sha256 7eb6bb0a...a4579 and test_engine.py c4cf03db...b3aa7 match the frozen hashes. The script asserts this. engine.py was not edited.
- Sanity check: IS and VAL n and avg_R for primary, fallback and baseline reproduce the frozen is_val_stats exactly.
- Only three configs were run on the holdout: primary, fallback and baseline. The only variants were their own cost-stress runs (slip 0.10, spread +0.10, both, and gross for decomposition).
- The holdout was run with engine.holdout(p). The script checks that it is identical to engine.run(p, start='2024-01-01').
- Null test: null.null_test refuses dates from 2024 on, so the same method was applied directly. That is null.both_ways on the holdout trades, with the re-walker checked to reproduce the engine exactly, then null._perm_block with 1000 permutations, seed 1, coin and shuffle. null.py was not modified.

Headline, holdout net per trade (R = planned stop distance; costs 0.07 commission, 0.05 slip, modelled spread)
| Config | n | Trades/yr | avg_R | t | PF | Win rate | maxDD | Coin-null p | Bootstrap 90% CI | Top-10 trades removed |
|---|---|---|---|---|---|---|---|---|---|---|
| Primary | 210 | 77.6 | +0.053 | 0.67 | 1.12 | 45.7% | 16.5R | 0.226 | -0.076..+0.177 | -0.091 |
| Fallback | 324 | 119.7 | +0.073 | 1.26 | 1.19 | 50.3% | 14.1R | 0.013 | -0.014..+0.162 | -0.026 |
| Baseline | 572 | 211.0 | +0.050 | 1.06 | 1.12 | 46.9% | 21.8R | 0.008 | not reported | -0.023 |

By year (avg_R and trade count):
| Config | 2024 | 2025 | 2026 YTD |
|---|---|---|---|
| Primary | +0.161 (57) | -0.080 (89) | +0.143 (64) |
| Fallback | +0.068 (82) | +0.018 (146) | +0.161 (96) |
| Baseline | +0.095 (229) | -0.053 (213) | +0.142 (130) |

Long/short, holdout:
- Primary: long +0.056 (105 trades), short +0.051 (105). In 2025 shorts were -0.220.
- Fallback: long +0.087 (171), short +0.058 (153).
- Baseline: long +0.106, short -0.022.

Cost stress (both = slip 0.10 and spread +0.10):
| Config | Default | Slip 0.10 | Spread +0.10 | Both | Gross |
|---|---|---|---|---|---|
| Primary | 0.053 | 0.050 | 0.052 | 0.048 | 0.071 |
| Fallback | 0.073 | 0.070 | 0.072 | 0.069 | 0.094 |
| Baseline | 0.050 | 0.043 | 0.042 | 0.034 | 0.083 |

These stresses barely move the results because 1R is now 27-48 USD, against 7 USD in IS.

Filter activity and regime: see the filter_activity field. In brief, gold went from about 1400 to 2400/3450/4560, ATR14 from 18 to 33/59/127, and 00-05 width/ATR from 0.35 to 0.45 in 2025-26. The min_w_atr filters therefore became much less selective: the fallback traded 57% and 52% of days in 2025-26, against 31% in IS. Costs in R fell from 0.080 (IS) to 0.046/0.034/0.019. Real Dukascopy sample-day spreads (0.36/0.58/0.62 USD) match the spread model. Data coverage is normal.

Comparison to expectation: see comparison_to_expectation.
- Both candidates fall inside their IS-based 90% predictive intervals, at the 25th and 19th percentiles. They also fall inside the zero-edge interval, so the holdout cannot tell the IS edge from no edge.
- The mechanism the filters were chosen for did not replicate. The primary's gross excess over the baseline went from +0.135R in IS to -0.013R in the holdout.
- At IS-level cost in R, the net holdout would be about -0.009R (primary), +0.029R (fallback) and -0.007R (baseline).

Verdict: see the verdict field. The PRIMARY is not confirmed. The FALLBACK looks better, but its result is not significant for net profit and is flattered by costs shrinking in R terms. Picking it now would be holdout selection. Only a small forward/demo test with real broker costs is justified. No parameter changes are proposed.

Files in /home/user/gold-oi-dashboard/research/range_breakout/final/holdout/:
- run_holdout.py: the main one-shot script. run_holdout.log holds its full printed output.
- holdout_results.json: all statistics, null tests, bootstrap and predictive intervals, and filter activity.
- trades_holdout_primary.csv, trades_holdout_fallback.csv, trades_holdout_baseline.csv
- regime_filter_activity_by_year.csv
- cost_parity_and_gross_decomposition.json
- spread_check.py and spread_check.log, with spread_real_vs_model_by_year.csv and coverage_by_year.csv
