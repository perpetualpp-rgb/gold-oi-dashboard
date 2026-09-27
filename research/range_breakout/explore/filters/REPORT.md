# Axis: filters

Configs tested: 254 (VAL checked: 8). Holdout (2024+) not used.

## Recommendation

No robust edge was found on the day-filter axis, but one family of filters consistently lifts the default Asian breakout from zero to a small positive expectancy. That family is: trade only days where the Asian range is at least 0.3-0.35 x ATR14, and optionally only when ATR14 (as of yesterday) is at or below its own 20-day average.

- **If the EA goes ahead:** freeze exactly two configs for the one-shot holdout test and do not tune further. F2 is the primary (min_w_atr=0.35 plus ATR14 <= SMA20(ATR14), SL 1 x range, no TP, exit 20:00 London, one trade a day). F4 (min_w_atr=0.35 only) is the simpler fallback.
- **Expected edge:** at best about +0.05 to +0.10R per trade after costs, on 50-110 trades a year. That is not statistically established: the best IS t is about 2.6 after roughly 150 distinct configs, and every VAL t is below 1.
- **Cost sensitivity:** the edge is about the size of the costs. It needs a round trip of at most about 0.5 USD/oz (spread about 0.3 + commission 0.07 + slippage). At slip 0.10 and spread +0.10, F1 VAL falls to +0.016R.
- **Drop these filters:** compression/NR (comp_max) hurts, and trend, day-of-week, NFP and month add nothing robust.
- **Keep these exits:** keep TP off and SL at 1 x range width. Every TP tested made results worse.
- **For the EA:** compute ATR14 as a simple average of true range on D1. NY-close broker days give the same results as London days (correlation 0.998). Modify the SL after the fill, as the audit says.
- **Worth combining with other axes:** the vol-regime filter also adds about +0.06R to other Asian-range timings, so it can be combined with the timing and entry findings. It should be judged on the holdout only once.

## Key findings

- No filter or combination reaches statistical significance once the search is accounted for. There are 254 IS evaluations, about 150 of them distinct filter/exit configs; the rest are 21 cost-stress runs, 16 other-timing runs and 12 gross/net decomposition runs, all logged in explore/filters/configs_log.csv. The best IS t is 2.55 (engine ATR) or 2.62 (MT5-style ATR), against a family-wise 5% threshold of about 2.9-3.4. No VAL t exceeds 1. The honest verdict is that there is a plausible, repeatable improvement but no proven edge.
- Costs, not the breakout itself, are the main problem. With zero costs (ASK=BID, no slip, no commission) the default earns +0.099R in IS (t 2.88, 6 of 8 years positive, longs +0.084, shorts +0.114). Costs take about 0.09R per trade on average, falling from 0.14R in the narrowest width/ATR quintile to 0.05R in the widest. Any filter that raises risk per trade in USD keeps more of this small gross edge.
- The classic compression / narrow-range idea is wrong here. comp_max <= 0.8 or <= 1.0 is negative for comp_n 10, 20 and 50 (IS -0.052 to -0.004R, 2-3 of 8 years positive). Only comp <= 0.6 is marginally positive, on about 185 trades with t < 0.6, which is noise. Narrow Asian ranges are the worst days after costs: w_atr <= 0.3 gives -0.074R (t -1.19, 2 of 8 years). The opposite filter (a wider-than-usual range, comp_min) helps modestly, for example comp10 >= 1.0 gives +0.055 (t 1.27), but it is not a clean plateau across comp_n.
- min_w_atr has a plateau from 0.3 to 0.4. IS avg_R is +0.056, +0.075 and +0.072 at 0.3, 0.35 and 0.4 (t 1.46-1.86, 5-6 of 8 years), keeping 34-63% of days. About half the gain is lower cost in R and half is a larger gross edge (gross +0.145 vs +0.058 below 0.35). Shorts carry more of it (IS L +0.034 / S +0.124). It is the most VAL-stable filter: F4 (min_w_atr=0.35) gives VAL +0.069 with both 2022 (+0.080) and 2023 (+0.055) positive.
- Vol regime is the only other consistent effect: breakouts work when daily volatility is not expanding. With ATR14(prev) <= its 20-day SMA the default gives IS +0.085R (t 1.79, 7 of 8 years), against -0.094R (t -2.08) on the complement. The gross split is +0.188 vs -0.018. The relationship is monotonic across quintiles of ATR/SMA50(ATR): +0.107, +0.066, -0.046, -0.025, -0.068. A circular-shift null (which keeps the mask's autocorrelation, IS days only, 286 shifts) gives p=0.003 on its own. The incremental p on top of w_atr >= 0.3 is about 0.06. The 250-day ATR rank bottom quintile is also good (+0.161, 7 of 8 years) but not monotonic. In VAL the effect weakens: F5 gives +0.043 (2022 +0.169, 2023 -0.062).
- The combined plateau is min_w_atr 0.3-0.35 with ATR14 <= SMA20 or SMA50 of ATR14. IS avg_R is 0.111-0.139, t 2.1-2.55, 7-8 of 8 years positive, keeping 27-38% of days (61-83 trades a year). Longs and shorts are both positive in IS, for example F1 L +0.123 / S +0.101, so this is not gold drift. Results are stable across 2014-17 and 2018-21 (F2 +0.139 / +0.138; F1 +0.127 / +0.101). The effect survives slip 0.10 plus spread +0.10 (F2 +0.102 t 1.91; F1 +0.074 t 1.40) and survives MT5-style NY-close daily ATR (F1 +0.128, F2 +0.144; the two ATRs correlate at 0.998).
- VAL results for the 8 pre-declared configs (IS -> VAL avg_R): default +0.008 -> -0.011; F4 w>=0.35 +0.075 -> +0.069; F5 a20<=1 +0.085 -> +0.043; F1 w>=0.3&a20<=1 (primary, chosen before VAL) +0.113 -> +0.039; F2 w>=0.35&a20<=1 +0.139 -> +0.114; F3 w>=0.3&a50<=1 +0.111 -> +0.006; F6 F1+noFri +0.143 -> -0.083 (rejected: the day-of-week overlay was overfit); F1 at stressed costs +0.074 -> +0.016. All VAL t-stats are below 1 (n 102-243). In VAL every variant has longs <= 0 and shorts strongly positive (for example F2 L -0.002 / S +0.286). With about 60 trades per side this is within noise, but it is unlike IS, where both sides were similar.
- Pooled 2014-2023 (the same configs, no retuning): F2 n 593, +0.134R, t 2.72, PF 1.33, maxDD 10R, 8 of 10 years positive. F4 n 1057, +0.074R, t 2.03. F1 n 797, +0.100R, t 2.11. Default n 2306, +0.004R.
- The trend filter (prev close vs SMA20/50/100/200) points the right way but is tiny. With-trend trades give +0.025 to +0.029R and against-trend trades -0.016 to -0.029R for every N; t is at most 0.63 and 4-5 of 8 years are positive. Most of the difference is longs against the trend (-0.065 to -0.092). Adding trend to the width and vol filters lowers t, so it is not additive. trend_mode=1 (counter-trend) is always worse.
- Day of week is weak and not robust: Mon +0.084, Tue +0.030, Wed -0.065, Thu +0.065, Fri -0.075R (2-6 of 8 years positive). The no-Friday overlay looked good in IS (+0.143) but failed VAL (-0.083). skip_nfp has no effect (+0.009 vs +0.008): NFP Fridays (-0.020, n 78) are not worse than other Fridays (-0.090). Month-of-year effects are noise.
- Exit interaction (sl_k 0.5/0.75/1 x tp_r 0/1/2/3, across 5 filter sets): a TP hurts in every filter set, tp=1 the most (default at tp1 is -0.037, t -1.70). sl_k=1 with no TP gives the best t for every filter. The edge, such as it is, sits in the right tail of time-exit winners. Filtered sets beat the unfiltered one in all 12 exit cells, which is evidence that the filter effect is not an artefact of one exit.
- Other timings: the vol-regime filter adds about +0.06 to +0.07R to other Asian-range variants (range 0-8 London with entry_end 13: +0.010 -> +0.077; range 1-7: +0.002 -> +0.063). It does not rescue London ranges (07-08 London: -0.040 -> +0.017; 08-13 London: -0.039 -> -0.001).
- Report files: the system rules for this subagent forbid writing report .md files (the audit agent's REPORT.md write was refused the same way), so explore/filters/REPORT.md was NOT written. Its full content is in this output. Per-stage tables are in explore/filters/out_s01_conditional.txt through out_s09_pooled.txt, every IS config is in configs_log.csv, and the 8 VAL configs are in val_log.csv.

## Candidates

### F2: w_atr>=0.35 AND ATR14 <= SMA20(ATR14)  [best on IS and VAL, but it is the IS peak and removes 73% of days]

- Params: `{"min_w_atr": 0.35, "custom_day_filter": "atr14_prev[d] <= mean(atr14_prev[d-19..d]) (rolling 20 London trading days, min_periods 12); explore/filters/features.py day_features()['atr_vs_mean20'] <= 1.0, applied with run_mask (post-hoc day mask, verified identical to the engine mask). All other Params default (range 0-7, entry_end 12, exit 20, sl_ref 0, sl_k 1, tp_r 0, max_trades 1, default costs)."}`
- IS: n 491, avg_R 0.1386, win_rate 0.483, PF 1.345, t_stat 2.55, trades_per_year 62.5, maxDD_R 8.5
- VAL: n 102, avg_R 0.114, win_rate 0.461, PF 1.263, t_stat 0.96, trades_per_year 51.5, maxDD_R 10
- IS years positive: 7; long avg_R IS 0.1535, short 0.1226
- Two a-priori sensible, independent mechanisms: wide range vs ATR lowers cost in R and has a higher gross edge, and a quiet or contracting vol regime gives follow-through instead of whipsaw. It sits on a plateau (neighbours w 0.3/0.4 and SMA50 are all +0.10 to +0.14R in IS), is positive in 7 of 8 IS years for both sides, and survives stressed costs and MT5-style ATR. Caveats: it keeps only 27% of days, which is over the 70% removal guard, and IS t 2.55 is not significant after about 150 distinct configs.

### F4: w_atr>=0.35 (engine-native, simplest; most VAL-stable)

- Params: `{"min_w_atr": 0.35}`
- IS: n 860, avg_R 0.0752, win_rate 0.456, PF 1.179, t_stat 1.86, trades_per_year 108.4, maxDD_R 12.1
- VAL: n 197, avg_R 0.0685, win_rate 0.431, PF 1.158, t_stat 0.81, trades_per_year 99.4, maxDD_R 12.1
- IS years positive: 6; long avg_R IS 0.0337, short 0.1237
- It is on a plateau (min_w_atr 0.3/0.35/0.4 give +0.056/+0.075/+0.072), keeps 47% of days, and has a clear mechanical rationale: cost in R is roughly halved, and the gross edge is also higher on wide-range days (8 of 8 years positive gross). IS and VAL agree best of all candidates (+0.075 -> +0.069), with both VAL years positive. It is weak: longs are near zero in IS and negative in VAL, and it is not significant.

### F1: w_atr>=0.3 AND ATR14 <= SMA20(ATR14)  [primary, declared before VAL as the centre of the plateau]

- Params: `{"min_w_atr": 0.3, "custom_day_filter": "atr_vs_mean20 <= 1.0 (as in F2)"}`
- IS: n 655, avg_R 0.1128, win_rate 0.45, PF 1.249, t_stat 2.12, trades_per_year 83.4, maxDD_R 12.1
- VAL: n 142, avg_R 0.039, win_rate 0.444, PF 1.083, t_stat 0.39, trades_per_year 71.6, maxDD_R 17.6
- IS years positive: 8; long avg_R IS 0.1235, short 0.1013
- It is the centre of the IS plateau, positive in all 8 IS years with both sides positive, and removes only 64% of days. VAL shrank to +0.039, with 2023 negative, so the out-of-sample evidence is weak.

### F5: ATR14 <= SMA20(ATR14) only (vol regime alone)

- Params: `{"custom_day_filter": "atr_vs_mean20 <= 1.0; all Params default"}`
- IS: n 1017, avg_R 0.0851, win_rate 0.41, PF 1.162, t_stat 1.79, trades_per_year 129.4, maxDD_R 21.2
- VAL: n 243, avg_R 0.0433, win_rate 0.403, PF 1.08, t_stat 0.47, trades_per_year 122.4, maxDD_R 29.5
- IS years positive: 7; long avg_R IS 0.061, short 0.112
- It has the strongest stand-alone statistical evidence on this axis (circular-shift p=0.003, a monotonic quintile pattern, complement -0.094R), but the effect decays in 2018-21 (+0.035) and in VAL (+0.043). It is shown to isolate the vol-regime component.

### F3: w_atr>=0.3 AND ATR14 <= SMA50(ATR14)  (lookback neighbour of F1)

- Params: `{"min_w_atr": 0.3, "custom_day_filter": "atr14_prev / mean(atr14_prev over 50 days, min_periods 30) <= 1.0"}`
- IS: n 687, avg_R 0.1109, win_rate 0.448, PF 1.242, t_stat 2.11, trades_per_year 87.8, maxDD_R 16.4
- VAL: n 156, avg_R 0.006, win_rate 0.397, PF 1.012, t_stat 0.06, trades_per_year 78.7, maxDD_R 16.2
- IS years positive: 7; long avg_R IS 0.13, short 0.09
- Robustness neighbour. VAL is flat (+0.006), which says the vol-regime increment is fragile to the lookback choice out of sample.

### F6 (REJECTED): F1 + no Friday

- Params: `{"min_w_atr": 0.3, "dow_mask": [1, 1, 1, 1, 0], "custom_day_filter": "atr_vs_mean20 <= 1.0"}`
- IS: n 542, avg_R 0.1427, win_rate 0.456, PF 1.324, t_stat 2.41, trades_per_year 69, maxDD_R 10.5
- VAL: n 114, avg_R -0.083, win_rate 0.421, PF 0.835, t_stat -0.83, trades_per_year 57.5, maxDD_R 23.7
- IS years positive: 8; long avg_R IS 0.168, short 0.117
- Included to test whether a weak day-of-week effect survives out of sample. It failed (VAL -0.083), which confirms the day-of-week effect is noise. Do not use.

## Engine / data notes

- No new engine bugs were found on this axis. The 21/21 tests in test_engine.py pass.
- Not a bug, a missing feature: the engine has no hook for custom day filters such as the ATR-regime filter (ATR14 vs its own N-day mean). I applied it as a post-hoc day mask on the engine's trades (explore/filters/features.py run_mask). For symmetric masks this is exactly equivalent to the engine's own mask: verify_posthoc() gives identical trades for comp20<=1.0 (n 1038) and comp50<=0.8 (n 603). It would NOT be equivalent for asymmetric (direction-dependent) filters. If the regime filter goes forward, consider adding something like Params.atr_ma_n / atr_ma_max to engine.py, lagged the same way as the other daily features when range_end < 0.
- Repository hygiene: commit 0a8f132 ('Engine audit: fix 9 backtest bugs...') snapshotted my in-progress explore/filters files, including a 534 KB scratch pickle s01_trades.pkl (IS trades only). I have since deleted that pickle and renamed the out_*.md table dumps to out_*.txt in the working tree, so git status shows them as deleted or modified. I made no commits.
- explore/filters/REPORT.md was not written, because the subagent rules forbid writing report .md files; the audit agent's write was refused the same way. The report content is in this structured output. Per-stage tables are in explore/filters/out_s01_conditional.txt through out_s09_pooled.txt, the IS config log is configs_log.csv (254 rows) and the VAL log is val_log.csv (8 rows).
- Data caveat relevant to filters: the modelled spread is constant within each London hour, so filters based on news or spread conditions, and max_spread, cannot be evaluated. The filtered strategies are cost-sensitive, with about 0.06-0.08R of cost per trade on the wide-range days they keep.
