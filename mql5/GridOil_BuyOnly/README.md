# GridOil Buy-Only v2.10 — MQL5 Market edition

Built from `GridOil_BuyOnly_NoKey.mq5` v2.00. All trading logic is the same: Auto/Manual Zone, Profit-Funded De-risk, Equity Stop, capital calculator and Trend Rider.

## Changes for MQL5 Market

| Topic | v2.00 | v2.10 Market |
|---|---|---|
| Language | Thai inputs, logs and panel | **English** throughout (Market rule) |
| Contacts | LINE `@krujeabforex` in Comment | Removed (external contacts are forbidden) |
| MessageBox | Shown on underfunding / netting | Replaced by Alert / log. When underfunded the EA loads in watch-only mode instead of refusing to load |
| Pre-order checks | None | Volume min/max, `ACCOUNT_LIMIT_ORDERS`, `SYMBOL_VOLUME_LIMIT`, margin (`InpMaxMarginUsage`), TP vs stops level, trade permissions, `SYMBOL_TRADE_MODE`. This avoids "not enough money" / "invalid volume" errors, which fail Market validation |
| Spread filter | Fixed `0.10` price units (never trades on symbols with larger prices, e.g. gold) | `InpMaxSpreadPct = 0.15` % of price (≈ 0.10 on WTI at 70) |
| Price rounding | `NormalizeDouble` | Snapped to `SYMBOL_TRADE_TICK_SIZE` |
| Trailing SL | Checked stops level only | Also checks freeze level |
| Tester | `Sleep`, Alert, Comment every tick | `Sleep`/Alert skipped in the tester; panel off in non-visual testing (faster optimization) |
| Inputs | Partly validated | `ValidateInputs()` → `INIT_PARAMETERS_INCORRECT` |
| Panel | Always on | `InpShowPanel` switch, redrawn at most once per second |

## Before publishing

1. Compile in MetaEditor (F7) and fix any errors or warnings (not compiled yet; no MetaEditor on the server).
2. Set `#property link` to your mql5.com seller profile.
3. Backtest on your oil symbol **and** on EURUSD H1 with a $1,000 deposit and default inputs. It must open trades with no `not enough money` / `invalid volume` errors in the journal.
4. **Hedging account only.** If validation reports "no trading operations", check first whether the validator ran on a netting account.
5. Paste `market_description_en.html` into the English description (HTML mode).
