# MT5 EA: XAU_AsianRangeBreakout.mq5

## Inputs

- InpPreset (enum): PRIMARY re5_w030_a20_W1.00 (default) / FALLBACK re5_w035_nor_W1.00 / CUSTOM. The two frozen presets are hard-coded from final/candidates.json and override every engine-knob input below, so switching to the fallback is one dropdown change.
- Engine knobs, used only when Preset = CUSTOM: InpRangeStart 0, InpRangeEnd 5, InpEntryEnd 12, InpExitTime 20 (all London hours), InpBufK 0, InpBufAtr 0, InpSlRef 0 (0 = range width, 1 = ATR14, 2 = opposite edge), InpSlK 1.0, InpTpR 0, InpBeR 0, InpTrailR 0, InpMinWAtr 0.30, InpMaxWAtr 99, InpAtrRegimeN 20, InpAtrRegimeMax 1.0, InpTradeMon..InpTradeFri true (dow_mask), InpSkipNfp false. entry_mode 0, max_trades 1, comp_n 0 and trend 0 are fixed at their frozen values and are not inputs.
- InpServerClock (enum): GMT+2/+3 following US DST (default) / GMT+2/+3 following EU DST / fixed offset / auto from TimeTradeServer()-TimeGMT() (live only; in the tester it falls back to the US rule with a warning). InpFixedOffsetHours 2.0. InpHaltOnClockMismatch true: live only, no trading if the chosen rule disagrees with TimeGMT() by more than 2 minutes (re-checked hourly).
- InpAtrSource (enum): London-day bars built from M1 (default; the exact engine definition) / broker D1 bars (NY close).
- InpSkipFullHolidays true: no trade on Dec 25, Jan 1, those two observed on a Monday, and Good Friday. The engine data has no valid range on these days.
- InpMaxSpread 1.0 USD/oz (engine max_spread). InpWideSpreadAtPlacement: WAIT (default, engine semantics) / SKIP the day.
- InpUsePendingOrders true (false = EA-side triggers + market orders). InpDeviationPoints 50, InpMaxRetries 3, InpReplaceThrottleSec 30.
- InpUseUSHolidayCalendar true. InpEarlyCloseFlatten 17.5 London hours. InpExtraEarlyCloseDates "YYYY.MM.DD,...". InpSessionEndBufferMin 5. InpFridayFlatten 21.5 London hours (weekend guard).
- InpRiskPercent 0.5. InpRiskBase: Balance / Equity. InpFixedLots 0 (> 0 overrides risk %). InpMaxLots 0 (no cap). InpCommissionPerLot 0: a round-trip commission per lot that is optionally added to the per-lot loss when sizing.
- InpMagic 20260927. InpExpectedContractSize 100 (0 disables the check). InpRequireGoldSymbol true. InpAllowMultipleInstances false. InpVerbose true.

## Design notes

WHAT I BUILT
- ea/XAU_AsianRangeBreakout.mq5 is a single file, about 1,830 lines, using Trade\Trade.mqh.
- Two Python checks sit next to it. ea/parity_check.py ports the EA's clock, holiday, range, ATR and regime logic line by line and compares it with engine.py. ea/divergence_check.py measures the remaining differences. Their logs are ea/parity_check.log and ea/divergence_check.log.
- Both scripts load data only up to VAL_END. engine.py was not edited, and its tests still pass (26).
- I could not compile the EA: there is no MetaEditor in this environment. I reviewed it by hand for MQL5 syntax and API signatures. Braces and parentheses balance, and every external call is a real MQL5 or CTrade function.

TIME
- Every decision runs on a London-clock datetime. The chain is server -> UTC -> London, using US DST rules (2007+ and pre-2007) and UK/EU DST rules written in code and cached per year. Nothing relies on TimeGMT in the tester.
- Check 1 compared these functions with zoneinfo at every 15 minutes from 2010 to 2030, for both the US and EU GMT+2/+3 conventions. There were 0 mismatches on weekdays; the only ambiguous hours fall on weekend DST switches.
- At init the EA logs server time, UTC, London time, the offset and BST/GMT. It also logs the day's schedule on the server clock at every new day.
- Live, the chosen rule is checked against TimeGMT(). A mismatch halts trading by default.

DAY STATE MACHINE
- Per London day the EA moves through IDLE -> ARMED -> INPOS -> DONE.
- At the first tick at or after range_end it computes the range and filters, sizes the trade and arms.
- Pending orders are deleted at min(entry_end, flatten time).
- The position is flattened at min(exit_time, US early close, broker session end minus 5 min, Friday 21:30).

STOP LEVEL / FREEZE LEVEL (the choice asked for)
- If a level is closer to the market than SYMBOL_TRADE_STOPS_LEVEL or FREEZE_LEVEL allows, that side becomes an EA-side trigger. The EA watches ASK >= buy level or BID <= sell level on every tick and sends a market order on the touch.
- If price is already beyond a level when the EA arms (the 05:00 bar opens through it), it enters at market.
- This matches the engine, which fills at max(level, open) + slip on the trigger bar. Skipping those days would change the trade set. Moving the level out to the stops distance would change the entry.
- Pending orders are placed only where the broker allows. If the spread goes above max, they are pulled and put back later, throttled to one attempt per 30 s.
- Deletes and modifications check the freeze level first.

SPREAD
- The engine skips the day only when the spread is too wide on the bar that triggers the entry.
- The EA does the same by default: while the spread is above max it removes its orders. A breakout during that time skips the day; once the spread is back to normal the orders are re-armed.
- The option to skip the day when the spread is wide at placement, as the task spec asked, is available as InpWideSpreadAtPlacement = SKIP.

STOP LOSS AFTER THE FILL
- The pending order carries a provisional SL measured from the level, so the position is protected from the moment it fills.
- After the fill the SL is moved to fill -/+ risk, using the actual fill price, as the audit requires.
- If the broker refuses the modification, an EA-side stop or TP on the same level closes the position at market.

BREAK-EVEN / TRAIL (off in both candidates, but implemented)
- The best price is rebuilt without stored state from completed M1 bars after the entry bar: BID high for longs, ASK low from ticks for shorts, falling back to bar low + bar spread.
- The SL is then max(base, entry + 0.05 if gain >= be_r, best - trail_r x R).
- This gives exactly the engine's result, because both updates only ever tighten.

RESTART SAFETY
- On init or a new day the state is rebuilt from the broker: today's positions, pending orders and deals (history counted by entry order and position ID), plus a GlobalVariable marker for days already skipped.
- Pending orders or positions from earlier London days are closed or deleted.
- Range and ATR are recomputed from history; the calculation is deterministic.
- Breakouts that happened on bars the EA never watched are logged as missed and not chased.
- Pending orders get an ORDER_TIME_SPECIFIED expiry at entry_end when the symbol allows it, as a broker-side backstop.

OTHER ROBUSTNESS
- Retcodes: requote, price changed, price off, timeout, connection, too many requests, locked and reject are retried. Invalid stops is retried without the SL. Invalid expiration is retried as GTC. Market closed is retried on the next tick.
- One instance per chart: the EA refuses to start if another chart runs it on the same symbol (CHART_EXPERT_NAME scan) or if another instance with the same magic is alive (heartbeat GlobalVariable).
- Symbol sanity: digits must be 1-3, contract size must equal 100, price must be 200-50,000, and the name must contain XAU or GOLD. Otherwise the EA refuses to trade.

SIZING
- lots = floor((balance x 0.5%) / (SL distance x value of 1.0 per lot) / step) x step. The value comes from OrderCalcProfit, so it is correct in any account currency; for a USD account it equals the contract size.
- If the result is below the minimum volume, or margin is insufficient, the day is skipped and the reason is logged. The EA never rounds up.

LOGGING
- Log lines are prefixed, and repeated messages are rate-limited.
- One DAILY SUMMARY line per day: range H/L/W, bar count, ATR14, W/ATR, regime ratio, the decision or skip reason, direction, lots, entry and exit with times, exit reason, P/L and R.

PARITY RESULTS (2014-03..2023, GMT+2/+3 US-DST server clock)
- The EA port arms exactly the engine's days: PRIMARY 712/712, FALLBACK 885/885. Ranges and ATR14 are identical, and all 640 / 775 engine trades fall on EA-armed days.
- Broker-D1 ATR agrees on 92.6% of days for the primary and 97% for the fallback. On engine trades filtered by the EA's D1 decisions:
  - PRIMARY: IS +0.144R (t 2.21) against +0.125R with London ATR; VAL +0.025R against +0.020R.
  - FALLBACK: IS +0.111R against +0.117R; VAL +0.050R against +0.040R.
  - These averages are from 2014-03 on, which is why they differ slightly from the frozen summary.
- London-day ATR stays the default because it is the exact engine definition.
- Early closes: the EA's US calendar matches 76 of the engine's 91 ex_close days. The other 15 are full holidays, which the EA skips anyway. The one calendar-only day is 2019-07-04, where the data shows quotes at 20:00. The engine's flat time on those days ranges from 17.72 to 19.78 London hours, median 18.00. The EA flattens at 17:30.

## Parity map (engine.py -> EA)

RULE-BY-RULE MAP (engine.py -> EA)

Clock and day
- Day = London calendar date, Mon-Fri (engine: lmin from tz_convert Europe/London, _daily drops weekend dates). EA: DayStart(ServerToLondon(TimeCurrent)); weekend London dates only close stale positions. Verified against zoneinfo (check 1).

Range
- Engine _windows_full: BID high/low of bars with London time in [rs, re), rounded to whole minutes. EA ComputeDay: CopyRates(M1, LondonToServer(key+rs), LondonToServer(key+re)-1), max(high), min(low). HoursToSec rounds to whole minutes like the engine.
- 60% coverage (b-a >= 0.6 x expected minutes): same test, n < 0.6*expected skips the day.
- The first bar at/after range_end must start < 30 min after it: Setup checks b[0].time - re_s < 1800 s.
- width > 0: same.

ATR14 and filters
- ATR14_prev (_daily): TR = max(h-l, |h-pc|, |l-pc|) on London weekday bars, rolling(14).mean().shift(1). EA DailyFeatures builds the same London-day OHLC from M1 (weekends dropped, prev close = previous weekday) and uses AtrEnd(m-1) = mean of the TRs of the 14 completed days before today. Broker D1 is an option.
- W/ATR filter (min_w_atr <= width/atr <= max_w_atr): identical test.
- ATR regime (rolling(n, min_periods=min(n, max(5, int(0.6n)))) mean of atr14_prev including today; trade if atr <= max x mean): EA mean of AtrEnd(m-1-j), j = 0..n-1, same min periods, same test.
- dow_mask and skip_nfp: London weekday of the key, and Friday with day of month <= 7.
- Engine days without a valid range (Dec 25, Jan 1, their Monday-observed days, Good Friday): the EA skips them explicitly. This made no difference to the parity result.
- Check 3: EA-armed days equal engine-mask days, 712/712 (PRIMARY) and 885/885 (FALLBACK), with 0 range and 0 ATR mismatches.

Entry
- Levels lvl_l = rh + buf, lvl_s = rl - buf, buf = buf_k*width + buf_atr*atr (BID based): identical, normalised to the tick.
- Buy trigger ah >= lvl_l, sell trigger bl <= lvl_s: a broker BUY STOP triggers on ASK and a SELL STOP on BID. EA-side triggers use tick.ask >= lvl_l and tick.bid <= lvl_s.
- Fill = max(lvl, ao) + slip: a real fill. A market order is used when price is already beyond the level at arming, or the level is inside the stops level.
- Both levels hit in the same bar -> skip day: skipped if both are crossed at once; otherwise the first fill wins. This happened on 0 IS/VAL days.
- Spread at the trigger bar > max_spread -> skip day: orders are pulled while spread > max, and a breakout during that time skips the day.
- Entries only on bars before entry_end: pending orders deleted at the first tick >= min(entry_end, flatten time), plus a broker expiry.
- max_trades 1, each side at most once: OCO deletion on fill, and today's entry deals counted by distinct order. After any entry the day is DONE.

Stops and targets
- risk = sl_k x width (sl_ref 0) or sl_k x atr (sl_ref 1), floored at 0.3; sl_ref 2 = distance from the fill to the opposite edge, floored at 0.1. Same values, measured from the ACTUAL fill: SL = fill - dir x risk (engine: sl = entry - pos x risk).
- Entry bar checks the SL only; TP from the next bar: the broker SL is active from the fill, and the TP is attached only once the minute after the entry bar starts.
- TP = entry + pos x tp_r x risk, only if tp_r > 0: same formula on the fill.
- Break-even (gain = pos*(best-entry)/risk >= be_r -> sl = entry +/- 0.05) and trail (sl = best -/+ trail_r x risk once BE is done, or immediately if be_r = 0): best is taken from bars after the entry bar and the result applied from the next bar. The stateless recompute is identical because both updates only ever tighten. Not used by either candidate.

Exits
- Time exit at the open of the first bar >= exit_time: close at the first tick >= exit_time London.
- ex_close (market closed at exit_time) -> flatten at the last bar's close: the EA flattens early at min(17:30 on US early-close days or InpExtraEarlyCloseDates, broker session end from SymbolInfoSessionTrade minus 5 min, Friday 21:30). Positions from an earlier London day are closed at once, so nothing is held over a weekend. Check 2: the calendar covers all 76 non-holiday ex_close days in 2014-2023.

Not in the engine
- Costs (commission 0.07, slip 0.05) are cost-model parameters, not EA rules; the real broker charges apply.
- R in the daily summary is P/L divided by (risk x lots x value of 1.0 price per lot).

## Known limitations

- Not compiled here: there is no MetaEditor in this environment. It was reviewed by hand and checked structurally. The first MetaEditor build may raise minor warnings, such as implicit long/datetime conversions.
- Fills are real: slippage, requotes and latency replace the engine's fixed 0.05 slip. Costs are about 0.09R per trade, the same size as the edge, so an ECN-type account with a round trip of about 0.5 USD/oz or less is needed.
- Spread semantics differ slightly. The engine checks the spread at the trigger bar's open. The EA checks it per tick, and a live broker stop can fill in the very tick the spread widens. max_spread 1.0 almost never binds in the backtest.
- Two engine conventions are resolved differently live, but neither changed a single IS/VAL day. When both levels are touched inside one M1 bar, the engine skips the day while the EA keeps the first fill; this happened on 0 IS/VAL days. An OCO race, where both stop orders fill before the second is deleted, is handled by closing the later position (hedging) or flattening (netting).
- US early closes flatten at a fixed 17:30 London from a built-in calendar: MLK, Presidents, Memorial, Juneteenth (2022+), July 4 observed, Labor Day, Thanksgiving and the day after, and Christmas Eve. The engine exits at the last bar before the halt, about 18:00 London. The EA does not know broker-specific or ad-hoc closures unless they appear in SymbolInfoSessionTrade or in InpExtraEarlyCloseDates.
- The late-arming check (breakouts on bars the EA did not watch) estimates the ASK high as BID high + MqlRates.spread. If the broker's M1 spread field is unreliable, a restarted EA may skip a day it could have armed.
- When break-even or trailing is enabled (off in both candidates), the short-side ASK low comes from CopyTicksRange and falls back to bar low + bar spread. The M1-OHLC tester mode only approximates it.
- Auto clock mode keeps a constant measured offset for all history. Around a DST switch the London-day ATR can be wrong by an hour of bars. The explicit US or EU rule is recommended.
- London-day ATR needs about 70 calendar days of M1 history (about 60k bars). Start tester runs at least 3 months after the broker's M1 history begins, and keep 'Max bars in chart' at 100k or more. Until the history is there the EA retries every 60 s and then logs the day as not traded.
- The broker's M1 history differs from the HistData/Dukascopy research data (feed, clock, gaps), so tester results will not match engine.py trade for trade. The parity guarantee covers the decision logic, not the broker's prices.
- Custom mode supports only entry_mode 0, max_trades 1, range_end > 0 and no comp or trend filters. Other values are rejected or are not inputs.
- Statistical caveat, repeated in the header and at init: the edge is not established. PRIMARY IS t is 1.94 and VAL avg is +0.020R (t 0.16). Its DSR is 0.18-0.35 and its family p is 0.16 in IS and 0.85 in VAL. The holdout (2024+) is still sealed and nothing was tuned on it.

## Independent review

### Fixed

- Live race could cause a duplicate entry (ManageArmed). When a broker-side stop triggered, the order could leave OrdersTotal() before the position or deal was visible. The EA would then see 'crossed and no order on that side' and send a second, market entry. On a netting account that doubles the position, which the OCO-race handler then flattens. Fix: new SDay fields seen_l/seen_s record when our BUY/SELL STOP was last seen live. They are cleared when the EA deletes the order itself in DeletePendings. If a level is crossed within 10 s of the order disappearing, the EA sets g_deal_flag and waits instead of sending a market order.
- One-trade-per-day (OCO) could leak. OnFilled tried to delete the opposite stop only once, and the INPOS state never retried, so a failed delete (requote, connection, freeze) could leave the opposite order live for a second trade. Fix: ManagePosition now retries DeletePendings every 5 s while any of our pending orders exist.
- Infinite no-SL loop in OnFilled/ManagePosition. With g_d.computed true but risk_plan 0 (ATR undefined), risk stayed 0 and the fallback to the position's own SL was unreachable because of an else-if. ManagePosition then re-ran the heavy ComputeDay (about 70k M1 bars) on every tick, and neither the EA-side stop nor the SL sync ran. Fix: the code now falls back to |fill - current SL| whenever risk <= 0, and the recompute is throttled to once per 30 s.
- Timer-driven Setup ran before the first tick at/after range_end (live; OnTimer runs on TimeTradeServer()). This had two effects. (a) The range could be computed while the 04:59 bar could still receive late ticks stamped before 05:00. (b) With nb==0 the heavy ComputeDay was repeated every second with no throttle. Fix: Setup now waits until SymbolInfoTick time >= range_end on the server clock. It skips the day if no tick arrives within 30 min, which is the engine's invalid-day rule. It does this before ComputeDay. The duplicate re_s declaration was removed.
- Order-type robustness. Added NextFilling(): on TRADE_RETCODE_INVALID_FILL, both market and stop orders switch to the next filling policy the symbol allows (FOK -> IOC -> RETURN), because some servers reject the market filling policy for stop orders. Expiration: if the symbol does not allow GTC, stop orders are sent as ORDER_TIME_DAY. On INVALID_EXPIRATION the fallback is now SPECIFIED -> GTC (if allowed) -> DAY. The old code retried GTC even when GTC was not allowed.
- Added an init warning if SYMBOL_CHART_MODE is not BID. The engine's range and ATR are BID-based; a LAST-built chart would silently change the range.

### Blocking

- none

### Parity verdict

For the frozen PRIMARY (and the FALLBACK), the EA's trade decisions match engine.py. File: /home/user/gold-oi-dashboard/research/range_breakout/ea/XAU_AsianRangeBreakout.mq5. engine.py is untouched (sha256 7eb6bb0a...a4579, 26 tests pass).

Verified items:
- Range: BID high/low of M1 bars in London [00:00, 05:00). CopyRates(rs_s, re_s-1) includes both end bars, which is correct. At least 60% of the minutes must exist, and the first bar at/after range_end must be less than 30 min late.
- ATR14: London-day bars built from M1, with weekend London dates dropped and weekdays only (as in the engine). ATR14 is the mean of the 14 true ranges up to yesterday. tr[0] is never used because AtrEnd needs k>=14 and m>=15.
- Regime filter: mean of atr14_prev over the last 20 London trading days including today, min periods min(n, max(5, int(0.6n))) = 12. The rule is ATR <= 1.0 x mean. W/ATR must be >= 0.30.
- Orders: buy stop at the range high triggers on ASK, sell stop at the range low triggers on BID (native MT5). OCO. No new entries at/after 12:00; pending orders are deleted and a broker-side expiry is set.
- Exits: SL = max(1.0 x width, 0.30) measured from the actual fill (POSITION_PRICE_OPEN), no TP, time exit at the first tick at/after 20:00 London, one trade per day (INPOS -> DONE).
- A breakout while the spread is above max_spread skips the day, as in the engine.
- MQL5 API: CopyRates arrays are non-series (index 0 is the oldest), which is how they are used. CTrade Buy, BuyStop, PositionModify and PositionClose signatures are correct. SymbolInfoSessionTrade, MqlDateTime and StructToTime are used correctly, and integer and datetime arithmetic is right.
- DST, checked by hand and with the code's port against zoneinfo, for a GMT+2/+3 US-DST server (London 00/05/07/12/20 -> server):
  - 2025-03-10: 03:00 / 08:00 / 10:00 / 15:00 / 23:00 (US DST, UK GMT)
  - 2025-03-31: 02:00 / 07:00 / 09:00 / 14:00 / 22:00
  - 2025-10-27: 03:00 / 08:00 / 10:00 / 15:00 / 23:00
  - 2025-11-03: 02:00 / 07:00 / 09:00 / 14:00 / 22:00
  All match the code.
- Risk: sizing uses OrderCalcProfit for a 1.0 price move per lot, times the planned SL distance (plus the optional commission). Volume is rounded down to the step; the trade is skipped if it is below the minimum volume or if free margin is short. This matches R in the engine: long entry on ASK, SL on BID.

Remaining divergences are intentional or tick-vs-bar effects (listed under risks). I could not compile the file because there is no MetaEditor here. My edits use only standard MQL5 and CTrade calls. Braces and parentheses balance.

### Remaining risks

- Not compiled: there is no MetaEditor in this environment. Compile it in MetaEditor before any tester run and fix any warnings or errors there. The new code uses SYMBOL_FILLING_MODE, CTrade::RequestTypeFilling/SetTypeFilling, EnumToString and SYMBOL_CHART_MODE.
- Early-close days: the EA flattens at 17:30 London (InpEarlyCloseFlatten). The engine flattens at the close of the last bar before 20:00, median 18:00 and minimum 17:72. This is a small, conservative difference. The engine also has 15 ex_close days (Dec 25, Jan 1, Good Friday) that the EA skips entirely; parity_check shows the engine made 0 trades on those days.
- Both levels in one M1 bar: the engine skips the day, while the EA takes the first touch and OCO-deletes the other order. divergence_check found 0 such days for PRIMARY in IS/VAL, so the impact is negligible but not zero live.
- London-day ATR needs about 70 calendar days of M1 (about 70k bars). Live, 'Max bars in chart' must be at least about 100k. In the tester, M1 history must exist before the test start; otherwise the first weeks of a test have no trades and are retried every 60 s. A CUSTOM atr_regime_n well above 20 needs proportionally more M1 history.
- Differences in data source: broker M1 history (holiday bars, Sunday open, spikes) differs from HistData, so ATR, the regime filter and range values can differ on some days. The broker-D1 ATR option agrees on only 93% of armed days for PRIMARY.
- The clock rule must match the broker. The default is GMT+2/+3 with US DST. In the tester there is no TimeGMT() check, so a wrong InpServerClock silently shifts every session by 1 hour. Check the init log (server/UTC/London) against the broker.
- The broker's holiday sessions are not visible to SymbolInfoSessionTrade, which only gives the weekly schedule. Unlisted early closes (e.g. broker-specific Dec 24/31 hours) need InpExtraEarlyCloseDates. Otherwise the 20:00 close fails with MARKET_CLOSED and the position is held until the market reopens.
- Execution costs decide the edge. Real stop-order slippage and spread on the account must be at or below about 0.5 USD/oz round trip. At slip 0.10 and spread +0.10, VAL turns negative (-0.024R).
- The statistical evidence is weak: VAL t 0.16, DSR 0.18-0.35, and the primary's family p is 0.85 in VAL. The EA faithfully implements a strategy whose edge is not established.
- The 10 s race-guard grace is a heuristic. If a broker cancels a triggered stop (for example on a margin reject), the EA sends a market entry up to 10 s late.
