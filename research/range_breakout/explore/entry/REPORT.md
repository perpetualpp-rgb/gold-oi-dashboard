# Axis: entry

Configs tested: 6954 (VAL checked: 7). Holdout (2024+) not used.

## Recommendation

No robust edge was found on the entry axis. For the MT5 EA, enter WITH the London break using plain stop orders at the range edge. The buffer should be 0, or at most 0.05 x range width, which is about one spread. Do not add ATR buffers, bar-close confirmation, stop-and-reverse, fades, or failed-break (Judas / turtle-soup) reversals: all of them are equal or worse, and every fade variant is negative gross and net, in IS and VAL.

Why nothing works: there is a small, real momentum effect after the first break. Gross it is about +0.1R per trade in IS (t about 2.9) and +0.06R in VAL. Round-trip costs take about 0.09R, and entry mechanics only move the fill price or remove trades. They do not raise the gross edge per trade. Any real edge has to come from other axes that lift gross edge per unit of range width, or cost per unit of range width, such as:
- day or regime selection, including range width versus the ~0.5 USD cost;
- exits and holding time: the edge grows with holding to the time exit and shrinks with fixed TPs;
- side or trend asymmetry.

Two leads are unvalidated and low priority. Neither should be promoted on its own:
- **Break-then-retest limit entry at T0/T1:** IS +0.087R (t 1.4), but the result is peaky, dominated by 2015 and fails at T3. VAL +0.030R.
- **T3 NY-session failed-break reversal:** IS +0.059R, shorts only, 39 trades a year. VAL +0.077R on 103 trades.

Re-check any candidate from later stages at slip 0.10 and spread +0.10. Both leads roughly halve under that stress.

EA note: the engine and MT5 trigger buy stops on ASK while the range is built on BID. About two thirds of longs open before BID actually breaks the range high. A spread-corrected trigger changes nothing on average, but the EA should implement whichever convention the backtest used.

## Key findings

- ANSWER: trade WITH the break, never against it. But no entry mechanic creates a net edge. After the first touch of a range edge, price is slightly MORE likely to continue than a random walk would allow, at all 4 timings and all 9 stop/target geometries tested (every z > 0). Example at T0 (range 00-07 London), gross: P(+1W beyond before -1W back) = 0.533 against 0.500 (z 2.6); P(+0.5W before -0.25W) = 0.369 against 0.333 (z 3.1). W = range width. The 'Judas swing' / stop-hunt hypothesis is rejected (s00b_race_prob.csv).
- Gross vs net (engine on a zero-spread copy of the data with commission=0 and slip=0; s07_results.csv). At T0 the default stop entry makes +0.099R gross (t 2.88; longs +0.084, shorts +0.114), and costs take 0.091R, leaving +0.008R net. The canonical fade (limit at the edge, stop 1W, TP 1R) is already negative before costs, -0.051R (t -2.34), and -0.109R net (t -4.9). The same holds at T1 (00-08, gross +0.079R) and T2 (07-08, gross +0.141R, but the tiny W makes costs 0.18R). At T3 (08-13 range, entries 13-17) momentum is weaker (gross +0.045R). In VAL 2022-23 the gross breakout edge persists but is smaller, +0.058R (t 0.84); the gross fade is -0.029R.
- The gross edge is about +0.1 range-width per trade and is almost exactly the ~0.47 USD round-trip cost at the median W of 5.5 USD. A later filter/exit stage can only help by raising gross edge per W or by trading when W is large relative to cost. Entry mechanics cannot close the gap.
- Stop entries with buffers (s01, 384 configs; buf_k {0,.05,.1,.2,.3,.5} x buf_atr {0,.05,.1,.2} x 4 exit geometries x 4 timings). Buffers do not remove enough false breaks to pay for the worse entry. T0 with stop 1W, avg_R by buf_k (buf_atr=0): 0 +0.008, 0.05 +0.016, 0.1 +0.012, 0.2 +0.010, 0.3 -0.010, 0.5 -0.068. Any ATR buffer makes it worse: buf_atr 0.1 = -0.013, 0.2 = -0.027. Best t over the whole family: 0.46. The share of configs with avg_R > 0 is 9% at T0, 4% at T1 and 0% at T2/T3. Gross per-trade edge barely changes with the buffer (T0 gross +0.099 / +0.116 / +0.096R at buf_k 0 / 0.1 / 0.3), so the buffer only removes trades and pays a worse fill.
- Bar-close confirmation (s02, 384 configs; M5/M15/M30/M60 x buffers x 3 exits x 4 timings). No improvement: the T0 stop-1W grid runs -0.005 to -0.078R, the best of the whole family is +0.013R (t 0.39), and 0-4% of configs are positive. Confirmation lowers the gross edge (T0 M15 gross +0.076R against +0.099R for the plain stop entry) because the entry comes later and further out.
- Stop-and-reverse (max_trades=2; s03, 192 configs). Total ~0 at best (T0 sl1W +0.0003R). The reversal leg on its own, i.e. trading against a failed break at the opposite edge, is negative at every timing: T0 sl1W reversal leg -0.050R (n 276), T1 -0.157R, T2 -0.087R, T3 -0.078R. With a 0.5W stop it is -0.37R to -0.43R.
- FADE limit orders against the break (s04 + s05a, 1316 configs; sl_k {.25,.5,.75,1} x tp_r {0,.5,1,1.5,2}, also midpoint and opposite-edge targets, buffers {0-0.5W, 0.1 ATR}, ATR stops, limit_pen 0.05). Not one of the 1316 configs has avg_R > 0, at any timing. T0 median -0.15R. The least bad is -0.055R (T3, t -2.4). A tight 0.25W stop gives -0.36R to -0.72R because costs dominate. Midpoint and opposite-edge targets are also all negative (T0 best -0.092R).
- Failed-breakout reversal, custom fb_sim.py (s05b + s09, 2632 configs). Logic: the break penetrates by pen*W, then a bar closes back inside the range (M1/M5/M15/M60), then enter against the break. Stop beyond the break extreme or fixed; target mid, opposite edge, 1.5R or none. Result: 0-5% of configs are positive, and the median is -0.13R at T0 and -0.065R at T3. Restricting to the London open (entries only until 08:00/09:00/10:00, the classic Judas window) makes it worse: -0.12R to -0.43R, t down to -11. Gross, the T0 reversal is about -0.05 to 0R, and the tight structural stops make costs 0.2-0.4R.
- Judas check by hour of the first break (T0, gross, 1W stop): breaks in the 07:00 hour +0.099W (n 1067, t 2.2), 08:00 +0.130W, 09:00 -0.037W (n 147), 10:00 +0.187W, 11:00 +0.240W. Early London breaks are not reversals on average.
- Break-then-retest, custom rt_sim.py (s06 + s10, 848 configs): trade WITH the break, but on a pullback limit at the edge after the break has gone pen*W beyond. This is the only family with a visible hump: at T0 and T1, pen 0.25-0.35 with the limit at the edge (off -0.05..0) and a 1W stop gives up to +0.094R (t 1.41). It is not a plateau: pen 0.40-0.45 turns negative. 45.4R of the 56.9R IS total comes from 2015 alone; without 2015 it is about +0.02R. At T3 it is strongly negative (-0.19R, t -6.0). VAL +0.030R (t 0.27), with longs -0.128 and shorts +0.156. Not validated.
- Spread-trigger asymmetry: MT5 buy stops trigger on ASK while the range is built on BID. 649 of 976 IS default longs (66%) open while BID is still below the range high. 53 longs never saw BID trade at the range high during the trade, and they average -1.0R. A 'spread-corrected' buy stop (triggers on the BID break, fills at ASK) was tested in a custom simulator, so_sim.py, which reproduces engine.run trade by trade on 6 configs. Across 64 paired configs the mean change is -0.0009R, and it helps in only 34% of them. No free lunch.
- Multiple testing: about 6190 net IS strategy configs were searched on this axis, and the best t-stat anywhere is 1.64 (a T3 failed-break cell). That is below what pure noise would produce over so many configs, so nothing on this axis survives a multiple-testing correction. The family overview is in s13_family_summary.csv.

## Candidates

### C_retest_T0 (break-then-retest, WITH the break; best IS cell on the axis, NOT validated)

- Params: `{"engine": "custom explore/entry/rt_sim.py run_rt", "timing": "range_start=0, range_end=7, entry_end=12, exit_time=20 (London)", "pen": 0.3, "off": 0, "sl_mode": 0, "sl_k": 1, "tp_r": 0, "logic": "After BID trades >=0.3W beyond a range edge (07:00-12:00 London), place a limit at that edge in the break direction from the next bar: buy limit at the range high, filled when ASK low <= level; sell limit at the range low, filled when BID high >= level. Stop 1W from entry, no target, flat at 20:00. One trade a day; the latest break side is the armed one. Costs at engine defaults, no slip on the limit fill."}`
- IS: n 645, avg_R 0.0871, win_rate 0.389, PF 1.157, t_stat 1.39, trades_per_year 81.3, maxDD_R 36.2
- VAL: n 194, avg_R 0.0304, win_rate 0.345, PF 1.054, t_stat 0.27, trades_per_year 97.7, maxDD_R 17.2
- IS years positive: 5; long avg_R IS 0.0689, short 0.1009
- Best IS cell of the only family with a hump, at T0/T1 pen 0.25-0.35. It is a peak, not a plateau: pen 0.4-0.45 is negative, 2015 supplies 80% of the IS profit, the rule fails badly at T3, and VAL is flat with the long side negative. Low priority. At most a combination-stage idea.

### D_failbrk_T3 (failed-break reversal, AGAINST the break, NY-session timing; NOT validated)

- Params: `{"engine": "custom explore/entry/fb_sim.py run_fb", "timing": "range_start=8, range_end=13, entry_end=17, exit_time=20 (London)", "pen": 0.5, "rec": 0, "tf": 60, "stop_mode": 0, "sbuf": 0.1, "tgt_mode": 3, "tp_r": 1.5, "logic": "After BID trades >=0.5W beyond a range edge, wait for an hourly bar that closes back inside the range, then enter against the break at the next bar open (market, slip 0.05). Stop at the session extreme since 13:00 plus 0.1W, TP 1.5R, flat at 20:00. One trade a day."}`
- IS: n 307, avg_R 0.0588, win_rate 0.495, PF 1.207, t_stat 1.31, trades_per_year 38.9, maxDD_R 10.5
- VAL: n 103, avg_R 0.0773, win_rate 0.495, PF 1.257, t_stat 0.96, trades_per_year 53.3, maxDD_R 5.8
- IS years positive: 5; long avg_R IS -0.0006, short 0.1279
- The only against-the-break setup with a mildly positive neighbourhood: T3 with M60 reclaim and pen >= 0.4 gives +0.02 to +0.08R. All of it comes from shorts, it is negative at every other timing, trades are few (39 a year), t is 1.3 among about 6000 configs, and VAL is 1 of 2 years positive. Treat as noise unless another axis finds independent support for NY-session mean reversion.

### B_stop_buf0.05_T0 (best plain stop-entry cell; reference for WITH the break)

- Params: `{"engine": "engine.Params", "buf_k": 0.05}`
- IS: n 1743, avg_R 0.0158, win_rate 0.392, PF 1.029, t_stat 0.46, trades_per_year 219.5, maxDD_R 35
- VAL: n 456, avg_R -0.009, win_rate 0.364, PF 0.984, t_stat -0.13, trades_per_year 229.7, maxDD_R 36.8
- IS years positive: 5; long avg_R IS 0.0046, short 0.0284
- Shows that buffers do nothing: +0.016R against +0.008R without a buffer, well inside noise, and negative under cost stress and in VAL. Recommended entry form for later stages: stop orders at the edge (buffer 0 to 0.05W), no confirmation, stop about 1W or at the opposite edge.

### F_fade_T0 (canonical fade: evidence for 'against' being wrong)

- Params: `{"engine": "engine.Params", "entry_mode": 2, "sl_k": 1, "tp_r": 1}`
- IS: n 1748, avg_R -0.1087, win_rate 0.459, PF 0.781, t_stat -4.92, trades_per_year 220.2, maxDD_R 205.9
- VAL: n 465, avg_R -0.0879, win_rate 0.477, PF 0.821, t_stat -2.04, trades_per_year 234.3, maxDD_R 41.9
- IS years positive: 1; long avg_R IS -0.1384, short -0.0824
- Not a candidate. Checked in VAL only to confirm the sign: the fade stays negative out of sample and at every timing (T1 -0.103, T2 -0.187, T3 -0.087 IS).

### G_failbrk_T0 (canonical Judas / turtle-soup reversal at the London open)

- Params: `{"engine": "custom explore/entry/fb_sim.py run_fb", "timing": "T0 (0-7, entry_end 12, exit 20)", "pen": 0.1, "rec": 0, "tf": 15, "stop_mode": 0, "sbuf": 0.1, "tgt_mode": 1}`
- IS: n 1090, avg_R -0.1922, win_rate 0.479, PF 0.648, t_stat -6.69, trades_per_year 137.3, maxDD_R 211.6
- VAL: n 304, avg_R -0.1539, win_rate 0.503, PF 0.7, t_stat -2.9, trades_per_year 153.2, maxDD_R 47.9
- IS years positive: 0; long avg_R IS -0.192, short -0.1923
- Not a candidate. It is the direct test of the Judas swing: M15 close back inside after a 0.1W break, stop above the sweep extreme, target the midpoint. It loses in all 8 IS years, on both sides, and in VAL.

## Engine / data notes

- No engine bug found. The custom stop-entry simulator explore/entry/so_sim.py (long_trig=0) reproduces engine.run trade by trade (day, dir, i_entry, i_exit, pnl) on 6 configs, including buffers, ATR stops, TP, and timings T2/T3. See the validate() output of s08_spread_fix.py: all IDENTICAL.
- Execution-model asymmetry, by design and not a bug: buy stops trigger on ASK high while the range high is a BID high, so a long can open with BID up to one spread below the range high. On the default config in IS, 649 of 976 longs have an entry bar whose BID high is below the range high. 53 longs never had BID reach the range high during the whole trade, and they average -1.006R (reproduce with explore/entry/s07b_spread_trigger.py). The mirror case: fade buy limits need BID to trade one spread below the range low, while sell limits fill on a BID touch. A spread-corrected trigger does not change results on average (-0.0009R mean over 64 paired configs), but the MT5 EA must use the same convention as the backtest.
- Methodology pitfall for other agents: a zero-spread copy of the data (ASK = BID) changes which trades are taken, because longs then trigger on the BID break. Per-trade gross-versus-net comparisons must add each trade's own costs back (commission + slip x fills + spread at entry), not merge a gross run with a net run on (day, dir). The merge silently drops about 5% of trades, mostly the losing spread-triggered longs, and makes the net figures look better.
- Safety suggestion: engine.load() loads the full history, including 2024+, into memory, and D['days'].index extends to 2026. Nothing in this axis read 2024+ prices: every engine call used end<=VAL_END, and the custom sims default to end=IS_END with VAL runs at start=2022-01-01, end=VAL_END. A load(until=...) option would make the holdout seal mechanical rather than procedural.
- The 'REPORT.md' deliverable was not written. The harness forbids subagents from writing report .md files, and the audit agent hit the same refusal. The full report is in this structured output. Raw result tables are saved as CSV and TXT files in explore/entry/ (s01..s13 *_results.csv, *_tables.txt, s09_judas.txt, s00b_race_prob.csv, s13_family_summary.csv, configs_log.csv).
