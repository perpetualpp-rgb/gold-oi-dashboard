//+------------------------------------------------------------------+
//|                                     KAA_Grid_BB_ProfitPlus.mq5   |
//|                                 Copyright 2026, KruJeab Forex    |
//|        Bollinger Bands grid with trend filter and dynamic exits  |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, KruJeab Forex"
#property link      "https://www.mql5.com"
#property version   "2.00"
#property description "KAA Grid BB ProfitPlus - Bollinger Bands basket grid EA."
#property description "Higher-timeframe EMA trend filter, ATR adaptive grid spacing,"
#property description "dynamic basket profit target, basket trailing and equity drawdown protection."
#property description "Works on hedging and netting accounts. Grid/martingale trading carries high risk."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

#define EA_NAME        "KAA Grid BB ProfitPlus"
#define EA_VERSION_STR "2.00"
#define PANEL_PREFIX   "KAA_PNL_"

//+------------------------------------------------------------------+
//| Enumerations                                                      |
//+------------------------------------------------------------------+
enum ENUM_GRID_DIRECTION
{
   GRID_BUY_ONLY  = 0,  // Buy only
   GRID_SELL_ONLY = 1,  // Sell only
   GRID_BOTH      = 2   // Both directions
};

enum ENUM_CLOSE_MODE
{
   CLOSE_TOTAL_PROFIT = 0,  // Basket profit (money)
   CLOSE_TOTAL_POINTS = 1,  // Basket points
   CLOSE_BB_MIDDLE    = 2,  // Price reaches BB middle band
   CLOSE_BB_OPPOSITE  = 3   // Price reaches opposite BB band
};

enum ENUM_LOT_MODE
{
   LOT_FIXED = 0,  // Fixed start lot
   LOT_AUTO  = 1   // Auto start lot by balance
};

//+------------------------------------------------------------------+
//| Inputs                                                            |
//+------------------------------------------------------------------+
input group "=== General ==="
input ulong    InpMagicNumber       = 202603;      // Magic number
input string   InpComment           = "KAA_Grid";  // Order comment prefix (max 20 chars)
input bool     InpShowPanel         = true;        // Show info panel on chart

input group "=== Bollinger Bands ==="
input int                InpBBPeriod    = 20;          // BB period
input double             InpBBDeviation = 2.0;         // BB deviation
input ENUM_TIMEFRAMES    InpBBTimeframe = PERIOD_M15;  // Signal timeframe (BB / ATR)
input ENUM_APPLIED_PRICE InpBBPrice     = PRICE_CLOSE; // BB applied price

input group "=== Trend Filter ==="
input bool            InpUseTrendFilter    = true;      // Use higher timeframe EMA trend filter
input ENUM_TIMEFRAMES InpTrendTimeframe    = PERIOD_H1; // Trend timeframe
input int             InpTrendMAPeriod     = 200;       // Trend EMA period
input bool            InpRequireTrendSlope = true;      // Require EMA slope confirmation

input group "=== Entry ==="
input bool     InpUseBBFilter       = true;   // First order only at BB band
input int      InpBBEntryPoints     = 50;     // Allowed distance inside the band (points)
input int      InpMinCandleBody     = 0;      // Min body of last closed candle (points, 0=off)

input group "=== Grid ==="
input ENUM_GRID_DIRECTION InpDirection   = GRID_BOTH; // Grid direction
input int      InpMaxGridLevels     = 12;     // Max grid levels per basket
input bool     InpOneBasketAtATime  = true;   // Do not run buy and sell baskets together
input int      InpReentryCooldownBars = 1;    // Bars to wait after a basket is closed
input int      InpGridStepPoints    = 300;    // Grid step (points) - fixed, or minimum when ATR is on
input bool     InpUseATRGrid        = true;   // Use ATR adaptive grid step
input int      InpATRPeriod         = 14;     // ATR period
input double   InpATRMultiplier     = 0.80;   // ATR multiplier
input int      InpMaxStepPoints     = 0;      // Max adaptive step (points, 0=no cap)

input group "=== Lot Size ==="
input ENUM_LOT_MODE InpLotMode      = LOT_FIXED; // Lot mode
input double   InpStartLot          = 0.01;   // Fixed start lot
input double   InpAutoLotPerStep    = 0.01;   // Auto: start lot per balance step
input double   InpAutoBalanceStep   = 1000.0; // Auto: balance step (account currency)
input double   InpLotMultiplier     = 1.12;   // Lot multiplier per level (1.0 = flat)
input double   InpMaxLot            = 0.50;   // Max lot per order
input double   InpMaxMarginUsage    = 80.0;   // Max % of free margin one order may use

input group "=== Lot Split (hedging accounts only) ==="
input bool     InpUseLotSplit       = false;  // Split each level into smaller orders
input double   InpSplitLotSize      = 0.03;   // Split order lot size
input int      InpMaxSplitOrders    = 8;      // Max split orders per level

input group "=== Basket Exit (money values refer to Reference lot) ==="
input ENUM_CLOSE_MODE InpCloseMode  = CLOSE_TOTAL_PROFIT; // Close mode
input double   InpTotalProfitTarget = 50.0;   // Basket profit target (money)
input int      InpTotalPointsTarget = 500;    // Basket points target (points mode)
input bool     InpUseBBClose        = false;  // Also close at BB middle band when in profit
input double   InpMinProfitToClose  = 5.0;    // Min profit to allow BB close (money)
input bool     InpScaleByLot        = true;   // Scale money values by start lot
input double   InpReferenceLot      = 0.10;   // Reference lot for money values

input group "=== Dynamic Profit Target ==="
input bool     InpUseDynamicTarget  = true;   // Increase target with basket size
input double   InpProfitPerLevel    = 15.0;   // Extra target per extra level (money)
input double   InpProfitPerLot      = 25.0;   // Extra target per 1.0 lot in basket (money)
input double   InpBBCloseTargetRatio = 0.60;  // BB close needs this ratio of target

input group "=== Basket Trailing ==="
input bool     InpUseTrailing        = false; // Enable basket trailing
input double   InpTrailingActivation = 25.0;  // Activation profit (money)
input double   InpTrailingStep       = 5.0;   // Peak update step (money)
input double   InpTrailingDistance   = 10.0;  // Close when profit falls this much from peak
input bool     InpUseDynamicTrailing = true;  // Scale trailing with basket target
input double   InpTrailingActivationRatio = 0.70; // Activation as ratio of target
input double   InpTrailingStepRatio       = 0.10; // Step as ratio of target
input double   InpTrailingDistanceRatio   = 0.25; // Distance as ratio of target

input group "=== Risk Management ==="
input double   InpMaxDrawdownPercent = 30.0;  // Max equity drawdown % of balance (0=off)
input double   InpMaxDrawdownMoney   = 0.0;   // Max equity drawdown money (0=off)
input bool     InpCloseOnMaxDD       = true;  // Close all baskets when max drawdown is hit
input int      InpMaxSpread          = 0;     // Max spread for new orders (points, 0=off)

input group "=== Time Filter (server time) ==="
input bool     InpUseTimeFilter     = false;  // Use time filter for new orders
input int      InpStartHour         = 1;      // Start hour
input int      InpEndHour           = 23;     // End hour
input bool     InpCloseOnFriday     = false;  // Close all baskets on Friday
input int      InpFridayCloseHour   = 22;     // Friday close hour

//+------------------------------------------------------------------+
//| Globals                                                           |
//+------------------------------------------------------------------+
CTrade         m_trade;
CPositionInfo  m_position;

int      g_bbHandle      = INVALID_HANDLE;
int      g_atrHandle     = INVALID_HANDLE;
int      g_trendMaHandle = INVALID_HANDLE;
double   g_bbUpper[];
double   g_bbMiddle[];
double   g_bbLower[];
double   g_atrValues[];
double   g_trendMa[];

bool     g_isHedging;
bool     g_useSplit;
bool     g_oneBasket;
string   g_comment;
string   g_gvPrefix;

datetime g_lastBarTime;
datetime g_lastPanelUpdate;
int      g_gridCountBuy;
int      g_gridCountSell;
int      g_totalPositionsBuy;
int      g_totalPositionsSell;
double   g_lowestBuyPrice;
double   g_highestSellPrice;

bool     g_trailingActiveBuy;
bool     g_trailingActiveSell;
double   g_peakProfitBuy;
double   g_peakProfitSell;

int      g_splitLevelBuy;
int      g_splitLevelSell;
int      g_splitsOpenedBuy;
int      g_splitsOpenedSell;
int      g_targetSplitsBuy;
int      g_targetSplitsSell;
int      g_latestBuyLevel;
int      g_latestSellLevel;
int      g_splitCountLatestBuy;
int      g_splitCountLatestSell;
datetime g_lastCloseTimeBuy;
datetime g_lastCloseTimeSell;

//+------------------------------------------------------------------+
//| Input validation                                                  |
//+------------------------------------------------------------------+
bool ValidateInputs()
{
   string err = "";
   if(InpBBPeriod < 2)                          err = "BB period must be >= 2";
   else if(InpBBDeviation <= 0)                 err = "BB deviation must be > 0";
   else if(InpTrendMAPeriod < 1)                err = "Trend EMA period must be >= 1";
   else if(InpATRPeriod < 1)                    err = "ATR period must be >= 1";
   else if(InpATRMultiplier <= 0)               err = "ATR multiplier must be > 0";
   else if(InpGridStepPoints < 1)               err = "Grid step must be >= 1 point";
   else if(InpMaxStepPoints < 0)                err = "Max adaptive step must be >= 0";
   else if(InpMaxStepPoints > 0 && InpMaxStepPoints < InpGridStepPoints)
                                                err = "Max adaptive step must be >= grid step";
   else if(InpMaxGridLevels < 1 || InpMaxGridLevels > 100)
                                                err = "Max grid levels must be 1..100";
   else if(InpStartLot <= 0)                    err = "Start lot must be > 0";
   else if(InpAutoLotPerStep <= 0)              err = "Auto lot per step must be > 0";
   else if(InpAutoBalanceStep <= 0)             err = "Auto balance step must be > 0";
   else if(InpLotMultiplier < 1.0 || InpLotMultiplier > 3.0)
                                                err = "Lot multiplier must be 1.0..3.0";
   else if(InpMaxLot <= 0)                      err = "Max lot must be > 0";
   else if(InpMaxMarginUsage <= 0 || InpMaxMarginUsage > 100)
                                                err = "Max margin usage must be 0..100 %";
   else if(InpUseLotSplit && InpSplitLotSize <= 0) err = "Split lot size must be > 0";
   else if(InpUseLotSplit && InpMaxSplitOrders < 1) err = "Max split orders must be >= 1";
   else if(InpTotalProfitTarget <= 0)           err = "Profit target must be > 0";
   else if(InpTotalPointsTarget <= 0)           err = "Points target must be > 0";
   else if(InpReferenceLot <= 0)                err = "Reference lot must be > 0";
   else if(InpMaxDrawdownPercent < 0 || InpMaxDrawdownPercent > 100)
                                                err = "Max drawdown % must be 0..100";
   else if(InpMaxDrawdownMoney < 0)             err = "Max drawdown money must be >= 0";
   else if(InpMaxSpread < 0)                    err = "Max spread must be >= 0";
   else if(InpReentryCooldownBars < 0)          err = "Cooldown bars must be >= 0";
   else if(InpStartHour < 0 || InpStartHour > 23 || InpEndHour < 0 || InpEndHour > 23)
                                                err = "Hours must be 0..23";
   else if(InpFridayCloseHour < 0 || InpFridayCloseHour > 23)
                                                err = "Friday close hour must be 0..23";

   if(err != "")
   {
      Print(EA_NAME, " - invalid input: ", err);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   if(!ValidateInputs())
      return INIT_PARAMETERS_INCORRECT;

   g_isHedging = ((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   g_useSplit  = (InpUseLotSplit && g_isHedging);
   g_oneBasket = (InpOneBasketAtATime || !g_isHedging);
   g_comment   = StringSubstr(InpComment, 0, 20);
   g_gvPrefix  = StringFormat("KAA_%I64u_%s_", InpMagicNumber, _Symbol);

   if(InpUseLotSplit && !g_isHedging)
      Print("Netting account: lot split is disabled.");
   if(!g_isHedging)
      Print("Netting account: one basket at a time is enforced.");

   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(30);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(_Symbol);
   m_trade.LogLevel(LOG_LEVEL_ERRORS);

   g_bbHandle = iBands(_Symbol, InpBBTimeframe, InpBBPeriod, 0, InpBBDeviation, InpBBPrice);
   if(g_bbHandle == INVALID_HANDLE)
   {
      Print("Failed to create Bollinger Bands, error ", GetLastError());
      return INIT_FAILED;
   }
   g_atrHandle = iATR(_Symbol, InpBBTimeframe, InpATRPeriod);
   if(g_atrHandle == INVALID_HANDLE)
   {
      Print("Failed to create ATR, error ", GetLastError());
      return INIT_FAILED;
   }
   g_trendMaHandle = iMA(_Symbol, InpTrendTimeframe, InpTrendMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   if(g_trendMaHandle == INVALID_HANDLE)
   {
      Print("Failed to create trend EMA, error ", GetLastError());
      return INIT_FAILED;
   }

   ArraySetAsSeries(g_bbUpper, true);
   ArraySetAsSeries(g_bbMiddle, true);
   ArraySetAsSeries(g_bbLower, true);
   ArraySetAsSeries(g_atrValues, true);
   ArraySetAsSeries(g_trendMa, true);

   g_lastBarTime        = 0;
   g_lastPanelUpdate    = 0;
   g_trailingActiveBuy  = false;
   g_trailingActiveSell = false;
   g_peakProfitBuy      = 0;
   g_peakProfitSell     = 0;
   ResetSplitState(POSITION_TYPE_BUY);
   ResetSplitState(POSITION_TYPE_SELL);
   g_lastCloseTimeBuy   = 0;
   g_lastCloseTimeSell  = 0;

   CountGridPositions();

   PrintFormat("%s v%s started on %s | %s account | magic %I64u",
               EA_NAME, EA_VERSION_STR, _Symbol, g_isHedging ? "hedging" : "netting", InpMagicNumber);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_bbHandle != INVALID_HANDLE)      IndicatorRelease(g_bbHandle);
   if(g_atrHandle != INVALID_HANDLE)     IndicatorRelease(g_atrHandle);
   if(g_trendMaHandle != INVALID_HANDLE) IndicatorRelease(g_trendMaHandle);
   ObjectsDeleteAll(0, PANEL_PREFIX);
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Expert tick                                                       |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!UpdateIndicatorData())
      return;

   CountGridPositions();
   UpdatePanel();

   bool ddHit = CheckDrawdownLimit();
   if(ddHit && InpCloseOnMaxDD)
      return;
   if(InpCloseOnFriday && CheckFridayClose())
      return;
   if(CheckTrailingStop())
      return;
   if(CheckCloseConditions())
      return;

   if(ddHit)
      return;   // no new orders while drawdown is above the limit
   if(InpUseTimeFilter && !IsWithinTradingHours())
      return;
   if(InpMaxSpread > 0 && CurrentSpreadPoints() > InpMaxSpread)
      return;

   CheckGridEntry();
}

//+------------------------------------------------------------------+
//| Indicator data                                                    |
//+------------------------------------------------------------------+
bool UpdateIndicatorData()
{
   if(CopyBuffer(g_bbHandle, 0, 0, 3, g_bbMiddle) < 3)       return false;
   if(CopyBuffer(g_bbHandle, 1, 0, 3, g_bbUpper) < 3)        return false;
   if(CopyBuffer(g_bbHandle, 2, 0, 3, g_bbLower) < 3)        return false;
   if(CopyBuffer(g_atrHandle, 0, 0, 3, g_atrValues) < 3)     return false;
   if(CopyBuffer(g_trendMaHandle, 0, 0, 3, g_trendMa) < 3)   return false;
   return true;
}

//+------------------------------------------------------------------+
//| Symbol / account helpers                                          |
//+------------------------------------------------------------------+
double PointSize()
{
   double p = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   return (p > 0) ? p : _Point;
}

int CurrentSpreadPoints()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   return (int)MathRound((tick.ask - tick.bid) / PointSize());
}

int VolumeDigits()
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   int digits = 0;
   while(digits < 8 && MathAbs(step * MathPow(10, digits) - MathRound(step * MathPow(10, digits))) > 1e-7)
      digits++;
   return digits;
}

double NormalizeVolume(double lot)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = vmin;
   if(step > 0)  lot = MathFloor(lot / step + 1e-9) * step;
   lot = MathMax(lot, vmin);
   lot = MathMin(lot, vmax);
   return NormalizeDouble(lot, VolumeDigits());
}

// Is a new position of this type allowed by the symbol's trade mode?
bool IsDirectionAllowed(ENUM_ORDER_TYPE type)
{
   ENUM_SYMBOL_TRADE_MODE mode = (ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED || mode == SYMBOL_TRADE_MODE_CLOSEONLY)
      return false;
   if(type == ORDER_TYPE_BUY  && mode == SYMBOL_TRADE_MODE_SHORTONLY) return false;
   if(type == ORDER_TYPE_SELL && mode == SYMBOL_TRADE_MODE_LONGONLY)  return false;
   return true;
}

bool IsTradingPermitted()
{
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))                 return false;
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))       return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))         return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))          return false;
   return true;
}

// Checks volume value, account order limit, symbol volume limit and margin.
bool CanOpenOrder(ENUM_ORDER_TYPE type, double lot, string &reason)
{
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(lot < vmin || lot > vmax)
   {
      reason = StringFormat("volume %.2f outside %.2f..%.2f", lot, vmin, vmax);
      return false;
   }

   long orderLimit = AccountInfoInteger(ACCOUNT_LIMIT_ORDERS);
   if(orderLimit > 0 && (PositionsTotal() + OrdersTotal()) >= orderLimit)
   {
      reason = "account order limit reached";
      return false;
   }

   double volumeLimit = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT);
   if(volumeLimit > 0)
   {
      double current = GetTotalVolume(POSITION_TYPE_BUY) + GetTotalVolume(POSITION_TYPE_SELL);
      if(current + lot > volumeLimit)
      {
         reason = "symbol volume limit reached";
         return false;
      }
   }

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
   {
      reason = "no price";
      return false;
   }
   double price  = (type == ORDER_TYPE_BUY) ? tick.ask : tick.bid;
   double margin = 0;
   if(!OrderCalcMargin(type, _Symbol, lot, price, margin))
   {
      reason = StringFormat("margin calculation failed (%d)", GetLastError());
      return false;
   }
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(margin > freeMargin * InpMaxMarginUsage / 100.0)
   {
      reason = StringFormat("not enough money: margin %.2f, free margin %.2f", margin, freeMargin);
      return false;
   }
   return true;
}

bool OpenMarketOrder(ENUM_ORDER_TYPE type, double lot, string comment)
{
   if(!IsTradingPermitted() || !IsDirectionAllowed(type))
      return false;

   lot = NormalizeVolume(lot);
   string reason = "";
   if(!CanOpenOrder(type, lot, reason))
   {
      PrintFormat("%s %.2f skipped: %s", (type == ORDER_TYPE_BUY) ? "BUY" : "SELL", lot, reason);
      return false;
   }

   bool sent = (type == ORDER_TYPE_BUY) ? m_trade.Buy(lot, _Symbol, 0.0, 0.0, 0.0, comment)
                                        : m_trade.Sell(lot, _Symbol, 0.0, 0.0, 0.0, comment);
   uint rc = m_trade.ResultRetcode();
   if(!sent || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED && rc != TRADE_RETCODE_DONE_PARTIAL))
   {
      PrintFormat("%s %.2f failed: %u - %s", (type == ORDER_TYPE_BUY) ? "BUY" : "SELL",
                  lot, rc, m_trade.ResultRetcodeDescription());
      return false;
   }
   PrintFormat(">>> %s %s | lot %.2f | price %s", (type == ORDER_TYPE_BUY) ? "BUY" : "SELL",
               comment, lot, DoubleToString(m_trade.ResultPrice(), _Digits));
   return true;
}

//+------------------------------------------------------------------+
//| Netting-mode basket state (stored in terminal global variables)   |
//+------------------------------------------------------------------+
string NetKey(ENUM_POSITION_TYPE type, string field)
{
   return g_gvPrefix + ((type == POSITION_TYPE_BUY) ? "B" : "S") + field;
}

double NetGet(ENUM_POSITION_TYPE type, string field)
{
   string key = NetKey(type, field);
   return GlobalVariableCheck(key) ? GlobalVariableGet(key) : 0.0;
}

void NetSet(ENUM_POSITION_TYPE type, string field, double value)
{
   GlobalVariableSet(NetKey(type, field), value);
}

void NetClear(ENUM_POSITION_TYPE type)
{
   GlobalVariableDel(NetKey(type, "L"));
   GlobalVariableDel(NetKey(type, "P"));
}

//+------------------------------------------------------------------+
//| Timing helpers                                                    |
//+------------------------------------------------------------------+
int GetTfSeconds(ENUM_TIMEFRAMES timeframe)
{
   int seconds = PeriodSeconds(timeframe);
   if(seconds <= 0) seconds = PeriodSeconds(_Period);
   if(seconds <= 0) seconds = 60;
   return seconds;
}

bool IsCooldownComplete(ENUM_POSITION_TYPE posType, datetime currentBarTime)
{
   if(InpReentryCooldownBars <= 0)
      return true;
   datetime lastClose = (posType == POSITION_TYPE_BUY) ? g_lastCloseTimeBuy : g_lastCloseTimeSell;
   if(lastClose <= 0)
      return true;
   return ((currentBarTime - lastClose) >= (GetTfSeconds(InpBBTimeframe) * InpReentryCooldownBars));
}

//+------------------------------------------------------------------+
//| Grid step (price units)                                           |
//+------------------------------------------------------------------+
double GetAdaptiveGridStep()
{
   double point = PointSize();
   double step  = InpGridStepPoints * point;

   if(InpUseATRGrid && g_atrValues[1] > 0)
   {
      step = MathMax(g_atrValues[1] * InpATRMultiplier, step);
      if(InpMaxStepPoints > 0)
         step = MathMin(step, InpMaxStepPoints * point);
   }
   return NormalizeDouble(step, _Digits);
}

//+------------------------------------------------------------------+
//| Trend filter                                                      |
//+------------------------------------------------------------------+
bool IsBuyTrendAllowed()
{
   if(!InpUseTrendFilter) return true;
   double trendClose = iClose(_Symbol, InpTrendTimeframe, 1);
   if(trendClose <= 0) return false;
   bool slopeOK = (!InpRequireTrendSlope || g_trendMa[1] > g_trendMa[2]);
   return (trendClose > g_trendMa[1] && slopeOK);
}

bool IsSellTrendAllowed()
{
   if(!InpUseTrendFilter) return true;
   double trendClose = iClose(_Symbol, InpTrendTimeframe, 1);
   if(trendClose <= 0) return false;
   bool slopeOK = (!InpRequireTrendSlope || g_trendMa[1] < g_trendMa[2]);
   return (trendClose < g_trendMa[1] && slopeOK);
}

//+------------------------------------------------------------------+
//| Lot size                                                          |
//+------------------------------------------------------------------+
double GetBaseLot()
{
   if(InpLotMode == LOT_AUTO)
      return NormalizeVolume(AccountInfoDouble(ACCOUNT_BALANCE) / InpAutoBalanceStep * InpAutoLotPerStep);
   return NormalizeVolume(InpStartLot);
}

double CalculateLotSize(int gridLevel)
{
   double lot = GetBaseLot();
   for(int i = 0; i < gridLevel; i++)
      lot *= InpLotMultiplier;
   lot = MathMin(lot, InpMaxLot);
   return NormalizeVolume(lot);
}

// Money values in the inputs are defined for InpReferenceLot.
double MoneyScale()
{
   if(!InpScaleByLot)
      return 1.0;
   return GetBaseLot() / InpReferenceLot;
}

//+------------------------------------------------------------------+
//| Basket statistics                                                 |
//+------------------------------------------------------------------+
bool SelectOwnPosition(int index)
{
   if(!m_position.SelectByIndex(index))        return false;
   if(m_position.Symbol() != _Symbol)          return false;
   if((ulong)m_position.Magic() != InpMagicNumber) return false;
   return true;
}

double GetTotalVolume(ENUM_POSITION_TYPE posType)
{
   double total = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!SelectOwnPosition(i)) continue;
      if(m_position.PositionType() != posType) continue;
      total += m_position.Volume();
   }
   return total;
}

double CalculateTotalProfit(ENUM_POSITION_TYPE posType)
{
   double total = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!SelectOwnPosition(i)) continue;
      if(m_position.PositionType() != posType) continue;
      total += m_position.Profit() + m_position.Swap();
   }
   return total;
}

double CalculateTotalPoints(ENUM_POSITION_TYPE posType)
{
   double point = PointSize();
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double total = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!SelectOwnPosition(i)) continue;
      if(m_position.PositionType() != posType) continue;
      double pts = (posType == POSITION_TYPE_BUY) ? (bid - m_position.PriceOpen()) / point
                                                  : (m_position.PriceOpen() - ask) / point;
      // On netting accounts one position represents the whole basket.
      if(!g_isHedging)
         pts *= MathMax((posType == POSITION_TYPE_BUY) ? g_gridCountBuy : g_gridCountSell, 1);
      total += pts;
   }
   return total;
}

double GetDynamicProfitTarget(ENUM_POSITION_TYPE posType)
{
   double scale  = MoneyScale();
   double target = InpTotalProfitTarget * scale;
   if(!InpUseDynamicTarget)
      return target;

   int levels = (posType == POSITION_TYPE_BUY) ? g_gridCountBuy : g_gridCountSell;
   if(levels > 1)
      target += (levels - 1) * InpProfitPerLevel * scale;
   target += GetTotalVolume(posType) * InpProfitPerLot;
   return target;
}

double GetMinProfitForBBClose(ENUM_POSITION_TYPE posType)
{
   double minProfit = InpMinProfitToClose * MoneyScale();
   if(InpUseDynamicTarget)
      minProfit = MathMax(minProfit, GetDynamicProfitTarget(posType) * InpBBCloseTargetRatio);
   return minProfit;
}

double GetTrailingActivationValue(ENUM_POSITION_TYPE posType)
{
   double v = InpTrailingActivation * MoneyScale();
   if(InpUseDynamicTrailing)
      v = MathMax(v, GetDynamicProfitTarget(posType) * InpTrailingActivationRatio);
   return v;
}

double GetTrailingStepValue(ENUM_POSITION_TYPE posType)
{
   double v = InpTrailingStep * MoneyScale();
   if(InpUseDynamicTrailing)
      v = MathMax(v, GetDynamicProfitTarget(posType) * InpTrailingStepRatio);
   return v;
}

double GetTrailingDistanceValue(ENUM_POSITION_TYPE posType)
{
   double v = InpTrailingDistance * MoneyScale();
   if(InpUseDynamicTrailing)
      v = MathMax(v, GetDynamicProfitTarget(posType) * InpTrailingDistanceRatio);
   return v;
}

//+------------------------------------------------------------------+
//| State resets                                                      |
//+------------------------------------------------------------------+
void MarkBasketClosed(ENUM_POSITION_TYPE posType)
{
   if(posType == POSITION_TYPE_BUY) g_lastCloseTimeBuy  = TimeCurrent();
   else                             g_lastCloseTimeSell = TimeCurrent();
   if(!g_isHedging)
      NetClear(posType);
}

void ResetTrailing(ENUM_POSITION_TYPE posType)
{
   if(posType == POSITION_TYPE_BUY) { g_trailingActiveBuy  = false; g_peakProfitBuy  = 0; }
   else                             { g_trailingActiveSell = false; g_peakProfitSell = 0; }
}

void ResetSplitState(ENUM_POSITION_TYPE posType)
{
   if(posType == POSITION_TYPE_BUY) { g_splitLevelBuy  = 0; g_splitsOpenedBuy  = 0; g_targetSplitsBuy  = 0; }
   else                             { g_splitLevelSell = 0; g_splitsOpenedSell = 0; g_targetSplitsSell = 0; }
}

void ResetBasketState(ENUM_POSITION_TYPE posType)
{
   ResetTrailing(posType);
   ResetSplitState(posType);
}

//+------------------------------------------------------------------+
//| Grid level parsing: "<prefix>_B3" or "<prefix>_B3_2" => 3         |
//+------------------------------------------------------------------+
int ExtractGridLevel(string comment, string tag)
{
   int pos = StringFind(comment, tag);
   if(pos < 0) return 0;
   string rest = StringSubstr(comment, pos + StringLen(tag));
   int us = StringFind(rest, "_");
   if(us > 0) rest = StringSubstr(rest, 0, us);
   return (int)StringToInteger(rest);
}

int SplitTarget(double totalLot)
{
   double splitLot = NormalizeVolume(InpSplitLotSize);
   int target = (splitLot > 0) ? (int)MathFloor(totalLot / splitLot + 1e-9) : 1;
   target = MathMin(target, InpMaxSplitOrders);
   return MathMax(target, 1);
}

//+------------------------------------------------------------------+
//| Count positions and rebuild grid state                            |
//+------------------------------------------------------------------+
void CountGridPositions()
{
   g_totalPositionsBuy    = 0;
   g_totalPositionsSell   = 0;
   g_gridCountBuy         = 0;
   g_gridCountSell        = 0;
   g_lowestBuyPrice       = 0;
   g_highestSellPrice     = 0;
   g_latestBuyLevel       = 0;
   g_latestSellLevel      = 0;
   g_splitCountLatestBuy  = 0;
   g_splitCountLatestSell = 0;

   if(!g_isHedging)
   {
      CountNettingPosition();
      return;
   }

   bool buyFound[], sellFound[];
   int  buySplits[], sellSplits[];
   ArrayResize(buyFound,  InpMaxGridLevels + 1);
   ArrayResize(sellFound, InpMaxGridLevels + 1);
   ArrayResize(buySplits, InpMaxGridLevels + 1);
   ArrayResize(sellSplits, InpMaxGridLevels + 1);
   ArrayInitialize(buyFound,  false);
   ArrayInitialize(sellFound, false);
   ArrayInitialize(buySplits, 0);
   ArrayInitialize(sellSplits, 0);

   string buyTag  = g_comment + "_B";
   string sellTag = g_comment + "_S";
   double lowestBuy   = DBL_MAX;
   double highestSell = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!SelectOwnPosition(i)) continue;
      double openPrice = m_position.PriceOpen();
      string comment   = m_position.Comment();

      if(m_position.PositionType() == POSITION_TYPE_BUY)
      {
         g_totalPositionsBuy++;
         lowestBuy = MathMin(lowestBuy, openPrice);
         int level = ExtractGridLevel(comment, buyTag);
         if(level > 0 && level <= InpMaxGridLevels)
         {
            if(!buyFound[level]) { buyFound[level] = true; g_gridCountBuy++; }
            buySplits[level]++;
            g_latestBuyLevel = MathMax(g_latestBuyLevel, level);
         }
      }
      else
      {
         g_totalPositionsSell++;
         highestSell = MathMax(highestSell, openPrice);
         int level = ExtractGridLevel(comment, sellTag);
         if(level > 0 && level <= InpMaxGridLevels)
         {
            if(!sellFound[level]) { sellFound[level] = true; g_gridCountSell++; }
            sellSplits[level]++;
            g_latestSellLevel = MathMax(g_latestSellLevel, level);
         }
      }
   }

   if(g_totalPositionsBuy > 0)  g_lowestBuyPrice   = lowestBuy;
   if(g_totalPositionsSell > 0) g_highestSellPrice = highestSell;
   if(g_latestBuyLevel > 0)     g_splitCountLatestBuy  = buySplits[g_latestBuyLevel];
   if(g_latestSellLevel > 0)    g_splitCountLatestSell = sellSplits[g_latestSellLevel];

   // Fallback when the broker changed the comments
   if(g_totalPositionsBuy > 0 && g_gridCountBuy == 0)
      g_gridCountBuy = g_useSplit ? (int)MathCeil((double)g_totalPositionsBuy / InpMaxSplitOrders) : g_totalPositionsBuy;
   if(g_totalPositionsSell > 0 && g_gridCountSell == 0)
      g_gridCountSell = g_useSplit ? (int)MathCeil((double)g_totalPositionsSell / InpMaxSplitOrders) : g_totalPositionsSell;

   // Rebuild unfinished split sequences after a restart
   if(g_useSplit)
   {
      if(g_splitLevelBuy == 0 && g_latestBuyLevel > 0)
      {
         int target = SplitTarget(CalculateLotSize(g_latestBuyLevel - 1));
         if(g_splitCountLatestBuy < target)
         {
            g_splitLevelBuy   = g_latestBuyLevel;
            g_splitsOpenedBuy = g_splitCountLatestBuy;
            g_targetSplitsBuy = target;
         }
      }
      if(g_splitLevelSell == 0 && g_latestSellLevel > 0)
      {
         int target = SplitTarget(CalculateLotSize(g_latestSellLevel - 1));
         if(g_splitCountLatestSell < target)
         {
            g_splitLevelSell   = g_latestSellLevel;
            g_splitsOpenedSell = g_splitCountLatestSell;
            g_targetSplitsSell = target;
         }
      }
   }
}

void CountNettingPosition()
{
   bool haveBuy = false, haveSell = false;

   if(PositionSelect(_Symbol) && (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
   {
      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double avgPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      int    levels   = (int)NetGet(type, "L");
      double lastPx   = NetGet(type, "P");
      if(levels < 1)    levels = 1;
      if(lastPx <= 0)   lastPx = avgPrice;

      if(type == POSITION_TYPE_BUY)
      {
         haveBuy = true;
         g_totalPositionsBuy = 1;
         g_gridCountBuy      = levels;
         g_lowestBuyPrice    = lastPx;
      }
      else
      {
         haveSell = true;
         g_totalPositionsSell = 1;
         g_gridCountSell      = levels;
         g_highestSellPrice   = lastPx;
      }
   }

   if(!haveBuy)  NetClear(POSITION_TYPE_BUY);
   if(!haveSell) NetClear(POSITION_TYPE_SELL);
}

//+------------------------------------------------------------------+
//| Open one order of a split level                                   |
//+------------------------------------------------------------------+
void OpenOneSplitOrder(ENUM_ORDER_TYPE orderType, int levelNum, int splitNum, double totalLot)
{
   double splitLot = NormalizeVolume(InpSplitLotSize);
   double vmin     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   int    target   = SplitTarget(totalLot);
   double lot      = splitLot;

   // Last split takes the remainder
   if(splitNum >= target)
   {
      double remaining = totalLot - splitLot * (target - 1);
      if(remaining >= vmin)
         lot = remaining;
   }

   string comment = StringFormat("%s_%s%d_%d", g_comment, (orderType == ORDER_TYPE_BUY) ? "B" : "S",
                                 levelNum, splitNum);
   OpenMarketOrder(orderType, lot, comment);
}

//+------------------------------------------------------------------+
//| Open a new grid level for one direction                           |
//+------------------------------------------------------------------+
void OpenGridLevel(ENUM_POSITION_TYPE posType, int levelNum, double totalLot)
{
   ENUM_ORDER_TYPE orderType = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   if(g_useSplit)
   {
      int target = SplitTarget(totalLot);
      if(posType == POSITION_TYPE_BUY)
      {
         g_splitLevelBuy   = levelNum;
         g_targetSplitsBuy = target;
         g_splitsOpenedBuy = 1;
         OpenOneSplitOrder(orderType, levelNum, 1, totalLot);
         if(g_splitsOpenedBuy >= g_targetSplitsBuy) g_splitLevelBuy = 0;
      }
      else
      {
         g_splitLevelSell   = levelNum;
         g_targetSplitsSell = target;
         g_splitsOpenedSell = 1;
         OpenOneSplitOrder(orderType, levelNum, 1, totalLot);
         if(g_splitsOpenedSell >= g_targetSplitsSell) g_splitLevelSell = 0;
      }
      return;
   }

   string comment = StringFormat("%s_%s%d", g_comment, (posType == POSITION_TYPE_BUY) ? "B" : "S", levelNum);
   if(OpenMarketOrder(orderType, totalLot, comment) && !g_isHedging)
   {
      double price = m_trade.ResultPrice();
      if(price <= 0)
         price = (posType == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                                : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      NetSet(posType, "L", levelNum);
      NetSet(posType, "P", price);
   }
}

//+------------------------------------------------------------------+
//| Entry logic (once per signal bar)                                 |
//+------------------------------------------------------------------+
void CheckGridEntry()
{
   datetime currentBarTime = iTime(_Symbol, InpBBTimeframe, 0);
   if(currentBarTime == 0 || currentBarTime == g_lastBarTime)
      return;
   g_lastBarTime = currentBarTime;

   if(!IsTradingPermitted())
      return;

   double point = PointSize();
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0)
      return;
   double step  = GetAdaptiveGridStep();
   double bandTolerance = InpBBEntryPoints * point;

   double prevOpen  = iOpen(_Symbol, InpBBTimeframe, 1);
   double prevClose = iClose(_Symbol, InpBBTimeframe, 1);
   bool candleOK = (InpMinCandleBody == 0 || MathAbs(prevClose - prevOpen) / point >= InpMinCandleBody);

   //=== BUY basket ===
   if((InpDirection == GRID_BUY_ONLY || InpDirection == GRID_BOTH) && IsDirectionAllowed(ORDER_TYPE_BUY)
      && g_gridCountBuy <= InpMaxGridLevels)
   {
      bool newLevel = false;
      if(g_gridCountBuy == 0)
      {
         bool canStart = (!g_oneBasket || g_gridCountSell == 0);
         if(canStart && candleOK && IsCooldownComplete(POSITION_TYPE_BUY, currentBarTime) && IsBuyTrendAllowed())
            newLevel = (!InpUseBBFilter || ask <= g_bbLower[1] + bandTolerance);
      }
      else if(g_gridCountBuy < InpMaxGridLevels)
         newLevel = (g_lowestBuyPrice > 0 && ask <= g_lowestBuyPrice - step);

      if(newLevel)
      {
         double lot = CalculateLotSize(g_gridCountBuy);
         if(lot > 0)
            OpenGridLevel(POSITION_TYPE_BUY, g_gridCountBuy + 1, lot);
      }
      else if(g_useSplit && g_splitLevelBuy > 0 && g_splitsOpenedBuy < g_targetSplitsBuy)
      {
         g_splitsOpenedBuy++;
         OpenOneSplitOrder(ORDER_TYPE_BUY, g_splitLevelBuy, g_splitsOpenedBuy, CalculateLotSize(g_splitLevelBuy - 1));
         if(g_splitsOpenedBuy >= g_targetSplitsBuy) g_splitLevelBuy = 0;
      }
   }

   //=== SELL basket ===
   if((InpDirection == GRID_SELL_ONLY || InpDirection == GRID_BOTH) && IsDirectionAllowed(ORDER_TYPE_SELL)
      && g_gridCountSell <= InpMaxGridLevels)
   {
      bool newLevel = false;
      if(g_gridCountSell == 0)
      {
         // Re-read buy count: a buy basket may have been opened above on this tick
         if(g_oneBasket && g_gridCountBuy == 0)
            CountGridPositions();
         bool canStart = (!g_oneBasket || g_gridCountBuy == 0);
         if(canStart && candleOK && IsCooldownComplete(POSITION_TYPE_SELL, currentBarTime) && IsSellTrendAllowed())
            newLevel = (!InpUseBBFilter || bid >= g_bbUpper[1] - bandTolerance);
      }
      else if(g_gridCountSell < InpMaxGridLevels)
         newLevel = (g_highestSellPrice > 0 && bid >= g_highestSellPrice + step);

      if(newLevel)
      {
         double lot = CalculateLotSize(g_gridCountSell);
         if(lot > 0)
            OpenGridLevel(POSITION_TYPE_SELL, g_gridCountSell + 1, lot);
      }
      else if(g_useSplit && g_splitLevelSell > 0 && g_splitsOpenedSell < g_targetSplitsSell)
      {
         g_splitsOpenedSell++;
         OpenOneSplitOrder(ORDER_TYPE_SELL, g_splitLevelSell, g_splitsOpenedSell, CalculateLotSize(g_splitLevelSell - 1));
         if(g_splitsOpenedSell >= g_targetSplitsSell) g_splitLevelSell = 0;
      }
   }
}

//+------------------------------------------------------------------+
//| Basket trailing                                                   |
//+------------------------------------------------------------------+
bool TrailBasket(ENUM_POSITION_TYPE posType, bool &active, double &peak)
{
   int count = (posType == POSITION_TYPE_BUY) ? g_gridCountBuy : g_gridCountSell;
   string name = (posType == POSITION_TYPE_BUY) ? "BUY" : "SELL";
   if(count == 0)
   {
      if(active) ResetTrailing(posType);
      return false;
   }

   double profit = CalculateTotalProfit(posType);
   if(!active)
   {
      double activation = GetTrailingActivationValue(posType);
      if(profit >= activation)
      {
         active = true;
         peak   = profit;
         PrintFormat("Trailing %s activated | profit %.2f | activation %.2f", name, profit, activation);
      }
      return false;
   }

   if(profit > peak + GetTrailingStepValue(posType))
      peak = profit;

   double distance = GetTrailingDistanceValue(posType);
   if(profit <= peak - distance && profit > 0)
   {
      PrintFormat("<<< Trailing close %s | peak %.2f | profit %.2f", name, peak, profit);
      if(CloseAllPositions(posType))
      {
         ResetBasketState(posType);
         return true;
      }
   }
   else if(profit < 0)
   {
      PrintFormat("Trailing %s deactivated | profit %.2f", name, profit);
      ResetTrailing(posType);
   }
   return false;
}

bool CheckTrailingStop()
{
   if(!InpUseTrailing)
      return false;
   bool closedBuy  = TrailBasket(POSITION_TYPE_BUY,  g_trailingActiveBuy,  g_peakProfitBuy);
   bool closedSell = TrailBasket(POSITION_TYPE_SELL, g_trailingActiveSell, g_peakProfitSell);
   return (closedBuy || closedSell);
}

//+------------------------------------------------------------------+
//| Basket take profit                                                |
//+------------------------------------------------------------------+
bool CheckBasketClose(ENUM_POSITION_TYPE posType)
{
   int count = (posType == POSITION_TYPE_BUY) ? g_gridCountBuy : g_gridCountSell;
   if(count == 0)
      return false;

   bool   isBuy     = (posType == POSITION_TYPE_BUY);
   double price     = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double profit    = CalculateTotalProfit(posType);
   double target    = GetDynamicProfitTarget(posType);
   double bbMin     = GetMinProfitForBBClose(posType);
   bool   atMiddle  = isBuy ? (price >= g_bbMiddle[1]) : (price <= g_bbMiddle[1]);
   bool   atOpposite= isBuy ? (price >= g_bbUpper[1])  : (price <= g_bbLower[1]);
   bool   close     = false;

   switch(InpCloseMode)
   {
      case CLOSE_TOTAL_PROFIT: close = (profit >= target); break;
      case CLOSE_TOTAL_POINTS: close = (CalculateTotalPoints(posType) >= InpTotalPointsTarget && profit > 0); break;
      case CLOSE_BB_MIDDLE:    close = (atMiddle && profit >= bbMin); break;
      case CLOSE_BB_OPPOSITE:  close = (atOpposite && profit >= bbMin); break;
   }
   if(!close && InpUseBBClose && profit >= bbMin)
      close = atMiddle;

   if(!close)
      return false;

   PrintFormat("<<< Closing %s basket | profit %.2f | target %.2f | levels %d",
               isBuy ? "BUY" : "SELL", profit, target, count);
   if(CloseAllPositions(posType))
   {
      ResetBasketState(posType);
      return true;
   }
   return false;
}

bool CheckCloseConditions()
{
   bool closedBuy  = CheckBasketClose(POSITION_TYPE_BUY);
   bool closedSell = CheckBasketClose(POSITION_TYPE_SELL);
   return (closedBuy || closedSell);
}

//+------------------------------------------------------------------+
//| Close all positions of one type                                   |
//+------------------------------------------------------------------+
bool CloseAllPositions(ENUM_POSITION_TYPE posType)
{
   bool found = false;
   for(int attempt = 0; attempt < 3; attempt++)
   {
      bool allClosed = true;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!SelectOwnPosition(i)) continue;
         if(m_position.PositionType() != posType) continue;
         found = true;
         ulong ticket = m_position.Ticket();
         if(!m_trade.PositionClose(ticket))
         {
            PrintFormat("Close #%I64u failed: %u - %s (attempt %d)", ticket,
                        m_trade.ResultRetcode(), m_trade.ResultRetcodeDescription(), attempt + 1);
            allClosed = false;
         }
      }
      if(allClosed)
      {
         if(found)
            MarkBasketClosed(posType);
         return true;
      }
      if(!MQLInfoInteger(MQL_TESTER))
         Sleep(200);
   }
   return false;
}

//+------------------------------------------------------------------+
//| Equity drawdown protection                                        |
//+------------------------------------------------------------------+
bool CheckDrawdownLimit()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   if(balance <= 0) return false;

   double dd    = balance - equity;
   double ddPct = dd / balance * 100.0;
   bool hit = (InpMaxDrawdownPercent > 0 && ddPct >= InpMaxDrawdownPercent)
           || (InpMaxDrawdownMoney > 0 && dd >= InpMaxDrawdownMoney);
   if(!hit)
      return false;

   if(InpCloseOnMaxDD && (g_totalPositionsBuy > 0 || g_totalPositionsSell > 0))
   {
      PrintFormat("!!! Max drawdown hit: %.2f%% (%.2f) - closing all baskets", ddPct, dd);
      CloseAllPositions(POSITION_TYPE_BUY);
      CloseAllPositions(POSITION_TYPE_SELL);
      ResetBasketState(POSITION_TYPE_BUY);
      ResetBasketState(POSITION_TYPE_SELL);
   }
   return true;
}

//+------------------------------------------------------------------+
//| Time filters                                                      |
//+------------------------------------------------------------------+
bool IsWithinTradingHours()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   if(InpStartHour == InpEndHour) return true;
   if(InpStartHour < InpEndHour)
      return (dt.hour >= InpStartHour && dt.hour < InpEndHour);
   return (dt.hour >= InpStartHour || dt.hour < InpEndHour);
}

bool CheckFridayClose()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.day_of_week != 5 || dt.hour < InpFridayCloseHour)
      return false;

   if(g_totalPositionsBuy > 0 || g_totalPositionsSell > 0)
   {
      Print("Friday close: closing all baskets");
      CloseAllPositions(POSITION_TYPE_BUY);
      CloseAllPositions(POSITION_TYPE_SELL);
      ResetBasketState(POSITION_TYPE_BUY);
      ResetBasketState(POSITION_TYPE_SELL);
   }
   return true;   // no new baskets after Friday close hour
}

//+------------------------------------------------------------------+
//| Chart panel                                                       |
//+------------------------------------------------------------------+
void PanelLabel(int row, string text, color clr)
{
   string name = PANEL_PREFIX + IntegerToString(row);
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 18);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 26 + row * 16);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   }
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

void AddLine(string &lines[], color &colors[], string text, color clr)
{
   int n = ArraySize(lines);
   ArrayResize(lines, n + 1);
   ArrayResize(colors, n + 1);
   lines[n]  = text;
   colors[n] = clr;
}

void UpdatePanel()
{
   if(!InpShowPanel)
      return;
   if(MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_VISUAL_MODE))
      return;
   if(!MQLInfoInteger(MQL_TESTER) && TimeLocal() == g_lastPanelUpdate)
      return;
   g_lastPanelUpdate = TimeLocal();

   double buyPL  = CalculateTotalProfit(POSITION_TYPE_BUY);
   double sellPL = CalculateTotalProfit(POSITION_TYPE_SELL);
   double bal    = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq     = AccountInfoDouble(ACCOUNT_EQUITY);
   double ddPct  = (bal > 0) ? (bal - eq) / bal * 100.0 : 0;
   string cur    = AccountInfoString(ACCOUNT_CURRENCY);

   string lines[];
   color  colors[];

   AddLine(lines, colors, EA_NAME + " v" + EA_VERSION_STR, clrGold);
   AddLine(lines, colors, StringFormat("%s  |  %s", _Symbol, g_isHedging ? "Hedging" : "Netting"), clrSilver);
   AddLine(lines, colors, StringFormat("BUY  %2d/%d  P/L %9.2f", g_gridCountBuy, InpMaxGridLevels, buyPL),
            buyPL >= 0 ? clrLimeGreen : clrTomato);
   AddLine(lines, colors, StringFormat("SELL %2d/%d  P/L %9.2f", g_gridCountSell, InpMaxGridLevels, sellPL),
            sellPL >= 0 ? clrLimeGreen : clrTomato);
   if(g_gridCountBuy > 0)
      AddLine(lines, colors, StringFormat("Buy target  %.2f %s", GetDynamicProfitTarget(POSITION_TYPE_BUY), cur), clrWhite);
   if(g_gridCountSell > 0)
      AddLine(lines, colors, StringFormat("Sell target %.2f %s", GetDynamicProfitTarget(POSITION_TYPE_SELL), cur), clrWhite);
   if(InpUseTrailing && g_trailingActiveBuy)
      AddLine(lines, colors, StringFormat("Trail BUY  peak %.2f", g_peakProfitBuy), clrDeepSkyBlue);
   if(InpUseTrailing && g_trailingActiveSell)
      AddLine(lines, colors, StringFormat("Trail SELL peak %.2f", g_peakProfitSell), clrDeepSkyBlue);
   if(g_useSplit && g_splitLevelBuy > 0)
      AddLine(lines, colors, StringFormat("Split BUY  L%d [%d/%d]", g_splitLevelBuy, g_splitsOpenedBuy, g_targetSplitsBuy), clrSilver);
   if(g_useSplit && g_splitLevelSell > 0)
      AddLine(lines, colors, StringFormat("Split SELL L%d [%d/%d]", g_splitLevelSell, g_splitsOpenedSell, g_targetSplitsSell), clrSilver);
   AddLine(lines, colors, StringFormat("Grid step %s  Lot %.2f", DoubleToString(GetAdaptiveGridStep(), _Digits), GetBaseLot()), clrWhite);
   AddLine(lines, colors, StringFormat("Balance %.2f  Equity %.2f", bal, eq), clrWhite);
   AddLine(lines, colors, StringFormat("Drawdown %.2f%%  Spread %d", ddPct, CurrentSpreadPoints()),
            ddPct >= InpMaxDrawdownPercent * 0.7 && InpMaxDrawdownPercent > 0 ? clrOrange : clrWhite);
   if(InpUseTrendFilter)
   {
      string trend = IsBuyTrendAllowed() ? "UP" : (IsSellTrendAllowed() ? "DOWN" : "FLAT");
      AddLine(lines, colors, "Trend filter: " + trend, clrSilver);
   }

   string bg = PANEL_PREFIX + "BG";
   if(ObjectFind(0, bg) < 0)
   {
      ObjectCreate(0, bg, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, bg, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, bg, OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, bg, OBJPROP_YDISTANCE, 20);
      ObjectSetInteger(0, bg, OBJPROP_XSIZE, 270);
      ObjectSetInteger(0, bg, OBJPROP_BGCOLOR, C'20,24,32');
      ObjectSetInteger(0, bg, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, bg, OBJPROP_COLOR, clrDimGray);
      ObjectSetInteger(0, bg, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, bg, OBJPROP_HIDDEN, true);
   }
   int n = ArraySize(lines);
   ObjectSetInteger(0, bg, OBJPROP_YSIZE, n * 16 + 12);

   for(int i = 0; i < n; i++)
      PanelLabel(i, lines[i], colors[i]);
   for(int i = n; i < 20; i++)
      ObjectDelete(0, PANEL_PREFIX + IntegerToString(i));

   ChartRedraw();
}
//+------------------------------------------------------------------+
