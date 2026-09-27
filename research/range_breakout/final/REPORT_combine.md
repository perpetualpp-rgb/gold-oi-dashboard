# Combine & freeze

# Stage: COMBINE AND FREEZE

The holdout (2024+) was not used. Every run in this stage used `engine.load(until=VAL_END)`, so no bar after 2023-12-31 was in memory. The one exception was the equality check in `verify_regime.py`, which loaded the full file but ran only to `end=VAL_END` and produced no 2024+ statistics.

## Summary

- **Frozen candidates** (written to `final/candidates.json`, `frozen_at` 2026-09-27):
  - **PRIMARY `re5_w030_a20_W1.00`:** range 00:00-05:00 London, min_w_atr 0.30, ATR14_prev <= mean20(ATR14_prev), SL 1x range width, no TP, entries until 12:00, exit 20:00, one trade a day.
  - **FALLBACK `re5_w035_nor_W1.00`:** the same without the regime filter, with min_w_atr 0.35.
  - **BASELINE:** `Params()`.
- **The primary is the weaker of the two.** The pre-declared rule chose it mechanically and the VAL veto did not trigger (+0.020). By every robustness check, though, the fallback is stronger:

  | Check | Primary | Fallback |
  |---|---|---|
  | IS t | 1.94 | 2.63 |
  | Family-wise p | 0.16 | 0.055 |
  | VAL avg_R | +0.020 | +0.040 |
  | IS with the top-10 trades removed | +0.009 | +0.054 |
  | DSR at N=100 | 0.26 | 0.54 |
  | VAL longs | -0.12 | +0.02 |

  The primary won because the neighbour-averaged score includes its strong but ineligible neighbours: w0.35 and w0.40 with the regime filter reach IS +0.19 and +0.21R, but only on 45 and 30 trades a year. The rule does not look at neighbour eligibility, which is a weakness of the rule. I did not override it.
- **Honest verdict:**
  - The breakout direction on wide-range days carries information. The random-direction null gives p <= 0.001 in IS, and 22 of 24 grid configs pass family-wise.
  - Net profitability after costs is not established. VAL t is below 0.5 for both candidates, the combined cost stress in VAL is about 0, and the DSR is below 0.5 for the primary at any N_eff >= 50.
  - Expect roughly 0 to +0.05R per trade out of sample, not the IS +0.12-0.13R.

## 1. Engine changes (tests first; 26/26 pass)

- **`Params.atr_regime_n` / `atr_regime_max`.**
  - Rule: trade day d only if `atr14_prev[d] <= max * rolling_mean(atr14_prev, n)[d]`.
  - Window: London trading days, including d. `min_periods = min(n, max(5, int(0.6n)))`, so n=20 gives 12. No trades while the mean is undefined.
  - It uses the same atr14_prev series as min_w_atr, including the extra 1-day lag when range_end < 0.
  - It reproduces explore/filters F5, F1 and F2 (and w0.40, at range_end 7 and 5) exactly: identical entry bars and R. F1 IS is +0.1128, F2 +0.1386, F5 +0.0851.
  - There is no difference from round 1: explore used `rolling(20, min_periods=12)`, and the ratio and product forms disagree on 0 days.
- **`engine.load(until=None)`.** This cuts at the London date right after the parquet files are read, before any features are computed, and caches the result separately. The default behaviour is unchanged.
- **New tests:**
  - the filter is off by default;
  - calm-day selection with min_periods (n=5);
  - n=20 gives min_periods 12;
  - the lagged ATR is used when range_end < 0;
  - load(until) on synthetic parquet files.
- **Not committed.** `engine_git_hash` is HEAD 66e9063, which does not contain these features. candidates.json therefore also stores the sha256 of the working-tree engine.py and test_engine.py, with `engine_worktree_dirty: true`. Commit before the holdout run to pin the hash.

## 2. Pre-declared grid (`final/grid_spec.json`, written before the grid run)

- **Grid:** 2 range_end {5, 7} x 3 min_w_atr {0.30, 0.35, 0.40} x regime {off, n20 max1} x 2 stops {W1.00 = sl_ref 0 sl_k 1.0; A0.75 = sl_ref 1 sl_k 0.75} = 24 configs. Everything else is fixed: stop entries, buffer 0, entry_end 12, exit 20, no TP, max_trades 1, default costs.
- **Disclosure:** `verify_regime.py` printed IS avg_R for 8 of these configs (the sl_ref 0 ones) before the spec file was written. The grid and rule were fixed verbatim by the task, so no discretion was exercised.

## 3. Selection (mechanical; `final/select_candidates.py`, `selection_table.csv`)

The 24 configs sorted by score. "yrs+" is the number of positive IS years out of 8.

| config | n | tpy | yrs+ | L | S | IS avg_R | t | eligible | score | VAL (veto) |
|---|---|---|---|---|---|---|---|---|---|---|
| re5_w040_a20_W1.00 | 236 | 30.2 | 7 | .247 | .168 | .2088 | 2.49 | no (tpy) | .1991 | |
| re5_w035_a20_W1.00 | 355 | 45.4 | 7 | .241 | .130 | .1894 | 2.77 | no (tpy) | .1732 | |
| **re5_w030_a20_W1.00** | 532 | 67.8 | 6 | .176 | .060 | .1216 | 1.94 | yes | **.1555** | +0.0202 -> PRIMARY |
| re5_w040_a20_A0.75 | 236 | 30.2 | 7 | .166 | .136 | .1513 | 2.67 | no | .1398 | |
| re7_w040_a20_W1.00 | 343 | 43.7 | 6 | .142 | .087 | .1158 | 1.88 | no | .1272 | |
| re7_w030_a20_W1.00 (F1) | 655 | 83.4 | 8 | .124 | .101 | .1128 | 2.12 | yes | .1257 | |
| re5_w035_a20_A0.75 | 355 | 45.4 | 7 | .153 | .099 | .1282 | 2.92 | no | .1248 | |
| re7_w035_a20_W1.00 (F2) | 491 | 62.5 | 7 | .154 | .123 | .1386 | 2.55 | yes | .1224 | |
| re5_w030_a20_A0.75 | 532 | 67.8 | 6 | .108 | .080 | .0947 | 2.67 | yes | .1115 | |
| re5_w030_nor_W1.00 | 945 | 119.2 | 5 | .085 | .080 | .0826 | 1.86 | no (yrs) | .1073 | |
| re5_w040_nor_W1.00 | 436 | 55.2 | 5 | .062 | .094 | .0764 | 1.34 | no | .1042 | |
| **re5_w035_nor_W1.00** | 638 | 80.8 | 6 | .106 | .164 | .1320 | 2.63 | yes | **.0970** | +0.0401 -> FALLBACK |
| re7_w040_a20_A0.75 | 343 | 43.7 | 6 | .091 | .069 | .0806 | 1.82 | no | .0790 | |
| re5_w040_nor_A0.75 | 436 | 55.2 | 6 | .056 | .088 | .0705 | 1.77 | yes | .0783 | |
| re7_w035_a20_A0.75 | 491 | 62.5 | 7 | .093 | .061 | .0773 | 2.14 | yes | .0757 | |
| re5_w030_nor_A0.75 | 945 | 119.2 | 6 | .058 | .073 | .0646 | 2.51 | yes | .0753 | |
| re5_w035_nor_A0.75 | 638 | 80.8 | 7 | .070 | .106 | .0861 | 2.67 | yes | .0737 | |
| re7_w040_nor_W1.00 | 617 | 77.8 | 5 | .041 | .110 | .0716 | 1.59 | no | .0734 | |
| re7_w030_a20_A0.75 | 655 | 83.4 | 6 | .071 | .067 | .0693 | 2.20 | yes | .0733 | |
| re7_w035_nor_W1.00 (F4) | 860 | 108.4 | 6 | .034 | .124 | .0752 | 1.86 | yes | .0675 | |
| re7_w030_nor_W1.00 | 1154 | 145.4 | 5 | .030 | .085 | .0556 | 1.46 | no | .0654 | |
| re7_w040_nor_A0.75 | 617 | 77.8 | 5 | .043 | .083 | .0607 | 1.90 | no | .0548 | |
| re7_w035_nor_A0.75 | 860 | 108.4 | 6 | .037 | .063 | .0488 | 1.84 | yes | .0508 | |
| re7_w030_nor_A0.75 | 1154 | 145.4 | 6 | .026 | .063 | .0428 | 1.88 | yes | .0458 | |

VAL was computed only for the two configs the rule reached. Neither was vetoed.

Grid patterns:
- range_end 5 beats range_end 7 in every matched cell.
- The regime filter adds about +0.04 to +0.06R.
- The width stop has higher avg_R. The 0.75 ATR stop has a higher t and a lower maxDD, because it has lower variance per R.

## 4. Candidate evaluation (`final/evaluate.py`, `eval_results.json`)

### IS / VAL

| | IS n | IS avg_R | IS t | PF | maxDD | L / S | VAL n | VAL avg_R | VAL t | VAL L / S |
|---|---|---|---|---|---|---|---|---|---|---|
| primary | 532 | +0.122 | 1.94 | 1.25 | 16.1 | +.176 / +.060 | 113 | +0.020 | 0.16 | -.120 / +.197 |
| fallback | 638 | +0.132 | 2.63 | 1.31 | 18.2 | +.106 / +.164 | 147 | +0.040 | 0.40 | +.023 / +.060 |
| baseline | 1828 | +0.008 | 0.23 | 1.02 | 43.5 | -.008 / +.026 | 478 | -0.011 | -0.16 | -.093 / +.084 |

### By year (avg_R)

| | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|---|---|
| primary | .653 | .000 | -.016 | .128 | .014 | .017 | .191 | .172 | .082 | -.043 |
| fallback | .503 | .103 | .028 | .104 | -.012 | -.027 | .152 | .247 | .058 | .019 |
| baseline | .031 | .167 | -.023 | -.003 | .014 | -.147 | .100 | -.076 | .017 | -.038 |

2014 carries a large share of the IS result for both candidates. For the primary, 2015-2019 is flat.

### Random-direction null (10k permutations)

| | IS p_coin | VAL p_coin |
|---|---|---|
| primary | 0.0006 | 0.36 |
| fallback | 0.0002 | 0.24 |
| baseline | 0.0098 | 0.28 |

### Cost stress (IS / VAL avg_R)

| Cost setting | primary | fallback | baseline |
|---|---|---|---|
| slip 0.10 | .108 / .011 | .120 / .032 | -.011 / -.020 |
| spread +0.10 | .098 / -.015 | .109 / .003 | -.015 / -.047 |
| both | .085 (t 1.37) / -.024 | .098 (t 1.98) / -.005 | -.032 / -.070 |
| gross | .233 / .033 | .203 / .082 | .099 / .058 |

### Top-trade removal

| | IS without top 5 | IS without top 10 | VAL without top 5 | VAL without top 10 |
|---|---|---|---|---|
| primary | +.049 | +.009 | -.153 | -.292 |
| fallback | +.084 | +.054 | -.073 | -.170 |
| baseline | -.016 | -.034 | | |

The edge lives in the right tail. The primary's IS result depends on about 10 trades, which is 2% of its trades.

### Family-wise reality check (24-config grid)

- **IS:** the q95 of max t* is 2.62. The primary has p_family 0.161 and the fallback 0.055. The best config is re5_w035_a20_A0.75 at 0.025.
- **VAL:** no config is below 0.27. The primary is at 0.85.
- **Direction information (family_null IS):** primary 0.008, fallback 0.001.
- **Correlation:** the 24 configs have mean pairwise daily-R correlation 0.62, which is about 2.3-5 effective independent configs.

### Deflated Sharpe Ratio (Bailey & Lopez de Prado)

- **Method:** per-trade SR, T = number of IS trades. SR0 = sqrt(V) * [(1-γ) Φ⁻¹(1-1/N) + γ Φ⁻¹(1-1/(Ne))], with the skew and kurtosis adjustment in the denominator.
- **Primary inputs:** SR 0.0839, skew 2.25, kurt 13.1, T 532.
- **Choice of V:** V = 1/T, the sampling variance of SR for a zero-edge trial, which is the "all trials are noise" benchmark. As a check, V = the SR variance inside the grid (0.0012) gives similar SR0.

| N | 1 (PSR) | 24 | 50 | 100 | 200 | 500 | 1000 | 2000 | 20000 |
|---|---|---|---|---|---|---|---|---|---|
| primary DSR | 0.983 | 0.48 | 0.354 | 0.257 | 0.182 | 0.11 | 0.074 | 0.049 | 0.011 |
| fallback DSR | 0.998 | 0.76 | 0.649 | 0.543 | 0.443 | 0.325 | 0.251 | 0.190 | 0.067 |
| baseline DSR | 0.593 | 0.04 | 0.020 | 0.011 | 0.006 | | | | 0.0001 |

**Why N_trials = 20,000 is too harsh, and why an effective N of 50-200 is reasonable:**
- The round-1 configs are nested sweeps: timing grids at 30-60 minute steps, exit grids of sl_k x tp_r x be x trail, and filter thresholds 0.05 apart. Neighbouring trials share most of their trades.
- Inside this 24-config grid alone, daily R correlates at 0.62 on average, and the participation ratio is 2.3 effective trials. That is roughly a 5-10x compression within a single small family.
- Round 1 spans about 6 axes with a few distinct mechanisms each (breakout vs fade, timing blocks, stop families, filter families). An independent-trial count in the tens to low hundreds is plausible. By the within-grid compression ratio, a few thousand is an upper bound.
- **Sensitivity with the empirical cross-trial SR variance:** 18,276 round-1 logged net IS configs with n >= 100 give V = 0.0114, and DSR is about 0 for every candidate. This V is dominated by genuinely different, strongly negative families (fades, tight stops), which breaks the DSR's assumption that every trial has a true SR of 0. It is reported, not used.
- **Conclusion:** at N_eff 50-200 the primary has DSR 0.18-0.35, which is not significant. The fallback is 0.44-0.65, better but also not significant. At N = 20,000 both are rejected (0.011 and 0.067).

## 5. Freeze

`final/candidates.json` contains:
- `frozen_at` "2026-09-27";
- `engine_git_hash` 66e9063f28c01f36807f4aeeb9413b8652efe931, plus the working-tree sha256 values;
- the full Params dicts for primary, fallback and baseline;
- the selection rule and selection log;
- IS/VAL stats, by-year results, cost stress, null p-values, top-trade removal, DSR and family p for each candidate.

The candidates are now FROZEN.

**Recommendations for the holdout stage:**
- Evaluate primary, fallback and baseline once each, with no retuning.
- Judge success by the net avg_R sign and the combined-stress result, not by t, because roughly 2.5 years of holdout gives only about 170-200 trades.
- Report the fallback alongside the primary, since the rule-selected primary is the weaker candidate.

## Files (final/)

- **Code:**
  - `common.py`: load with until=VAL_END.
  - `verify_regime.py` (+ .log): native filter vs post-hoc mask.
  - `make_grid_spec.py`: writes `grid_spec.json`.
  - `run_grid.py`: writes `grid_results.csv` and `run_grid.log`.
  - `select_candidates.py`: writes `selection.json`, `selection_table.csv` and `select.log`.
  - `evaluate.py`: writes `eval_results.json`, `evaluate.log` and `family_*.csv`.
  - `neff.py`: writes `neff.json`.
  - `dsr_extra.py`: writes `dsr.json` and `dsr.log`.
  - `make_candidates.py`: writes `candidates.json`.
- **Engine:** `../engine.py` and `../test_engine.py`, modified and not committed.


## Engine changes

engine.py (backward compatible, all 26 tests pass; 5 new tests were written first and failed before the change):
(a) New Params.atr_regime_n (int, default 0 = off) and Params.atr_regime_max (float, default 1.0). Day d is traded only if atr14_prev[d] <= atr_regime_max * rolling_mean(atr14_prev, n)[d]. The window runs over London trading days and includes d itself. min_periods = min(n, max(5, int(0.6*n))), so n=20 gives 12. Days where the mean is undefined never trade. The filter uses the same atr14_prev series as min_w_atr, including the extra 1-day lag when range_end < 0. The min(n, ...) clamp only matters for n < 5, which would otherwise raise in pandas.
Reproduction of explore/filters: F5, F1, F2 and w>=0.40 at range_end 7 and 5 give IDENTICAL trades (same entry bars, same R to 1e-12) to the post-hoc run_mask on features.day_features()['atr_vs_mean20'] <= 1. F1 IS is +0.1128 (n 797 IS+VAL), F2 +0.1386 (n 593), F5 +0.0851 (n 1260). There is no difference: explore used rolling(20, min_periods=12), which equals the rule above. Comparing the ratio form (atr/mean <= 1) with the product form (atr <= 1*mean) gives 0 disagreeing days. Log: final/verify_regime.log.
(b) engine.load(force=False, until=None). With until set, bars whose London date is after `until` are dropped right after the parquet read, before the spread filter and daily features. The cut dataset is cached separately in _DATA_CUT, keyed by date. load() with no argument returns and caches the full dataset exactly as before. On real data, load(until=VAL_END) gives the same trades through VAL_END as load(); verify_regime.py checked this for the default config and for F2.
New tests in test_engine.py: default off; calm-day selection and min_periods (n=5); n=20 -> min_periods 12; lagged ATR when range_end < 0; load(until) on synthetic parquet files, checking the cut, that the cached full dataset is unchanged, and that the cut equals the head of the full data.
Not committed: HEAD is still 66e9063, and candidates.json records the sha256 of the working-tree engine.py.

## Null tests

Random-direction null (explore/null_costs null_test, 10,000 permutations, seed 1, same entry bars, risk and costs). p_coin is P(null avg_R >= actual).
- Primary: IS actual +0.1216 vs coin-null mean -0.037 (sd 0.049), p_coin 0.0006, p_shuffle 0.0007. Longs beat the opposite trade by 0.38R and shorts by 0.25R. VAL actual +0.020 vs null -0.019 (sd 0.104), p_coin 0.36, p_shuffle 0.32. In VAL, longs are worse than the opposite trade (-0.09R) and shorts are better (+0.29R).
- Fallback: IS +0.132 vs -0.025 (sd 0.041), p_coin 0.0002. VAL +0.040 vs -0.019 (sd 0.084), p_coin 0.24. Direction information is positive for both sides in VAL: L +0.03R, S +0.21R.
- Baseline: IS +0.0078 vs -0.056, p_coin 0.0098. VAL -0.0105 vs -0.043, p_coin 0.28. This reproduces round 1.
Family-wise direction test over the 24-config grid (family_null, max-z with one shared coin per date, IS): 22 of 24 configs have p_family < 0.05. Primary p_family is 0.0076, fallback 0.0008. The breakout direction carries information on these filtered days. Profitability is a separate question, covered by the reality check. Full distributions are in final/eval_results.json and final/family_null_IS.csv.

## Family reality check

Studentised stationary-bootstrap reality check (family_bootstrap: max-t, mean block 10 days, 5,000 resamples, dates resampled jointly across configs) over the pre-declared 24-config grid.
IS: the 95% quantile of the max t* is 2.62. Four configs reach p_family < 0.05: re5_w035_a20_A0.75 (0.025), re7_w035_a20_W1.00 (0.033, which is F2), re5_w030_a20_A0.75 (0.041) and re5_w035_a20_W1.00 (0.050). The fallback re5_w035_nor_W1.00 has p_family 0.055 (t_boot 2.57, raw p 0.007). The PRIMARY has p_family 0.161 (t_boot 2.00, raw p 0.026); it ranks 14th of 24 on t.
VAL, reported for information after selection: no config is significant. The best p_family is 0.27 (re7_w035_a20_A0.75); the fallback is 0.77 and the primary 0.85, the second-worst of the 24.
This correction covers only the 24-config family. That family was built from the winners of a roughly 20,000-config round-1 search, so these p-values are strongly optimistic. The DSR, which is the appropriate global correction, puts the primary at 0.18-0.35 for N_eff 50-200.
Correlation structure: the mean pairwise correlation of daily R in IS is 0.62, with a minimum of 0.32. The eigenvalue participation ratio gives an effective 2.3 independent configs, and 5 eigenvalues explain 90% of the variance (final/neff.json). The CSVs are final/family_bootstrap_IS.csv, final/family_bootstrap_VAL.csv and final/family_null_IS.csv.

## Cost stress

avg_R (t in brackets) for IS / VAL. Default costs: commission 0.07, slip 0.05, modelled spread. Stress: slip 0.10, and/or ASK + 0.10 via a modified data dict. The range is built from BID, so the stress does not change it.
- Primary: default +0.122 (1.94) / +0.020; slip 0.10: +0.108 / +0.011; spread +0.10: +0.098 / -0.015; both: +0.085 (1.37) / -0.024; gross, no costs at all: +0.233 (3.65) / +0.033.
- Fallback: default +0.132 (2.63) / +0.040; slip 0.10: +0.120 / +0.032; spread +0.10: +0.109 / +0.003; both: +0.098 (1.98) / -0.005; gross: +0.203 (4.02) / +0.082.
- Baseline: default +0.008 / -0.011; slip 0.10: -0.011 / -0.020; spread +0.10: -0.015 / -0.047; both: -0.032 / -0.070; gross: +0.099 / +0.058.
Both filtered candidates keep a positive IS margin under combined stress, about +0.09R. That margin is gone in VAL, where both are about 0 or slightly negative. The filters roughly halve the cost in R (about 0.05R against 0.09R for the baseline) and raise gross R in IS. In VAL, however, the primary's gross edge is only +0.033R.
