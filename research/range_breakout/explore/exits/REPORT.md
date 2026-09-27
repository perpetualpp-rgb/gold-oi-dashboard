# Axis: exits

Configs tested: 9529 (VAL checked: 6). Holdout (2024+) not used.

## Recommendation

No robust edge on this axis. The exit structure only reshapes the R distribution: TPs raise win rate and cut skew, while wide trails and time exits keep the fat right tail. It cannot turn the naive Asian-range breakout into a profitable strategy. The best of 4,756 net-cost IS configs has t 0.79, nothing survives slip 0.10 or spread +0.10, and all 4 VAL finalists are negative. The entry does have a small gross continuation: +0.10R per trade at zero cost, IS t 2.9; MFE +0.15R over the mirror trade; drift peaking at +0.04R 1-2 h after entry. But it is smaller than the ~0.09R round-trip cost, weaker in VAL (gross t 0.84), and concentrated in shorts and in 2015. For the EA, whatever entry or filter the other axes find, choose exits for cost efficiency and stability, not for edge:
- Stop: ATR14-based, 0.75-1.5 x ATR14(prev). This gives the lowest cost in R (0.02-0.04R), the smallest drawdown and a flat parameter plateau. It beats range-width stops, whose cost in R explodes on narrow-range days.
- Time exit: 18-21h London.
- Optional: BE at 1R plus a 1.5-2R trail. Roughly neutral in mean, but it cuts drawdown a little.
- Avoid: TPs of 1-2R (-0.02 to -0.04R vs no TP), BE at 0.5R, trails under 1R (these act as a hidden tight stop), stops under 0.5x width or 0.25 ATR (cost 0.12-0.20R), and holding caps or clock exits before 13h.
- Implement the SL/trail as a post-fill modification measured from the actual fill, as the engine does.
Edge must come from entry selection, filters or lower costs. Costs would need to fall by roughly 40-50% for the IS gross continuation to matter, and that continuation is itself not confirmed in VAL.

## Key findings

- VERDICT: changing the exits alone does not create an edge from the naive entry; it only reshapes the distribution. I tested 4,756 net-cost IS configs: the brief's full grid (4,500), 216 wider-stop configs, 34 custom exits, 5 early exit times, and the default. The best t_stat is 0.79. No config reaches t>1, and only 10% have avg_R>0. Win rate ranges from 0.20 to 0.60 and skew from -0.1 to +3.2, but the mean stays at about 0 or below. All 4 VAL finalists are negative (-0.006 to -0.027R).
- The entry does carry a small gross continuation, but it is smaller than costs. I reran the same 4,500-config grid at zero cost (commission 0, slip 0, ASK=BID). All 4,500 are positive, t 0.83 to 4.23 (median 2.73), with gross avg_R about +0.10R at the default stop (t 2.88). The median ratio of gross edge to cost is 0.69 and the maximum is 1.28. Cost is about 0.09R per trade at 1x range width, 0.18R at 0.5x width and 0.20R at 0.15 ATR. Because exits cannot change the entry's gross drift, the best net result is about zero.
- Mid-price drift in the breakout direction (no stop, no costs, IS n=1828), in R = range width: +0.016 at 1 min (t 6.1), +0.021 at 5 min (t 5.0), +0.040 at 60 min (t 4.0), +0.044 at 120 min (t 3.3), +0.026 at 240 min (t 1.4), +0.069 at 20:00 (t 1.6). The drift peaks at 1-2 h after entry at about half the round-trip cost (0.082R median, 0.090R mean), then partly reverts. Longs and shorts both show it; shorts are slightly stronger.
- Barrier test on mid prices (no costs): P(+1R before -1R) = 0.530 (z 2.3 vs 0.5). Longs 0.511 (z 0.6), shorts 0.549 (z 2.7). MFE before a 1R stop: 1.241R in the breakout direction vs 1.089R for the opposite (mirror) trade at the same moment, +0.152R (t 3.0). Longs +0.07 (t 1.0), shorts +0.24 (t 3.4). So most of the MFE is plain volatility that the mirror trade also sees. The directional part is about 0.15R of the 1.2R MFE.
- Default R distribution (IS): mean +0.0078, median -0.58, skew 2.03, excess kurtosis 6.4, p90 1.84, p95 2.77, p99 4.92. The top 10% of trades produce 59% of all positive R. 47.8% of trades exit at the full stop; all profit comes from the 20:00 time exit.
- MFE/MAE at the default exit: the average MFE before the stop is 1.165R (median 0.74). Share of trades reaching +0.5/+1/+2/+3/+4R before the stop: 61/41/18/9/4%. Of the 874 stopped trades, 33% had first been +0.5R and 13% +1R. The median MFE is reached 264 min after entry, and MFE clusters at 07-08h and 13-14h London. Median MAE before MFE is 0.29R. Rule-based exits capture at most 2% of MFE net: trail 2R gives 0.023R against a perfect ex-post exit of 1.17R.
- Which exit captures MFE best, default stop, IS: on trades reaching MFE >= 1R, trail 2R keeps 1.13R per trade (49% of their MFE), time-only 1.10R, BE1+trail1.5 1.10R, TP3 1.10R, TP1 0.99R, trail 1R 0.84R, BE 0.5R 0.79R. Wide trails and wide or no TPs capture the most because the right tail pays for everything. Tight TPs (1-2R) cut the tail: TP1 lowers skew to 0.04 and raises win rate to 48%, but costs 0.045R per trade vs no TP.
- Profit share by exit reason, default stop, exit 20:00: TP1 94% of positive R from TP. TP2 70% TP / 30% time. TP3 49/51. Trail 1R 64% trail / 36% time. Trail 2R 16% trail / 84% time. BE1+trail1.5 33% trail / 67% time. With any TP of 2R or more, or a trail of 1.5R or more, most profit still comes from the time exit, i.e. from holding the rare trend days.
- Marginal effects, mean net t over the rest of the grid. Stop width is the only knob with a monotone effect, because cost in R scales as 1/stop. ATR stops: 0.15 -> -5.7, 0.25 -> -2.1, 0.35 -> -1.5, 0.5 -> -0.7, 0.75 -> +0.2. Width stops: 0.5 -> -5.0, 0.75 -> -2.2, 1.0 -> -1.2, 1.5 -> -0.9. Opposite-edge stop -1.3 (the same as 1x width). TP: none -1.5 (best), 1R -3.0 (worst). BE: 1R -1.6, 0.5R -2.2 (BE 0.5 hurts). Trail: 0.5R -3.7 (worst), 0 / 1.5 / 2 about -1.5. Exit time: 18-21h about -1.9, 14h -2.3. Early exits at 9-13h all have t -2.5 to -5.4.
- Exits the engine cannot express (own simulator exitsim.py, which matches engine R and exit bars exactly on 7 configs). Holding-time caps of 15/30/60/120/180/240/360 min are all net negative: at 1x width -0.072 to -0.033R (t -12.6 to -1.5); at ATR0.75 -0.028 to -0.009R. Time-stops (exit if not above 0R or 0.25R after 15/30/60/120 min) are negative except ATR0.75 with 120 min and <0R: +0.0046R, t 0.35. Capturing the 1-2 h drift peak fails because that peak (0.04R) is below cost (0.09R).
- Wider stops (extension): ATR 1/1.5/2/3 and 2/3x width. Net avg_R tends to +0.002 to +0.004R as the stop becomes irrelevant, which is a pure time exit (ATR3: 0% stopped, +0.0020R, t 0.45). Gross is still t about 3. The time-exit-only version of the entry is marginally above zero in IS and -0.006R in VAL.
- Robustness of the top net configs: 1x width + trail 2R (IS t 0.70) is not a plateau. Its grid neighbours average t -0.15 (min -1.70), and trail 1.5R gives 0.24. The ATR0.75 family, with or without BE 1R and trail 1.5-2R, exit 18-21h, is a flat plateau with neighbours averaging t 0.38-0.43. The plateau is flat because the edge is about 0 (+0.010R), not because it is good. In every top config the result comes from shorts (S_t about 1.0, L_t about 0), against gold's upward drift. That is not significant after about 4,750 tests.
- Cost stress (IS): every finalist goes to zero or below. F1 (trail 2R) +0.0226 -> +0.0050 at slip 0.10, -0.0003 at spread +0.10, -0.0183 with both. F2 (ATR0.75 BE1 trail1.5) +0.0115 -> +0.0029 / -0.0008 / -0.0084. F3 (ATR1.5 time exit) +0.0034 -> -0.0008 / -0.0025 / -0.0066. Default +0.0078 -> -0.0109 / -0.0145 / -0.0321.
- VAL 2022-23, 6 configs. Net: default -0.0105 (t -0.16), F1 -0.0271 (t -0.46), F2 -0.0059 (t -0.17), F3 -0.0062 (t -0.33). All four VAL longs are negative and shorts are 0 to +0.08. Zero-cost diagnostics: default gross +0.058R (t 0.84; IS +0.099, t 2.88) and ATR1.5 time-exit gross +0.009R (t 0.46; IS +0.026, t 2.91). The gross continuation weakens out of sample. Gross IS by year is positive in 6/8 years, with 2015 contributing +0.31R.
- Count, for the multiple-testing correction: 9,529 distinct evaluations (out/configs_log.csv has 9,530 rows; the default appears twice). They are 4,756 net-cost IS search configs, 4,755 zero-cost diagnostic IS runs, 12 IS cost-stress runs and 6 VAL runs. For a correction, the relevant family is the 4,756 net configs. Only 3,558 of the 4,500 brief-grid configs are behaviourally distinct; for example, TP 1R makes BE 1R and trails of 1R or more irrelevant.

FULL REPORT.md CONTENT (not written to disk, because subagents are instructed not to write report .md files; please save it as explore/exits/REPORT.md):

# Exits & risk axis: XAUUSD Asian-range breakout

Setup: default timing (range 00:00-07:00 London, stop entries at the range edges, entries until 12:00, 1 trade/day), engine default costs. Search on IS 2014-2021 only. VAL 2022-2023 for 6 configs. Holdout never touched: every run uses end=IS_END or VAL_END, and engine.holdout() is never called.

## Verdict
The exit structure alone does not create an edge from the naive entry; it only reshapes the R distribution. Across 4,756 net-cost IS configs, the best t is 0.79, none reaches t>1, and all 4 VAL finalists are negative. The same grid at zero cost is positive everywhere (t 0.8-4.2, median 2.7): the entry has a small gross continuation of about +0.05-0.10R per trade at 1x width, but it is smaller than the ~0.09R cost, and no exit keeps more of it than costs take.

## 1. Default R distribution (IS n=1828)
| mean | median | skew | ex.kurt | p90 | p95 | p99 | stopped | top-10% share of +R |
|---|---|---|---|---|---|---|---|---|
| +0.0078 | -0.58 | 2.03 | 6.4 | 1.84 | 2.77 | 4.92 | 47.8% | 59% |

## 2. MFE/MAE (default stop, re-walked M1 bars; s01_mfe_mae.py)
- MFE before the stop: mean 1.165R, median 0.74. Share reaching +k before -1R: 0.25:75%, 0.5:61%, 1:41%, 1.5:27%, 2:18%, 3:9%, 4:4%. Longs 39% and shorts 43% reach 1R.
- Of the 874 stopped trades, 33% had been +0.5R and 13% +1R.
- Median time to MFE is 264 min; median MAE before MFE is 0.29R.

| mid drift in breakout dir (no costs) | 1m | 5m | 15m | 30m | 60m | 120m | 240m | 20:00 |
|---|---|---|---|---|---|---|---|---|
| mean R | .016 | .021 | .019 | .026 | .040 | .044 | .026 | .069 |
| t | 6.1 | 5.0 | 3.2 | 3.5 | 4.0 | 3.3 | 1.4 | 1.6 |

- Cost is 0.082R median and 0.090R mean. Mid barrier P(+1R before -1R) = 0.530 (z 2.3); longs 0.511, shorts 0.549.
- MFE in the breakout direction vs the mirror trade: 1.241 vs 1.089R (+0.15, t 3.0; longs +0.07, shorts +0.24).

## 3. Brief grid (s02, 4,500 net + 4,500 zero-cost)
| stop | mean net avgR | mean net t | max net t | mean gross avgR | cost R |
|---|---|---|---|---|---|
| W0.5 | -0.112 | -5.0 | -0.31 | .064 | .178 |
| W0.75 | -0.045 | -2.2 | 0.10 | .076 | .122 |
| W1.0 | -0.022 | -1.2 | 0.79 | .067 | .089 |
| W1.5 | -0.017 | -0.9 | 0.01 | .043 | .060 |
| OPP | -0.024 | -1.3 | 0.67 | .067 | .091 |
| ATR.15 | -0.134 | -5.7 | -0.68 | .067 | .201 |
| ATR.25 | -0.042 | -2.1 | 0.46 | .079 | .121 |
| ATR.35 | -0.030 | -1.5 | 0.25 | .056 | .087 |
| ATR.5 | -0.013 | -0.7 | -0.03 | .050 | .063 |
| ATR.75 | +0.003 | +0.2 | 0.67 | .047 | .044 |

Mean net t by the other knobs:
- TP: none -1.46 / 1R -3.01 / 1.5R -2.39 / 2R -2.13 / 3R -1.70 / 4R -1.59.
- BE: 0 -2.34 / 0.5R -2.17 / 1R -1.62.
- Trail: 0 -1.50 / 0.5R -3.68 / 1R -1.92 / 1.5R -1.60 / 2R -1.53.
- Exit time: 14h -2.31 / 16h -2.14 / 18h -1.95 / 20h -1.92 / 21h -1.91.

Reshaping at 1x width, exit 20:00:
| exit | avgR | t | win | skew | +R from TP/trail/time |
|---|---|---|---|---|---|
| time only | .0078 | .23 | .39 | 2.03 | 0/0/100% |
| TP1 | -.0370 | -1.70 | .48 | 0.04 | 94/0/6 |
| TP2 | -.0180 | -.66 | .41 | 0.70 | 70/0/30 |
| TP3 | .0079 | .26 | .40 | 1.09 | 49/0/51 |
| trail1 | .0031 | .13 | .38 | 1.98 | 0/64/36 |
| trail2 | .0226 | .70 | .39 | 2.07 | 0/16/84 |
| BE0.5 | -.0163 | -.62 | .22 | 2.33 | - |
| BE1+trail1.5 | .0096 | .32 | .38 | 1.76 | 0/33/67 |
| BE0.5+trail0.5 | -.0316 | -1.64 | .60 | 0.45 | 0/92/8 |

## 4. Custom and extended exits (IS)
- Holding caps of 15-360 min at 1x width: -0.072 to -0.033R, all t<-1.4. At ATR0.75: -0.028 to -0.009R.
- Time-stops: all negative except ATR0.75, 120 min, <0R: +0.0046R (t 0.35).
- Exit time 9-13h: -0.064 to -0.045R.
- Wider stops (ATR 1-3): +0.002 to +0.004R, max t 0.51, the same as a pure time exit.

## 5. Finalists
They are not edges; they are shown as the least-bad exit structures.

| cfg | Params (non-default) | IS n | IS avgR | win | PF | t | tr/yr | maxDD | yrs+ | L avgR (t) | S avgR (t) | VAL avgR | VAL win | VAL PF | VAL t | VAL maxDD | VAL L / S |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F0 | default | 1828 | .0078 | .391 | 1.015 | .23 | 230 | 43.5 | 4 | -.008(-.18) | .026(.53) | -.0105 | .366 | .981 | -.16 | 37.1 | -.093/.084 |
| F1 | trail_r=2 | 1828 | .0226 | .394 | 1.044 | .70 | 230 | 32.1 | 5 | .005(.11) | .043(.90) | -.0271 | .368 | .948 | -.46 | 41.5 | -.111/.069 |
| F2 | sl_ref=1, sl_k=.75, be_r=1, trail_r=1.5, exit_time=21 | 1828 | .0115 | .467 | 1.042 | .67 | 230 | 27.7 | 5 | -.002(-.10) | .027(1.06) | -.0059 | .456 | .981 | -.17 | 21.0 | -.034/.027 |
| F3 | sl_ref=1, sl_k=1.5 | 1828 | .0034 | .478 | 1.024 | .38 | 230 | 16.3 | 4 | -.002(-.13) | .009(.66) | -.0062 | .475 | .960 | -.33 | 12.8 | -.012/.000 |

IS cost stress (slip .10 / spread +.10 / both):
- F1: .0050 / -.0003 / -.0183
- F2: .0029 / -.0008 / -.0084
- F3: -.0008 / -.0025 / -.0066

Zero-cost VAL: default +.058R (t .84; IS t 2.88); F3 +.009R (t .46).

## 6. Implications for the EA
Pick exits for cost-efficiency and low parameter sensitivity, not for edge.
- Use an ATR14-based stop of 0.75-1.5 ATR, which gives the lowest cost in R and the smallest drawdown. Add a time exit at 18-21h London and optionally BE 1R + trail 1.5R.
- Avoid stops under 0.5x width or 0.25 ATR, TPs of 1-2R, BE at 0.5R, trails under 1R, and holding caps under 6 h.
- Any edge must come from entry or filters (shorts show more continuation, but it is not significant) or from lower costs. The gross continuation of +0.10R at t 2.9 in IS would need costs roughly halved to be worth trading, and it is weaker in VAL.

Configs: 9,529 evaluations. They are 4,756 net IS, 4,755 zero-cost IS diagnostics, 12 IS cost-stress runs and 6 VAL runs.

Files: explore/exits/s01_mfe_mae.py, s02_grid.py, s03_grid_analysis.py, exitsim.py, s04_custom_exits.py, s05_wide_stops.py, s06_capture.py, s07_finalists_is.py, s08_val.py. Outputs are in explore/exits/out/.


## Candidates

### F1_W1_trail2 (best net t in brief grid; NOT an edge)

- Params: `{"trail_r": 2}`
- IS: n 1828, avg_R 0.0226, win_rate 0.394, PF 1.044, t_stat 0.7, trades_per_year 230.2, maxDD_R 32.1
- VAL: n 478, avg_R -0.0271, win_rate 0.368, PF 0.948, t_stat -0.46, trades_per_year 240.8, maxDD_R 41.5
- IS years positive: 5; long avg_R IS 0.0047, short 0.043
- Highest net IS t (0.70; 0.79 at exit 18h) among 4,500 brief-grid configs. The wide trail keeps the right tail and cuts some give-back. It is not a plateau: trail 1.5R gives t 0.24, sl_k 0.75 or 1.5 is negative, and neighbours average t -0.15. The result is short-driven (S t 0.90, L t 0.11), is about 0 under either cost stress, and VAL is -0.027R. Reject.

### F2_ATR0.75_BE1_trail1.5_exit21 (flattest plateau; NOT an edge)

- Params: `{"sl_ref": 1, "sl_k": 0.75, "be_r": 1, "trail_r": 1.5, "exit_time": 21}`
- IS: n 1828, avg_R 0.0115, win_rate 0.467, PF 1.042, t_stat 0.67, trades_per_year 230.2, maxDD_R 27.7
- VAL: n 478, avg_R -0.0059, win_rate 0.456, PF 0.981, t_stat -0.17, trades_per_year 240.8, maxDD_R 21
- IS years positive: 5; long avg_R IS -0.0023, short 0.0273
- The ATR0.75 family is the only broad plateau: many BE/trail/TP/exit-time variants sit at t 0.6-0.67 and neighbours average t 0.4. That is because an ATR stop lowers the cost in R to about 0.044R, not because of a signal: the mean is only +0.01R, it is short-only (L t -0.10), it is about 0 under cost stress, and VAL is -0.006R. It is the recommended exit template if an entry edge is found elsewhere, but it is not a strategy on its own.

### F3_ATR1.5_time_exit (quasi no-stop, time exit 20h; NOT an edge)

- Params: `{"sl_ref": 1, "sl_k": 1.5}`
- IS: n 1828, avg_R 0.0034, win_rate 0.478, PF 1.024, t_stat 0.38, trades_per_year 230.2, maxDD_R 16.3
- VAL: n 478, avg_R -0.0062, win_rate 0.475, PF 0.96, t_stat -0.33, trades_per_year 240.8, maxDD_R 12.8
- IS years positive: 4; long avg_R IS -0.0015, short 0.0089
- Measures the entry's raw drift to 20:00 with the stop almost never hit (1.4% stopped). Gross IS t 2.9, but gross is only about 1.15x cost, so net is +0.003R. VAL gross falls to +0.009R (t 0.46) and VAL net is -0.006R. It shows the ceiling of what any exit can extract from this entry: about zero after costs.

### F0_default (reference)

- Params: `{}`
- IS: n 1828, avg_R 0.0078, win_rate 0.391, PF 1.015, t_stat 0.23, trades_per_year 230.2, maxDD_R 43.5
- VAL: n 478, avg_R -0.0105, win_rate 0.366, PF 0.981, t_stat -0.16, trades_per_year 240.8, maxDD_R 37.1
- IS years positive: 4; long avg_R IS -0.0082, short 0.0261
- Reference for comparison. Reproduces the audit's baseline exactly (IS +0.0078, VAL -0.0105).

## Engine / data notes

- No new engine bug found. Independent check: my exit re-simulator explore/exits/exitsim.py, which replicates only the documented rules, reproduces engine R and exit-bar indices exactly (max |dR| = 0, 0 exit-bar mismatches over 1,828 trades) for 7 configs covering TP, BE, trail 0.5, BE+TP, ATR stop + BE + trail with exit 21h, and trail with exit 14h. Reproduce with python3 explore/exits/s04_custom_exits.py; the validation block is printed first.
- Semantics, not a bug, but it affects how the trail_r grid should be read. With be_r=0, the trail is active from the first managed bar with best=entry, so trail_r<1 silently tightens the initial stop to trail_r x R while R is still normalised by the original stop. Params(trail_r=0.5) is effectively a 0.5R hard stop from bar 2: IS -0.060R, t -5.0, 66% of trades stopped. Other agents should not read 'trail 0.5' as a trailing stop.
- Reason-label quirk: an exit at a stop at or beyond entry is labelled 'trail' even when trail_r=0, which covers BE exits (be_r>0 moves the stop to entry+0.05 and it is labelled 'trail'). A trailed stop still below entry is labelled 'sl'. Use R, not the reason label, to separate losses from BE and trailing exits.
- The engine is conservative in two ways that bias tight TPs slightly downward. The entry bar's favourable extreme is never used: TP is not checked there and best is not updated. When SL and TP fall in the same bar, SL is assumed to hit first. Both are sensible; noting them for anyone comparing with MT5 tick tests.
- Spread stress changes the entries, not only the costs. Buy stops trigger on ASK high against a BID-based range high, so +0.10 spread makes longs trigger earlier: IS n goes from 1828 to 1842, longs from 976 to 1004 and shorts from 852 to 838. This is realistic MT5 behaviour, and the EA must place buy stops at the BID range high so the fill replicates it.
- Process note: files from my in-progress folder (explore/exits/common.py, s01/s02 scripts and out/*) were swept into another agent's commit 0a8f132 ('Engine audit: fix 9 backtest bugs...') while I was running. The committed out/configs_log.csv is partial; the working-tree version has the complete 9,530-row log. I committed nothing.
- REPORT.md was not written to disk: this subagent's instructions say not to write report .md files, and the audit agent's Write of REPORT.md was refused. The full report content is the last key_findings entry, ready to be saved as explore/exits/REPORT.md.
