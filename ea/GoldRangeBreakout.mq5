//+------------------------------------------------------------------+
//|                                            GoldRangeBreakout.mq5 |
//|                                                gold-oi-dashboard |
//|                                                                  |
//| Range Breakout EA for XAUUSD (works on any symbol).              |
//| Once per day, at a check time in a chosen timezone (New York /   |
//| London follow their own DST), it measures the range formed by    |
//| the N candles just before that moment. If the range is tight     |
//| enough (x ATR), it trades the break with pending stop orders or  |
//| a market entry on a candle close outside the range.              |
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
//+------------------------------------------------------------------+
#property copyright "gold-oi-dashboard"
#property version   "1.00"
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
input int                 InpEntryWindowMin   = 240;               // Entry window after check time (minutes), 0 = until close time / end of day
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
input bool                InpSkipNFPDay       = true;              // Skip NFP day (first Friday of the month, NY date)
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

//--- state
struct GRBSide
  {
   bool              enabled;   // side allowed for today's setup
   bool              done;      // nothing more to do for this side
   bool              filled;    // this side became a position
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
   double            top;
   double            bottom;
   double            atr;           // range ATR at check time
   GRBSide           buy;
   GRBSide           sell;
   string            status;        // short text for the panel
  };

CTrade    g_trade;
GRBSetup  g_s;
double    g_pip              = 0.0;
double    g_vv               = 1.0;
int       g_hATR             = INVALID_HANDLE;
int       g_hVVATR           = INVALID_HANDLE;
bool      g_optimizing       = false;
bool      g_tester           = false;
datetime  g_lastDay          = 0;     // last local day whose check time was processed
datetime  g_closeServer      = 0;     // pending time exit (server clock), 0 = none
datetime  g_lastBar          = 0;     // last seen RangeTF bar (close-confirmed mode)
datetime  g_lastNewsCheck    = 0;
int       g_liveOffset       = 0;
bool      g_liveOffsetValid  = false;
datetime  g_lastOffsetCheck  = 0;
datetime  g_guardDay         = 0;
double    g_guardEquity      = 0.0;
bool      g_halted           = false;
datetime  g_lastPanel        = 0;
string    g_prefix           = "";

ulong     g_riskIds[];               // position id -> initial SL distance cache
double    g_riskVals[];

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
//| Calendar / DST helpers                                           |
//+------------------------------------------------------------------+
int DaysInMonth(const int year, const int month)
  {
   static const int days[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
   if(month == 2 && ((year % 4 == 0 && year % 100 != 0) || year % 400 == 0))
      return 29;
   return days[month - 1];
  }

// n-th Sunday of a month at 00:00 (n >= 1), or the last Sunday when n == 0
datetime NthSunday(const int year, const int month, const int n)
  {
   MqlDateTime t;
   ZeroMemory(t);
   t.year = year;
   t.mon  = month;
   t.day  = 1;
   MqlDateTime f;
   TimeToStruct(StructToTime(t), f);
   int firstSunday = 1 + (7 - f.day_of_week) % 7;
   int day = firstSunday;
   if(n > 0)
      day = firstSunday + 7 * (n - 1);
   else
     {
      int dim = DaysInMonth(year, month);
      while(day + 7 <= dim)
         day += 7;
     }
   t.day = day;
   return StructToTime(t);
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

void UpdateVV()
  {
   g_vv = 1.0;
   if(InpVVDefaultATR > 0)
     {
      double atr;
      if(ReadATR(g_hVVATR, atr))
         g_vv = atr / InpVVDefaultATR;
      else
         Log("Variable Values: ATR not ready, factor 1.0 used");
     }
   else
      if(InpVVDefaultPrice > 0)
        {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(bid > 0)
            g_vv = bid / InpVVDefaultPrice;
        }
   if(g_vv <= 0)
      g_vv = 1.0;
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

void CloseAllPositions(const string why)
  {
   ulong tk;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurPosition(i, tk))
         continue;
      if(g_trade.PositionClose(tk, InpSlippagePoints))
         Log(StringFormat("Closed position %I64u (%s)", tk, why), true);
      else
         Log(StringFormat("Close position %I64u failed: %u %s", tk, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()), true);
     }
  }

void DeleteAllPendings(const string why)
  {
   ulong tk;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurOrder(i, tk))
         continue;
      ENUM_ORDER_TYPE type = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(type != ORDER_TYPE_BUY_STOP && type != ORDER_TYPE_SELL_STOP)
         continue;
      if(g_trade.OrderDelete(tk))
         Log(StringFormat("Deleted pending %I64u (%s)", tk, why));
      else
         Log(StringFormat("Delete pending %I64u failed: %u %s", tk, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()), true);
     }
   if(g_s.buy.ticket > 0 && !g_s.buy.filled)
     {
      g_s.buy.ticket = 0;
      g_s.buy.done   = true;
     }
   if(g_s.sell.ticket > 0 && !g_s.sell.filled)
     {
      g_s.sell.ticket = 0;
      g_s.sell.done   = true;
     }
  }

//+------------------------------------------------------------------+
//| Range box drawing                                                |
//+------------------------------------------------------------------+
string BoxName()
  {
   return g_prefix + "box_" + TimeToString(g_s.localDay, TIME_DATE);
  }

void DrawBox(const datetime t1, const datetime t2, const double top, const double bottom, const color col, const string text)
  {
   if(!InpDrawBoxes || g_optimizing || (g_tester && !MQLInfoInteger(MQL_VISUAL_MODE)))
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
   if(!InpDrawBoxes || g_optimizing || (g_tester && !MQLInfoInteger(MQL_VISUAL_MODE)))
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
void TodayCheck(const datetime now, datetime &localDay, datetime &checkServer)
  {
   datetime localNow = ServerToLocal(now);
   localDay    = DayStart(localNow);
   checkServer = LocalToServer(localDay + InpCheckHour * 3600 + InpCheckMinute * 60);
  }

// time exit for the setup of localDay, server clock (0 = none)
datetime CloseTimeFor(const datetime localDay)
  {
   if(InpCloseHour < 0)
      return 0;
   datetime checkLocal = localDay + InpCheckHour * 3600 + InpCheckMinute * 60;
   datetime closeLocal = localDay + InpCloseHour * 3600 + InpCloseMinute * 60;
   if(closeLocal <= checkLocal)
      closeLocal += 86400;
   return LocalToServer(closeLocal);
  }

datetime WindowEndFor(const datetime localDay, const datetime checkServer)
  {
   datetime closeServer = CloseTimeFor(localDay);
   datetime end;
   if(InpEntryWindowMin > 0)
      end = checkServer + InpEntryWindowMin * 60;
   else
      end = (closeServer > 0) ? closeServer : LocalToServer(localDay + 86400);
   if(closeServer > 0 && end > closeServer)
      end = closeServer;
   return end;
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
   if(InpSkipNFPDay)
     {
      datetime utc = ServerToUTC(checkServer);
      datetime ny  = utc + NYOffsetAtUTC(utc) * 3600;
      MqlDateTime n;
      TimeToStruct(ny, n);
      if(n.day_of_week == 5 && n.day <= 7)
        {
         why = "NFP day";
         return false;
        }
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
bool MeasureRange(const datetime checkServer, double &top, double &bottom, datetime &firstBar, string &why)
  {
   MqlRates r[];
   int want = InpRangeCandles;
   int n = CopyRates(_Symbol, InpRangeTF, checkServer - 1, want, r);
   if(n < want)
     {
      why = StringFormat("only %d of %d candles available", n, want);
      return false;
     }
   int tf = PeriodSeconds(InpRangeTF);
   // r[0] is the oldest, r[n-1] the newest (array is not a series)
   if(r[n - 1].time < checkServer - tf)
     {
      why = "no candle right before the check time (market closed?)";
      return false;
     }
   if(r[0].time < checkServer - (datetime)(2 * want * tf))
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
   return top > bottom;
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
         double level = isBuy ? g_s.bottom - Pips(InpSLBeyondPips) : g_s.top + Pips(InpSLBeyondPips);
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
//| Order placement                                                  |
//+------------------------------------------------------------------+
string TradeComment()
  {
   return InpComment;
  }

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

void RegisterRisk(const ulong positionId, const double slDist)
  {
   int n = ArraySize(g_riskIds);
   for(int i = 0; i < n; i++)
      if(g_riskIds[i] == positionId)
        {
         g_riskVals[i] = slDist;
         return;
        }
   if(n >= 500)
     {
      ArrayRemove(g_riskIds, 0, 250);
      ArrayRemove(g_riskVals, 0, 250);
      n = ArraySize(g_riskIds);
     }
   ArrayResize(g_riskIds, n + 1);
   ArrayResize(g_riskVals, n + 1);
   g_riskIds[n]  = positionId;
   g_riskVals[n] = slDist;
  }

bool MarketEntry(const bool isBuy, const string why)
  {
   if(!SpreadOK())
     {
      Log("Market entry postponed: spread too wide");
      return false;
     }
   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl, tp, slDist;
   if(!ComputeStops(isBuy, price, sl, tp, slDist))
      return false;
   double lots = CalcLots(isBuy, price, sl);
   if(lots <= 0)
      return false;
   bool sent = isBuy ? g_trade.Buy(lots, _Symbol, price, sl, tp, TradeComment())
                     : g_trade.Sell(lots, _Symbol, price, sl, tp, TradeComment());
   uint rc = g_trade.ResultRetcode();
   if(!sent || !RetcodeOK(rc))
     {
      Log(StringFormat("%s market entry failed: %u %s", isBuy ? "Buy" : "Sell", rc, g_trade.ResultRetcodeDescription()), true);
      return false;
     }
   ulong order = g_trade.ResultOrder();
   if(order > 0)
      RegisterRisk(order, slDist);
   Log(StringFormat("%s %.2f lots at market %s (%s) SL %s TP %s", isBuy ? "BUY" : "SELL", lots,
                    DoubleToString(price, _Digits), why, DoubleToString(sl, _Digits), DoubleToString(tp, _Digits)), true);
   return true;
  }

bool PlacePending(const bool isBuy)
  {
   GRBSide side;
   GetSide(isBuy, side);
   double sl, tp, slDist;
   if(!ComputeStops(isBuy, side.entry, sl, tp, slDist))
      return false;
   double lots = CalcLots(isBuy, side.entry, sl);
   if(lots <= 0)
      return false;
   ENUM_ORDER_TYPE_TIME ttype = ORDER_TIME_GTC;
   if((SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE) & SYMBOL_EXPIRATION_GTC) == 0)
      ttype = ORDER_TIME_DAY;
   bool sent = isBuy ? g_trade.BuyStop(lots, side.entry, _Symbol, sl, tp, ttype, 0, TradeComment())
                     : g_trade.SellStop(lots, side.entry, _Symbol, sl, tp, ttype, 0, TradeComment());
   uint rc = g_trade.ResultRetcode();
   if(!sent || !RetcodeOK(rc))
     {
      Log(StringFormat("%s stop at %s failed: %u %s", isBuy ? "Buy" : "Sell", DoubleToString(side.entry, _Digits),
                       rc, g_trade.ResultRetcodeDescription()), true);
      return false;
     }
   ulong ticket = g_trade.ResultOrder();
   RegisterRisk(ticket, slDist);
   if(isBuy)
      g_s.buy.ticket = ticket;
   else
      g_s.sell.ticket = ticket;
   Log(StringFormat("%s STOP %.2f lots at %s SL %s TP %s (ticket %I64u)", isBuy ? "BUY" : "SELL", lots,
                    DoubleToString(side.entry, _Digits), DoubleToString(sl, _Digits), DoubleToString(tp, _Digits), ticket), true);
   return true;
  }

void MarkFilled(const bool isBuy)
  {
   if(isBuy)
     {
      g_s.buy.filled = true;
      g_s.buy.done   = true;
      g_s.buy.ticket = 0;
     }
   else
     {
      g_s.sell.filled = true;
      g_s.sell.done   = true;
      g_s.sell.ticket = 0;
     }
   RecolorBox(isBuy ? InpColUp : InpColDown);
   g_s.status = isBuy ? "broken UP - long" : "broken DOWN - short";
   if(!InpOCO)
      return;
   GRBSide other;
   GetSide(!isBuy, other);
   if(other.ticket > 0)
     {
      if(g_trade.OrderDelete(other.ticket))
         Log(StringFormat("OCO: deleted opposite pending %I64u", other.ticket), true);
      else
         Log(StringFormat("OCO: delete %I64u failed: %u %s", other.ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()), true);
     }
   if(isBuy)
     {
      g_s.sell.ticket = 0;
      g_s.sell.done   = true;
     }
   else
     {
      g_s.buy.ticket = 0;
      g_s.buy.done   = true;
     }
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
   if(HistoryOrderSelect(ticket))
     {
      ENUM_ORDER_STATE st = (ENUM_ORDER_STATE)HistoryOrderGetInteger(ticket, ORDER_STATE);
      filled = (st == ORDER_STATE_FILLED || st == ORDER_STATE_PARTIAL);
     }
   else
     {
      // history not loaded yet: look for a position opened by this order
      ulong tk;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
         if(SelectOurPosition(i, tk) && (ulong)PositionGetInteger(POSITION_IDENTIFIER) == ticket)
            filled = true;
      if(!filled)
         return; // unknown yet, retry next tick
     }
   if(filled)
     {
      Log(StringFormat("%s stop %I64u filled", isBuy ? "Buy" : "Sell", ticket), true);
      MarkFilled(isBuy);
     }
   else
     {
      Log(StringFormat("%s stop %I64u disappeared (cancelled/expired/rejected)", isBuy ? "Buy" : "Sell", ticket), true);
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
   bool crossed  = isBuy ? (ask >= side.entry) : (bid <= side.entry);
   bool farEnough = isBuy ? (side.entry - ask > minDist) : (bid - side.entry > minDist);

   if(crossed)
     {
      double beyond = isBuy ? ask - side.entry : side.entry - bid;
      if(InpMaxChasePips > 0 && beyond <= Pips(InpMaxChasePips))
        {
         if(MarketEntry(isBuy, "level already crossed"))
            MarkFilled(isBuy);
         else
            FailSide(isBuy);
        }
      else
        {
         Log(StringFormat("%s level %s already passed by %.1f pips - side skipped", isBuy ? "Buy" : "Sell",
                          DoubleToString(side.entry, _Digits), beyond / g_pip), true);
         if(isBuy)
            g_s.buy.done = true;
         else
            g_s.sell.done = true;
        }
      return;
     }
   if(!farEnough)
      return; // too close to place a stop order: wait for price to move away or cross
   if(!PlacePending(isBuy))
      FailSide(isBuy);
  }

void FailSide(const bool isBuy)
  {
   if(isBuy)
     {
      g_s.buy.fails++;
      if(g_s.buy.fails >= 3)
        {
         g_s.buy.done = true;
         Log("Buy side given up after 3 failed attempts", true);
        }
     }
   else
     {
      g_s.sell.fails++;
      if(g_s.sell.fails >= 3)
        {
         g_s.sell.done = true;
         Log("Sell side given up after 3 failed attempts", true);
        }
     }
  }

// close-confirmed entries: evaluate each finished RangeTF candle after the check time
void ServiceCloseEntries()
  {
   datetime bar0 = iTime(_Symbol, InpRangeTF, 0);
   if(bar0 == 0 || bar0 == g_lastBar)
      return;
   g_lastBar = bar0;
   datetime bar1 = iTime(_Symbol, InpRangeTF, 1);
   if(bar1 < g_s.checkServer)
      return;
   double close1 = iClose(_Symbol, InpRangeTF, 1);
   if(close1 <= 0)
      return;
   if(g_s.buy.enabled && !g_s.buy.done && close1 >= g_s.buy.entry)
     {
      if(MarketEntry(true, "candle closed above range"))
         MarkFilled(true);
      else
         FailSide(true);
     }
   else
      if(g_s.sell.enabled && !g_s.sell.done && close1 <= g_s.sell.entry)
        {
         if(MarketEntry(false, "candle closed below range"))
            MarkFilled(false);
         else
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
   side.ticket  = 0;
   side.entry   = 0.0;
   side.fails   = 0;
  }

void ResetSetup()
  {
   g_s.active      = false;
   g_s.localDay    = 0;
   g_s.checkServer = 0;
   g_s.windowEnd   = 0;
   g_s.firstBar    = 0;
   g_s.top         = 0.0;
   g_s.bottom      = 0.0;
   g_s.atr         = 0.0;
   ResetSide(g_s.buy);
   ResetSide(g_s.sell);
   g_s.status      = "waiting for check time";
  }

void EndSetup(const string why)
  {
   if(!g_s.active)
      return;
   DeleteAllPendings(why);
   g_s.active = false;
   if(!g_s.buy.filled && !g_s.sell.filled)
      g_s.status = "no trade (" + why + ")";
   Log("Setup ended: " + why);
  }

void BuildSetup(const datetime localDay, const datetime checkServer)
  {
   EndSetup("new day");
   ResetSetup();
   g_s.localDay    = localDay;
   g_s.checkServer = checkServer;
   g_s.windowEnd   = WindowEndFor(localDay, checkServer);
   datetime closeServer = CloseTimeFor(localDay);
   string day = TimeToString(localDay, TIME_DATE);

   if(g_halted)
     {
      g_s.status = "halted (daily loss limit)";
      return;
     }
   string why = "";
   if(!DayAllowed(localDay, checkServer, why))
     {
      g_s.status = "skipped: " + why;
      Log(day + " skipped: " + why);
      return;
     }
   if(HighImpactNews(checkServer - InpNewsMinBefore * 60, checkServer + InpNewsMinAfter * 60))
     {
      g_s.status = "skipped: high-impact news";
      return;
     }

   UpdateVV();
   double top, bottom;
   datetime firstBar;
   if(!MeasureRange(checkServer, top, bottom, firstBar, why))
     {
      g_s.status = "no range: " + why;
      Log(day + " no range: " + why, true);
      return;
     }
   g_s.top      = top;
   g_s.bottom   = bottom;
   g_s.firstBar = firstBar;
   double height = top - bottom;

   double atr = 0;
   if(!ReadATR(g_hATR, atr))
     {
      g_s.status = "no range: ATR not ready";
      Log(day + " ATR not ready", true);
      return;
     }
   g_s.atr = atr;

   string reject = "";
   if(InpMaxRangeATR > 0 && height > InpMaxRangeATR * atr)
      reject = StringFormat("height %.2f ATR > max %.2f", height / atr, InpMaxRangeATR);
   else
      if(InpMaxRangePips > 0 && height > Pips(InpMaxRangePips))
         reject = StringFormat("height %.1f pips > max %.1f", height / g_pip, Pips(InpMaxRangePips) / g_pip);
      else
         if(InpMinRangePips > 0 && height < Pips(InpMinRangePips))
            reject = StringFormat("height %.1f pips < min %.1f", height / g_pip, Pips(InpMinRangePips) / g_pip);

   string info = StringFormat("%s  %.1f pips  %.2f ATR", day, height / g_pip, height / atr);
   if(reject != "")
     {
      g_s.status = "range rejected: " + reject;
      DrawBox(firstBar, checkServer, top, bottom, InpColRejected, info + "  rejected");
      Log(day + " range rejected: " + reject, true);
      return;
     }

   g_s.buy.enabled  = InpAllowBuy;
   g_s.sell.enabled = InpAllowSell;
   g_s.buy.done     = !InpAllowBuy;
   g_s.sell.done    = !InpAllowSell;
   g_s.buy.entry    = NormPrice(top + Pips(InpBuyBufferPips));
   g_s.sell.entry   = NormPrice(bottom - Pips(InpSellBufferPips));
   g_s.active       = true;
   g_s.status       = "range armed";
   g_closeServer    = closeServer;
   g_lastBar        = iTime(_Symbol, InpRangeTF, 0);
   DrawBox(firstBar, g_s.windowEnd, top, bottom, InpColForming, info);
   Log(StringFormat("%s range %s - %s (%s), buy >= %s, sell <= %s, window until %s, VV factor %.3f", day,
                    DoubleToString(bottom, _Digits), DoubleToString(top, _Digits), info,
                    DoubleToString(g_s.buy.entry, _Digits), DoubleToString(g_s.sell.entry, _Digits),
                    TimeToString(g_s.windowEnd, TIME_DATE | TIME_MINUTES), g_vv), true);
  }

void ServiceSetup(const datetime now)
  {
   if(!g_s.active)
      return;
   if(now >= g_s.windowEnd)
     {
      EndSetup("entry window over");
      return;
     }
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
      ServicePendingSide(true);
      ServicePendingSide(false);
     }
   else
      ServiceCloseEntries();
   if(g_s.buy.done && g_s.sell.done)
     {
      g_s.active = false;
      if(!g_s.buy.filled && !g_s.sell.filled)
         g_s.status = "no trade (both sides skipped)";
     }
  }

//+------------------------------------------------------------------+
//| Position management                                              |
//+------------------------------------------------------------------+
double InitialRisk(const ulong positionId, const double openPrice, const double currentSL)
  {
   int n = ArraySize(g_riskIds);
   for(int i = 0; i < n; i++)
      if(g_riskIds[i] == positionId)
         return g_riskVals[i];
   double risk = 0;
   if(HistoryOrderSelect(positionId))
     {
      double sl = HistoryOrderGetDouble(positionId, ORDER_SL);
      double price = HistoryOrderGetDouble(positionId, ORDER_PRICE_OPEN);
      if(sl > 0 && price > 0)
         risk = MathAbs(price - sl);
     }
   if(risk <= 0 && currentSL > 0)
      risk = MathAbs(openPrice - currentSL);
   if(risk > 0)
      RegisterRisk(positionId, risk);
   return risk;
  }

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
      double risk  = InitialRisk(id, open, sl);
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

void ServiceTimeExit(const datetime now)
  {
   if(g_closeServer <= 0 || now < g_closeServer)
      return;
   g_closeServer = 0;
   EndSetup("close time");
   DeleteAllPendings("close time");
   if(CountOurPositions() > 0)
      CloseAllPositions("close time");
  }

void DailyGuard(const datetime now)
  {
   datetime day = DayStart(now);
   if(day != g_guardDay)
     {
      g_guardDay    = day;
      g_guardEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(g_halted)
         Log("Daily loss limit reset for the new day", true);
      g_halted = false;
     }
   if(InpMaxDailyLossPct <= 0 || g_halted || g_guardEquity <= 0)
      return;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= g_guardEquity * (1.0 - InpMaxDailyLossPct / 100.0))
     {
      g_halted = true;
      Log(StringFormat("Daily loss limit hit: equity %.2f vs day start %.2f - closing and pausing until tomorrow", equity, g_guardEquity), true);
      EndSetup("daily loss limit");
      DeleteAllPendings("daily loss limit");
      CloseAllPositions("daily loss limit");
      g_s.status = "halted (daily loss limit)";
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
   string s = "Gold Range Breakout v1.00  |  " + _Symbol + "  magic " + (string)InpMagic + "\n";
   s += StringFormat("%s time %s  |  server %s\n", TZName(), TimeToString(ServerToLocal(now), TIME_MINUTES),
                     TimeToString(now, TIME_MINUTES));
   s += StringFormat("Check %02d:%02d %s = %s server  |  pip %s  |  VV x%.3f\n", InpCheckHour, InpCheckMinute, TZName(),
                     TimeToString(checkServer, TIME_MINUTES), DoubleToString(g_pip, _Digits), g_vv);
   if(g_s.top > 0)
      s += StringFormat("Range %s - %s  (%.1f pips)\n", DoubleToString(g_s.bottom, _Digits), DoubleToString(g_s.top, _Digits),
                        (g_s.top - g_s.bottom) / g_pip);
   if(g_s.active)
      s += StringFormat("Buy >= %s   Sell <= %s   until %s\n", DoubleToString(g_s.buy.entry, _Digits),
                        DoubleToString(g_s.sell.entry, _Digits), TimeToString(g_s.windowEnd, TIME_MINUTES));
   s += "Status: " + g_s.status + "\n";
   s += StringFormat("Open positions: %d", CountOurPositions());
   if(g_closeServer > 0)
      s += "  |  time exit " + TimeToString(g_closeServer, TIME_MINUTES);
   if(InpMaxDailyLossPct > 0)
      s += StringFormat("\nDaily loss guard: %.1f%% of %.2f%s", InpMaxDailyLossPct, g_guardEquity, g_halted ? "  HALTED" : "");
   Comment(s);
  }

//+------------------------------------------------------------------+
//| Restart recovery                                                 |
//+------------------------------------------------------------------+
// After a restart or timeframe change: never open a fresh setup late,
// but keep managing today's pending orders and the time exit.
void RecoverOnInit(const datetime now)
  {
   datetime localDay, checkServer;
   TodayCheck(now, localDay, checkServer);
   if(now < checkServer)
      return;
   g_lastDay = localDay;

   ulong buyTk = 0, sellTk = 0, tk;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!SelectOurOrder(i, tk))
         continue;
      ENUM_ORDER_TYPE type = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(type == ORDER_TYPE_BUY_STOP)
         buyTk = tk;
      if(type == ORDER_TYPE_SELL_STOP)
         sellTk = tk;
     }
   datetime closeServer = CloseTimeFor(localDay);
   if((CountOurPositions() > 0 || buyTk > 0 || sellTk > 0) && closeServer > now)
      g_closeServer = closeServer;
   if(buyTk == 0 && sellTk == 0)
     {
      g_s.status = "started after check time - next setup tomorrow";
      return;
     }

   ResetSetup();
   g_s.localDay    = localDay;
   g_s.checkServer = checkServer;
   g_s.windowEnd   = WindowEndFor(localDay, checkServer);
   string why;
   double top, bottom;
   datetime firstBar;
   UpdateVV();
   if(MeasureRange(checkServer, top, bottom, firstBar, why))
     {
      g_s.top      = top;
      g_s.bottom   = bottom;
      g_s.firstBar = firstBar;
      double atr = 0;
      if(ReadATR(g_hATR, atr))
         g_s.atr = atr;
     }
   g_s.buy.enabled  = buyTk > 0;
   g_s.buy.done     = buyTk == 0;
   g_s.buy.ticket   = buyTk;
   g_s.sell.enabled = sellTk > 0;
   g_s.sell.done    = sellTk == 0;
   g_s.sell.ticket  = sellTk;
   if(buyTk > 0 && OrderSelect(buyTk))
      g_s.buy.entry = OrderGetDouble(ORDER_PRICE_OPEN);
   if(sellTk > 0 && OrderSelect(sellTk))
      g_s.sell.entry = OrderGetDouble(ORDER_PRICE_OPEN);
   g_s.active = true;
   g_s.status = "resumed today's pending orders";
   Log(StringFormat("Resumed today's setup (buy stop %I64u, sell stop %I64u)", buyTk, sellTk), true);
   if(now >= g_s.windowEnd)
      EndSetup("entry window over");
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
   if(InpVVDefaultATR > 0)
     {
      g_hVVATR = iATR(_Symbol, InpVVATRTF, InpVVATRPeriod);
      if(g_hVVATR == INVALID_HANDLE)
        {
         Print("GoldRangeBreakout: cannot create Variable Values ATR handle, error ", GetLastError());
         return INIT_FAILED;
        }
     }

   ResetSetup();
   g_liveOffsetValid = false;
   UpdateLiveOffset();
   datetime now = TimeCurrent();
   g_guardDay    = DayStart(now);
   g_guardEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_halted      = false;
   UpdateVV();
   RecoverOnInit(now);

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
   DailyGuard(now);
   ServiceTimeExit(now);
   ManagePositions();

   datetime localDay, checkServer;
   TodayCheck(now, localDay, checkServer);
   if(localDay != g_lastDay && now >= checkServer)
     {
      g_lastDay = localDay;
      if(now - checkServer <= 15 * 60)
         BuildSetup(localDay, checkServer);
      else
        {
         // weekend / holiday / EA started late: no fresh setup for this day
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
