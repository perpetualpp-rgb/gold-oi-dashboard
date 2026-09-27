# Axis: timing

Configs tested: 2347 (VAL checked: 3). Holdout (2024+) not used.

## Recommendation

Session timing alone does not turn the range breakout into a tradeable edge. There is a real gross follow-through signal (about 0.5-0.7 USD/oz per trade, gross t of 3-4), but it is the same size as the retail round-trip cost (about 0.47 USD). Timing changes shift gross and cost together.

If the breakout is carried forward, use F1 as the timing base for the other axes: range_start 0, range_end 5 (plateau 4-5.5), entry_end about 12 (insensitive), exit_time 18-21 London (20 is fine). Never exit around noon: exits at or before 14:00 lose about 0.02-0.06R, costs included. F1 is about +0.03R better than the default in both IS and VAL at the same trade count. It is still within noise (t 1.0, VAL t 0.38), depends on about 10 tail trades, and goes to about 0 under the slip 0.10 + spread +0.10 stress.

Do not pursue NY-session breakouts of the London morning range: 771 configs, none positive after costs. Do not use evening range starts either. Improvements have to come from other axes:
- lower costs (ECN pricing),
- filters or exits that raise follow-through per trade (the edge lives in rare big trend days, so wide or no targets and a long hold matter),
- the short-side asymmetry. Down-breaks of the late-Asian range follow through more, and this is not explained by the unconditional drift. It is post hoc, so a direction/trend agent should test it as a hypothesis, keeping in mind that gold rallied strongly after the in-sample period.

The pre-fix drifts are statistically solid but too small for retail costs: -1.1 bp into the 15:00 PM fix, negative in 8/8 IS years, and -0.6 bp into the 10:30 AM fix. They are useful as context, e.g. a short breakout benefits from being held through 14:45-15:00.

## Key findings

- HEADLINE: timing alone gives no robust edge after costs. I ran 2335 distinct IS timing configs at default costs: 1158 main grid, 771 New York (NY) session, 102 sliding window, 378 local late-Asia grid, 4 late-break variants and a few reference/decomposition runs. None has t > 2; the best is t = 1.48. 451 have t < -2. Mean avg_R by grid: main -0.009R, NY -0.055R, sliding -0.053R, late-Asia local +0.021R. With this many (correlated) trials a t of 1.48 is well within noise. I also ran 12 IS cost-stress variants (2347 counted in total) and 2012 zero-cost diagnostic runs, which are not tradeable and not counted.
- WHERE THE SIGNAL LIVES (gross vs costs). With zero commission, slip and spread (ASK = BID), breakout follow-through is real: 900 of 1158 main-grid configs have gross t > 2. The default is gross +0.099R (t 2.88; longs +0.084, shorts +0.114); range 00-05 is gross +0.148R (t 3.76). In USD, gross R x median width is about 0.5-0.7 USD/oz per trade for every range definition. Round-trip cost is about 0.47 USD (0.07-0.17R). Changing the timing moves gross R and cost R almost one for one: narrower ranges raise both. Mean over entry_end and exit >= 16: range 02-05 gross 0.175R vs cost 0.166R; range 00-05 0.136 vs 0.106; range -3 to 9 0.066 vs 0.072. So timing cannot separate the signal from the costs.
- EXIT TIME IS THE BIGGEST TIMING KNOB: hold through the US afternoon. Net avg_R for range_end = 5, averaged over range_start and entry_end, by exit hour: 12 -0.042 | 14 -0.007 | 16 -0.005 | 17 +0.011 | 18 +0.021 | 20 +0.019 | 21 +0.022. The same pattern holds for every range_end (exit 12 is the worst, about -0.04 to -0.06R). Gross follow-through roughly doubles between 12:00 and 18:00 and is flat from 18 to 21, so exit 18-21 London is a plateau. Every short hold (exit <= 14, or sliding exit h+4) is negative net.
- RANGE DEFINITION. An Asian range starting 00:00-01:00 and ending 04:00-05:30 London beats the default 07:00 end. Ranges starting the previous evening (-3/-2/-1) are worse everywhere, because the quiet 21:00-00:00 hours widen the range and lower gross R. range_start -2 and -1 are almost identical, since 22:00-23:00 is the daily halt. Net avg_R, range_start x range_end at entry_end 12 / exit 20: rs 0 -> re5 +0.037, re6 +0.020, re7 +0.008, re8 +0.010, re9 +0.030; rs -3 -> +0.011 / -0.002 / -0.012 / -0.012 / +0.012. Local plateau (rs 0-1, re 4-5.5, entry_end 9-13, exit 18-21, 108 configs): 98% positive, mean +0.022R, max t 1.08, mean 6 of 8 IS years positive. entry_end barely matters for Asian ranges: most first breaks come within 1-2 hours of range_end.
- NEW YORK SESSION VARIANT: no edge. I tested 771 configs: range_start 7-13, range_end 12:30 / 13:00 / 13:15 / 13:30 / 14:00 / 15:00, entry_end 14-17, exit 16-21. The best is +0.0009R. Mean -0.055R, and 296 have t < -2. Gross is only about +0.01 to +0.11R, and entries after the US data (range_end 14:00) have gross of about 0 (+0.01 to +0.02R). Range 08:00-13:30 with entries to 14-17 and exit 16-21 gives -0.010 to -0.039R. The 13:20/13:30 volatility spike (mean absolute 1-minute move 0.57 USD at 13:30 vs about 0.33 around it) produces no follow-through. The engine is also optimistic on those fills (spread is constant within the hour, slip 0.05), so real results would be worse.
- SLIDING MAP (range [h-L, h), entries [h, h+2), exit 21:00 or h+4). Gross follow-through is strongest for ranges ending 03:00-06:00 London held to 21:00: 0.16-0.25R for L = 2-4. It decays through the London day and is about 0 for ranges ending at 14:00 or later. Net is positive only for L = 4-6, h = 4-6, exit 21 (+0.02 to +0.06R). All 51 exit h+4 variants are negative net (mean about -0.07R).
- DESCRIPTIVE STATS (IS, BID, no costs, 2003 days). The Asian 00-07 range breaks between 07:00 and 16:00 on 97.8% of days: up first 49.3%, down first 48.5%, median first break 07:49. The other side also breaks on 38% of days by 16:00 and on 44% by 20:00. For the 00-05 range these are 45% and 50%. The first break agrees with the later move only weakly. Follow-through from the broken level to 20:00 is +0.10 range widths (t 2.5), positive on 51% of days. The 20:00 price is beyond the broken edge on about 51% of days, beyond the opposite edge on 19-21%, and inside the range on 28-30%. It is symmetric: up-first +0.100 and down-first +0.099 widths for 00-07; +0.146 and +0.189 for 00-05. Unconditional drift 07:00->20:00 is -0.02 widths (t -0.5). Late first breaks (10:00-11:59) of an intact 00-07 range follow through strongly (+0.34 to +0.51 widths, 150 days). As a strategy (range 00-07 still intact at 10:00, trade breaks 10:00-12:00) that is only n = 165, +0.075R, t 0.72, 5 of 8 years positive: not robust. A London 08-13 range gives +0.036 widths to 20:00 (t 1.05) with 34% double breaks, weaker than the Asian range.
- LONG VS SHORT. Net longs are about 0 or negative in almost every cell; shorts carry all the positive results. Default: longs -0.008 / shorts +0.026. F1: longs +0.009 / shorts +0.071 in IS, longs -0.024 / shorts +0.088 in VAL. This is NOT the unconditional time-of-day drift: subtracting the IS per-minute drift over each trade's holding interval moves results by only about ±0.01R. Gross longs are also positive (+0.08 to +0.11R), so the gap is conditional: down-breaks of the late-Asian range follow through more (00-05 down-breaks in the 05:00 hour: +0.39 widths, t 2.7; up-breaks +0.02). A shorts-only tilt is a post-hoc idea and carries regime risk (gold roughly doubled after the IS). I did not submit it as a candidate.
- GOLD EVENT WINDOWS (IS mean BID move in basis points; t-stat; years negative of 8). Into the PM fix, 14:45->15:00: -1.13 bp, t -3.3, negative in all 8 years. Into the AM fix, 10:15->10:30: -0.64 bp, t -4.0 (5 of 8 negative), with a rebound 10:30->10:45 of +0.42 bp (t 2.5). London open hour 07:00->08:00: -1.01 bp, t -2.7 (7 of 8 negative). COMEX open 13:15->13:29: +0.32 bp (t 1.1). US data 13:29->13:45: -0.37 bp (t -0.8). Hourly profile: 00:00-07:00 London drifts up +2.2 bp a day; 07:00-20:00 drifts down -1.2 bp. These drifts are 0.05-0.15 USD per day, far below the 0.47 USD round trip. They slightly favour shorts held through 07:00-08:00 and 14:45-15:00 but are not a standalone edge at retail costs.
- FRAGILITY AND COSTS. The F1 and F2 IS edge sits entirely in the right tail. Dropping the 5 best of F1's 1933 trades takes it from +0.037R to +0.009R; dropping the best 10 gives -0.011R. The best single trade is 13.8R (narrow range, big trend day). F2: +0.074 -> +0.033 (top 5) -> +0.002 (top 10). Cost stress at slip 0.10 plus spread +0.10: F1 -0.004R, F2 +0.026R, F3 +0.007R, default -0.032R.
- VAL (3 configs, base costs). F1: +0.029R (t 0.38), both years positive (2022 +0.008, 2023 +0.052). F2: +0.057R (t 0.57), both years positive (+0.096 / +0.015). F3: -0.020R, failed (longs -0.097). For comparison, the audit's default VAL is -0.0105R. F1 and F2 kept their IS sign but VAL confirms nothing statistically. Pooled IS+VAL: F1 +0.036R (t 1.06), shorts +0.075R (t 1.44); F2 +0.071R (t 1.58), shorts +0.137R (t 1.80).

Net avg_R heatmap, range_end x exit_time (mean over range_start and entry_end):
| re | ex12 | ex14 | ex16 | ex17 | ex18 | ex20 | ex21 |
|---|---|---|---|---|---|---|---|
| 5 | -0.042 | -0.007 | -0.005 | +0.011 | +0.021 | +0.019 | +0.022 |
| 6 | -0.053 | -0.025 | -0.020 | -0.006 | +0.006 | +0.003 | +0.006 |
| 7 | -0.057 | -0.024 | -0.018 | -0.011 | +0.001 | -0.004 | -0.003 |
| 8 | -0.062 | -0.030 | -0.020 | -0.015 | 0.000 | -0.004 | -0.007 |
| 9 | -0.038 | -0.007 | -0.010 | -0.005 | +0.005 | +0.006 | -0.004 |
Same grid gross (zero cost): re5 0.066 -> 0.137 (ex12 -> ex18); re8 0.014 -> 0.072. All other heatmaps are in explore/timing/out/heatmaps.txt.

- REPORT.md WAS NOT WRITTEN: the harness forbids subagents from writing report .md files (the audit agent hit the same block). The full content is in this output. Per-analysis tables are in explore/timing/out/: heatmaps.txt (all pivot heatmaps), descriptive.txt, decompose.txt, finalists_is.txt, val_check.txt, fix_windows.txt, outlier_check.txt, late_break_is.txt, the grid CSVs, and configs_log.csv (every evaluated config, by stage).

## Candidates

### F1 Asian 00-05, entries to 12:00, exit 20:00 (plateau centre)

- Params: `{"range_end": 5}`
- IS: n 1933, avg_R 0.0374, win_rate 0.371, PF 1.064, t_stat 1, trades_per_year 243.5, maxDD_R 37.2
- VAL: n 495, avg_R 0.0294, win_rate 0.329, PF 1.048, t_stat 0.38, trades_per_year 249.4, maxDD_R 31.5
- IS years positive: 7; long avg_R IS 0.0085, short 0.0713
- Centre of the broadest positive plateau: rs 0-1, re 4-5.5, any entry_end, exit 18-21. Best timing base for other axes, about +0.03R over the default in both IS and VAL at the same trade count. Not an edge on its own: t 1.0, driven by about 10 tail trades, -0.004R under combined cost stress, and longs about 0.

### F2 Asian 00:00-05:30, entries only 05:30-07:00 (before London open), exit 21:00

- Params: `{"range_end": 5.5, "entry_end": 7, "exit_time": 21}`
- IS: n 1195, avg_R 0.0742, win_rate 0.367, PF 1.125, t_stat 1.48, trades_per_year 150.5, maxDD_R 29.3
- VAL: n 306, avg_R 0.0568, win_rate 0.333, PF 1.092, t_stat 0.57, trades_per_year 154.2, maxDD_R 27.8
- IS years positive: 5; long avg_R IS 0.0236, short 0.1479
- Highest IS t of all 2335 net configs (still only 1.48), and it survives the combined cost stress at +0.026R. It is a peak inside the late-Asia plateau and very tail-dependent (0 after dropping the top 10 trades), with 5/8 years positive and a strong short skew. I list it for transparency, not as a recommendation.

### F3 range 02:00-09:00, entries 09-12, exit 20:00 (REJECTED)

- Params: `{"range_start": 2, "range_end": 9}`
- IS: n 1440, avg_R 0.0471, win_rate 0.408, PF 1.1, t_stat 1.36, trades_per_year 181.4, maxDD_R 30.7
- VAL: n 380, avg_R -0.0203, win_rate 0.392, PF 0.961, t_stat -0.3, trades_per_year 191.7, maxDD_R 38.4
- IS years positive: 4; long avg_R IS -0.0028, short 0.1043
- Highest avg_R on the main grid, but only 4/8 years positive, entirely short-driven, a peak rather than a plateau (36 neighbours average +0.018), and negative in VAL. Rejected.

## Engine / data notes

- No engine bugs found on this axis. Results were consistent with the audit: default IS +0.0078R reproduced exactly, and range_start -2 and -1 are nearly identical because 22:00-23:00 London is the daily halt.
- Limitation, not a bug: range_end is also the start of the entry window, so there is no way to leave a gap between range end and first entry (e.g. range 08:00-13:00, entries from 13:30). I used range 08:00-13:30 instead. A Params.entry_start knob would be needed to test that properly.
- Limitation: the session clock is London only. The COMEX open (13:20) and US data (13:30) shift to 12:20 and 12:30 London during the 3-4 US/UK DST-mismatch weeks each year, so an NY-anchored window would need a NY-clock option. Immaterial here, since every NY variant was negative.
- Cost realism at event bars: the modelled spread is constant within each hour, and stop fills use level/open + 0.05 slip. Entries on the 13:30 US-data bar, the 07:00 London open or the 08:00 bar are therefore optimistic. NY configs with range_end 13.5 fill on the release bar and are still negative, so conclusions do not change, but any later candidate that enters at event minutes should be stress-tested with larger slip.
- Not an issue, but worth knowing when comparing gross and net runs: with ASK = BID the trade set changes. About 2% of default trades (41 of 1828) exist only because the ASK high touched the range high, i.e. the buy stop triggers on ASK. That is correct MT5 behaviour, but gross and net runs cannot be matched trade by trade.
