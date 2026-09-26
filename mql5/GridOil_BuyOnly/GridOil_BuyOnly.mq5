//+------------------------------------------------------------------+
//|                                              GridOil_BuyOnly.mq5 |
//|                                  Copyright 2026, KruJeab Forex   |
//|   Buy-only percentage grid for crude oil (WTI / Brent)           |
//|   MQL5 Market edition v2.10 (based on GridOil_BuyOnly v2.00)     |
//|                                                                  |
//|   Principles: grid orders have no stop loss, stuck orders are    |
//|   cleared only with profit the EA has actually realized, and     |
//|   the ladder follows price while the basket is empty.            |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, KruJeab Forex"
#property link      "https://www.mql5.com"
#property version   "2.10"
#property description "Buy-only percentage grid for crude oil (WTI / Brent). Grid orders have no per-order stop loss."
#property description "Auto Zone: ladder built down from an anchor price that follows the market while the basket is empty."
#property description "Manual Zone: up to 3 fixed price zones. Profit-Funded De-risk closes deep orders with realized profit only."
#property description "Trend Rider: optional EMA trend orders with their own trailing stop. Built-in capital calculator."
#property description "Hedging accounts only. Grid trading without stop loss carries high risk."

#include <Trade\Trade.mqh>

#define EA_NAME    "GridOil Buy-Only"
#define EA_VER     "2.10"
#define MAX_LEVELS 400

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
input group "=== Grid Mode ==="
input bool   InpUseAutoZone     = true;   // true = Auto Zone (ladder from anchor) | false = Manual Zones

input group "=== Auto Zone ==="
input double InpAutoAnchor      = 0.0;    // Anchor price (0 = market price at first start, then remembered)
input double InpAutoStartOffPct = 0.5;    // First level below the anchor (%)
input double InpAutoStepPct     = 2.0;    // Grid step between levels (%)
input int    InpAutoLevels      = 15;     // Number of levels
input double InpAutoLot         = 0.01;   // Lot of the top level
input int    InpAutoLotAddEvery = 0;      // Increase lot every N levels deeper (0 = same lot)
input double InpAutoLotAdd      = 0.01;   // Lot added each time
input bool   InpResetAnchor     = false;  // Reset anchor to current price (one-shot switch)
input double InpAutoReanchorPct = 3.0;    // Move anchor when basket is empty and price rises this % above it (0 = off)

input group "=== Manual Zone 1 (upper, 0 = not used) ==="
input double InpZ1Top      = 0.0;    // Top price
input double InpZ1Bottom   = 0.0;    // Bottom price
input double InpZ1StepPct  = 2.0;    // Grid step (%)
input double InpZ1Lot      = 0.01;   // Lot per level

input group "=== Manual Zone 2 (middle) ==="
input double InpZ2Top      = 75.0;   // Top price
input double InpZ2Bottom   = 55.0;   // Bottom price
input double InpZ2StepPct  = 2.0;    // Grid step (%)
input double InpZ2Lot      = 0.01;   // Lot per level

input group "=== Manual Zone 3 (lower) ==="
input double InpZ3Top      = 55.0;   // Top price
input double InpZ3Bottom   = 35.0;   // Bottom price
input double InpZ3StepPct  = 2.5;    // Grid step (%)
input double InpZ3Lot      = 0.02;   // Lot per level

input group "=== Portfolio Risk ==="
input double InpFloor              = 0.0;    // Floor price: no new levels below it (0 = auto, one step below last level)
input double InpMaxDDPct           = 0.0;    // Equity Stop: max drawdown % from cycle start equity (0 = off)
input double InpEquityStopUSD      = 0.0;    // Equity Stop: fixed equity level in money (0 = off)
input int    InpMaxOpenGrid        = 0;      // Max grid orders open + pending (0 = no limit)
input bool   InpBlockIfUnderfunded = true;   // Do not open new orders if balance is below the calculated need
input bool   InpFillMissedAtMarket = false;  // Buy at market for levels price has already passed
input double InpMaxMarginUsage     = 90.0;   // Max % of free margin a single order may use

input group "=== Profit-Funded De-risk ==="
input double InpClearStepPct      = 1.0;    // Run a clear each time equity rises this % (0 = off)
input int    InpClearMode         = 1;      // 1 = close deepest losing orders, 2 = close the whole basket
input double InpClearMinDepthPct  = 4.0;    // Mode 1: only orders deeper than this % below price
input int    InpClearMaxOrders    = 3;      // Mode 1: max orders closed per clear
input double InpClearBudgetFrac   = 1.0;    // Budget = realized profit of this EA x this factor
input bool   InpClearIncludeRiders = true;  // Trend Rider orders can also be cleared

input group "=== Order Entry ==="
input bool   InpUsePendingOrders  = false;  // true = Buy Limit orders on server | false = market order on touch
input int    InpDeviationPoints   = 100;    // Max slippage (points)
input double InpMaxSpreadPct      = 0.15;   // Max spread as % of price for new orders (0 = off)

input group "=== Trend Rider (lot 0 = off) ==="
input double          InpTrendLot            = 0.0;       // Lot per trend order (0 = disabled)
input ENUM_TIMEFRAMES InpTrendTF             = PERIOD_H4; // Trend timeframe
input int             InpTrendEMAFast        = 50;        // EMA period (entry: close above EMA and EMA rising)
input int             InpTrendMaxRiders      = 3;         // Max trend orders (pyramid)
input double          InpTrendPyramidStepPct = 3.0;       // Add next trend order after this % move
input double          InpTrendTrailPct       = 3.0;       // Trailing stop distance (% of price)
input bool            InpTrendNoCut          = true;      // No-cut mode: no initial SL, trailing only locks profit
input double          InpTrendFlipMinPct     = 0.5;       // On trend flip close only orders this % in profit (no-cut mode)

input group "=== System ==="
input long   InpMagic       = 660035; // Magic number
input bool   InpCheckSymbol = true;   // Warn if the chart symbol does not look like oil
input bool   InpResetHalt   = false;  // Start a new cycle after Equity Stop (one-shot switch)
input bool   InpShowPanel   = true;   // Show info panel on chart

//+------------------------------------------------------------------+
//| Globals                                                          |
//+------------------------------------------------------------------+
double   g_price[MAX_LEVELS];
double   g_lot[MAX_LEVELS];
double   g_step[MAX_LEVELS];      // fraction, e.g. 0.02
int      g_zone[MAX_LEVELS];      // 0 = auto, 1..3 = manual zone
bool     g_occupied[MAX_LEVELS];
bool     g_missedFired[MAX_LEVELS];
bool     g_wasAbove[MAX_LEVELS];  // market mode: price has been above the level (armed)
int      g_total = 0;

CTrade   g_trade;
string   g_gvHalt      = "";
string   g_gvHaltDone  = "";
string   g_gvEq0       = "";
string   g_gvClearRef  = "";
string   g_gvClearTime = "";
string   g_gvAnchor    = "";
string   g_gvAnchDone  = "";
string   g_gvCycTime   = "";
string   g_gvCashApp   = "";
string   g_gvBalSeen   = "";
datetime g_lastFailLog  = 0;
datetime g_lastBuildLog = 0;
int      g_emaFast = INVALID_HANDLE;
bool     g_riderOn = false;
datetime g_riderTrailBlock = 0;
datetime g_lastTrendBar = 0;
double   g_anchorUsed   = 0.0;
double   g_maxFloating  = 0.0;   // estimated floating loss if price reaches the floor
double   g_needMargin   = 0.0;   // estimated margin for the worst case
double   g_totalLots    = 0.0;   // total lots in the worst case
double   g_planFloor    = 0.0;   // floor used by the capital calculator
bool     g_watchOnly    = false; // manage existing orders only, no new orders
string   g_watchReason  = "";

bool   SelectedIsRider();
double EquityStopLine();
void   ComputeCapitalNeeds();
bool   HasExposure();
bool   HasOpenPositions();
void   ResetCycleBaselines(const string why);

//+------------------------------------------------------------------+
//| Symbol helpers                                                   |
//+------------------------------------------------------------------+
double NormalizeLot(double lot)
{
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step > 0.0)
      lot = MathRound(lot / step) * step;
   lot = MathMax(minL, MathMin(maxL, lot));
   return NormalizeDouble(lot, 8);
}

double NormalizePrice(const double p)
{
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double v  = (ts > 0.0) ? MathRound(p / ts) * ts : p;
   return NormalizeDouble(v, _Digits);
}

double SnapPriceDown(const double p)
{
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double v  = (ts > 0.0) ? MathFloor(p / ts) * ts : p;
   return NormalizeDouble(v, _Digits);
}

double MinStopDistance()
{
   return (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
}

double FreezeDistance()
{
   return (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL) * _Point;
}

// Money value of a 1.0 price move for 1 lot (capital calculator)
double ValuePer1Move()
{
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv > 0.0 && ts > 0.0)
      return tv / ts;
   double cs = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   return (cs > 0.0) ? cs : 100.0;
}

double RefPrice()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(ask > 0.0) return ask;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(bid > 0.0) return bid;
   double c = iClose(_Symbol, PERIOD_D1, 0);
   return (c > 0.0) ? c : 0.0;
}

bool IsTester()
{
   return (MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION));
}

//+------------------------------------------------------------------+
//| Pre-trade checks (required by MQL5 Market validation)            |
//+------------------------------------------------------------------+
bool IsTradingPermitted()
{
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))           return false;
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)) return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))   return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))    return false;
   ENUM_SYMBOL_TRADE_MODE mode = (ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   return (mode == SYMBOL_TRADE_MODE_FULL || mode == SYMBOL_TRADE_MODE_LONGONLY);
}

double OurTotalVolume()
{
   double v = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetTicket(i) > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol)
         v += PositionGetDouble(POSITION_VOLUME);
   for(int i = OrdersTotal() - 1; i >= 0; i--)
      if(OrderGetTicket(i) > 0 && OrderGetString(ORDER_SYMBOL) == _Symbol)
         v += OrderGetDouble(ORDER_VOLUME_CURRENT);
   return v;
}

// Volume, order count, symbol volume limit and margin check for a new buy
bool CanOpenBuy(const double lot, const double price, string &reason)
{
   if(!IsTradingPermitted())
   { reason = "trading not allowed"; return false; }

   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(lot < minL || lot > maxL)
   { reason = StringFormat("volume %.2f outside %.2f..%.2f", lot, minL, maxL); return false; }

   long limitOrders = AccountInfoInteger(ACCOUNT_LIMIT_ORDERS);
   if(limitOrders > 0 && PositionsTotal() + OrdersTotal() >= limitOrders)
   { reason = "account order limit reached"; return false; }

   double volLimit = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT);
   if(volLimit > 0.0 && OurTotalVolume() + lot > volLimit)
   { reason = "symbol volume limit reached"; return false; }

   double margin = 0.0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lot, price, margin))
   { reason = "margin calculation failed"; return false; }
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(margin > freeMargin * InpMaxMarginUsage / 100.0)
   { reason = StringFormat("not enough money (margin %.2f, free %.2f)", margin, freeMargin); return false; }

   return true;
}

bool ResultOK()
{
   uint rc = g_trade.ResultRetcode();
   return (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL);
}

void LogFail(const string what, const int idx)
{
   if(TimeCurrent() - g_lastFailLog < 30)
      return;
   g_lastFailLog = TimeCurrent();
   string at = (idx >= 0 && idx < g_total) ? StringFormat(" at level %d (%s)", idx, DoubleToString(g_price[idx], _Digits)) : "";
   PrintFormat("%s: %s failed%s retcode=%u %s", EA_NAME, what, at,
               g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
}

void LogSkip(const string what, const int idx, const string reason)
{
   if(TimeCurrent() - g_lastFailLog < 30)
      return;
   g_lastFailLog = TimeCurrent();
   PrintFormat("%s: %s skipped at level %d - %s", EA_NAME, what, idx, reason);
}

// Market buy with checks. TP must respect the broker stops level.
bool SafeBuy(const double lot, const double tp, const string comment, const int idx)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   string reason = "";
   if(!CanOpenBuy(lot, ask, reason))
   { LogSkip("Buy", idx, reason); return false; }
   if(tp > 0.0 && tp - ask <= MinStopDistance())
   { LogSkip("Buy", idx, "TP too close to price"); return false; }
   if(!g_trade.Buy(lot, _Symbol, 0.0, 0.0, tp, comment) || !ResultOK())
   { LogFail("Buy", idx); return false; }
   return true;
}

bool SafeBuyLimit(const double lot, const double price, const double tp, const string comment, const int idx)
{
   string reason = "";
   if(!CanOpenBuy(lot, price, reason))
   { LogSkip("BuyLimit", idx, reason); return false; }
   if(!g_trade.BuyLimit(lot, price, _Symbol, 0.0, tp, ORDER_TIME_GTC, 0, comment) || !ResultOK())
   { LogFail("BuyLimit", idx); return false; }
   return true;
}

//+------------------------------------------------------------------+
//| Realized P/L of this EA since a time (budget for de-risk)        |
//| Deposits and other EAs' profit are not counted.                  |
//+------------------------------------------------------------------+
double RealizedSince(const datetime from)
{
   if(!HistorySelect(from, TimeCurrent() + 3600))
      return 0.0;
   double sum = 0.0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0) continue;
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != InpMagic) continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol)  continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(tk, DEAL_ENTRY) == DEAL_ENTRY_IN) continue;
      sum += HistoryDealGetDouble(tk, DEAL_PROFIT)
           + HistoryDealGetDouble(tk, DEAL_SWAP)
           + HistoryDealGetDouble(tk, DEAL_COMMISSION);
   }
   return sum;
}

// Deposits / withdrawals / credit since a time (not counted as drawdown)
double CashFlowSince(const datetime from)
{
   if(!HistorySelect(from, TimeCurrent() + 3600))
      return 0.0;
   double cash = 0.0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0) continue;
      ENUM_DEAL_TYPE dt = (ENUM_DEAL_TYPE)HistoryDealGetInteger(tk, DEAL_TYPE);
      if(dt != DEAL_TYPE_BALANCE && dt != DEAL_TYPE_CREDIT) continue;
      cash += HistoryDealGetDouble(tk, DEAL_PROFIT);
   }
   return cash;
}

//+------------------------------------------------------------------+
//| Cycle baselines (Equity Stop + Profit-Funded De-risk)            |
//+------------------------------------------------------------------+
void ResetCycleBaselines(const string why)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   GlobalVariableSet(g_gvEq0,       eq);
   GlobalVariableSet(g_gvClearRef,  eq);
   GlobalVariableSet(g_gvClearTime, (double)TimeCurrent());
   GlobalVariableSet(g_gvCycTime,   (double)TimeCurrent());
   GlobalVariableSet(g_gvCashApp,   0.0);
   GlobalVariableSet(g_gvBalSeen,   AccountInfoDouble(ACCOUNT_BALANCE));
   PrintFormat("%s: new cycle baseline (%s) - equity %.2f | equity stop line %.2f",
               EA_NAME, why, eq, EquityStopLine());
}

// With no open positions the baseline follows equity. With open positions
// it only moves with deposits / withdrawals, so a withdrawal is not a drawdown.
void MaintainBaselines()
{
   static datetime last = 0;
   if(TimeCurrent() - last < 30)
      return;
   last = TimeCurrent();

   if(!HasOpenPositions())
   {
      double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
      double eq0 = GlobalVariableGet(g_gvEq0);
      if(MathAbs(eq - eq0) > 0.005 * MathMax(eq, 1.0))
         ResetCycleBaselines("no open positions");
      return;
   }

   double balNow = AccountInfoDouble(ACCOUNT_BALANCE);
   if(MathAbs(balNow - GlobalVariableGet(g_gvBalSeen)) < 0.005)
      return;
   GlobalVariableSet(g_gvBalSeen, balNow);

   double total = CashFlowSince((datetime)GlobalVariableGet(g_gvCycTime));
   double delta = total - GlobalVariableGet(g_gvCashApp);
   if(MathAbs(delta) < 0.01)
      return;
   GlobalVariableSet(g_gvCashApp,  total);
   GlobalVariableSet(g_gvEq0,      GlobalVariableGet(g_gvEq0)      + delta);
   GlobalVariableSet(g_gvClearRef, GlobalVariableGet(g_gvClearRef) + delta);
   PrintFormat("%s: %s of %.2f detected - baseline moved to %.2f (equity stop line %.2f)",
               EA_NAME, (delta > 0.0 ? "deposit" : "withdrawal"), delta, GlobalVariableGet(g_gvEq0), EquityStopLine());
}

//+------------------------------------------------------------------+
//| Grid construction                                                |
//+------------------------------------------------------------------+
int BuildZone(const int zoneId, const double top, const double bottom,
              const double stepPct, const double lot)
{
   if(top <= 0.0 || bottom <= 0.0 || top <= bottom)   return 0;
   if(stepPct <= 0.0 || stepPct >= 100.0 || lot <= 0) return 0;
   double d = stepPct / 100.0;
   int    n = 0;
   double p = top;
   while(p > bottom && g_total < MAX_LEVELS)
   {
      if(InpFloor > 0.0 && p < InpFloor)
         break;
      g_price[g_total] = NormalizePrice(p);
      g_step[g_total]  = d;
      g_lot[g_total]   = NormalizeLot(lot);
      g_zone[g_total]  = zoneId;
      g_total++;
      n++;
      p *= (1.0 - d);
   }
   return n;
}

int BuildAutoZone(const double anchor)
{
   double d = InpAutoStepPct / 100.0;
   double p = anchor * (1.0 - MathMax(0.0, InpAutoStartOffPct) / 100.0);
   int    n = 0;
   for(int i = 0; i < InpAutoLevels && g_total < MAX_LEVELS; i++)
   {
      if(InpFloor > 0.0 && p < InpFloor)
         break;
      double lot = InpAutoLot;
      if(InpAutoLotAddEvery > 0 && InpAutoLotAdd > 0.0)
         lot += InpAutoLotAdd * MathFloor((double)i / (double)InpAutoLotAddEvery);

      g_price[g_total] = NormalizePrice(p);
      g_step[g_total]  = d;
      g_lot[g_total]   = NormalizeLot(lot);
      g_zone[g_total]  = 0;
      g_total++;
      n++;
      p *= (1.0 - d);
   }
   return n;
}

// Anchor: input > remembered value > market price (then remembered)
double ResolveAnchor()
{
   if(InpAutoAnchor > 0.0)
      return InpAutoAnchor;
   if(GlobalVariableCheck(g_gvAnchor))
      return GlobalVariableGet(g_gvAnchor);
   double p = RefPrice();
   if(p > 0.0)
      GlobalVariableSet(g_gvAnchor, p);
   return p;
}

void BuildLog(const string msg)
{
   if(TimeCurrent() - g_lastBuildLog < 60)
      return;
   g_lastBuildLog = TimeCurrent();
   Print(EA_NAME, ": ", msg);
}

// Returns 1 = built, 0 = no price yet (retry on next tick), -1 = invalid inputs
int BuildGrid()
{
   g_total = 0;
   for(int i = 0; i < MAX_LEVELS; i++)
   {
      g_occupied[i]    = false;
      g_missedFired[i] = false;
      g_wasAbove[i]    = false;
   }

   if(InpUseAutoZone)
   {
      if(InpAutoStepPct <= 0.0 || InpAutoStepPct >= 100.0)
      { BuildLog("Auto step % must be between 0 and 100"); return -1; }
      if(InpAutoLevels <= 0)
      { BuildLog("Number of levels must be > 0"); return -1; }
      if(InpAutoLot <= 0.0)
      { BuildLog("Auto lot must be > 0"); return -1; }

      double anchor = ResolveAnchor();
      if(anchor <= 0.0)
         return 0;

      double first = anchor * (1.0 - MathMax(0.0, InpAutoStartOffPct) / 100.0);
      if(InpFloor > 0.0 && first < InpFloor)
      {
         BuildLog(StringFormat("Floor (%s) is above the first level (%s, anchor %s) - lower the floor or reset the anchor",
                               DoubleToString(InpFloor, _Digits), DoubleToString(first, _Digits), DoubleToString(anchor, _Digits)));
         return -1;
      }

      g_anchorUsed = anchor;
      int n = BuildAutoZone(anchor);
      if(n == 0)
      { BuildLog("Auto Zone could not be built - check step / levels / lot / floor"); return -1; }

      PrintFormat("%s: Auto Zone - anchor %s | first %s | last %s | %d levels | step %.2f%%", EA_NAME,
                  DoubleToString(anchor, _Digits), DoubleToString(g_price[0], _Digits),
                  DoubleToString(g_price[g_total-1], _Digits), n, InpAutoStepPct);
   }
   else
   {
      g_anchorUsed = 0.0;
      int n1 = BuildZone(1, InpZ1Top, InpZ1Bottom, InpZ1StepPct, InpZ1Lot);
      int n2 = BuildZone(2, InpZ2Top, InpZ2Bottom, InpZ2StepPct, InpZ2Lot);
      int n3 = BuildZone(3, InpZ3Top, InpZ3Bottom, InpZ3StepPct, InpZ3Lot);
      if(g_total == 0)
      { BuildLog("Manual Zones produced no levels - check top / bottom / step / lot / floor"); return -1; }

      if(n1 > 0 && n2 > 0 && MathAbs(InpZ1Bottom - InpZ2Top) > _Point)
         Print(EA_NAME, ": warning - zone 1 and zone 2 are not continuous");
      if(n2 > 0 && n3 > 0 && MathAbs(InpZ2Bottom - InpZ3Top) > _Point)
         Print(EA_NAME, ": warning - zone 2 and zone 3 are not continuous");

      PrintFormat("%s: Manual Zones - %d + %d + %d = %d levels", EA_NAME, n1, n2, n3, g_total);
   }

   if(g_total >= MAX_LEVELS)
      Print(EA_NAME, ": warning - level count reached the limit of ", MAX_LEVELS);

   ComputeCapitalNeeds();
   return 1;
}

//+------------------------------------------------------------------+
//| Capital calculator - worst case the system allows.               |
//| With a max-order cap, the most expensive set of levels is used.  |
//+------------------------------------------------------------------+
void ComputeCapitalNeeds()
{
   double vpd = ValuePer1Move();
   double flr = (InpFloor > 0.0) ? InpFloor : 0.0;
   if(flr <= 0.0 && g_total > 0)
      flr = g_price[g_total-1] * (1.0 - g_step[g_total-1]);
   g_planFloor   = flr;
   g_maxFloating = 0.0;
   g_totalLots   = 0.0;
   g_needMargin  = 0.0;
   if(g_total <= 0)
      return;

   double term[MAX_LEVELS], lotv[MAX_LEVELS], prc[MAX_LEVELS];
   int n = 0;
   for(int i = 0; i < g_total; i++)
   {
      if(g_price[i] < flr) continue;
      term[n] = (g_price[i] - flr) * g_lot[i] * vpd;
      lotv[n] = g_lot[i];
      prc[n]  = g_price[i];
      n++;
   }
   if(n == 0)
      return;

   int cap = (InpMaxOpenGrid > 0) ? (int)MathMin(InpMaxOpenGrid, n) : n;

   double srt[];
   ArrayResize(srt, n);
   for(int i = 0; i < n; i++) srt[i] = term[i];
   ArraySort(srt);
   for(int i = n - 1; i >= n - cap; i--) g_maxFloating += srt[i];

   int idx[];
   ArrayResize(idx, n);
   for(int i = 0; i < n; i++) idx[i] = i;
   for(int a = 0; a < n - 1; a++)
      for(int b = a + 1; b < n; b++)
         if(lotv[idx[b]] > lotv[idx[a]])
         { int t = idx[a]; idx[a] = idx[b]; idx[b] = t; }

   double notional = 0.0;
   for(int i = 0; i < cap; i++)
   {
      g_totalLots += lotv[idx[i]];
      notional    += prc[idx[i]] * lotv[idx[i]];
   }

   if(g_totalLots > 0.0)
   {
      double avg = notional / g_totalLots;
      double m   = 0.0;
      if(avg > 0.0 && OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, g_totalLots, avg, m))
         g_needMargin = m;
   }
}

// true = balance is below the calculated need and new orders must be blocked
bool CapitalGateBlocked()
{
   if(g_total <= 0)
      return false;
   double bal  = AccountInfoDouble(ACCOUNT_BALANCE);
   double need = g_maxFloating + g_needMargin;
   if(bal <= 0.0 || need <= bal)
      return false;

   PrintFormat("%s: balance %.2f is below the %.2f this ladder needs - reduce levels / lot, raise the floor or set a max order count",
               EA_NAME, bal, need);
   if(!InpBlockIfUnderfunded || IsTester())
      return false;       // the tester always runs so results can be studied
   return true;
}

//+------------------------------------------------------------------+
//| Input validation                                                 |
//+------------------------------------------------------------------+
bool ValidateInputs()
{
   string err = "";
   if(InpAutoStartOffPct < 0.0)                                 err = "First level offset must be >= 0";
   else if(InpAutoLotAddEvery < 0 || InpAutoLotAdd < 0.0)       err = "Lot increase settings must be >= 0";
   else if(InpAutoReanchorPct < 0.0)                            err = "Re-anchor % must be >= 0";
   else if(InpFloor < 0.0)                                      err = "Floor must be >= 0";
   else if(InpMaxDDPct < 0.0 || InpMaxDDPct >= 100.0)           err = "Max drawdown % must be 0..99";
   else if(InpEquityStopUSD < 0.0)                              err = "Equity stop must be >= 0";
   else if(InpMaxOpenGrid < 0)                                  err = "Max open grid orders must be >= 0";
   else if(InpMaxMarginUsage <= 0.0 || InpMaxMarginUsage > 100) err = "Max margin usage must be 0..100 %";
   else if(InpClearStepPct < 0.0)                               err = "Clear step % must be >= 0";
   else if(InpClearMode != 1 && InpClearMode != 2)              err = "Clear mode must be 1 or 2";
   else if(InpClearMaxOrders < 1)                               err = "Clear max orders must be >= 1";
   else if(InpClearBudgetFrac <= 0.0)                           err = "Clear budget factor must be > 0";
   else if(InpDeviationPoints < 0)                              err = "Deviation must be >= 0";
   else if(InpMaxSpreadPct < 0.0)                               err = "Max spread % must be >= 0";
   else if(InpTrendLot < 0.0)                                   err = "Trend lot must be >= 0";
   else if(InpTrendLot > 0.0 && (InpTrendEMAFast < 2 || InpTrendMaxRiders < 1 || InpTrendTrailPct <= 0.0 || InpTrendPyramidStepPct <= 0.0))
                                                                err = "Trend Rider settings are invalid";
   if(err != "")
   {
      Print(EA_NAME, " - invalid input: ", err);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
int OnInit()
{
   // Several buy orders on one symbol at the same time need a hedging account
   if((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
   {
      Print(EA_NAME, ": this EA requires a hedging account (netting accounts merge all grid orders into one position)");
      Comment(EA_NAME, ": a hedging account is required.");
      return INIT_FAILED;
   }

   if(!ValidateInputs())
      return INIT_PARAMETERS_INCORRECT;

   if(InpCheckSymbol)
   {
      string s = _Symbol;
      StringToUpper(s);
      if(StringFind(s, "WTI") < 0 && StringFind(s, "OIL") < 0 && StringFind(s, "BRENT") < 0 &&
         StringFind(s, "XTI") < 0 && StringFind(s, "XBR") < 0 && StringFind(s, "CL") < 0)
         Print(EA_NAME, ": note - ", _Symbol, " does not look like crude oil. Default settings are designed for WTI.");
   }

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   g_trade.SetMarginMode();
   g_trade.LogLevel(LOG_LEVEL_ERRORS);
   g_watchOnly   = false;
   g_watchReason = "";

   // State is bound to symbol + magic + account, so demo state never leaks into a live account
   string tag = _Symbol + "_" + IntegerToString(InpMagic) + "_" +
                IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   g_gvHalt      = "GO_HALT_"     + tag;
   g_gvHaltDone  = "GO_HALTDONE_" + tag;
   g_gvEq0       = "GO_EQ0_"      + tag;
   g_gvClearRef  = "GO_CLREF_"    + tag;
   g_gvClearTime = "GO_CLTIME_"   + tag;
   g_gvAnchor    = "GO_ANCH_"     + tag;
   g_gvAnchDone  = "GO_ANCHDONE_" + tag;
   g_gvCycTime   = "GO_CYCTIME_"  + tag;
   g_gvCashApp   = "GO_CASHAPP_"  + tag;
   g_gvBalSeen   = "GO_BALSEEN_"  + tag;

   bool anyExposure = HasExposure();
   bool flatPos     = !HasOpenPositions();

   // InpResetHalt is a one-shot switch: a re-init must not clear a new halt by itself
   bool didReset = false;
   if(InpResetHalt)
   {
      if(!GlobalVariableCheck(g_gvHaltDone))
      {
         GlobalVariableSet(g_gvHaltDone, 1.0);
         if(GlobalVariableCheck(g_gvHalt))
         {
            GlobalVariableDel(g_gvHalt);
            Print(EA_NAME, ": halt cleared - trading resumed");
            ResetCycleBaselines("user started a new cycle");
            didReset = true;
         }
         else
            Print(EA_NAME, ": Reset Halt is on but there is no halt - nothing to do");
      }
      else
         Print(EA_NAME, ": Reset Halt was already used - set it back to false");
   }
   else if(GlobalVariableCheck(g_gvHaltDone))
      GlobalVariableDel(g_gvHaltDone);

   if(!didReset && (flatPos || !GlobalVariableCheck(g_gvEq0) || !GlobalVariableCheck(g_gvClearRef)))
      ResetCycleBaselines(flatPos ? "no open positions" : "first start");

   if(!GlobalVariableCheck(g_gvClearTime)) GlobalVariableSet(g_gvClearTime, (double)TimeCurrent());
   if(!GlobalVariableCheck(g_gvCycTime))   GlobalVariableSet(g_gvCycTime,   (double)TimeCurrent());
   if(!GlobalVariableCheck(g_gvCashApp))   GlobalVariableSet(g_gvCashApp,   0.0);
   if(!GlobalVariableCheck(g_gvBalSeen))   GlobalVariableSet(g_gvBalSeen,   AccountInfoDouble(ACCOUNT_BALANCE));

   // InpResetAnchor is also a one-shot switch
   if(InpResetAnchor)
   {
      if(!GlobalVariableCheck(g_gvAnchDone))
      {
         if(GlobalVariableCheck(g_gvAnchor))
            GlobalVariableDel(g_gvAnchor);
         GlobalVariableSet(g_gvAnchDone, 1.0);
         Print(EA_NAME, ": anchor cleared - a new anchor will be set from the current price");
         if(anyExposure)
            Print(EA_NAME, ": warning - orders are open while the anchor is reset; the new ladder overlaps them");
      }
      else
         Print(EA_NAME, ": Reset Anchor was already used - set it back to false");
   }
   else if(GlobalVariableCheck(g_gvAnchDone))
      GlobalVariableDel(g_gvAnchDone);

   int code = BuildGrid();
   if(code < 0)
   {
      // Open orders have no stop loss, so the EA must still load to watch them
      if(anyExposure)
      {
         g_watchOnly   = true;
         g_watchReason = "grid inputs are invalid";
         Print(EA_NAME, ": invalid grid inputs but orders are open - watch-only mode (Equity Stop still active)");
      }
      else
      {
         Print(EA_NAME, ": invalid grid inputs - see the previous message");
         return INIT_PARAMETERS_INCORRECT;
      }
   }
   if(code == 0)
      Print(EA_NAME, ": no price yet for the anchor - the grid will be built on the first tick");

   g_emaFast = INVALID_HANDLE;
   g_riderOn = false;
   g_riderTrailBlock = 0;
   g_lastTrendBar = 0;
   if(InpTrendLot > 0.0)
   {
      g_emaFast = iMA(_Symbol, InpTrendTF, InpTrendEMAFast, 0, MODE_EMA, PRICE_CLOSE);
      if(g_emaFast == INVALID_HANDLE)
         Print(EA_NAME, ": could not create the trend EMA - Trend Rider disabled");
      else
         g_riderOn = true;
   }

   if(g_total > 0)
   {
      PrintFormat("%s v%s ready: %d levels | worst-case lots %.2f | floor %s | equity baseline %.2f | equity stop %.2f",
                  EA_NAME, EA_VER, g_total, g_totalLots, DoubleToString(g_planFloor, _Digits),
                  GlobalVariableGet(g_gvEq0), EquityStopLine());
      PrintFormat("%s capital: at %s floating is about -%.2f, margin about %.2f, recommended balance about %.2f",
                  EA_NAME, DoubleToString(g_planFloor, _Digits), g_maxFloating, g_needMargin, g_maxFloating + g_needMargin);

      if(CapitalGateBlocked())
      {
         double bal  = AccountInfoDouble(ACCOUNT_BALANCE);
         double need = g_maxFloating + g_needMargin;
         g_watchOnly   = true;
         g_watchReason = StringFormat("balance %.2f < needed %.2f", bal, need);
         if(!anyExposure)
            Alert(EA_NAME, ": balance ", DoubleToString(bal, 2), " is below the ", DoubleToString(need, 2),
                  " this grid needs. No new orders will be opened. Reduce levels / lot, raise the floor, set Max open grid orders, or turn off Block if underfunded.");
      }
   }
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_emaFast != INVALID_HANDLE) IndicatorRelease(g_emaFast);
   if(reason != REASON_INITFAILED)
      Comment("");
}

//+------------------------------------------------------------------+
//| Equity Stop line = the higher of the % and the fixed money line  |
//+------------------------------------------------------------------+
double EquityStopLine()
{
   double line = 0.0;
   if(InpEquityStopUSD > 0.0)
      line = InpEquityStopUSD;
   if(InpMaxDDPct > 0.0)
   {
      double eq0 = GlobalVariableGet(g_gvEq0);
      line = MathMax(line, eq0 * (1.0 - InpMaxDDPct / 100.0));
   }
   return line;
}

//+------------------------------------------------------------------+
//| Level mapping ("G12" or "G12M" comments, checked against price)  |
//+------------------------------------------------------------------+
int IdxFromComment(const string cmt)
{
   if(StringLen(cmt) < 2 || StringGetCharacter(cmt, 0) != 'G')
      return -1;
   string num = StringSubstr(cmt, 1);
   int len = StringLen(num);
   if(len > 0 && StringGetCharacter(num, len - 1) == 'M')
      num = StringSubstr(num, 0, len - 1);
   long v = StringToInteger(num);
   if(v < 0 || v >= g_total)
      return -1;
   if(num != IntegerToString(v))
      return -1;
   return (int)v;
}

int NearestLevel(const double price)
{
   int    best = -1;
   double bestDist = DBL_MAX;
   for(int i = 0; i < g_total; i++)
   {
      double dist = MathAbs(price - g_price[i]);
      if(dist < bestDist)
      {
         bestDist = dist;
         best = i;
      }
   }
   if(best >= 0 && bestDist > g_price[best] * g_step[best] * 0.6)
      return -1;
   return best;
}

int LevelOf(const string cmt, const double price)
{
   int idx = IdxFromComment(cmt);
   if(idx >= 0 && MathAbs(price - g_price[idx]) <= g_price[idx] * g_step[idx] * 0.6)
      return idx;
   return NearestLevel(price);
}

// Marks occupied levels. Returns the number of open grid positions (riders excluded).
int BuildOccupancy(int &pendOut)
{
   for(int i = 0; i < g_total; i++)
      g_occupied[i] = false;

   pendOut = 0;
   int gridCount = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
      if(SelectedIsRider()) continue;
      gridCount++;
      int idx = LevelOf(PositionGetString(POSITION_COMMENT), PositionGetDouble(POSITION_PRICE_OPEN));
      if(idx >= 0)
         g_occupied[idx] = true;
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderGetTicket(i) == 0) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol)  continue;
      pendOut++;
      int idx = LevelOf(OrderGetString(ORDER_COMMENT), OrderGetDouble(ORDER_PRICE_OPEN));
      if(idx >= 0)
         g_occupied[idx] = true;
   }
   return gridCount;
}

bool HasExposure()
{
   if(HasOpenPositions())
      return true;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
      if(OrderGetTicket(i) > 0 &&
         OrderGetInteger(ORDER_MAGIC) == InpMagic &&
         OrderGetString(ORDER_SYMBOL) == _Symbol)
         return true;
   return false;
}

bool HasOpenPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetTicket(i) > 0 &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         return true;
   return false;
}

void DeleteOurPendings()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol)  continue;
      g_trade.OrderDelete(tk);
   }
}

void FlattenOnce()
{
   DeleteOurPendings();
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
      g_trade.PositionClose(tk);
   }
}

// Equity Stop: close everything, then halt until the user starts a new cycle
void CloseEverythingAndHalt(const string reason)
{
   Print(EA_NAME, " EQUITY STOP: ", reason, " - closing all orders and halting");
   GlobalVariableSet(g_gvHalt, 1.0);
   for(int attempt = 0; attempt < 10 && HasExposure(); attempt++)
   {
      FlattenOnce();
      if(HasExposure() && !IsTester())
         Sleep(500);
   }
   if(HasExposure())
      Print(EA_NAME, ": not everything is closed yet (market closed / requote) - retrying every tick");
   if(!IsTester())
      Alert(EA_NAME, ": Equity Stop triggered - all orders closed and trading halted (", _Symbol, ")");
}

double GridBasketPL()
{
   double pl = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
      if(SelectedIsRider() && !InpClearIncludeRiders) continue;
      pl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   }
   return pl;
}

//+------------------------------------------------------------------+
//| Profit-Funded De-risk                                            |
//| Each time equity rises by InpClearStepPct, close deep losing     |
//| orders, paid only by profit this EA has actually realized.       |
//+------------------------------------------------------------------+
void ProfitFundedClear()
{
   if(InpClearStepPct <= 0.0)
      return;

   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   double ref = GlobalVariableGet(g_gvClearRef);
   if(ref <= 0.0)
   {
      GlobalVariableSet(g_gvClearRef, eq);
      GlobalVariableSet(g_gvClearTime, (double)TimeCurrent());
      return;
   }
   if(eq < ref * (1.0 + InpClearStepPct / 100.0))
      return;

   static datetime lastScan = 0;
   if(TimeCurrent() - lastScan < 30)
      return;
   lastScan = TimeCurrent();

   datetime refTime  = (datetime)GlobalVariableGet(g_gvClearTime);
   double   realized = RealizedSince(refTime);
   if(realized <= 0.0)
      return;

   double budget = realized * InpClearBudgetFrac;
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(bid <= 0.0)
      return;

   int closed = 0;

   if(InpClearMode == 2)
   {
      // Whole basket: realized profit must cover the whole basket loss first
      double basketPL = GridBasketPL();
      if(basketPL < 0.0 && -basketPL > budget)
      {
         static datetime lastWarn = 0;
         if(TimeCurrent() - lastWarn > 300)
         {
            lastWarn = TimeCurrent();
            PrintFormat("%s CLEAR: mode 2 skipped - basket loss %.2f is larger than realized profit budget %.2f",
                        EA_NAME, basketPL, budget);
         }
         return;
      }

      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
         bool rider = SelectedIsRider();
         if(rider && !InpClearIncludeRiders) continue;
         int lidx = rider ? -1 : LevelOf(PositionGetString(POSITION_COMMENT), PositionGetDouble(POSITION_PRICE_OPEN));
         if(g_trade.PositionClose(tk))
         {
            if(lidx >= 0)
               g_missedFired[lidx] = true;
            closed++;
         }
      }
      if(closed == 0)
      {
         GlobalVariableSet(g_gvClearRef, eq);
         GlobalVariableSet(g_gvClearTime, (double)TimeCurrent());
         return;
      }
   }
   else
   {
      ulong  tks[];
      double dep[];
      double pl[];
      int    lvls[];
      int    n = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
         bool rider = SelectedIsRider();
         if(rider && !InpClearIncludeRiders) continue;
         double op = PositionGetDouble(POSITION_PRICE_OPEN);
         double d  = (op - bid) / bid * 100.0;
         if(d < InpClearMinDepthPct)
            continue;
         ArrayResize(tks,  n + 1);
         ArrayResize(dep,  n + 1);
         ArrayResize(pl,   n + 1);
         ArrayResize(lvls, n + 1);
         tks[n]  = tk;
         dep[n]  = d;
         pl[n]   = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
         lvls[n] = rider ? -1 : LevelOf(PositionGetString(POSITION_COMMENT), op);
         n++;
      }
      if(n == 0)
         return;

      for(int a = 0; a < n - 1; a++)          // deepest first
         for(int b = a + 1; b < n; b++)
            if(dep[b] > dep[a])
            {
               ulong  ut = tks[a];  tks[a]  = tks[b];  tks[b]  = ut;
               double dt = dep[a];  dep[a]  = dep[b];  dep[b]  = dt;
               dt = pl[a];  pl[a] = pl[b];  pl[b] = dt;
               int it = lvls[a];  lvls[a] = lvls[b];  lvls[b] = it;
            }

      double spent = 0.0;
      for(int i = 0; i < n && closed < InpClearMaxOrders; i++)
      {
         double cost = MathMax(0.0, -pl[i]);
         if(spent + cost > budget)
            continue;
         if(g_trade.PositionClose(tks[i]))
         {
            if(lvls[i] >= 0)
               g_missedFired[lvls[i]] = true;
            spent += cost;
            closed++;
            PrintFormat("%s CLEAR: closed order %.1f%% deep, loss %.2f (realized budget %.2f, used %.2f)",
                        EA_NAME, dep[i], pl[i], budget, spent);
         }
      }
   }

   if(closed > 0)
   {
      GlobalVariableSet(g_gvClearRef, AccountInfoDouble(ACCOUNT_EQUITY));
      GlobalVariableSet(g_gvClearTime, (double)TimeCurrent());
      PrintFormat("%s CLEAR: %d orders closed - new equity reference %.2f (next step +%.1f%%)",
                  EA_NAME, closed, GlobalVariableGet(g_gvClearRef), InpClearStepPct);
   }
}

//+------------------------------------------------------------------+
//| Trend Rider - separate trend orders ("TR" comment)               |
//| Entry: last closed bar above EMA and EMA rising.                 |
//| Exit: server-side trailing stop, or trend flip (close below EMA).|
//+------------------------------------------------------------------+
bool SelectedIsRider()
{
   string c = PositionGetString(POSITION_COMMENT);
   if(StringLen(c) >= 2 && StringSubstr(c, 0, 2) == "TR")
      return true;
   return (PositionGetDouble(POSITION_SL) > 0.0); // grid orders never have a stop loss
}

void CloseRiders(const string reason)
{
   static datetime lastPrint = 0;
   if(TimeCurrent() - lastPrint >= 60)
   {
      lastPrint = TimeCurrent();
      Print(EA_NAME, " Rider: ", reason, InpTrendNoCut ? " - closing profitable trend orders only"
                                                       : " - closing all trend orders");
   }
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
      if(!SelectedIsRider()) continue;
      if(InpTrendNoCut)
      {
         double op = PositionGetDouble(POSITION_PRICE_OPEN);
         if(PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP) <= 0.0 ||
            bid < op * (1.0 + InpTrendFlipMinPct / 100.0))
            continue;
      }
      g_trade.PositionClose(tk);
   }
}

void RiderModule(const double bid, const double ask, const bool blockNewEntries)
{
   if(!g_riderOn)
      return;

   double minStop   = MinStopDistance();
   double freeze    = FreezeDistance();
   double trailDist = MathMax(bid * InpTrendTrailPct / 100.0, minStop + _Point);
   double moveMin   = MathMax(trailDist * 0.05, MathMax(minStop, 10 * _Point));
   bool   trailOK   = (TimeCurrent() >= g_riderTrailBlock);

   int    riders   = 0;
   double topEntry = 0.0;
   double lowEntry = 0.0;
   bool   allUnder = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
      if(!SelectedIsRider()) continue;
      riders++;
      double opR   = PositionGetDouble(POSITION_PRICE_OPEN);
      double curSL = PositionGetDouble(POSITION_SL);
      topEntry = MathMax(topEntry, opR);
      lowEntry = (lowEntry <= 0.0) ? opR : MathMin(lowEntry, opR);
      if(bid >= opR) allUnder = false;
      if(!trailOK) continue;
      double newSL = SnapPriceDown(bid - trailDist);
      if(InpTrendNoCut && newSL <= opR + MathMax(ask - bid, 10 * _Point))
         continue;                             // no-cut: SL only once it locks profit
      if(curSL > 0.0 && bid - curSL <= freeze)
         continue;                             // inside freeze level: broker will reject
      if(bid - newSL <= minStop)
         continue;
      if(newSL > curSL + moveMin)
      {
         if(!g_trade.PositionModify(tk, newSL, 0.0))
         {
            LogFail("PositionModify(rider)", -1);
            g_riderTrailBlock = TimeCurrent() + 30;
            trailOK = false;
         }
      }
   }

   double f[];
   ArraySetAsSeries(f, true);
   if(CopyBuffer(g_emaFast, 0, 0, 3, f) < 3)
      return;
   double c1       = iClose(_Symbol, InpTrendTF, 1);
   bool   aboveEMA = (c1 > f[1]);
   bool   slopeUp  = (f[1] > f[2]);

   if(!aboveEMA)
   {
      if(riders > 0)
         CloseRiders("trend flipped down (close below EMA" + IntegerToString(InpTrendEMAFast) + ")");
      return;
   }
   if(!slopeUp || blockNewEntries)
      return;

   datetime bar = iTime(_Symbol, InpTrendTF, 0);
   if(bar == g_lastTrendBar)
      return;
   g_lastTrendBar = bar;

   bool fire = false;
   if(riders == 0)
      fire = true;
   else if(riders < InpTrendMaxRiders)
   {
      if(ask >= topEntry * (1.0 + InpTrendPyramidStepPct / 100.0))
         fire = true;                          // pyramid while the trend continues
      else if(InpTrendNoCut && allUnder && lowEntry > 0.0 &&
              ask <= lowEntry * (1.0 - InpTrendPyramidStepPct / 100.0))
         fire = true;                          // no-cut: new signal well below losing orders
   }
   if(!fire)
      return;

   double lot = NormalizeLot(InpTrendLot);
   string reason = "";
   if(!CanOpenBuy(lot, ask, reason))
   {
      LogSkip("Buy(rider)", -1, reason);
      return;
   }
   double sl = InpTrendNoCut ? 0.0
             : SnapPriceDown(ask - MathMax(ask * InpTrendTrailPct / 100.0, minStop + _Point));
   if(!g_trade.Buy(lot, _Symbol, 0.0, sl, 0.0, "TR") || !ResultOK())
      LogFail("Buy(rider)", -1);
}

//+------------------------------------------------------------------+
//| Chart panel                                                      |
//+------------------------------------------------------------------+
void UpdatePanel(const bool halted)
{
   if(!InpShowPanel)
      return;
   if(MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_VISUAL_MODE))
      return;
   static datetime lastDraw = 0;
   if(!MQLInfoInteger(MQL_TESTER) && TimeLocal() == lastDraw)
      return;
   lastDraw = TimeLocal();

   int    posCnt = 0, pendCnt = 0, riderCnt = 0;
   double floating = 0.0, swapSum = 0.0, lots = 0.0, riderPL = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)  continue;
      if(SelectedIsRider())
      {
         riderCnt++;
         riderPL += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
         continue;
      }
      posCnt++;
      floating += PositionGetDouble(POSITION_PROFIT);
      swapSum  += PositionGetDouble(POSITION_SWAP);
      lots     += PositionGetDouble(POSITION_VOLUME);
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderGetTicket(i) == 0) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol)  continue;
      pendCnt++;
   }

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   string cur = AccountInfoString(ACCOUNT_CURRENCY);

   string txt = "\n--- " + EA_NAME + " v" + EA_VER + " ---";
   txt += InpUseAutoZone ? StringFormat("\nGrid: Auto Zone, anchor %s (step %.2f%%)", DoubleToString(g_anchorUsed, _Digits), InpAutoStepPct)
                         : "\nGrid: Manual Zones";
   if(InpUseAutoZone && InpAutoReanchorPct > 0.0 && InpAutoAnchor <= 0.0 && g_total > 0)
      txt += StringFormat("\nRe-anchor when basket is empty and Bid >= %s or < %s",
                          DoubleToString(g_anchorUsed * (1.0 + InpAutoReanchorPct / 100.0), _Digits),
                          DoubleToString(g_price[g_total-1], _Digits));
   txt += InpUsePendingOrders ? "\nEntry: Buy Limit orders on server"
                              : "\nEntry: market order on touch (keep terminal online)";
   if(halted)
      txt += "\nStatus: HALTED by Equity Stop (set Reset Halt = true to start a new cycle)";
   else if(g_watchOnly)
      txt += "\nStatus: WATCH ONLY, no new orders - " + g_watchReason;
   else if(g_total == 0)
      txt += "\nStatus: grid not built yet (see Experts log)";
   else
      txt += "\nStatus: running";
   txt += StringFormat("\nOpen %d | Pending %d | Levels %d", posCnt, pendCnt, g_total);
   if(InpMaxOpenGrid > 0)
      txt += StringFormat(" (max open+pending %d)", InpMaxOpenGrid);
   txt += StringFormat("\nLots %.2f | Floating %.2f | Swap %.2f %s", lots, floating, swapSum, cur);
   if(g_riderOn)
      txt += StringFormat("\nTrend orders %d/%d | P/L %.2f | Trailing %.1f%%%s",
                          riderCnt, InpTrendMaxRiders, riderPL, InpTrendTrailPct,
                          InpTrendNoCut ? " (profit lock only)" : "");
   txt += StringFormat("\nEquity %.2f | Cycle base %.2f | Equity Stop %.2f",
                       AccountInfoDouble(ACCOUNT_EQUITY), GlobalVariableGet(g_gvEq0), EquityStopLine());
   txt += StringFormat("\nRecommended balance ~%.2f %s (floating at %s: -%.2f + margin %.2f | lots %.2f)",
                       g_maxFloating + g_needMargin, cur, DoubleToString(g_planFloor, _Digits),
                       g_maxFloating, g_needMargin, g_totalLots);
   if(InpClearStepPct > 0.0)
      txt += StringFormat("\nNext de-risk when equity >= %.2f with realized profit (mode %d)",
                          GlobalVariableGet(g_gvClearRef) * (1.0 + InpClearStepPct / 100.0), InpClearMode);
   txt += StringFormat("\nFloor %s | Bid %s | Spread %s",
                       (InpFloor > 0.0 ? DoubleToString(InpFloor, _Digits) : "auto"),
                       DoubleToString(bid, _Digits), DoubleToString(ask - bid, _Digits));
   Comment(txt);
}

//+------------------------------------------------------------------+
//| Move the anchor with price - only while the grid basket is empty |
//+------------------------------------------------------------------+
bool MaybeReanchor(const double bid, const int openGrid, const int pendCnt)
{
   if(!InpUseAutoZone || InpAutoReanchorPct <= 0.0 || InpAutoAnchor > 0.0)
      return false;
   if(g_total <= 0 || g_anchorUsed <= 0.0 || bid <= 0.0)
      return false;
   if(openGrid > 0 || pendCnt > 0)
      return false;

   bool goUp   = (bid >= g_anchorUsed * (1.0 + InpAutoReanchorPct / 100.0));
   bool goDown = (bid <  g_price[g_total-1]);
   if(!goUp && !goDown)
      return false;

   static datetime last = 0;
   if(TimeCurrent() - last < 60)
      return false;
   last = TimeCurrent();

   double oldAnchor = g_anchorUsed;
   GlobalVariableSet(g_gvAnchor, bid);
   if(BuildGrid() != 1)
   {
      GlobalVariableSet(g_gvAnchor, oldAnchor);
      BuildGrid();
      return false;
   }
   PrintFormat("%s: anchor moved %s - %s -> %s | first %s | last %s | recommended balance ~%.2f",
               EA_NAME, (goUp ? "up" : "down"), DoubleToString(oldAnchor, _Digits), DoubleToString(g_anchorUsed, _Digits),
               DoubleToString(g_price[0], _Digits), DoubleToString(g_price[g_total-1], _Digits),
               g_maxFloating + g_needMargin);

   if(CapitalGateBlocked())
   {
      g_watchOnly   = true;
      g_watchReason = StringFormat("balance %.2f < needed %.2f (after re-anchor)",
                                   AccountInfoDouble(ACCOUNT_BALANCE), g_maxFloating + g_needMargin);
      Print(EA_NAME, ": balance too low for the new ladder - watch-only mode");
   }
   return true;
}

//+------------------------------------------------------------------+
void OnTick()
{
   // 0) Baselines follow deposits / withdrawals
   MaintainBaselines();

   // 1) Halted: keep closing what is left, nothing else
   if(GlobalVariableCheck(g_gvHalt))
   {
      if(HasExposure())
         FlattenOnce();
      UpdatePanel(true);
      return;
   }

   // 2) Equity Stop - always active, even if the grid could not be built
   double eqLine    = EquityStopLine();
   double eq        = AccountInfoDouble(ACCOUNT_EQUITY);
   bool   belowStop = (eqLine > 0.0 && eq <= eqLine);
   if(belowStop && HasExposure())
   {
      CloseEverythingAndHalt(StringFormat("equity %.2f <= stop line %.2f", eq, eqLine));
      UpdatePanel(true);
      return;
   }

   // 3) Profit-funded de-risk - allowed even in watch-only mode
   ProfitFundedClear();

   if(g_watchOnly)
   {
      UpdatePanel(false);
      return;
   }

   // 4) Build the grid on the first tick if there was no price at start
   if(g_total == 0)
   {
      if(BuildGrid() != 1)
      {
         UpdatePanel(false);
         return;
      }
      PrintFormat("%s: grid built on first tick - %d levels | recommended balance ~%.2f",
                  EA_NAME, g_total, g_maxFloating + g_needMargin);
      if(CapitalGateBlocked())
      {
         g_watchOnly   = true;
         g_watchReason = StringFormat("balance %.2f < needed %.2f",
                                      AccountInfoDouble(ACCOUNT_BALANCE), g_maxFloating + g_needMargin);
         Alert(EA_NAME, ": balance too low for this grid - no new orders (", _Symbol, ")");
         UpdatePanel(false);
         return;
      }
   }

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0.0 || bid <= 0.0)
      return;

   bool spreadOK = !(InpMaxSpreadPct > 0.0 && (ask - bid) > bid * InpMaxSpreadPct / 100.0);
   bool canTrade = IsTradingPermitted();

   if(!InpUsePendingOrders)
      DeleteOurPendings();   // market mode: remove pending orders left from pending mode

   int pendCnt  = 0;
   int openGrid = BuildOccupancy(pendCnt);

   // 5) Move the ladder with price while the basket is empty
   if(MaybeReanchor(bid, openGrid, pendCnt))
   {
      if(g_watchOnly)
      {
         UpdatePanel(false);
         return;
      }
      openGrid = BuildOccupancy(pendCnt);
   }

   // Max-order cap counts pending orders too
   int slots = INT_MAX;
   if(InpMaxOpenGrid > 0)
      slots = (int)MathMax(0, InpMaxOpenGrid - (openGrid + pendCnt));

   // 6) Grid entries - none while equity is below the stop line
   double minDist = MathMax(MinStopDistance(), FreezeDistance());
   if(!belowStop && canTrade && bid > InpFloor && spreadOK && slots > 0)
   {
      for(int i = 0; i < g_total && slots > 0; i++)
      {
         double lvl = g_price[i];
         if(InpFloor > 0.0 && lvl < InpFloor - _Point)
            continue;
         if(g_occupied[i])
            continue;
         double tp = NormalizePrice(lvl * (1.0 + g_step[i]));

         if(InpUsePendingOrders)
         {
            if(ask - lvl > MathMax(minDist, _Point))
            {
               if(SafeBuyLimit(g_lot[i], lvl, tp, "G" + IntegerToString(i), i))
                  slots--;
            }
            else if(InpFillMissedAtMarket && !g_missedFired[i] && ask < lvl)
            {
               if(SafeBuy(g_lot[i], tp, "G" + IntegerToString(i) + "M", i))
               {
                  g_missedFired[i] = true;
                  slots--;
               }
            }
         }
         else
         {
            // Market on touch: price must first be above the level, then touch it
            if(ask - lvl > MathMax(minDist, _Point))
               g_wasAbove[i] = true;
            else if(ask <= lvl)
            {
               if(g_wasAbove[i])
               {
                  if(SafeBuy(g_lot[i], tp, "G" + IntegerToString(i), i))
                  {
                     g_wasAbove[i] = false;
                     slots--;
                  }
               }
               else if(InpFillMissedAtMarket && !g_missedFired[i])
               {
                  if(SafeBuy(g_lot[i], tp, "G" + IntegerToString(i) + "M", i))
                  {
                     g_missedFired[i] = true;
                     slots--;
                  }
               }
            }
         }
      }
   }
   else if(!belowStop && spreadOK && !InpUsePendingOrders)
   {
      // Cap full / below floor: keep arming levels price is above
      for(int i = 0; i < g_total; i++)
         if(!g_occupied[i] && ask - g_price[i] > MathMax(minDist, _Point))
            g_wasAbove[i] = true;
   }

   // 7) Trend Rider
   if(canTrade)
      RiderModule(bid, ask, belowStop);

   UpdatePanel(false);
}
//+------------------------------------------------------------------+
