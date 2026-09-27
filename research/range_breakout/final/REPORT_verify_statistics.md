# Verification: Statistical validity / overfitting (IS 2014-2021 + VAL 2022-2023 only; data loaded with engine.load(until=VAL_END), no 2024+ bars in memory)

**Verdict: weak**

**Expected live edge:** About +0.02 to +0.03R per trade is the central estimate at backtest costs (shrinkage consensus: EB with prior mean 0 gives +0.027, EB updated with VAL +0.027, a skeptical prior of tau 0.05 gives +0.047, the IS->VAL regression gives +0.058). An 80% interval is roughly -0.04 to +0.08R. Net of realistic retail live costs (an extra 0.02-0.04R), the expectation is about 0.00 to +0.02R. P(true edge > 0) is about 0.80-0.83 after selection shrinkage at backtest costs, and about 0.5-0.65 under stressed live costs. It is nowhere near the backtest's +0.12R.

## Findings

- Bootstrap CIs (stationary bootstrap by London trading day, mean block 10 days, 20,000 resamples; blocks of 1-60 days give the same SEs within 10%). IS: avg_R +0.122, 90% CI [+0.022, +0.224], P(avg_R>0)=0.979. VAL: +0.020, 90% CI [-0.177, +0.234], P>0=0.554. Pooled 2014-2023: +0.104, 90% CI [+0.015, +0.198], P>0=0.974. Trade SD is 1.44R, so one year of trades (about 60) has an SE of about 0.19R. These P>0 values are unconditional and take no account of the search.
- Reality check on a broad family: 12,960 engine-native configs as a proxy for the round-1 space (8,856 with n>=100 in IS). The configs cross 5 Asian ranges, min_w_atr 0-0.5, 4 ATR regimes, 6 stop/TP variants, exits 18/20/21, 3 compression settings and trend 0/50. The run is a studentised stationary-bootstrap max-t with 2,000 resamples. The PRIMARY ranks 1,140th in IS by t_boot (1.91), with p_family 0.905. The fallback ranks 224th (t 2.50), p_family 0.64. Even the best config in the whole family (t 3.29) has p_family 0.21, against a max-t 95% quantile of 3.96. In VAL the primary ranks 5,594th of 8,874.
- Effective number of trials. The 24-config grid has a participation ratio of 2.3, but that understates multiplicity for a max-type selection. Matching the grid's max-t 95% quantile (2.62) to independent tests gives N_eff about 12. In the broad proxy, the mean max-t (2.77) gives N_eff about 204 and the 95% quantile gives about 1,350. The mean pairwise correlation (0.62) shrinks N_eff by 1 to 2 orders of magnitude from 20,000, but not to single digits. N_eff of 50-1,000 is the honest range for the round-1 plus combine process.
- Deflated Sharpe for the primary. Trade-level SR is 0.084 (IS) with skew 2.25 and kurtosis 13.1. With V=1/T: DSR 0.98 at N=1, 0.92 at N=2.3, 0.62 at N=12, 0.18 at N_eff=204, 0.06 at N_eff=1,350, and 0.01 at N=20,000. Using V equal to the cross-sectional SR variance of the broad family (sd 0.054) gives 0.05 at N_eff=204. Pooled IS+VAL figures are slightly worse (0.16 at N_eff=204). At no honest N does the DSR reach 0.95.
- Harvey-Liu haircut (annualised on 66.5 trades a year). IS SR_ann is 0.68 (t 1.93, two-sided p 0.053). Bonferroni/Holm with N=12 cuts it to 0.17 (a 75% haircut). BHY at N=12, and every method at N>=24, gives a 100% haircut. Pooled SR_ann is 0.58 (p 0.067): an 86% haircut at N=12 and 100% at N>=24. Nothing is left once the grid alone is accounted for.
- Shrinkage estimates of the expected OOS avg_R (at backtest costs). (a) Skeptical priors N(0, tau): tau 0.03 gives +0.023 (P>0 0.81), tau 0.05 gives +0.047 (0.89), tau 0.10 gives +0.083 (0.95). (b) Empirical Bayes with tau = 0.033, taken from the split-half (2014-17 vs 2018-21) covariance of config effects in the broad family: prior mean 0 gives +0.027 (P>0 0.82); prior mean equal to the family mean +0.057 gives +0.071. (c) Updating (b) with VAL gives +0.027, posterior sd 0.028, P>0 0.83. (d) Regressing VAL on IS across 8.8k configs (slope 0.26, corr 0.17) predicts +0.058. Configs with IS t 1.8-2.2 decay from +0.113 to +0.076 in VAL (ratio 0.68). Within IS, split-half decay ratios for t 1.5-2.5 are 0.27-0.49. Central estimate: about +0.03R, range +0.02 to +0.07R.
- Dependence on the top trades. Median trade is -0.27R and win rate 0.445. The strategy is a right-tail harvester. In IS, dropping the top 1/5/10/20 trades gives +0.100/+0.049/+0.009/-0.054. Removing the top 12 of 532 trades (2.3%) takes IS to zero, and the top 5% of trades carry 167% of total R. Winsorising at 2R gives +0.003 and at 3R +0.060. In VAL, removing the single best trade (+5.2R, 2023-09-27) turns the period negative (-0.026). The largest trade is +11.7R on 2014-06-19 (post-FOMC rally), confirmed on real Dukascopy data (+11.76R).
- Dependence on single years. 2014 is the dominant year, not 2015 or 2020: 42 trades at +0.65R each, 27.4R of the 64.7R IS total (42%). IS without 2014 is +0.076 (t 1.26). Without 2020: +0.110 (t 1.62). Without 2021: +0.113 (t 1.63). Without 2015: +0.136 (t 2.03, since 2015 was flat at -0.00). Without 2015 and 2020: +0.126 (t 1.71). Without 2014, 2020 and 2021: +0.029 (t 0.41, n 340). Years 2015, 2016, 2018 and 2019 have avg_R between -0.016 and +0.017, so outside 3 strong years the edge is about zero.
- Is 2014 a data artefact? Mostly not. Over 2014-02..2014-10, the primary on real Dukascopy BID/ASK agrees with the HistData-based cache on direction on all 31 common days (R correlation 1.00), and the big trades match. Dukascopy's slightly different ATR admits 7 extra days (and drops 2), which cuts that window from +0.39R/trade to +0.26R/trade (12.98R to 9.86R). The day filter at w/ATR = 0.30 is feed-sensitive: a live broker feed will select a partly different set of days.
- Neighbour stability. The primary's IS/VAL results swing sharply under small knob changes. min_w_atr 0/0.2/0.3/0.35/0.4/0.5 gives VAL +0.100/+0.019/+0.020/+0.099/+0.131/-0.006. atr_regime n=20 vs n=50 gives IS 0.122 vs 0.093. range_end 6 gives +0.133/+0.082. This non-monotonic noise of about ±0.08R per config in VAL is the scale of the sampling error, and it means that the primary's specific parameters carry no information beyond the family.
- Family-level evidence, the strongest argument against a full refutation. 83% of the 8.8k broad-family configs are positive in IS and 71% in VAL. However, they are highly correlated, and the equal-weight family portfolio is only +0.057R (Newey-West t 1.67) in IS, +0.043 (t 1.17) without 2014, and +0.038 (t 0.63) in VAL, with 2023 negative (-0.075). The family was built around round-1 winners (wide stops, late time exit), so even this is optimistic. The evidence supports a small, cost-sized common effect at best, not the primary's +0.12R.
- IS/VAL direction inconsistency. IS longs +0.176 / shorts +0.060. VAL longs -0.120 / shorts +0.197. VAL does not reject IS (z = -0.8 vs the IS mean) and does not support it either: VAL is uninformative (SE 0.125R).
- Power for live confirmation (one-sided 5%, 80% power, sd 1.44R, 60 trades/yr; a simulation with the empirical fat-tailed R distribution agrees within 3%). True +0.12R needs about 880 trades (14.5 years). +0.10 needs 1,270 (21 years). +0.06 needs 3,500 (58 years). +0.04 needs 8,000 (133 years). +0.02 needs 32,000 (530 years). Telling +0.12 from +0.04 needs about 2,000 trades (33 years). The minimum detectable edge is 0.46R after 1 year, 0.33R after 2, 0.21R after 5 and 0.15R after 10. A Wald SPRT of 0 vs +0.06 needs about 30 years on average to accept H0 when the true mean is 0. Live data cannot confirm or reject this edge on any retail timescale; it can only catch cost or execution failures.
- Live P&L will not discriminate. Even if the true edge were +0.12R, after 60 trades P(cumulative R < 0) = 0.27 and the 95th-percentile maxDD is 16R. At a true edge of +0.03R, after 120 trades P(<0) = 0.43 and the p95 maxDD is 29R. At a true 0, the p95 maxDD over 250 trades is 47R.

## Risks

- Selection bias: the primary ranks only 14th of 24 in the pre-declared grid and 1,140th of 8,856 in the broad proxy. It was preferred for a composite score, not t. Its IS avg_R of 0.12 is an upward-biased draw, and the honest expectation is about a quarter of it.
- Concentration: 42% of IS profit comes from 2014 (42 trades), and 2.3% of trades (12) carry all of the IS profit. Two or three dull years in a row (as in 2015-2016 and 2018-2019) are the normal state.
- Costs: the shrunk edge (about +0.03R) is smaller than the stressed-cost penalty. Slip 0.10 plus spread +0.10 costs about 0.037R in IS and turned VAL to -0.024R. A retail broker with a 0.35-0.50 spread at 07:00-12:00 London plus commission can make it negative.
- Feed sensitivity: the w/ATR >= 0.30 and ATR-regime boundaries select different days on a different feed. Dukascopy vs HistData in 2014 differed on 9 of about 40 days and moved that window by 0.13R/trade. The broker's D1 ATR (NY close) is another source of drift.
- Positive-skew profile: median trade -0.27R, win rate 44%, losing streaks of 10 in history. Psychological or operational abandonment after a normal drawdown is likely before any statistical conclusion can be reached.
- Regime and direction shift: VAL longs were negative and shorts positive, the reverse balance to IS. The edge may depend on the gold volatility regime (2014, 2020 and 2021 were strong) that live conditions may not repeat.
- Holdout: the primary's VAL rank (5,594 of 8,874) was known before freezing. The holdout is the only uncontaminated test, and with about 150 trades (2024-2026) it has an SE of about 0.12R, so it too can only detect gross failure.

## Guardrails

- Treat the EA as an experiment with a small, possibly zero edge, not a proven system. Size risk per trade at <=0.25-0.5% of equity so that a 30-50R drawdown (p95 at a true edge of 0 to +0.03 over 1-4 years) costs <=15-25% of equity.
- Minimum account size: median 1R is about 6.7 USD/oz (p90 11.6) = 6.7 USD per 0.01 lot, and up to about 12 USD at p90. At 0.25-0.5% risk per trade with the 0.01-lot minimum, you need about 2,500-5,000 USD, or the lot rounding will push risk well above the target.
- Broker requirements: ECN/raw account with XAUUSD spread <=0.30 USD in the 05:00-12:00 London entry window and commission <=7 USD per lot round trip. Stop orders must fill with a median slippage <=0.05 USD, and the SL must be modified after the fill as in the audit. Total round-trip cost must stay <=0.50 USD/oz, or the expected edge is <=0.
- Cost kill switch (the only fast, statistically meaningful monitor): log the realised spread, slippage and commission per trade. If the rolling 30-trade average round-trip cost exceeds 0.60 USD/oz, stop.
- Performance kill switch (a drawdown or catastrophe check, not a significance test): stop if the drawdown exceeds 25R within the first 120 trades (p99 at a true +0.12R is about 28R; p95 at a true 0 is 32R), or 35R at any time. Also stop if cumulative R after 250 trades is below -30R (the p5 at a true +0.03 is -29R).
- Do not re-optimise on live results: 1-3 years of data cannot tell +0.12R from 0 (the minimum detectable edge after 2 years is 0.33R). Parameter changes after a drawdown would be pure noise-fitting.
- Compute ATR14 and the 20-day ATR-regime filter exactly as the engine does, on London days (or verify the broker D1 series matches, correlation >= 0.99). Log for each day whether the filter passed, for a side-by-side comparison with the engine.
- Run the frozen FALLBACK (or the whole small family, if run as a basket) on a demo account in parallel. The family-level evidence is the less selection-biased signal, and the primary's specific knobs carry no extra information.

## Engine/data notes

- No engine bug found. The primary reproduces exactly: IS n 532, avg_R 0.1216; VAL n 113, avg_R 0.0202.
- The 2014 HistData block is valid by direction and R on the common days against real Dukascopy (31/31 same direction, R correlation 1.00; the 11.7R trade on 2014-06-19 is confirmed). The w/ATR and ATR-regime day filters are sensitive to the feed: over 2014-02..10, Dukascopy admits 7 extra days and drops 2, cutting that window's avg from +0.39 to +0.26R/trade.
- The ASK is modelled (BID + hourly median spread), so spread spikes at news-driven breakouts, which are exactly the right-tail winners, are not represented. The live cost on the trades that matter most is probably above the model.
- Minor: the engine requires 12 days of ATR-regime warm-up plus 14 of ATR, so the primary starts on 2014-02-20. Only 42 trades fall in 2014 because the regime and width filters remove most days, not because of missing data.

## Full report

STATISTICAL VALIDITY / OVERFITTING LENS: the frozen PRIMARY re5_w030_a20_W1.00 (IS+VAL only)

Verdict: WEAK, bordering on refuted. There may be a small positive effect shared by the whole wide-stop, late-exit Asian-breakout family. Once the search is accounted for, the primary's own IS +0.12R is not supported.

1. Bootstrap confidence intervals (stationary bootstrap by trading day, mean block 10 days, 20k resamples)
| Period | avg_R | 90% CI | P(avg_R > 0), selection ignored |
|---|---|---|---|
| IS | +0.122 | [+0.022, +0.224] | 0.979 |
| VAL | +0.020 | [-0.177, +0.234] | 0.554 |
| Pooled | +0.104 | [+0.015, +0.198] | 0.974 |
- Block lengths from 1 to 60 days change the SE by less than 10%, so serial dependence is negligible.
- VAL is uninformative (SE 0.125R). It neither confirms nor rejects IS (z = -0.8).

2. Honest multiple testing
- The 24-grid's participation ratio of 2.3 understates multiplicity for a max-type choice. Matching its max-t 95% quantile (2.62) to independent tests gives N_eff about 12.
- I built a 12,960-config engine-native proxy of the round-1 space (final/verify_statistics/s02_broad_family.py). Its studentised stationary-bootstrap max-t gives:
  - N_eff about 204 (matched on the mean max-t, 2.77) or about 1,350 (matched on the q95, 3.96).
  - The primary ranks 1,140th of 8,856 (t 1.91), with p_family 0.905. The fallback's p_family is 0.64.
  - The best config in the entire family (t 3.29) has p_family 0.21.
- Deflated Sharpe: 0.62 at N=12, 0.18 at N=204, 0.06 at N=1,350 and 0.01 at N=20,000. Using the family's cross-sectional SR variance gives 0.05 at N=204. The pooled figures are no better.
- Harvey-Liu haircut: IS SR_ann 0.68 (two-sided p 0.053) is cut 75% at N=12 (Bonferroni/Holm) and 100% at N>=24 with every method. Pooled: 86% at N=12, 100% at N>=24.

3. Shrinkage (expected OOS avg_R at backtest costs)
- Empirical Bayes with a prior mean of 0 and tau 0.033 (the split-half persistent-effect SD across the family): +0.027 (P>0 0.82). After updating with VAL: +0.027 ± 0.028.
- Skeptical priors: tau 0.03 gives +0.023, tau 0.05 gives +0.047, tau 0.10 gives +0.083.
- IS->VAL regression across 8.8k configs (slope 0.26): predicts +0.058. Configs with IS t 1.8-2.2 keep 68% of their IS mean in VAL. Split-half decay within IS keeps 27-49%.
- Consensus: about +0.03R, with a plausible range of 0 to +0.07R. At stressed or retail live costs, about 0 to +0.02R.

4. Fragility
- Top trades: removing the top 12 of 532 IS trades (2.3%) takes IS to zero. Dropping the top 10 leaves +0.009. Winsorising at 2R leaves +0.003. Removing the single best VAL trade makes VAL negative. The median trade is -0.27R.
- Years: 2014 is the key year, not 2015 or 2020. It has 42 trades at +0.65R each, 42% of the IS R.
  - IS without 2014: +0.076 (t 1.26).
  - Without 2020: t 1.62. Without 2021: t 1.63.
  - Without 2015: t 2.03 (2015 was flat).
  - Without 2014, 2020 and 2021: +0.029 (t 0.41).
- Data check on 2014: re-running on real Dukascopy BID/ASK for 2014 matches direction on all common days, and the 11.7R trade is real. The filter selects 9 of about 40 days differently, which lowers that window by 0.13R/trade, so the filters are feed-sensitive.
- Neighbours: VAL swings by about ±0.08R across adjacent min_w_atr values (0: +0.100, 0.2: +0.019, 0.3: +0.020, 0.35: +0.099, 0.4: +0.131, 0.5: -0.006). The chosen knobs carry no information beyond the family.
- Family portfolio: the equal-weight portfolio of all 8.8k configs is +0.057 (NW t 1.67) in IS, t 1.17 without 2014, and +0.038 (t 0.63) in VAL. This is the only argument against a full refutation, and it is itself optimistic because the family was built from round-1 winners.

5. Power
- With sd 1.44R and 60 trades a year, 80% power at one-sided 5% needs:
  - about 880 trades (14.5 years) if the true edge is +0.12R
  - 3,500 trades (58 years) at +0.06R
  - 8,000 trades (133 years) at +0.04R
- Minimum detectable edge: 0.46R after 1 year, 0.33R after 2, 0.21R after 5.
- A Wald SPRT of 0 vs +0.06 needs about 30 years on average to accept a zero edge.
- Even at a true +0.12R, P(losing after 1 year) = 0.27.
- Live trading therefore cannot confirm or reject this edge. Only cost and execution monitoring and a drawdown catastrophe stop are meaningful.

Files (all in /home/user/gold-oi-dashboard/research/range_breakout/final/verify_statistics/):
- s01_core.py -> s01_core.json, trades_primary.csv, trades_fallback.csv (bootstrap CIs, tails, years)
- s02_broad_family.py -> broad_family_S_IS.npz, broad_family_S_VAL.npz, broad_family_configs.json (12,960-config proxy)
- s03_inference.py -> s03_inference.json (reality check, N_eff, DSR, Harvey-Liu, decay)
- s04_shrink_power.py -> s04_shrink_power.json (shrinkage, family-level test, neighbours, power, SPRT)
- s05_duka_2014.py -> s05_duka_2014.json (2014 checked on real Dukascopy)
- s06_dd_killswitch.py -> s06_dd_killswitch.json (drawdown and final-R bands by true mu and horizon)

engine.py was not modified, and no 2024+ data was loaded.
