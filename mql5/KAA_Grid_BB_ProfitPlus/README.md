# KAA Grid BB ProfitPlus v2.00 — MQL5 Market edition

The version for sale on mql5.com, built from `EA_KAA_Grid_BB_ProfitPlus_Free.mq5` v1.10.

## What changed from the Free edition

| Topic | Free v1.10 | Market v2.00 |
|---|---|---|
| License | Offline key + LINE contact + MessageBox | **Removed.** MQL5 Market handles licensing, activations and the demo. Market rules forbid external contacts in the product. |
| Distances | Price units (`3.0`, `0.5`) that only work on XAUUSD | **Points** (`InpGridStepPoints`, `InpBBEntryPoints`, `InpMaxStepPoints`), so the EA works on any symbol the validator uses |
| Lot size | Fixed 0.19 | Fixed **0.01** by default, plus **Auto lot by balance** (`LOT_AUTO`) |
| Money targets | Absolute $ | Can scale with lot size (`InpScaleByLot` + `InpReferenceLot = 0.10`). Defaults match the old values (0.19 lot → $100) |
| Checks before every order | Margin only | Volume min/max/step, `ACCOUNT_LIMIT_ORDERS`, `SYMBOL_VOLUME_LIMIT`, margin (`InpMaxMarginUsage`), `SYMBOL_TRADE_MODE` (disabled/close-only/long-only/short-only), terminal/account/EA trade permissions |
| Netting accounts | Broken (levels were read from comments) | Supported. Basket state is kept in GlobalVariables, and one basket at a time is enforced |
| Inputs | Not validated | Validated, returns `INIT_PARAMETERS_INCORRECT` |
| Dashboard | `Comment()` on every tick | Graphic panel, refreshed at most once per second, turned off in non-visual testing and optimization |
| Bugs fixed | – | Level parser now uses the comment prefix; lot rounding follows `SYMBOL_VOLUME_STEP`; spread comes from the current tick; hitting max DD with `CloseOnMaxDD=false` no longer blocks basket TP; `Sleep()` is skipped in the tester |

## Before publishing — checklist

1. Open `KAA_Grid_BB_ProfitPlus.mq5` in MetaEditor, compile (F7) and fix any warnings (this version has not been compiled yet because MetaEditor is not available on the server).
2. Change `#property link` to your mql5.com seller profile URL.
3. Run the Strategy Tester in "Every tick based on real ticks" mode on:
   - XAUUSD M15 (the main use case)
   - EURUSD H1 and GBPUSD M1 with the default inputs and a $1000 deposit (simulates the Market validator; it must open at least one trade with no `invalid volume` / `not enough money` errors).
   - A netting account, if your broker has one.
4. For 3-digit gold (e.g. 2345.678), multiply the point-based inputs by 10 (`GridStepPoints 3000`, `BBEntryPoints 500`). With `UseATRGrid=true` (the default), grid spacing already follows ATR on either digit setting.
5. Upload at mql5.com → Profile → Sell → Add product → Expert Advisor. Upload the compiled `.ex5`, then wait for the automatic validation.
6. Prepare at least 1 screenshot, a 200×200 logo and the description below.

---

## Product description (English — paste into mql5.com)

**KAA Grid BB ProfitPlus** is a basket grid Expert Advisor that opens its first trade at the Bollinger Band edge, only in the direction of the higher-timeframe EMA trend. It adds positions at ATR-adaptive distances and closes the whole basket at a dynamic profit target.

**Key features**
- First entry at the lower band (buy) or upper band (sell) of Bollinger Bands, with an optional candle body filter.
- Higher-timeframe EMA trend filter with slope confirmation, so baskets are not opened against the trend.
- ATR adaptive grid step with a minimum and an optional maximum distance.
- Dynamic basket take profit that grows with the number of levels and the total lot.
- Alternative exits: basket points, BB middle band, or opposite BB band.
- Basket trailing profit that scales with the target.
- Fixed or auto lot by balance, lot multiplier and max lot cap.
- Equity drawdown protection (% or money), spread filter, trading hours and Friday close.
- Optional lot splitting (hedging accounts).
- Works on hedging and netting accounts. Every order is checked for volume, margin and symbol trade mode.

**Recommended**
- Symbol: XAUUSD (works on other symbols with adjusted point inputs)
- Timeframe: the EA uses its own signal timeframe input (default M15), so any chart timeframe works
- Minimum deposit: $1,000 per 0.01 start lot; a low-spread ECN / Raw account
- Run it on a VPS 24/5

**Risk warning:** This EA uses grid and lot-multiplier techniques. Losses can be large in a strong one-way trend. Always use the drawdown protection, test on a demo account first, and only risk money you can afford to lose. Past results do not guarantee future results.

## คำอธิบายสินค้า (ภาษาไทย)

**KAA Grid BB ProfitPlus** คือ EA แบบกริดตะกร้า เปิดไม้แรกที่ขอบ Bollinger Bands และเข้าเฉพาะทิศเดียวกับเทรนด์ EMA ของไทม์เฟรมใหญ่ ระยะห่างของกริดปรับตาม ATR และปิดทั้งตะกร้าเมื่อถึงเป้ากำไรแบบไดนามิก

- เข้าไม้แรกที่ขอบล่าง (Buy) หรือขอบบน (Sell) ของ BB และกรองด้วยเทรนด์ EMA พร้อมความชัน
- ระยะกริดปรับตาม ATR, เป้ากำไรเพิ่มตามจำนวนไม้และขนาด Lot, มี Trailing ทั้งตะกร้า
- เลือกได้ทั้ง Lot คงที่หรือ Lot อัตโนมัติตามบาลานซ์ มีตัวคูณ Lot และจำกัด Lot สูงสุด
- ป้องกัน Drawdown (เป็น % หรือเป็นเงิน), กรองสเปรด, กำหนดเวลาเทรด, ปิดออเดอร์วันศุกร์
- รองรับบัญชีทั้ง Hedging และ Netting

**คำเตือน:** EA นี้ใช้ระบบกริดและตัวคูณ Lot ซึ่งมีความเสี่ยงสูงเมื่อราคาวิ่งทางเดียวแรงๆ ควรทดสอบบนบัญชีทดลองก่อนเสมอ

## Recommended Market settings

- Price: set as you like; Market also offers rental (1/3/6/12 months).
- Activations: 5–10.
- A free demo is created automatically from the `.ex5` (Strategy Tester only), which replaces the old "Demo/Backtest = FREE" system.
