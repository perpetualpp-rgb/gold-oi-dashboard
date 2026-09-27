//+------------------------------------------------------------------+
//|                                            GoldRangeBreakout.mq5 |
//|                                                gold-oi-dashboard |
//|                                                                  |
//| Range Breakout EA for XAUUSD (works on any symbol).              |
//| Once per day, at a check time in a chosen timezone (New York /   |
//| London follow their own DST), it measures the range formed by    |
//| the N candles that closed before that moment. If the range is    |
//| tight enough (x ATR), it trades the break with pending stop      |
//| orders or a market entry on a candle close outside the range.    |
//|                                                                  |
//| - SL: fixed / beyond the opposite side of the range / x ATR      |
//| - TP: fixed / multiple of the SL distance (R)                    |
//| - Break-even and trailing in pips or in R                        |
//| - Hard time exit in the same timezone as the check time          |
//| - "Variable Values": every pip distance scales with a long ATR   |
//|   (or with price) so settings survive gold's price growth        |
//| - Lot size: fixed / % risk / money risk, from the real SL        |
//| - Filters: weekdays, NFP day, spread, daily loss limit,          |
//|   MQL5 calendar high-impact USD news (live only)                 |
//| - OnTester custom score: min trades / recovery factor / payoff   |
//|                                                                  |
//| Time exit, window expiry and OCO clean-up are derived from each  |
//| order's / position's own open time, so they keep working after  |
//| a restart and are retried until they succeed.                    |
//+------------------------------------------------------------------+
#property copyright "gold-oi-dashboard"
#property version   "1.12"
#property description "Range Breakout for XAUUSD: daily range before a session open, DST-aware check time, ATR range filter, pending or close-confirmed entries, ATR-scaled distances, risk-based lots."

#include <Trade/Trade.mqh>

//--- enums (the comment after each member is what MT5 shows in the Inputs tab)
enum ENUM_GRB_TZ
  {
   GRB_TZ_SERVER  = 0, // Broker server time
   GRB_TZ_NEWYORK = 1, // New York time (follows US DST)
   GRB_TZ_LONDON  = 2  // London time (follows EU DST)
  };

enum ENUM_GRB_BROKER_DST
  {
   GRB_BROKER_DST_US   = 0, // Broker switches with US DST (most GMT+2/+3 brokers)
   GRB_BROKER_DST_EU   = 1, // Broker switches with EU DST
   GRB_BROKER_DST_NONE = 2  // Broker never switches (always winter offset)
  };

enum ENUM_GRB_MEASURE
  {
   GRB_MEASURE_WICKS  = 0, // High/Low (wicks)
   GRB_MEASURE_BODIES = 1  // Open/Close (bodies)
  };

enum ENUM_GRB_ENTRY
  {
   GRB_ENTRY_PENDING = 0, // Pending buy stop / sell stop at the range edges
   GRB_ENTRY_CLOSE   = 1  // Market entry on a candle closing outside the range
  };

enum ENUM_GRB_SL
  {
   GRB_SL_FIXED    = 0, // Fixed distance (pips)
   GRB_SL_OPPOSITE = 1, // Beyond the opposite side of the range
   GRB_SL_ATR      = 2  // Multiple of the range ATR
  };

enum ENUM_GRB_TP
  {
   GRB_TP_FIXED = 0, // Fixed distance (pips)
   GRB_TP_RR    = 1, // Multiple of the SL distance (R)
   GRB_TP_NONE  = 2  // No take profit
  };

enum ENUM_GRB_UNITS
  {
   GRB_UNITS_PIPS = 0, // Pips (scaled by Variable Values)
   GRB_UNITS_R    = 1  // Multiples of the initial SL distance (R)
  };

enum ENUM_GRB_LOTS
  {
   GRB_LOTS_FIXED        = 0, // Manual (fixed) lot size
   GRB_LOTS_RISK_PERCENT = 1, // Risk per trade (% of balance/equity)
   GRB_LOTS_RISK_MONEY   = 2  // Risk per trade (account currency)
  };

//--- inputs
input group "=== General ==="
input ulong               InpMagic            = 26092701;          // Magic number (unique per chart/set)
input string              InpComment          = "GRB";             // Comment for trades
input bool                InpAllowBuy         = true;              // Allow buy trades
input bool                InpAllowSell        = true;              // Allow sell trades
input double              InpPipSize          = 0.0;               // Pip size in price (0 = auto: XAU/GOLD = 0.1)

input group "=== Check time / timezone ==="
input ENUM_GRB_TZ         InpTZ               = GRB_TZ_NEWYORK;    // Timezone for the check time
input int                 InpCheckHour        = 9;                 // Hour to check the range
input int                 InpCheckMinute      = 30;                // Minute to check the range
input int                 InpBrokerGMTWinter  = 2;                 // Broker GMT offset in winter (hours)
input int                 InpBrokerGMTSummer  = 3;                 // Broker GMT offset in summer (hours)
input ENUM_GRB_BROKER_DST InpBrokerDST        = GRB_BROKER_DST_US; // Broker DST schedule
input bool                InpAutoGMTLive      = true;              // Detect broker offset automatically (live only)

input group "=== Range determination ==="
input ENUM_TIMEFRAMES     InpRangeTF          = PERIOD_M15;        // Timeframe to monitor
input int                 InpRangeCandles     = 12;                // Candles measured before the check time
input ENUM_GRB_MEASURE    InpRangeMeasure     = GRB_MEASURE_WICKS; // How to measure the range
input int                 InpATRPeriod        = 14;                // ATR period (range height yardstick)
input ENUM_TIMEFRAMES     InpATRTF            = PERIOD_H1;         // ATR timeframe
input double              InpMaxRangeATR      = 1.5;               // Max range height (x ATR), 0 = off
input double              InpMaxRangePips     = 0;                 // Max range height (pips), 0 = off
input double              InpMinRangePips     = 0;                 // Min range height (pips), 0 = off

input group "=== Entry ==="
input ENUM_GRB_ENTRY      InpEntryMode        = GRB_ENTRY_PENDING; // How to enter the breakout
input double              InpBuyBufferPips    = 5;                 // Extra pips above range TOP for buy
input double              InpSellBufferPips   = 5;                 // Extra pips below range BOTTOM for sell
input bool                InpSpreadAdjust     = true;              // Add the spread to Ask-side levels (buy stop, sell SL)
input int                 InpEntryWindowMin   = 240;               // Entry window after check time (minutes), 0 = until close time / end of day
input bool                InpStopAtDailyBreak = true;              // Pending orders never live past 16:55 New York (daily break / weekend)
input bool                InpOCO              = true;              // Delete opposite side once one fills (OCO)
input double              InpMaxChasePips     = 10;                // Max pips to chase at market if the level was already crossed, 0 = never
input int                 InpMaxSpreadPoints  = 0;                 // Max spread to place/enter (points), 0 = off
input int                 InpSlippagePoints   = 30;                // Max slippage for market orders (points)

input group "=== Exit ==="
input ENUM_GRB_SL         InpSLMode           = GRB_SL_OPPOSITE;   // Initial SL placement
input double              InpSLPips           = 150;               // Fixed SL distance (pips)          [Fixed]
input double              InpSLBeyondPips     = 10;                // Pips beyond the opposite side     [Opposite side]
input double              InpSLATRMult        = 1.5;               // SL distance (x range ATR)         [ATR]
input double              InpMinSLPips        = 30;                // Minimum SL distance (pips), 0 = off
input double              InpMaxSLPips        = 0;                 // Skip the side if SL is wider than (pips), 0 = off
input ENUM_GRB_TP         InpTPMode           = GRB_TP_RR;         // Take profit mode
input double              InpTPPips           = 300;               // Fixed TP distance (pips)          [Fixed]
input double              InpTPRR             = 2.0;               // TP as a multiple of the SL distance [R]
input int                 InpCloseHour        = 15;                // Close trades at this hour (same timezone), -1 = never
input int                 InpCloseMinute      = 55;                // Close trades at this minute
input bool                InpCloseBeforeWeekend = true;            // A time exit that would fall on the weekend closes Friday 16:55 New York

input group "=== Break-even / trailing ==="
input ENUM_GRB_UNITS      InpMgmtUnits        = GRB_UNITS_R;       // Units for BE start / trailing values below
input double              InpBEStart          = 1.0;               // Break-even start (profit), 0 = off
input double              InpBEExtraPips      = 2;                 // Break-even extra (pips beyond entry)
input double              InpTrailStart       = 0;                 // Trailing start (profit), 0 = off
input double              InpTrailDistance    = 1.0;               // Trailing distance behind price
input double              InpTrailStep        = 0.1;               // Trailing step (minimum SL improvement)

input group "=== Variable Values (distance scaling) ==="
input double              InpVVDefaultATR     = 0;                 // Default ATR value (price units), 0 = off
input int                 InpVVATRPeriod      = 30;                // ATR period for scaling
input ENUM_TIMEFRAMES     InpVVATRTF          = PERIOD_D1;         // ATR timeframe for scaling
input double              InpVVDefaultPrice   = 0;                 // Default price for calculation, 0 = off (ATR wins if both set)

input group "=== Lot size ==="
input ENUM_GRB_LOTS       InpLotMode          = GRB_LOTS_FIXED;    // Lot size method
input double              InpFixedLots        = 0.1;               // Manual lot size
input bool                InpFixedLotsVV      = false;             // Adjust manual lot size to Variable Values
input double              InpRiskPercent      = 1.0;               // Risk per trade (%)
input double              InpRiskMoney        = 100;               // Risk per trade (account currency)
input bool                InpUseEquity        = false;             // Use equity instead of balance for % risk
input double              InpMaxLots          = 5.0;               // Maximum lot size per trade

input group "=== Filters ==="
input bool                InpTradeMonday      = true;              // Trade Monday
input bool                InpTradeTuesday     = true;              // Trade Tuesday
input bool                InpTradeWednesday   = true;              // Trade Wednesday
input bool                InpTradeThursday    = true;              // Trade Thursday
input bool                InpTradeFriday      = true;              // Trade Friday
input bool                InpSkipNFPDay       = true;              // Skip NFP release day (BLS schedule rule, NY date)
input bool                InpSkipUSHolidays   = true;              // Skip US holidays / early-close days (the time exit may get no tick)
input bool                InpNewsFilter       = false;             // High-impact USD news filter (MQL5 calendar, live only)
input int                 InpNewsMinBefore    = 60;                // News: minutes before the event
input int                 InpNewsMinAfter     = 60;                // News: minutes after the event
input double              InpMaxDailyLossPct  = 0;                 // Daily loss limit (% of day-start equity), 0 = off

input group "=== Custom optimization (OnTester) ==="
input int                 InpOptMinTrades     = 100;               // Minimum number of trades, 0 = off
input double              InpOptMinRF         = 0;                 // Minimum recovery factor, 0 = off
input double              InpOptMinEP         = 0;                 // Minimum expected payoff, 0 = off

input group "=== Visuals / logging ==="
input bool                InpShowPanel        = true;              // Show info panel
input bool                InpDrawBoxes        = true;              // Draw range boxes on chart
input color               InpColForming       = clrGold;           // Colour: range measured, waiting
input color               InpColUp            = clrLimeGreen;      // Colour: broken upward
input color               InpColDown          = clrTomato;         // Colour: broken downward
input color               InpColRejected      = clrSilver;         // Colour: range rejected
input bool                InpVerbose          = false;             // Detailed logging

//--- constants
#define GRB_LATE_SECONDS   (15 * 60)   // a setup is only built if the first tick comes within this after the check time
#define GRB_RETRY_SECONDS  5           // pause between retries of a failed close / delete
#define GRB_MAX_FAILS      3           // failed order attempts before a side is given up

enum ENUM_GRB_BUILD
  {
   GRB_BUILD_DONE  = 0,  // setup armed, or the day is definitively skipped
   GRB_BUILD_RETRY = 1   // transient problem (data / ATR not ready): try again on the next tick
  };

//--- state
struct GRBSide
  {
   bool              enabled;   // side allowed for today's setup
   bool              done;      // nothing more to do for this side
   bool              filled;    // this side became a position
   bool              signal;    // close-confirmed mode: breakout candle seen, market entry pending
   ulong             ticket;    // pending order ticket (0 = not placed)
   double            entry;     // trigger price (pending price / close threshold)
   int               fails;     // failed order attempts
  };

struct GRBSetup
  {
   bool              active;        // entries still possible
   datetime          localDay;      // local (timezone) date of the setup
   datetime          checkServer;   // check time, server clock
   datetime          windowEnd;     // end of entry window, server clock
   datetime          firstBar;      // open time of the first measured candle
   datetime          lastEval;      // close mode: open time of the last candle evaluated
   datetime          lastBar0;      // close mode: last seen forming candle
   double            top;
   double            bottom;
   double            atr;           // range ATR at check time
   double            spread;        // spread (price) used for the Ask-side adjustment
   GRBSide           buy;
   GRBSide           sell;
   string            status;        // short text for the panel
  };

CTrade    g_trade;
GRBSetup  g_s;
double    g_pip              = 0.0;
double    g_vv               = 1.0;
bool      g_vvReady          = false;
int       g_hATR             = INVALID_HANDLE;
int       g_hVVATR           = INVALID_HANDLE;
bool      g_optimizing       = false;
bool      g_tester           = false;
datetime  g_lastDay          = 0;     // last local day whose check time was processed
datetime  g_lastNewsCheck    = 0;
int       g_liveOffset       = 0;
bool      g_liveOffsetValid  = false;
datetime  g_lastOffsetCheck  = 0;
datetime  g_guardDay         = 0;
double    g_guardEquity      = 0.0;
bool      g_halted           = false;
datetime  g_lastPanel        = 0;
datetime  g_nextCleanupTry   = 0;
bool      g_noSpecifiedExpiry = false;
string    g_prefix           = "";    // chart objects
string    g_gv               = "";    // terminal global variables
datetime  g_killDay          = 0;     // setup day whose pending orders must all go (OCO / setup ended), persisted
bool      g_needRecover      = false; // rebuild the day's state on the first tick (fresh server time / history)

//+------------------------------------------------------------------+
//| Logging                                                          |
//+------------------------------------------------------------------+
void Log(const string msg, const bool important = false)
  {
   if(g_optimizing)
      return;
   if(important || InpVerbose)
      Print("[GRB ", _Symbol, " #", InpMagic, "] ", msg);
  }

//+------------------------------------------------------------------+
//| Terminal global variables (survive restarts)                     |
//+------------------------------------------------------------------+
void GVSet(const string key, const double value)
  {
   GlobalVariableSet(g_gv + key, value);
  }

double GVGet(const string key, const double fallback = 0.0)
  {
   double v;
   if(GlobalVariableGet(g_gv + key, v))
      return v;
   return fallback;
  }

// write state that must survive a crash straight to disk
void GVFlush()
  {
   if(!g_optimizing)
      GlobalVariablesFlush();
  }

//+------------------------------------------------------------------+
//| Calendar / DST helpers                                           |
//+------------------------------------------------------------------+
int DaysInMonth(const int year, const int month)
  {
   static const int days[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
   if(month == 2 && ((year % 4 == 0 && year % 100 != 0) || year % 400 == 0))
      return 29;
   return days[month - 1];
  }

datetime MakeDate(const int year, const int month, const int day)
  {
   MqlDateTime t;
   ZeroMemory(t);
   t.year = year;
   t.mon  = month;
   t.day  = day;
   return StructToTime(t);
  }

// n-th given weekday (0 = Sunday) of a month at 00:00 (n >= 1), or the last one when n == 0
datetime NthWeekday(const int year, const int month, const int weekday, const int n)
  {
   MqlDateTime f;
   TimeToStruct(MakeDate(year, month, 1), f);
   int day = 1 + (7 + weekday - f.day_of_week) % 7;
   if(n > 0)
      day += 7 * (n - 1);
   else
     {
      int dim = DaysInMonth(year, month);
      while(day + 7 <= dim)
         day += 7;
     }
   return MakeDate(year, month, day);
  }

datetime NthSunday(const int year, const int month, const int n)
  {
   return NthWeekday(year, month, 0, n);
  }

// US DST, evaluated in UTC. 2007+: 2nd Sun Mar 02:00 EST -> 1st Sun Nov 02:00 EDT.
// Before 2007: 1st Sun Apr -> last Sun Oct.
bool IsUSDST(const datetime utc)
  {
   MqlDateTime t;
   TimeToStruct(utc, t);
   datetime start, end;
   if(t.year >= 2007)
     {
      start = NthSunday(t.year, 3, 2)  + 7 * 3600;
      end   = NthSunday(t.year, 11, 1) + 6 * 3600;
     }
   else
     {
      start = NthSunday(t.year, 4, 1)  + 7 * 3600;
      end   = NthSunday(t.year, 10, 0) + 6 * 3600;
     }
   return (utc >= start && utc < end);
  }

// EU DST, evaluated in UTC: last Sun Mar 01:00 UTC -> last Sun Oct 01:00 UTC
bool IsEUDST(const datetime utc)
  {
   MqlDateTime t;
   TimeToStruct(utc, t);
   datetime start = NthSunday(t.year, 3, 0)  + 3600;
   datetime end   = NthSunday(t.year, 10, 0) + 3600;
   return (utc >= start && utc < end);
  }

int BrokerOffsetAtUTC(const datetime utc)
  {
   if(g_liveOffsetValid)
      return g_liveOffset;
   bool dst = false;
   if(InpBrokerDST == GRB_BROKER_DST_US)
      dst = IsUSDST(utc);
   else
      if(InpBrokerDST == GRB_BROKER_DST_EU)
         dst = IsEUDST(utc);
   return dst ? InpBrokerGMTSummer : InpBrokerGMTWinter;
  }

datetime ServerToUTC(const datetime server)
  {
   datetime guess = server - InpBrokerGMTWinter * 3600;
   return server - BrokerOffsetAtUTC(guess) * 3600;
  }

datetime UTCToServer(const datetime utc)
  {
   return utc + BrokerOffsetAtUTC(utc) * 3600;
  }

int NYOffsetAtUTC(const datetime utc)
  {
   return IsUSDST(utc) ? -4 : -5;
  }

datetime ServerToNY(const datetime server)
  {
   datetime utc = ServerToUTC(server);
   return utc + NYOffsetAtUTC(utc) * 3600;
  }

datetime NYToServer(const datetime ny)
  {
   datetime guess = ny + 5 * 3600;
   return UTCToServer(ny - NYOffsetAtUTC(guess) * 3600);
  }

int LocalOffsetAtUTC(const datetime utc)
  {
   if(InpTZ == GRB_TZ_NEWYORK)
      return NYOffsetAtUTC(utc);
   if(InpTZ == GRB_TZ_LONDON)
      return IsEUDST(utc) ? 1 : 0;
   return BrokerOffsetAtUTC(utc);
  }

int LocalStandardOffset()
  {
   if(InpTZ == GRB_TZ_NEWYORK)
      return -5;
   if(InpTZ == GRB_TZ_LONDON)
      return 0;
   return InpBrokerGMTWinter;
  }

datetime ServerToLocal(const datetime server)
  {
   if(InpTZ == GRB_TZ_SERVER)
      return server;
   datetime utc = ServerToUTC(server);
   return utc + LocalOffsetAtUTC(utc) * 3600;
  }

datetime LocalToServer(const datetime local)
  {
   if(InpTZ == GRB_TZ_SERVER)
      return local;
   datetime guess = local - LocalStandardOffset() * 3600;
   datetime utc   = local - LocalOffsetAtUTC(guess) * 3600;
   return UTCToServer(utc);
  }

datetime DayStart(const datetime t)
  {
   return t - (t % 86400);
  }

void UpdateLiveOffset()
  {
   if(g_tester || !InpAutoGMTLive)
      return;
   datetime now = TimeLocal();
   if(g_liveOffsetValid && now - g_lastOffsetCheck < 60)
      return;
   g_lastOffsetCheck = now;
   datetime gmt = TimeGMT();
   datetime srv = TimeTradeServer();
   if(gmt <= 0 || srv <= 0)
      return;
   int off = (int)MathRound((double)(srv - gmt) / 3600.0);
   if(off < -12 || off > 14)
      return;
   if(!g_liveOffsetValid || off != g_liveOffset)
      Log(StringFormat("Broker GMT offset detected: %+d", off), true);
   g_liveOffset      = off;
   g_liveOffsetValid = true;
  }

//+------------------------------------------------------------------+
//| Price / symbol helpers                                           |
//+------------------------------------------------------------------+
double DetectPip()
  {
   if(InpPipSize > 0)
      return InpPipSize;
   string name = _Symbol;
   StringToUpper(name);
   if(StringFind(name, "XAU") >= 0 || StringFind(name, "GOLD") >= 0)
      return 0.1;
   if(_Digits == 3 || _Digits == 5)
      return 10 * _Point;
   return _Point;
  }

double NormPrice(const double price)
  {
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0)
      tick = _Point;
   return NormalizeDouble(MathRound(price / tick) * tick, _Digits);
  }

double Pips(const double pips)
  {
   return pips * g_pip * g_vv;
  }

double StopsDistance()
  {
   long stops  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freeze = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   return (double)MathMax(stops, freeze) * _Point;
  }

bool SpreadOK()
  {
   if(InpMaxSpreadPoints <= 0)
      return true;
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   return spread <= InpMaxSpreadPoints;
  }

bool ReadATR(const int handle, double &value)
  {
   value = 0;
   if(handle == INVALID_HANDLE)
      return false;
   double buf[];
   if(CopyBuffer(handle, 0, 1, 1, buf) != 1)
      return false;
   value = buf[0];
   return value > 0;
  }

// Variable Values factor. g_vvReady stays false while the scaling ATR is not
// calculated yet, so callers can wait instead of trading unscaled distances.
void UpdateVV()
  {
   if(InpVVDefaultATR > 0)
     {
      double atr;
      if(ReadATR(g_hVVATR, atr))
        {
         g_vv      = atr / InpVVDefaultATR;
         g_vvReady = true;
        }
      else
         g_vvReady = false;
      return;
     }
   g_vv      = 1.0;
   g_vvReady = true;
   if(InpVVDefaultPrice > 0)
     {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(bid > 0)
         g_vv = bid / InpVVDefaultPrice;
      else
         g_vvReady = false;
     }
  }

//+------------------------------------------------------------------+
//| Ownership helpers                                                |
//+------------------------------------------------------------------+
bool SelectOurPosition(const int index, ulong &ticket)
  {
   ticket = PositionGetTicket(index);
   if(ticket == 0)
      return false;
   return PositionGetString(POSITION_SYMBOL) == _Symbol
          && (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic;
  }

bool SelectOurOrder(const int index, ulong &ticket)
  {
   ticket = OrderGetTicket(index);
   if(ticket == 0)
      return false;
   return OrderGetString(ORDER_SYMBOL) == _Symbol
          && (ulong)OrderGetInteger(ORDER_MAGIC) == InpMagic;
  }

int CountOurPositions()
  {
   int n = 0;
   ulong tk;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(SelectOurPosition(i, tk))
         n++;
   return n;
  }

// our buy stop / sell stop placed at or after `since` (0 if none)
ulong FindOurPending(const bool isBuy, const datetime since)
  {
   ulong tk;
   ENUM_ORDER_TYPE want = isBuy ? ORDER_TYPE_BUY_STOP : ORDER_TYPE_SELL_STOP;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurOrder(i, tk))
         continue;
      if((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == want && (datetime)OrderGetInteger(ORDER_TIME_SETUP) >= since)
         return tk;
     }
   return 0;
  }

//+------------------------------------------------------------------+
//| Range box drawing                                                |
//+------------------------------------------------------------------+
bool DrawingEnabled()
  {
   return InpDrawBoxes && !g_optimizing && !(g_tester && !MQLInfoInteger(MQL_VISUAL_MODE));
  }

string BoxName()
  {
   return g_prefix + "box_" + TimeToString(g_s.localDay, TIME_DATE);
  }

void DrawBox(const datetime t1, const datetime t2, const double top, const double bottom, const color col, const string text)
  {
   if(!DrawingEnabled())
      return;
   string name = BoxName();
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, top, t2, bottom);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_FILL, false);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_TIME, 0, t1);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 0, top);
   ObjectSetInteger(0, name, OBJPROP_TIME, 1, t2);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 1, bottom);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);

   string label = name + "_txt";
   if(ObjectFind(0, label) < 0)
     {
      ObjectCreate(0, label, OBJ_TEXT, 0, t1, top);
      ObjectSetInteger(0, label, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
      ObjectSetInteger(0, label, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, label, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, label, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, label, OBJPROP_TIME, 0, t1);
   ObjectSetDouble(0, label, OBJPROP_PRICE, 0, top);
   ObjectSetInteger(0, label, OBJPROP_COLOR, col);
   ObjectSetString(0, label, OBJPROP_TEXT, text);
  }

void RecolorBox(const color col)
  {
   if(!DrawingEnabled())
      return;
   string name = BoxName();
   if(ObjectFind(0, name) >= 0)
      ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   if(ObjectFind(0, name + "_txt") >= 0)
      ObjectSetInteger(0, name + "_txt", OBJPROP_COLOR, col);
  }

//+------------------------------------------------------------------+
//| Schedule helpers                                                 |
//+------------------------------------------------------------------+
int CheckSeconds()
  {
   return InpCheckHour * 3600 + InpCheckMinute * 60;
  }

datetime CheckServerFor(const datetime localDay)
  {
   return LocalToServer(localDay + CheckSeconds());
  }

void TodayCheck(const datetime now, datetime &localDay, datetime &checkServer)
  {
   datetime localNow = ServerToLocal(now);
   localDay    = DayStart(localNow);
   checkServer = CheckServerFor(localDay);
  }

// local day of the most recent check time at or before t: the setup an order / position belongs to
datetime SetupDayOf(const datetime serverTime)
  {
   datetime local = ServerToLocal(serverTime);
   datetime day   = DayStart(local);
   if(local - day < CheckSeconds())
      day -= 86400;
   return day;
  }

// next 16:55 New York after t (gold's daily break starts 17:00 NY; Friday's is the weekend close)
datetime NextNYBreak(const datetime serverTime)
  {
   datetime ny  = ServerToNY(serverTime);
   datetime brk = DayStart(ny) + 16 * 3600 + 55 * 60;
   if(brk <= ny)
      brk += 86400;
   return NYToServer(brk);
  }

// time exit for the setup of localDay, server clock (0 = none)
datetime CloseTimeFor(const datetime localDay)
  {
   if(InpCloseHour < 0)
      return 0;
   datetime checkLocal = localDay + CheckSeconds();
   datetime closeLocal = localDay + InpCloseHour * 3600 + InpCloseMinute * 60;
   if(closeLocal <= checkLocal)
      closeLocal += 86400;
   datetime closeServer = LocalToServer(closeLocal);
   if(InpCloseBeforeWeekend)
     {
      // a close on Saturday/Sunday (or after Friday's 17:00 NY close) is pulled back to Friday 16:55 NY
      datetime ny = ServerToNY(closeServer);
      MqlDateTime d;
      TimeToStruct(ny, d);
      int tod = (int)(ny - DayStart(ny));
      int back = -1;
      if(d.day_of_week == 5 && tod > 16 * 3600 + 55 * 60)
         back = 0;
      else
         if(d.day_of_week == 6)
            back = 1;
         else
            if(d.day_of_week == 0)
               back = 2;
      if(back >= 0)
        {
         datetime fri = DayStart(ny) - back * 86400 + 16 * 3600 + 55 * 60;
         closeServer = NYToServer(fri);
        }
     }
   return closeServer;
  }

datetime WindowEndFor(const datetime localDay)
  {
   datetime checkServer = CheckServerFor(localDay);
   datetime closeServer = CloseTimeFor(localDay);
   datetime end;
   if(InpEntryWindowMin > 0)
      end = checkServer + InpEntryWindowMin * 60;
   else
      end = (closeServer > 0) ? closeServer : LocalToServer(localDay + 86400);
   if(closeServer > 0 && end > closeServer)
      end = closeServer;
   if(InpStopAtDailyBreak)
     {
      datetime brk = NextNYBreak(checkServer);
      if(end > brk)
         end = brk;
     }
   return end;
  }

// NFP release date for a reference month (BLS rule: the third Friday after the
// week that contains the 12th). Exceptions: 4 July falls back to Thursday 3 July;
// December's report moves a week later when the rule lands on 1-3 January.
datetime NFPReleaseDate(const int year, const int month)
  {
   datetime d12 = MakeDate(year, month, 12);
   MqlDateTime s;
   TimeToStruct(d12, s);
   datetime saturday = d12 + (6 - s.day_of_week) * 86400;
   datetime release  = saturday + 20 * 86400;
   MqlDateTime r;
   TimeToStruct(release, r);
   if(r.mon == 7 && r.day == 4)
      release -= 86400;
   if(month == 12 && r.day <= 3)
      release += 7 * 86400;
   return release;
  }

bool IsNFPDay(const datetime nyDate)
  {
   MqlDateTime n;
   TimeToStruct(nyDate, n);
   int refYear  = (n.mon == 1) ? n.year - 1 : n.year;
   int refMonth = (n.mon == 1) ? 12 : n.mon - 1;
   return DayStart(nyDate) == NFPReleaseDate(refYear, refMonth);
  }

// Gregorian Easter Sunday (anonymous algorithm)
datetime EasterSunday(const int y)
  {
   int a = y % 19, b = y / 100, c = y % 100, d = b / 4, e = b % 4;
   int f = (b + 8) / 25, g = (b - f + 1) / 3;
   int h = (19 * a + b - d - g + 15) % 30;
   int i = c / 4, k = c % 4;
   int l = (32 + 2 * e + 2 * i - h - k) % 7;
   int m = (a + 11 * h + 22 * l) / 451;
   int month = (h + l - 7 * m + 114) / 31;
   int day   = ((h + l - 7 * m + 114) % 31) + 1;
   return MakeDate(y, month, day);
  }

// fixed-date holiday moved to Friday / Monday when it falls on a weekend
bool IsObserved(const datetime date, const int year, const int month, const int day)
  {
   datetime h = MakeDate(year, month, day);
   MqlDateTime t;
   TimeToStruct(h, t);
   if(t.day_of_week == 6)
      h -= 86400;
   else
      if(t.day_of_week == 0)
         h += 86400;
   return date == h;
  }

// US market holidays and the usual early-close days (NY date). Gold trades on most of
// them, but the session ends early, so the 15:55 NY time exit would get no tick.
bool IsUSHolidayOrEarlyClose(const datetime nyDate)
  {
   datetime d = DayStart(nyDate);
   MqlDateTime t;
   TimeToStruct(d, t);
   int y = t.year;
   if(IsObserved(d, y, 1, 1) || IsObserved(d, y + 1, 1, 1))                   // New Year (observed)
      return true;
   if(d == NthWeekday(y, 1, 1, 3) || d == NthWeekday(y, 2, 1, 3))             // MLK, Presidents' Day
      return true;
   if(d == EasterSunday(y) - 2 * 86400)                                        // Good Friday
      return true;
   if(d == NthWeekday(y, 5, 1, 0))                                             // Memorial Day
      return true;
   if(y >= 2022 && IsObserved(d, y, 6, 19))                                    // Juneteenth
      return true;
   if(IsObserved(d, y, 7, 4) || (t.mon == 7 && t.day == 3))                   // Independence Day + eve
      return true;
   if(d == NthWeekday(y, 9, 1, 1))                                             // Labor Day
      return true;
   datetime thanksgiving = NthWeekday(y, 11, 4, 4);
   if(d == thanksgiving || d == thanksgiving + 86400)                          // Thanksgiving + Friday after
      return true;
   if(IsObserved(d, y, 12, 25) || (t.mon == 12 && (t.day == 24 || t.day == 31))) // Christmas, eves
      return true;
   return false;
  }

bool DayAllowed(const datetime localDay, const datetime checkServer, string &why)
  {
   MqlDateTime d;
   TimeToStruct(localDay, d);
   bool ok = true;
   switch(d.day_of_week)
     {
      case 1:
         ok = InpTradeMonday;
         break;
      case 2:
         ok = InpTradeTuesday;
         break;
      case 3:
         ok = InpTradeWednesday;
         break;
      case 4:
         ok = InpTradeThursday;
         break;
      case 5:
         ok = InpTradeFriday;
         break;
      default:
         ok = false;
     }
   if(!ok)
     {
      why = "weekday disabled";
      return false;
     }
   if(InpSkipNFPDay && IsNFPDay(ServerToNY(checkServer)))
     {
      why = "NFP day";
      return false;
     }
   if(InpSkipUSHolidays && IsUSHolidayOrEarlyClose(ServerToNY(checkServer)))
     {
      why = "US holiday / early close";
      return false;
     }
   return true;
  }

// true if a high-impact USD event lies inside [from, to] (server clock). Live only.
bool HighImpactNews(const datetime from, const datetime to)
  {
   if(!InpNewsFilter || g_tester)
      return false;
   MqlCalendarValue values[];
   ResetLastError();
   CalendarValueHistory(values, from, to, NULL, "USD");
   int n = ArraySize(values);
   for(int i = 0; i < n; i++)
     {
      MqlCalendarEvent ev;
      if(CalendarEventById(values[i].event_id, ev) && ev.importance == CALENDAR_IMPORTANCE_HIGH)
        {
         Log(StringFormat("High-impact USD event at %s: %s", TimeToString(values[i].time, TIME_DATE | TIME_MINUTES), ev.name), true);
         return true;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Range measurement                                                |
//+------------------------------------------------------------------+
// Measures the InpRangeCandles candles that had CLOSED by the check time.
// transient = true when the failure may go away on a later tick.
bool MeasureRange(const datetime checkServer, double &top, double &bottom, datetime &firstBar, datetime &lastBar,
                  string &why, bool &transient)
  {
   transient = false;
   MqlRates r[];
   int want = InpRangeCandles;
   int tf   = PeriodSeconds(InpRangeTF);
   // a candle opening at or before (check - tf) has closed by the check time
   ResetLastError();
   int n = CopyRates(_Symbol, InpRangeTF, checkServer - tf, want, r);
   if(n < want)
     {
      why = StringFormat("only %d of %d candles available (error %d)", MathMax(n, 0), want, GetLastError());
      transient = true;
      return false;
     }
   // r[0] is the oldest, r[n-1] the newest (array is not a series)
   if(r[n - 1].time < checkServer - 2 * tf)
     {
      why = "no candle right before the check time (market closed?)";
      return false;
     }
   if(r[0].time < checkServer - (datetime)((2 * want + 1) * tf))
     {
      why = "measured candles span a market gap";
      return false;
     }
   top    = -DBL_MAX;
   bottom =  DBL_MAX;
   for(int i = 0; i < n; i++)
     {
      double hi = (InpRangeMeasure == GRB_MEASURE_WICKS) ? r[i].high : MathMax(r[i].open, r[i].close);
      double lo = (InpRangeMeasure == GRB_MEASURE_WICKS) ? r[i].low  : MathMin(r[i].open, r[i].close);
      top    = MathMax(top, hi);
      bottom = MathMin(bottom, lo);
     }
   firstBar = r[0].time;
   lastBar  = r[n - 1].time;
   if(top <= bottom)
     {
      why = "flat range";
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Stops and lot size                                               |
//+------------------------------------------------------------------+
bool ComputeStops(const bool isBuy, const double entry, double &sl, double &tp, double &slDist)
  {
   slDist = 0;
   switch(InpSLMode)
     {
      case GRB_SL_FIXED:
         slDist = Pips(InpSLPips);
         break;
      case GRB_SL_OPPOSITE:
        {
         // a sell's stop is hit by the Ask, so it sits a spread further above the top
         double level = isBuy ? g_s.bottom - Pips(InpSLBeyondPips) : g_s.top + Pips(InpSLBeyondPips) + g_s.spread;
         slDist = isBuy ? entry - level : level - entry;
         break;
        }
      case GRB_SL_ATR:
         slDist = InpSLATRMult * g_s.atr;
         break;
     }
   if(InpMinSLPips > 0)
      slDist = MathMax(slDist, Pips(InpMinSLPips));
   slDist = MathMax(slDist, StopsDistance() + 2 * _Point);
   if(InpMaxSLPips > 0 && slDist > Pips(InpMaxSLPips))
     {
      Log(StringFormat("%s skipped: SL %.1f pips > max %.1f", isBuy ? "Buy" : "Sell", slDist / g_pip, Pips(InpMaxSLPips) / g_pip), true);
      return false;
     }
   double tpDist = 0;
   if(InpTPMode == GRB_TP_FIXED)
      tpDist = Pips(InpTPPips);
   else
      if(InpTPMode == GRB_TP_RR)
         tpDist = slDist * InpTPRR;
   if(tpDist > 0)
      tpDist = MathMax(tpDist, StopsDistance() + 2 * _Point);
   sl = NormPrice(isBuy ? entry - slDist : entry + slDist);
   tp = (tpDist > 0) ? NormPrice(isBuy ? entry + tpDist : entry - tpDist) : 0.0;
   slDist = MathAbs(entry - sl);
   return slDist > 0;
  }

double NormalizeLots(double lots, const bool clampUpToMin)
  {
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0)
      step = 0.01;
   lots = MathFloor(lots / step + 1e-7) * step;
   if(lots < minLot)
     {
      if(!clampUpToMin)
         return 0.0;
      lots = minLot;
     }
   lots = MathMin(lots, maxLot);
   if(InpMaxLots > 0)
      lots = MathMin(lots, InpMaxLots);
   int digits = (int)MathMax(0, MathCeil(-MathLog10(step) - 1e-9));
   return NormalizeDouble(lots, digits);
  }

double CalcLots(const bool isBuy, const double entry, const double sl)
  {
   double lots = 0;
   if(InpLotMode == GRB_LOTS_FIXED)
     {
      lots = InpFixedLots;
      if(InpFixedLotsVV && g_vv > 0)
         lots /= g_vv;
      lots = NormalizeLots(lots, true);
     }
   else
     {
      double base = InpUseEquity ? AccountInfoDouble(ACCOUNT_EQUITY) : AccountInfoDouble(ACCOUNT_BALANCE);
      double risk = (InpLotMode == GRB_LOTS_RISK_PERCENT) ? base * InpRiskPercent / 100.0 : InpRiskMoney;
      double lossPerLot = 0;
      double profit = 0;
      ENUM_ORDER_TYPE type = isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      if(OrderCalcProfit(type, _Symbol, 1.0, entry, sl, profit) && profit < 0)
         lossPerLot = -profit;
      else
        {
         double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
         if(tickValue <= 0)
            tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
         double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
         if(tickSize > 0)
            lossPerLot = MathAbs(entry - sl) / tickSize * tickValue;
        }
      if(lossPerLot <= 0 || risk <= 0)
        {
         Log("Lot size: cannot compute loss per lot", true);
         return 0;
        }
      lots = NormalizeLots(risk / lossPerLot, false);
      if(lots <= 0)
        {
         Log(StringFormat("Lot size: risk %.2f is below the minimum lot for this SL", risk), true);
         return 0;
        }
     }
   // margin check
   double margin = 0;
   ENUM_ORDER_TYPE mtype = isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(OrderCalcMargin(mtype, _Symbol, lots, entry, margin) && margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
     {
      Log(StringFormat("Not enough free margin for %.2f lots (needs %.2f)", lots, margin), true);
      return 0;
     }
   return lots;
  }

//+------------------------------------------------------------------+
//| Initial risk (R) per position, kept in terminal global variables |
//+------------------------------------------------------------------+
// R and setup day of a position, keyed by its id (= ticket of the opening order)
void RegisterRisk(const ulong positionId, const double slDist)
  {
   if(positionId == 0)
      return;
   if(slDist > 0)
      GVSet("R_" + (string)positionId, slDist);
   if(g_s.localDay > 0)
      GVSet("D_" + (string)positionId, (double)g_s.localDay);
   GVFlush();
  }

// setup day an order / position belongs to: the recorded one, else derived from its time
datetime SetupDayFor(const ulong id, const datetime serverTime)
  {
   datetime d = (datetime)GVGet("D_" + (string)id, 0);
   return (d > 0) ? d : SetupDayOf(serverTime);
  }

double InitialRisk(const ulong positionId, const bool isBuy, const double openPrice, const double currentSL)
  {
   double risk = GVGet("R_" + (string)positionId, 0.0);
   if(risk > 0)
      return risk;
   // fall back to the SL of the order that opened the position
   if(HistorySelectByPosition(positionId))
     {
      datetime first = 0;
      for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
        {
         ulong o = HistoryOrderGetTicket(i);
         if(o == 0)
            continue;
         datetime t  = (datetime)HistoryOrderGetInteger(o, ORDER_TIME_SETUP);
         double   sl = HistoryOrderGetDouble(o, ORDER_SL);
         if(sl > 0 && (first == 0 || t < first))
           {
            first = t;
            risk  = MathAbs(openPrice - sl);
           }
        }
     }
   // last resort: the current stop, but only while it is still on the losing side
   if(risk <= 0 && currentSL > 0 && (isBuy ? currentSL < openPrice : currentSL > openPrice))
      risk = MathAbs(openPrice - currentSL);
   if(risk > 0)
      RegisterRisk(positionId, risk);
   return risk;
  }

// drop R records of positions that no longer exist
void CleanupRiskRecords()
  {
   string preR = g_gv + "R_", preD = g_gv + "D_";
   for(int i = GlobalVariablesTotal() - 1; i >= 0; i--)
     {
      string name = GlobalVariableName(i);
      string pre  = "";
      if(StringFind(name, preR) == 0)
         pre = preR;
      else
         if(StringFind(name, preD) == 0)
            pre = preD;
      if(pre == "")
         continue;
      ulong id = (ulong)StringToInteger(StringSubstr(name, StringLen(pre)));
      bool open = false;
      ulong tk;
      for(int p = PositionsTotal() - 1; p >= 0 && !open; p--)
         if(SelectOurPosition(p, tk) && (ulong)PositionGetInteger(POSITION_IDENTIFIER) == id)
            open = true;
      // a pending order's ticket becomes its position id: keep records of live pendings too
      for(int o = OrdersTotal() - 1; o >= 0 && !open; o--)
         if(OrderGetTicket(o) == id)
            open = true;
      if(!open)
         GlobalVariableDel(name);
     }
  }

//+------------------------------------------------------------------+
//| Order placement                                                  |
//+------------------------------------------------------------------+
bool RetcodeOK(const uint rc)
  {
   return rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL || rc == TRADE_RETCODE_PLACED;
  }

void GetSide(const bool isBuy, GRBSide &out)
  {
   if(isBuy)
      out = g_s.buy;
   else
      out = g_s.sell;
  }

// 1 = entered, 0 = postponed (spread too wide), -1 = failed
int MarketEntry(const bool isBuy, const string why)
  {
   if(!SpreadOK())
     {
      Log("Market entry postponed: spread too wide");
      return 0;
     }
   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl, tp, slDist;
   if(!ComputeStops(isBuy, price, sl, tp, slDist))
      return -1;
   double lots = CalcLots(isBuy, price, sl);
   if(lots <= 0)
      return -1;
   bool sent = isBuy ? g_trade.Buy(lots, _Symbol, price, sl, tp, InpComment)
                     : g_trade.Sell(lots, _Symbol, price, sl, tp, InpComment);
   uint rc = g_trade.ResultRetcode();
   if(!sent || !RetcodeOK(rc))
     {
      Log(StringFormat("%s market entry failed: %u %s", isBuy ? "Buy" : "Sell", rc, g_trade.ResultRetcodeDescription()), true);
      return -1;
     }
   RegisterRisk(g_trade.ResultOrder(), slDist);
   Log(StringFormat("%s %.2f lots at market %s (%s) SL %s TP %s", isBuy ? "BUY" : "SELL", lots,
                    DoubleToString(price, _Digits), why, DoubleToString(sl, _Digits), DoubleToString(tp, _Digits)), true);
   return 1;
  }

// 1 = placed (or adopted), 0 = try again later, -1 = failed
int PlacePending(const bool isBuy)
  {
   // an earlier request may have been placed although its reply was lost: adopt it instead of duplicating
   ulong existing = FindOurPending(isBuy, g_s.checkServer);
   if(existing > 0)
     {
      if(isBuy)
         g_s.buy.ticket = existing;
      else
         g_s.sell.ticket = existing;
      Log(StringFormat("Adopted existing %s stop %I64u", isBuy ? "buy" : "sell", existing), true);
      return 1;
     }
   GRBSide side;
   GetSide(isBuy, side);
   double sl, tp, slDist;
   if(!ComputeStops(isBuy, side.entry, sl, tp, slDist))
      return -1;
   double lots = CalcLots(isBuy, side.entry, sl);
   if(lots <= 0)
      return -1;
   // let the broker expire the order at the end of the window where possible (also works while the terminal is off)
   ENUM_ORDER_TYPE_TIME ttype = ORDER_TIME_GTC;
   datetime expiry = 0;
   long modes = SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
   if(!g_noSpecifiedExpiry && (modes & SYMBOL_EXPIRATION_SPECIFIED) != 0 && g_s.windowEnd > TimeCurrent() + 120)
     {
      ttype  = ORDER_TIME_SPECIFIED;
      expiry = g_s.windowEnd;
     }
   else
      if((modes & SYMBOL_EXPIRATION_GTC) == 0)
         ttype = ORDER_TIME_DAY;
   bool sent = isBuy ? g_trade.BuyStop(lots, side.entry, _Symbol, sl, tp, ttype, expiry, InpComment)
                     : g_trade.SellStop(lots, side.entry, _Symbol, sl, tp, ttype, expiry, InpComment);
   uint rc = g_trade.ResultRetcode();
   if(!sent || !RetcodeOK(rc))
     {
      Log(StringFormat("%s stop at %s failed: %u %s", isBuy ? "Buy" : "Sell", DoubleToString(side.entry, _Digits),
                       rc, g_trade.ResultRetcodeDescription()), true);
      if(rc == TRADE_RETCODE_INVALID_EXPIRATION && ttype == ORDER_TIME_SPECIFIED)
        {
         g_noSpecifiedExpiry = true;   // broker refuses specified expiry: fall back to GTC + EA-side expiry
         return 0;
        }
      if(rc == TRADE_RETCODE_TIMEOUT || rc == TRADE_RETCODE_CONNECTION || rc == 0)
         return 0;                     // outcome unknown: the next attempt adopts the order if it exists
      return -1;
     }
   ulong ticket = g_trade.ResultOrder();
   RegisterRisk(ticket, slDist);
   if(isBuy)
      g_s.buy.ticket = ticket;
   else
      g_s.sell.ticket = ticket;
   Log(StringFormat("%s STOP %.2f lots at %s SL %s TP %s (ticket %I64u)", isBuy ? "BUY" : "SELL", lots,
                    DoubleToString(side.entry, _Digits), DoubleToString(sl, _Digits), DoubleToString(tp, _Digits), ticket), true);
   return 1;
  }

//--- per-day state persisted for restarts: A_DAY / A_ACT / A_SIDES / A_VV / A_SPR / A_ATR, KILL
void SaveSides()
  {
   if(g_s.localDay == 0 || (datetime)GVGet("A_DAY", 0) != g_s.localDay)
      return;
   int mask = (g_s.buy.done ? 1 : 0) | (g_s.sell.done ? 2 : 0) | (g_s.buy.filled ? 4 : 0) | (g_s.sell.filled ? 8 : 0);
   GVSet("A_SIDES", mask);
   GVSet("A_ACT", g_s.active ? 1.0 : 0.0);
   GVFlush();
  }

// every pending order of this setup day must go (OCO fill / setup ended)
void KillDay(const datetime day)
  {
   if(day == 0 || day == g_killDay)
      return;
   g_killDay = day;
   GVSet("KILL", (double)day);
   GVFlush();
  }

void MarkFilled(const bool isBuy)
  {
   if(isBuy)
     {
      g_s.buy.filled = true;
      g_s.buy.done   = true;
      g_s.buy.signal = false;
      g_s.buy.ticket = 0;
     }
   else
     {
      g_s.sell.filled = true;
      g_s.sell.done   = true;
      g_s.sell.signal = false;
      g_s.sell.ticket = 0;
     }
   RecolorBox(isBuy ? InpColUp : InpColDown);
   g_s.status = isBuy ? "broken UP - long" : "broken DOWN - short";
   if(!InpOCO)
     {
      SaveSides();
      return;
     }
   // OCO: the opposite side is finished
   if(isBuy)
     {
      g_s.sell.done   = true;
      g_s.sell.signal = false;
     }
   else
     {
      g_s.buy.done   = true;
      g_s.buy.signal = false;
     }
   // delete the opposite stop in this same tick: on a spike bar the next tick may already fill it
   ulong other = isBuy ? g_s.sell.ticket : g_s.buy.ticket;
   if(other > 0 && OrderSelect(other))
     {
      if(g_trade.OrderDelete(other))
        {
         Log(StringFormat("OCO: deleted opposite pending %I64u", other), true);
         SideGone(!isBuy);
        }
      else
         Log(StringFormat("OCO: delete %I64u failed: %u %s - will retry", other, g_trade.ResultRetcode(),
                          g_trade.ResultRetcodeDescription()), true);
     }
   KillDay(g_s.localDay);   // Housekeeping() retries a failed delete and covers restarts
   SaveSides();
  }

void FailSide(const bool isBuy)
  {
   if(isBuy)
     {
      g_s.buy.fails++;
      g_s.buy.signal = false;
      if(g_s.buy.fails >= GRB_MAX_FAILS)
        {
         g_s.buy.done = true;
         SaveSides();
         Log("Buy side given up after repeated failures", true);
        }
     }
   else
     {
      g_s.sell.fails++;
      g_s.sell.signal = false;
      if(g_s.sell.fails >= GRB_MAX_FAILS)
        {
         g_s.sell.done = true;
         SaveSides();
         Log("Sell side given up after repeated failures", true);
        }
     }
  }

void SideGone(const bool isBuy)
  {
   if(isBuy)
     {
      g_s.buy.ticket = 0;
      g_s.buy.done   = true;
     }
   else
     {
      g_s.sell.ticket = 0;
      g_s.sell.done   = true;
     }
   SaveSides();
  }

// pending order still waiting / filled / gone
void CheckPendingStatus(const bool isBuy)
  {
   ulong ticket = isBuy ? g_s.buy.ticket : g_s.sell.ticket;
   if(ticket == 0)
      return;
   if(OrderSelect(ticket))
      return; // still pending
   bool filled = false;
   bool known  = false;
   if(HistoryOrderSelect(ticket))
     {
      ENUM_ORDER_STATE st = (ENUM_ORDER_STATE)HistoryOrderGetInteger(ticket, ORDER_STATE);
      filled = (st == ORDER_STATE_FILLED || st == ORDER_STATE_PARTIAL);
      known  = true;
     }
   if(!filled)
     {
      // history may lag behind: look for a position opened by this order
      ulong tk;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
         if(SelectOurPosition(i, tk) && (ulong)PositionGetInteger(POSITION_IDENTIFIER) == ticket)
            filled = true;
     }
   if(filled)
     {
      Log(StringFormat("%s stop %I64u filled", isBuy ? "Buy" : "Sell", ticket), true);
      MarkFilled(isBuy);
     }
   else
      if(known)
        {
         Log(StringFormat("%s stop %I64u gone (cancelled/expired/rejected)", isBuy ? "Buy" : "Sell", ticket), true);
         SideGone(isBuy);
        }
  }

// place a pending order, or enter at market if the level is already crossed
void ServicePendingSide(const bool isBuy)
  {
   GRBSide side;
   GetSide(isBuy, side);
   if(!side.enabled || side.done)
      return;
   if(side.ticket > 0)
     {
      CheckPendingStatus(isBuy);
      return;
     }
   if(!SpreadOK())
      return;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double minDist = StopsDistance() + _Point;
   bool crossed   = isBuy ? (ask >= side.entry) : (bid <= side.entry);
   bool farEnough = isBuy ? (side.entry - ask > minDist) : (bid - side.entry > minDist);

   if(crossed)
     {
      double beyond = isBuy ? ask - side.entry : side.entry - bid;
      if(InpMaxChasePips > 0 && beyond <= Pips(InpMaxChasePips))
        {
         int r = MarketEntry(isBuy, "level already crossed");
         if(r > 0)
            MarkFilled(isBuy);
         else
            if(r < 0)
               FailSide(isBuy);
        }
      else
        {
         Log(StringFormat("%s level %s already passed by %.1f pips - side skipped", isBuy ? "Buy" : "Sell",
                          DoubleToString(side.entry, _Digits), beyond / g_pip), true);
         SideGone(isBuy);
        }
      return;
     }
   if(!farEnough)
      return; // too close to place a stop order: wait for price to move away or cross
   int r = PlacePending(isBuy);
   if(r < 0)
      FailSide(isBuy);
  }

// close-confirmed entries: every candle that closed after the check time and within the window
void ServiceCloseEntries()
  {
   int tf = PeriodSeconds(InpRangeTF);
   datetime bar0 = iTime(_Symbol, InpRangeTF, 0);
   if(bar0 > 0 && bar0 != g_s.lastBar0)
     {
      // a signal only lives until the next candle closes
      g_s.buy.signal  = false;
      g_s.sell.signal = false;
      MqlRates r[];
      int n = CopyRates(_Symbol, InpRangeTF, 1, 64, r);   // closed candles, oldest first
      if(n > 0)
        {
         g_s.lastBar0 = bar0;
         for(int i = 0; i < n; i++)
           {
            datetime closeTime = r[i].time + tf;
            if(r[i].time <= g_s.lastEval || closeTime <= g_s.checkServer || closeTime > g_s.windowEnd)
               continue;
            g_s.lastEval = r[i].time;
            if(g_s.buy.enabled && !g_s.buy.done && r[i].close >= g_s.buy.entry)
              {
               g_s.buy.signal = true;
               break;
              }
            if(g_s.sell.enabled && !g_s.sell.done && r[i].close <= g_s.sell.entry)
              {
               g_s.sell.signal = true;
               break;
              }
           }
        }
     }
   // no fresh entry at/after the time exit: it would be flattened on the next tick
   datetime closeServer = CloseTimeFor(g_s.localDay);
   if(closeServer > 0 && TimeCurrent() >= closeServer)
     {
      g_s.buy.signal  = false;
      g_s.sell.signal = false;
      return;
     }
   if(g_s.buy.signal && !g_s.buy.done)
     {
      int res = MarketEntry(true, "candle closed above range");
      if(res > 0)
         MarkFilled(true);
      else
         if(res < 0)
            FailSide(true);
     }
   else
      if(g_s.sell.signal && !g_s.sell.done)
        {
         int res = MarketEntry(false, "candle closed below range");
         if(res > 0)
            MarkFilled(false);
         else
            if(res < 0)
               FailSide(false);
        }
  }

//+------------------------------------------------------------------+
//| Daily setup                                                      |
//+------------------------------------------------------------------+
void ResetSide(GRBSide &side)
  {
   side.enabled = false;
   side.done    = true;
   side.filled  = false;
   side.signal  = false;
   side.ticket  = 0;
   side.entry   = 0.0;
   side.fails   = 0;
  }

void ResetSetup()
  {
   g_s.active       = false;
   g_s.localDay     = 0;
   g_s.checkServer  = 0;
   g_s.windowEnd    = 0;
   g_s.firstBar     = 0;
   g_s.lastEval     = 0;
   g_s.lastBar0     = 0;
   g_s.top          = 0.0;
   g_s.bottom       = 0.0;
   g_s.atr          = 0.0;
   g_s.spread       = 0.0;
   ResetSide(g_s.buy);
   ResetSide(g_s.sell);
   g_s.status       = "waiting for check time";
  }

// the setup takes no more entries: a restart must not resume it
void Deactivate()
  {
   g_s.active = false;
   SaveSides();
  }

void EndSetup(const string why)
  {
   if(!g_s.active)
      return;
   // record fills that happened since the last tick before giving up the orders
   CheckPendingStatus(true);
   CheckPendingStatus(false);
   Deactivate();
   KillDay(g_s.localDay);
   if(!g_s.buy.filled && !g_s.sell.filled)
      g_s.status = "no trade (" + why + ")";
   Log("Setup ended: " + why);
  }

// arm today's setup (entries, sides, box). resumed = rebuilt after a restart.
void ArmSetup(const datetime localDay, const double top, const double bottom, const datetime firstBar,
              const datetime lastBar, const double atr, const bool resumed)
  {
   g_s.localDay     = localDay;
   g_s.checkServer  = CheckServerFor(localDay);
   g_s.windowEnd    = WindowEndFor(localDay);
   g_s.top          = top;
   g_s.bottom       = bottom;
   g_s.firstBar     = firstBar;
   g_s.lastEval     = lastBar;
   g_s.atr          = atr;
   g_s.spread       = 0.0;
   if(InpSpreadAdjust)
      g_s.spread = MathMax(0.0, SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID));
   g_s.buy.enabled  = InpAllowBuy;
   g_s.sell.enabled = InpAllowSell;
   g_s.buy.done     = !InpAllowBuy;
   g_s.sell.done    = !InpAllowSell;
   // pending buy stops trigger on the Ask, candle closes are Bid prices
   double askAdj    = (InpEntryMode == GRB_ENTRY_PENDING) ? g_s.spread : 0.0;
   g_s.buy.entry    = NormPrice(top + Pips(InpBuyBufferPips) + askAdj);
   g_s.sell.entry   = NormPrice(bottom - Pips(InpSellBufferPips));
   g_s.active       = true;
   g_s.status       = resumed ? "resumed after restart" : "range armed";
   if(!resumed)
     {
      GVSet("A_DAY", (double)localDay);
      GVSet("A_VV", g_vv);
      GVSet("A_SPR", g_s.spread);
      GVSet("A_ATR", atr);
      SaveSides();   // also sets A_ACT = 1 and flushes
     }
   string info = StringFormat("%s  %.1f pips  %.2f ATR", TimeToString(localDay, TIME_DATE), (top - bottom) / g_pip,
                              atr > 0 ? (top - bottom) / atr : 0.0);
   DrawBox(firstBar, g_s.windowEnd, top, bottom, InpColForming, info);
  }

ENUM_GRB_BUILD BuildSetup(const datetime localDay, const datetime checkServer)
  {
   EndSetup("new day");
   ResetSetup();
   g_s.localDay    = localDay;
   g_s.checkServer = checkServer;
   string day = TimeToString(localDay, TIME_DATE);

   if(g_halted)
     {
      g_s.status = "halted (daily loss limit)";
      return GRB_BUILD_DONE;
     }
   string why = "";
   if(!DayAllowed(localDay, checkServer, why))
     {
      g_s.status = "skipped: " + why;
      Log(day + " skipped: " + why);
      return GRB_BUILD_DONE;
     }
   if(HighImpactNews(checkServer - InpNewsMinBefore * 60, checkServer + InpNewsMinAfter * 60))
     {
      g_s.status = "skipped: high-impact news";
      return GRB_BUILD_DONE;
     }

   UpdateVV();
   if(!g_vvReady)
     {
      g_s.status = "waiting: Variable Values ATR not ready";
      Log(day + " Variable Values ATR not ready, retrying");
      return GRB_BUILD_RETRY;
     }
   double top, bottom;
   datetime firstBar, lastBar;
   bool transient;
   if(!MeasureRange(checkServer, top, bottom, firstBar, lastBar, why, transient))
     {
      g_s.status = "no range: " + why;
      Log(day + " no range: " + why, !transient);
      return transient ? GRB_BUILD_RETRY : GRB_BUILD_DONE;
     }
   double atr = 0;
   if(!ReadATR(g_hATR, atr))
     {
      g_s.status = "waiting: ATR not ready";
      Log(day + " ATR not ready, retrying");
      return GRB_BUILD_RETRY;
     }

   double height = top - bottom;
   string reject = "";
   if(InpMaxRangeATR > 0 && height > InpMaxRangeATR * atr)
      reject = StringFormat("height %.2f ATR > max %.2f", height / atr, InpMaxRangeATR);
   else
      if(InpMaxRangePips > 0 && height > Pips(InpMaxRangePips))
         reject = StringFormat("height %.1f pips > max %.1f", height / g_pip, Pips(InpMaxRangePips) / g_pip);
      else
         if(InpMinRangePips > 0 && height < Pips(InpMinRangePips))
            reject = StringFormat("height %.1f pips < min %.1f", height / g_pip, Pips(InpMinRangePips) / g_pip);
   if(reject != "")
     {
      g_s.top    = top;
      g_s.bottom = bottom;
      g_s.status = "range rejected: " + reject;
      DrawBox(firstBar, checkServer, top, bottom, InpColRejected,
              StringFormat("%s  %.1f pips  %.2f ATR  rejected", day, height / g_pip, height / atr));
      Log(day + " range rejected: " + reject, true);
      return GRB_BUILD_DONE;
     }

   ArmSetup(localDay, top, bottom, firstBar, lastBar, atr, false);
   Log(StringFormat("%s range %s - %s (%.1f pips, %.2f ATR), buy >= %s, sell <= %s, window until %s, VV factor %.3f", day,
                    DoubleToString(bottom, _Digits), DoubleToString(top, _Digits), height / g_pip, height / atr,
                    DoubleToString(g_s.buy.entry, _Digits), DoubleToString(g_s.sell.entry, _Digits),
                    TimeToString(g_s.windowEnd, TIME_DATE | TIME_MINUTES), g_vv), true);
   return GRB_BUILD_DONE;
  }

void ServiceSetup(const datetime now)
  {
   if(!g_s.active)
      return;
   if(InpNewsFilter && !g_tester && now - g_lastNewsCheck >= 60)
     {
      g_lastNewsCheck = now;
      if(HighImpactNews(now, now + InpNewsMinBefore * 60))
        {
         EndSetup("high-impact news ahead");
         return;
        }
     }
   if(InpEntryMode == GRB_ENTRY_PENDING)
     {
      if(now >= g_s.windowEnd)
        {
         EndSetup("entry window over");
         return;
        }
      ServicePendingSide(true);
      ServicePendingSide(false);
     }
   else
     {
      // candles that closed up to the window end are still evaluated
      ServiceCloseEntries();
      if(now >= g_s.windowEnd && !g_s.buy.signal && !g_s.sell.signal)
        {
         EndSetup("entry window over");
         return;
        }
      if(now >= g_s.windowEnd + PeriodSeconds(InpRangeTF))
        {
         EndSetup("entry window over");
         return;
        }
     }
   if(g_s.buy.done && g_s.sell.done && g_s.active)
     {
      Deactivate();
      if(!g_s.buy.filled && !g_s.sell.filled)
         g_s.status = "no trade (both sides finished)";
     }
  }

//+------------------------------------------------------------------+
//| Housekeeping: window expiry, OCO, time exit, loss halt           |
//| Derived from each order's / position's own time, retried until   |
//| it succeeds, and independent of in-memory state (restart-safe).  |
//+------------------------------------------------------------------+
void Housekeeping(const datetime now)
  {
   if(now < g_nextCleanupTry)
      return;
   bool failed = false;
   ulong tk;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurOrder(i, tk))
         continue;
      ENUM_ORDER_TYPE type = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(type != ORDER_TYPE_BUY_STOP && type != ORDER_TYPE_SELL_STOP)
         continue;
      datetime day = SetupDayFor(tk, (datetime)OrderGetInteger(ORDER_TIME_SETUP));
      string why = "";
      if(g_halted)
         why = "daily loss limit";
      else
         if(now >= WindowEndFor(day))
            why = "entry window over";
         else
            if(day == g_killDay)
               why = "OCO / setup finished";
      if(why == "")
         continue;
      if(g_trade.OrderDelete(tk))
        {
         Log(StringFormat("Deleted pending %I64u (%s)", tk, why), true);
         if(tk == g_s.buy.ticket)
            SideGone(true);
         if(tk == g_s.sell.ticket)
            SideGone(false);
        }
      else
        {
         failed = true;
         Log(StringFormat("Delete pending %I64u failed (%s): %u %s - will retry", tk, why,
                          g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()), true);
        }
     }

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurPosition(i, tk))
         continue;
      string why = "";
      if(g_halted)
         why = "daily loss limit";
      else
        {
         ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
         datetime closeServer = CloseTimeFor(SetupDayFor(id, (datetime)PositionGetInteger(POSITION_TIME)));
         if(closeServer > 0 && now >= closeServer)
            why = "close time";
        }
      if(why == "")
         continue;
      if(g_trade.PositionClose(tk, InpSlippagePoints))
         Log(StringFormat("Closed position %I64u (%s)", tk, why), true);
      else
        {
         failed = true;
         Log(StringFormat("Close position %I64u failed (%s): %u %s - will retry", tk, why,
                          g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()), true);
        }
     }
   g_nextCleanupTry = failed ? now + GRB_RETRY_SECONDS : 0;
  }

//+------------------------------------------------------------------+
//| Position management                                              |
//+------------------------------------------------------------------+
double MgmtDistance(const double value, const double risk)
  {
   if(value <= 0)
      return 0;
   if(InpMgmtUnits == GRB_UNITS_R)
      return (risk > 0) ? value * risk : 0;
   return Pips(value);
  }

void ManagePositions()
  {
   if(InpBEStart <= 0 && InpTrailStart <= 0)
      return;
   if(InpMgmtUnits == GRB_UNITS_PIPS && !g_vvReady)
      return; // pip distances would not be scaled yet
   double minDist = StopsDistance() + _Point;
   ulong tk;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurPosition(i, tk))
         continue;
      bool   isBuy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
      double open  = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double tp    = PositionGetDouble(POSITION_TP);
      ulong  id    = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double profit = isBuy ? price - open : open - price;
      double risk  = (InpMgmtUnits == GRB_UNITS_R) ? InitialRisk(id, isBuy, open, sl) : 0.0;
      double newSL = sl;

      double beStart = MgmtDistance(InpBEStart, risk);
      if(beStart > 0 && profit >= beStart)
        {
         double be = NormPrice(isBuy ? open + Pips(InpBEExtraPips) : open - Pips(InpBEExtraPips));
         if(isBuy ? (newSL == 0 || be > newSL) : (newSL == 0 || be < newSL))
            newSL = be;
        }

      double trStart = MgmtDistance(InpTrailStart, risk);
      double trDist  = MgmtDistance(InpTrailDistance, risk);
      double trStep  = MgmtDistance(InpTrailStep, risk);
      if(trStart > 0 && trDist > 0 && profit >= trStart)
        {
         double cand = NormPrice(isBuy ? price - trDist : price + trDist);
         bool better = isBuy ? (newSL == 0 || cand >= newSL + trStep) : (newSL == 0 || cand <= newSL - trStep);
         if(better)
            newSL = isBuy ? MathMax(newSL, cand) : (newSL == 0 ? cand : MathMin(newSL, cand));
        }

      if(newSL == sl)
         continue;
      // respect stops/freeze level and never move the stop the wrong way
      if(isBuy && (price - newSL < minDist || (sl > 0 && newSL <= sl)))
         continue;
      if(!isBuy && (newSL - price < minDist || (sl > 0 && newSL >= sl)))
         continue;
      if(g_trade.PositionModify(tk, newSL, tp))
         Log(StringFormat("Position %I64u SL %s -> %s", tk, DoubleToString(sl, _Digits), DoubleToString(newSL, _Digits)));
      else
         Log(StringFormat("Modify %I64u failed: %u %s", tk, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()));
     }
  }

//+------------------------------------------------------------------+
//| Daily loss guard (state kept in terminal global variables)       |
//+------------------------------------------------------------------+
void SaveGuard()
  {
   GVSet("GUARD_DAY", (double)g_guardDay);
   GVSet("GUARD_EQ", g_guardEquity);
   GVSet("GUARD_HALT", g_halted ? 1.0 : 0.0);
   GVFlush();
  }

void LoadGuard(const datetime now)
  {
   datetime day = DayStart(now);
   if((datetime)GVGet("GUARD_DAY", 0) == day && GVGet("GUARD_EQ", 0) > 0)
     {
      g_guardDay    = day;
      g_guardEquity = GVGet("GUARD_EQ", 0);
      g_halted      = GVGet("GUARD_HALT", 0) > 0.5;
      return;
     }
   g_guardDay    = day;
   g_guardEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_halted      = false;
   SaveGuard();
  }

void DailyGuard(const datetime now)
  {
   datetime day = DayStart(now);
   if(day != g_guardDay)
     {
      if(g_halted)
         Log("Daily loss limit reset for the new day", true);
      g_guardDay    = day;
      g_guardEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_halted      = false;
      SaveGuard();
      CleanupRiskRecords();
     }
   if(InpMaxDailyLossPct <= 0 || g_halted || g_guardEquity <= 0)
      return;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= g_guardEquity * (1.0 - InpMaxDailyLossPct / 100.0))
     {
      g_halted = true;
      SaveGuard();
      Log(StringFormat("Daily loss limit hit: equity %.2f vs day start %.2f - closing and pausing until tomorrow", equity, g_guardEquity), true);
      EndSetup("daily loss limit");
      g_s.status = "halted (daily loss limit)";
      g_nextCleanupTry = 0;   // Housekeeping() flattens now and keeps retrying while halted
     }
  }

//+------------------------------------------------------------------+
//| Info panel                                                       |
//+------------------------------------------------------------------+
string TZName()
  {
   if(InpTZ == GRB_TZ_NEWYORK)
      return "New York";
   if(InpTZ == GRB_TZ_LONDON)
      return "London";
   return "Server";
  }

void UpdatePanel(const datetime now)
  {
   if(!InpShowPanel || g_optimizing || (g_tester && !MQLInfoInteger(MQL_VISUAL_MODE)))
      return;
   if(now == g_lastPanel)
      return;
   g_lastPanel = now;
   datetime localDay, checkServer;
   TodayCheck(now, localDay, checkServer);
   string s = "Gold Range Breakout v1.12  |  " + _Symbol + "  magic " + (string)InpMagic + "\n";
   s += StringFormat("%s time %s  |  server %s\n", TZName(), TimeToString(ServerToLocal(now), TIME_MINUTES),
                     TimeToString(now, TIME_MINUTES));
   s += StringFormat("Check %02d:%02d %s = %s server  |  pip %s  |  VV x%.3f%s\n", InpCheckHour, InpCheckMinute, TZName(),
                     TimeToString(checkServer, TIME_MINUTES), DoubleToString(g_pip, _Digits), g_vv, g_vvReady ? "" : " (waiting)");
   if(g_s.top > 0)
      s += StringFormat("Range %s - %s  (%.1f pips)\n", DoubleToString(g_s.bottom, _Digits), DoubleToString(g_s.top, _Digits),
                        (g_s.top - g_s.bottom) / g_pip);
   if(g_s.active)
      s += StringFormat("Buy >= %s   Sell <= %s   until %s\n", DoubleToString(g_s.buy.entry, _Digits),
                        DoubleToString(g_s.sell.entry, _Digits), TimeToString(g_s.windowEnd, TIME_MINUTES));
   s += "Status: " + g_s.status + "\n";
   int n = CountOurPositions();
   s += StringFormat("Open positions: %d", n);
   if(n > 0 && InpCloseHour >= 0)
      s += "  |  time exit " + TimeToString(CloseTimeFor(SetupDayOf(now)), TIME_DATE | TIME_MINUTES);
   if(InpMaxDailyLossPct > 0)
      s += StringFormat("\nDaily loss guard: %.1f%% of %.2f%s", InpMaxDailyLossPct, g_guardEquity, g_halted ? "  HALTED" : "");
   Comment(s);
  }

//+------------------------------------------------------------------+
//| Restart recovery                                                 |
//+------------------------------------------------------------------+
// Runs on the first tick after (re)initialisation, when server time and
// trade history are fresh. A setup that was still active before a restart /
// timeframe change / input edit is rebuilt from the chart (the range is
// deterministic), the saved VV factor / spread / ATR / side flags, today's
// deals and open positions, and the live pending orders. Otherwise the EA
// never opens a fresh setup after the check time has passed.
// Returns false when the chart history is not ready yet (try again next tick).
bool RecoverState(const datetime now)
  {
   datetime localDay, checkServer;
   TodayCheck(now, localDay, checkServer);
   if(now >= checkServer)
      g_lastDay = localDay;              // today's check time is behind us: no late fresh setup

   datetime day = SetupDayOf(now);        // the setup whose window could still be open
   if((datetime)GVGet("A_DAY", 0) != day || GVGet("A_ACT", 0) < 0.5 || now >= WindowEndFor(day))
     {
      if(now >= checkServer)
         g_s.status = "started after check time - next setup tomorrow";
      return true;
     }

   datetime check = CheckServerFor(day);
   double top, bottom;
   datetime firstBar, lastBar;
   string why;
   bool transient;
   if(!MeasureRange(check, top, bottom, firstBar, lastBar, why, transient))
     {
      if(transient)
        {
         g_s.status = "resuming: waiting for chart history";
         return false;
        }
      Log("Could not rebuild today's range after restart: " + why, true);
      return true;
     }
   double atr = GVGet("A_ATR", 0.0);
   if(atr <= 0 && !ReadATR(g_hATR, atr))
     {
      g_s.status = "resuming: waiting for ATR";
      return false;
     }
   g_vv      = GVGet("A_VV", 1.0);
   g_vvReady = true;

   ResetSetup();
   ArmSetup(day, top, bottom, firstBar, lastBar, atr, true);
   double savedSpread = GVGet("A_SPR", -1.0);
   if(InpSpreadAdjust && savedSpread >= 0)
     {
      g_s.spread    = savedSpread;
      g_s.buy.entry = NormPrice(top + Pips(InpBuyBufferPips) + ((InpEntryMode == GRB_ENTRY_PENDING) ? savedSpread : 0.0));
     }

   // side flags saved by the running EA (finished / filled)
   int mask = (int)GVGet("A_SIDES", 0);
   if((mask & 1) != 0)
      g_s.buy.done = true;
   if((mask & 2) != 0)
      g_s.sell.done = true;
   if((mask & 4) != 0)
      MarkFilled(true);
   if((mask & 8) != 0)
      MarkFilled(false);

   // fills that happened while the EA was not running: entry deals since the check time ...
   if(HistorySelect(check, now + 86400))
     {
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
        {
         ulong d = HistoryDealGetTicket(i);
         if(d == 0 || HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol || (ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic)
            continue;
         ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(d, DEAL_ENTRY);
         ulong order = (ulong)HistoryDealGetInteger(d, DEAL_ORDER);
         ENUM_ORDER_TYPE otype = (ENUM_ORDER_TYPE)HistoryOrderGetInteger(order, ORDER_TYPE);
         // a stop order fill is an entry even when it nets against a position (netting accounts)
         bool isEntry = (entry == DEAL_ENTRY_IN) || otype == ORDER_TYPE_BUY_STOP || otype == ORDER_TYPE_SELL_STOP;
         if(!isEntry)
            continue;
         ENUM_DEAL_TYPE dt = (ENUM_DEAL_TYPE)HistoryDealGetInteger(d, DEAL_TYPE);
         if(dt == DEAL_TYPE_BUY && !g_s.buy.filled)
            MarkFilled(true);
         if(dt == DEAL_TYPE_SELL && !g_s.sell.filled)
            MarkFilled(false);
        }
     }
   // ... and our positions opened since the check time (in case history is still loading)
   ulong tk;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurPosition(i, tk) || (datetime)PositionGetInteger(POSITION_TIME) < check)
         continue;
      bool isBuy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
      if(isBuy && !g_s.buy.filled)
         MarkFilled(true);
      if(!isBuy && !g_s.sell.filled)
         MarkFilled(false);
     }
   // re-attach to today's pending orders
   if(!g_s.buy.done)
     {
      g_s.buy.ticket = FindOurPending(true, check);
      if(g_s.buy.ticket > 0 && OrderSelect(g_s.buy.ticket))
         g_s.buy.entry = OrderGetDouble(ORDER_PRICE_OPEN);
     }
   if(!g_s.sell.done)
     {
      g_s.sell.ticket = FindOurPending(false, check);
      if(g_s.sell.ticket > 0 && OrderSelect(g_s.sell.ticket))
         g_s.sell.entry = OrderGetDouble(ORDER_PRICE_OPEN);
     }
   // close mode: candles that closed while the EA was off are not traded late
   int tf = PeriodSeconds(InpRangeTF);
   g_s.lastBar0 = 0;
   g_s.lastEval = MathMax(lastBar, (datetime)((now - now % tf) - tf));
   if(g_s.buy.done && g_s.sell.done)
      Deactivate();
   else
      SaveSides();
   Log(StringFormat("Resumed today's setup: range %s - %s, buy %s (stop %I64u), sell %s (stop %I64u)",
                    DoubleToString(bottom, _Digits), DoubleToString(top, _Digits),
                    g_s.buy.filled ? "filled" : (g_s.buy.done ? "done" : "open"), g_s.buy.ticket,
                    g_s.sell.filled ? "filled" : (g_s.sell.done ? "done" : "open"), g_s.sell.ticket), true);
   return true;
  }

//+------------------------------------------------------------------+
//| Expert events                                                    |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpCheckHour < 0 || InpCheckHour > 23 || InpCheckMinute < 0 || InpCheckMinute > 59
      || InpCloseHour < -1 || InpCloseHour > 23 || InpCloseMinute < 0 || InpCloseMinute > 59
      || InpRangeCandles < 1 || InpATRPeriod < 1 || InpVVATRPeriod < 1 || InpEntryWindowMin < 0
      || InpFixedLots <= 0 || InpRiskPercent < 0 || InpRiskMoney < 0 || InpTPRR < 0
      || InpBrokerGMTWinter < -12 || InpBrokerGMTWinter > 14 || InpBrokerGMTSummer < -12 || InpBrokerGMTSummer > 14)
     {
      Print("GoldRangeBreakout: invalid input parameters");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(!InpAllowBuy && !InpAllowSell)
     {
      Print("GoldRangeBreakout: both buy and sell are disabled");
      return INIT_PARAMETERS_INCORRECT;
     }

   g_tester     = (bool)MQLInfoInteger(MQL_TESTER);
   g_optimizing = (bool)MQLInfoInteger(MQL_OPTIMIZATION);
   g_pip        = DetectPip();
   g_prefix     = StringFormat("GRB_%I64u_", InpMagic);
   g_gv         = StringFormat("GRB_%I64u_%I64d_%s_", InpMagic, AccountInfoInteger(ACCOUNT_LOGIN), _Symbol);

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.SetMarginMode();
   g_trade.LogLevel(InpVerbose ? LOG_LEVEL_ALL : LOG_LEVEL_ERRORS);

   g_hATR = iATR(_Symbol, InpATRTF, InpATRPeriod);
   if(g_hATR == INVALID_HANDLE)
     {
      Print("GoldRangeBreakout: cannot create ATR handle, error ", GetLastError());
      return INIT_FAILED;
     }
   g_hVVATR = INVALID_HANDLE;
   if(InpVVDefaultATR > 0)
     {
      g_hVVATR = iATR(_Symbol, InpVVATRTF, InpVVATRPeriod);
      if(g_hVVATR == INVALID_HANDLE)
        {
         Print("GoldRangeBreakout: cannot create Variable Values ATR handle, error ", GetLastError());
         return INIT_FAILED;
        }
     }

   // globals keep their values across a timeframe change / input edit, so reset everything explicitly
   ResetSetup();
   g_lastDay          = 0;
   g_lastPanel        = 0;
   g_lastNewsCheck    = 0;
   g_nextCleanupTry   = 0;
   g_noSpecifiedExpiry = false;
   g_liveOffsetValid  = false;
   g_killDay          = (datetime)GVGet("KILL", 0);
   g_needRecover      = true;   // state is rebuilt on the first tick (server time / history are fresh then)
   UpdateLiveOffset();
   datetime now = TimeCurrent();
   UpdateVV();

   Log(StringFormat("Started: pip %s, check %02d:%02d %s, range %d x %s, %s entries", DoubleToString(g_pip, _Digits),
                    InpCheckHour, InpCheckMinute, TZName(), InpRangeCandles, EnumToString(InpRangeTF),
                    InpEntryMode == GRB_ENTRY_PENDING ? "pending" : "close-confirmed"), true);
   UpdatePanel(now);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(g_hATR != INVALID_HANDLE)
      IndicatorRelease(g_hATR);
   if(g_hVVATR != INVALID_HANDLE)
      IndicatorRelease(g_hVVATR);
   g_hATR   = INVALID_HANDLE;
   g_hVVATR = INVALID_HANDLE;
   if(!g_optimizing)
      Comment("");
   if(reason == REASON_REMOVE || reason == REASON_PROGRAM)
      ObjectsDeleteAll(0, g_prefix);
  }

void OnTick()
  {
   datetime now = TimeCurrent();
   UpdateLiveOffset();
   if(g_needRecover)
     {
      LoadGuard(now);
      CleanupRiskRecords();
      if(!RecoverState(now))
        {
         Housekeeping(now);
         UpdatePanel(now);
         return;   // chart history not ready yet
        }
      g_needRecover = false;
     }
   if(!g_vvReady)
      UpdateVV();
   DailyGuard(now);
   Housekeeping(now);
   ManagePositions();

   datetime localDay, checkServer;
   TodayCheck(now, localDay, checkServer);
   if(localDay != g_lastDay && now >= checkServer)
     {
      if(now - checkServer <= GRB_LATE_SECONDS)
        {
         if(BuildSetup(localDay, checkServer) == GRB_BUILD_DONE)
            g_lastDay = localDay;
        }
      else
        {
         // weekend / holiday / no ticks near the check time: no fresh setup for this day
         g_lastDay = localDay;
         EndSetup("new day");
         ResetSetup();
         g_s.status = "no ticks near check time - skipped";
         Log(TimeToString(localDay, TIME_DATE) + " skipped: first tick came too late after the check time");
        }
     }
   ServiceSetup(now);
   UpdatePanel(now);
  }

double OnTester()
  {
   double trades = TesterStatistics(STAT_TRADES);
   double rf     = TesterStatistics(STAT_RECOVERY_FACTOR);
   double ep     = TesterStatistics(STAT_EXPECTED_PAYOFF);
   double profit = TesterStatistics(STAT_PROFIT);
   if(profit <= 0 || ep <= 0 || rf <= 0)
      return 0.0;
   if(InpOptMinTrades > 0 && trades < InpOptMinTrades)
      return 0.0;
   if(InpOptMinRF > 0 && rf < InpOptMinRF)
      return 0.0;
   if(InpOptMinEP > 0 && ep < InpOptMinEP)
      return 0.0;
   // recovery factor carries the most weight, then trade count, then expected payoff
   return rf * rf * MathSqrt(trades) * MathLog(1.0 + ep);
  }
//+------------------------------------------------------------------+
