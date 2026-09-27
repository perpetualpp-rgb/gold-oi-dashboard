//+------------------------------------------------------------------+
//|                                       XAU_AsianRangeBreakout.mq5 |
//|        XAUUSD Asian-session range breakout (London clock, M1)     |
//+------------------------------------------------------------------+
/*
  STRATEGY (a port of research/range_breakout/engine.py, frozen 2026-09-27)
  --------------------------------------------------------------------------
  All session times are on the LONDON clock (GMT/BST, DST aware). A trading day is a London
  calendar date, Monday to Friday.

   1. Range     : BID high / low of the M1 bars whose London open time is in [range_start, range_end).
                  At least 60% of the expected minutes must exist, the first bar at/after range_end
                  must start less than 30 min after range_end, and the width must be > 0.
   2. ATR14     : simple mean of the true range of the 14 completed daily bars before today
                  (London-day bars built from M1 by default = engine; broker D1 optional).
   3. Filters   : min_w_atr <= width / ATR14 <= max_w_atr;
                  ATR regime (if atr_regime_n > 0): ATR14_prev(today) <= atr_regime_max x mean of the
                  last atr_regime_n ATR14_prev values (today included, min periods min(n, max(5, int(0.6 n))));
                  day-of-week mask; optional first-Friday skip; one trade per day.
   4. Entry     : at range_end a BUY STOP at range high + buffer and a SELL STOP at range low - buffer
                  (BID-based levels; MT5 triggers buy stops on ASK and sell stops on BID, like the engine).
                  OCO. Pending orders are removed at entry_end. The day is skipped if both levels are
                  crossed at once, or if the breakout happens while the spread exceeds max_spread.
   5. Exit      : SL measured from the ACTUAL fill (sl_ref 0: sl_k x range width, 1: sl_k x ATR14,
                  2: opposite edge; floored at 0.30 USD for 0/1). TP only if tp_r > 0 (armed from the bar
                  after the entry bar). Optional break-even / trail updated on completed M1 bars after
                  the entry bar and applied from the next bar. Time exit at exit_time London; earlier on
                  US-holiday early closes / broker session end; never held over a weekend.

  FROZEN CANDIDATES (final/candidates.json, engine sha256 7eb6bb0a...a4579)
  --------------------------------------------------------------------------
  PRIMARY  re5_w030_a20_W1.00 : range 00:00-05:00, entry_end 12:00, exit 20:00, stop entry, buffer 0,
                                SL 1.0 x range width, no TP/BE/trail, max_trades 1,
                                min_w_atr 0.30, max_w_atr 99, atr_regime_n 20, atr_regime_max 1.0,
                                all weekdays, skip_nfp false, max_spread 1.0.
  FALLBACK re5_w035_nor_W1.00 : identical except min_w_atr 0.35 and atr_regime_n 0 (regime filter off).
  DEFAULT PRESET = FALLBACK. The pre-declared rule picked PRIMARY, but on evidence available BEFORE the
  holdout the FALLBACK is more robust (IS t 2.63 vs 1.94, family p 0.055 vs 0.16, both VAL years
  positive, and no ATR-regime threshold, which is knife-edge and feed-sensitive). Neither is changed.
  Engine knobs that are fixed in this EA at the frozen values: entry_mode 0 (stop orders),
  max_trades 1, comp_n 0, trend 0.

  BACKTEST EVIDENCE AND CAVEATS (engine, costs 0.07 USD/oz commission + 0.05 slip per fill + modelled spread)
  --------------------------------------------------------------------------
  PRIMARY  IS 2014-2021 : n 532, 67.8 tr/yr, avg +0.122R, t 1.94, PF 1.25, maxDD 16.1R, 6/8 years positive.
           VAL 2022-2023: n 113, avg +0.020R, t 0.16, PF 1.04 (longs -0.12R, shorts +0.20R).
  FALLBACK IS: n 638, avg +0.132R, t 2.63, PF 1.31.   VAL: n 147, avg +0.040R, t 0.40, PF 1.09.
  - About 20,000 configs were searched in round 1. The deflated Sharpe ratio of the PRIMARY is
    0.18-0.35 for N_eff 50-200; its family-wise p (24-config bootstrap) is 0.16 in IS and 0.85 in VAL.
    THE EDGE IS NOT STATISTICALLY ESTABLISHED. Expect anything from about -0.05R to +0.10R per trade.
  - The edge is about the size of the costs (~0.09R round trip). It needs an ECN-type account
    (round trip <= ~0.5 USD/oz). At slip 0.10 + spread +0.10 IS falls to +0.085R and VAL to -0.024R.
  - HOLDOUT 2024-01..2026-09 (sealed during design, run once, nothing tuned on it; final/REPORT_holdout.md):
      PRIMARY  n 210, avg +0.053R, t 0.67, PF 1.12 (2024 +0.16, 2025 -0.08, 2026 YTD +0.14)
      FALLBACK n 324, avg +0.073R, t 1.26, PF 1.19 (2024 +0.07, 2025 +0.02, 2026 YTD +0.16)
      naive baseline (range 00-07, no filters) +0.050R. Verdict: NOT CONFIRMED - the filters' extra
      edge did not replicate; the small positive result owes much to costs being only ~0.02-0.05R
      at 2025-26 gold prices (ranges 25-55 USD) versus ~0.08R in 2014-2021.
    Results in the MT5 tester depend on the broker's history and clock; check the
    clock setting first (the EA logs server time, UTC and London time at init).
  - Treat live use as an experiment: demo first, risk <= 0.5%/trade, stop at a 25R drawdown
    (see research/range_breakout/STRATEGY_TH.md for the full guardrails).
  - Parity: ea/parity_check.py ports this EA's clock, holiday, range, ATR14 and regime logic to Python and
    compares it with engine.py on 2014-03..2023 (no holdout data loaded): London-day ATR mode arms exactly
    the engine's days (PRIMARY 712/712, FALLBACK 885/885, identical ranges and ATR). Broker-D1 ATR agrees
    on 93% / 97% of days (ea/divergence_check.py: IS +0.144R vs +0.125R, VAL +0.025R vs +0.020R).
  - Risk per trade defaults to 0.5% of balance. With ~0.45 win rate and maxDD of 16R in IS,
    a 10-20R drawdown (5-10% at 0.5%) is normal.
*/
#property copyright   "gold-oi-dashboard research/range_breakout"
#property version     "1.00"
#property description "XAUUSD Asian range (London 00:00-05:00) stop-order breakout, M1 exact port of engine.py."
#property description "Presets: PRIMARY re5_w030_a20_W1.00 / FALLBACK re5_w035_nor_W1.00 (frozen). Edge NOT established; see header."

#include <Trade\Trade.mqh>

//--- enums ------------------------------------------------------------
enum ENUM_ARB_PRESET
  {
   ARB_PRESET_PRIMARY  = 0, // PRIMARY re5_w030_a20_W1.00 (frozen)
   ARB_PRESET_FALLBACK = 1, // FALLBACK re5_w035_nor_W1.00 (frozen)
   ARB_PRESET_CUSTOM   = 2  // CUSTOM (use the engine knobs below)
  };
enum ENUM_ARB_CLOCK
  {
   ARB_CLOCK_GMT2_US = 0,   // GMT+2 winter / GMT+3 summer, US DST (most XAUUSD brokers)
   ARB_CLOCK_GMT2_EU = 1,   // GMT+2 winter / GMT+3 summer, EU DST
   ARB_CLOCK_FIXED   = 2,   // Fixed offset (InpFixedOffsetHours)
   ARB_CLOCK_AUTO    = 3    // Auto from TimeTradeServer()-TimeGMT() (live only)
  };
enum ENUM_ARB_ATR_SRC
  {
   ARB_ATR_LONDON = 0,      // London-day bars built from M1 (exact engine definition)
   ARB_ATR_D1     = 1       // Broker D1 bars (NY-close days, research corr 0.998)
  };
enum ENUM_ARB_RISK_BASE
  {
   ARB_RISK_BALANCE = 0,    // Balance
   ARB_RISK_EQUITY  = 1     // Equity
  };
enum ENUM_ARB_WIDE_SPREAD
  {
   ARB_WS_WAIT = 0,         // Wait: only a breakout during a wide spread skips the day (engine)
   ARB_WS_SKIP = 1          // Skip the day if the spread is wide at placement
  };

//--- inputs -----------------------------------------------------------
input group "=== Strategy preset ==="
input ENUM_ARB_PRESET InpPreset        = ARB_PRESET_FALLBACK; // Preset (PRIMARY / FALLBACK are frozen; FALLBACK recommended)

input group "=== Engine knobs (used ONLY when Preset = CUSTOM) ==="
input double InpRangeStart    = 0.0;    // range_start, London hours (may be negative)
input double InpRangeEnd      = 5.0;    // range_end, London hours (> 0)
input double InpEntryEnd      = 12.0;   // entry_end, London hours (pending orders removed)
input double InpExitTime      = 20.0;   // exit_time, London hours (flat)
input double InpBufK          = 0.0;    // buf_k: buffer = buf_k x width + buf_atr x ATR14
input double InpBufAtr        = 0.0;    // buf_atr
input int    InpSlRef         = 0;      // sl_ref: 0 range width, 1 ATR14, 2 opposite edge
input double InpSlK           = 1.0;    // sl_k
input double InpTpR           = 0.0;    // tp_r in R (0 = no TP)
input double InpBeR           = 0.0;    // be_r in R (0 = off)
input double InpTrailR        = 0.0;    // trail_r in R (0 = off)
input double InpMinWAtr       = 0.30;   // min_w_atr (width / ATR14)
input double InpMaxWAtr       = 99.0;   // max_w_atr
input int    InpAtrRegimeN    = 20;     // atr_regime_n (0 = off)
input double InpAtrRegimeMax  = 1.0;    // atr_regime_max
input bool   InpTradeMon      = true;   // dow_mask Monday
input bool   InpTradeTue      = true;   // dow_mask Tuesday
input bool   InpTradeWed      = true;   // dow_mask Wednesday
input bool   InpTradeThu      = true;   // dow_mask Thursday
input bool   InpTradeFri      = true;   // dow_mask Friday
input bool   InpSkipNfp       = false;  // skip_nfp (first Friday of the month)

input group "=== Server clock ==="
input ENUM_ARB_CLOCK InpServerClock    = ARB_CLOCK_GMT2_US; // Broker server clock convention
input double InpFixedOffsetHours       = 2.0;   // Fixed server offset vs UTC, hours (Fixed mode)
input bool   InpHaltOnClockMismatch    = true;  // Live: no trading if clock rule disagrees with TimeGMT() by > 2 min

input group "=== Data / filters ==="
input ENUM_ARB_ATR_SRC InpAtrSource    = ARB_ATR_LONDON; // ATR14 daily bars
input bool   InpSkipFullHolidays       = true;  // No trade Dec 25, Jan 1 (+ Monday if observed), Good Friday

input group "=== Execution ==="
input double InpMaxSpread              = 1.0;   // max_spread, price units (USD/oz)
input ENUM_ARB_WIDE_SPREAD InpWideSpreadAtPlacement = ARB_WS_WAIT; // Wide spread at placement
input bool   InpUsePendingOrders       = true;  // Broker stop orders (false = EA-side triggers + market orders)
input int    InpDeviationPoints        = 50;    // Max deviation for market orders, points
input int    InpMaxRetries             = 3;     // Retries on requote / price changed / timeout
input int    InpReplaceThrottleSec     = 30;    // Min seconds between pending (re)placement attempts

input group "=== Session end / holidays ==="
input bool   InpUseUSHolidayCalendar   = true;  // Flatten early on US-holiday early-close days
input double InpEarlyCloseFlatten      = 17.5;  // Early-close flatten time, London hours (halt is ~18:00)
input string InpExtraEarlyCloseDates   = "";    // Extra early-close dates, "YYYY.MM.DD,YYYY.MM.DD"
input int    InpSessionEndBufferMin    = 5;     // Flatten this many minutes before the broker session end
input double InpFridayFlatten          = 21.5;  // Friday hard flatten, London hours (weekend guard)

input group "=== Risk ==="
input double InpRiskPercent            = 0.5;   // Risk per trade, % of balance/equity
input ENUM_ARB_RISK_BASE InpRiskBase   = ARB_RISK_BALANCE; // Risk base
input double InpFixedLots              = 0.0;   // Fixed lots (> 0 overrides risk %)
input double InpMaxLots                = 0.0;   // Max lots cap (0 = none)
input double InpCommissionPerLot       = 0.0;   // Round-trip commission per lot added to the sizing loss

input group "=== Safety ==="
input long   InpMagic                  = 20260927; // Magic number
input double InpExpectedContractSize   = 100.0; // Expected contract size (0 = do not check)
input bool   InpRequireGoldSymbol      = true;  // Refuse symbols without XAU/GOLD in the name
input bool   InpAllowMultipleInstances = false; // Allow another chart with this EA on the same symbol
input bool   InpVerbose                = true;  // Verbose logging

//--- parameter set ----------------------------------------------------
struct SParams
  {
   string            name;
   double            range_start, range_end, entry_end, exit_time;
   double            buf_k, buf_atr;
   int               sl_ref;
   double            sl_k, tp_r, be_r, trail_r;
   double            min_w_atr, max_w_atr;
   int               atr_regime_n;
   double            atr_regime_max;
   bool              dow[5];
   bool              skip_nfp;
  };

//--- per-day state ----------------------------------------------------
enum ENUM_DAY_STATE { DS_IDLE = 0, DS_ARMED = 1, DS_INPOS = 2, DS_DONE = 3 };

struct SDay
  {
   datetime          key;           // London date 00:00 on the London clock
   int               state;
   bool              computed;      // range + filters computed
   bool              decision;      // filters passed
   string            reason;        // why no trade / why done
   double            rh, rl, width, atr, reg_mean, wa;
   int               reg_cnt, n_range;
   double            buf, lvl_l, lvl_s, risk_plan;
   double            volume, val_per_price_lot;
   bool              armed_l, armed_s;
   datetime          next_setup_try, next_place_try, next_modify_try, entry_sent_at;
   bool              paused;
   bool              virt_logged_l, virt_logged_s;
   datetime          seen_l, seen_s;  // server time our BUY / SELL STOP was last seen live (0 = deleted by us)
   // position
   ulong             pos_ticket;
   int               dir;
   double            fill, risk, best;
   datetime          entry_bar, best_upto;
   string            exit_reason;
   bool              summary_done;
   void              Reset(datetime k)
     {
      key = k; state = DS_IDLE; computed = false; decision = false; reason = "";
      rh = 0; rl = 0; width = 0; atr = 0; reg_mean = 0; wa = 0; reg_cnt = 0; n_range = 0;
      buf = 0; lvl_l = 0; lvl_s = 0; risk_plan = 0; volume = 0; val_per_price_lot = 0;
      armed_l = false; armed_s = false;
      next_setup_try = 0; next_place_try = 0; next_modify_try = 0; entry_sent_at = 0;
      paused = false; virt_logged_l = false; virt_logged_s = false; seen_l = 0; seen_s = 0;
      pos_ticket = 0; dir = 0; fill = 0; risk = 0; best = 0; entry_bar = 0; best_upto = 0;
      exit_reason = ""; summary_done = false;
     }
  };

struct SDeals
  {
   int               entries;       // distinct entry orders today
   bool              long_used, short_used;
   int               first_dir;
   double            entry_px, exit_px, vol, pnl;
   datetime          entry_t, exit_t;
   bool              closed;
  };

//--- globals ----------------------------------------------------------
CTrade   g_trade;
SParams  P;
SDay     g_d;
bool     g_init_ok = false;
bool     g_tester = false;
int      g_clock = ARB_CLOCK_GMT2_US;
long     g_fixed_off = 7200;
long     g_auto_off = 7200;
bool     g_clock_halt = false;
bool     g_price_checked = false;
bool     g_hedging = true;
bool     g_stop_orders_ok = true;
bool     g_deal_flag = true;
datetime g_next_deal_scan = 0;
datetime g_next_clock_check = 0;
long     g_rs_sec, g_re_sec, g_ee_sec, g_ex_sec, g_early_sec, g_fri_sec;
int      g_digits = 2;
double   g_point = 0.01, g_tick = 0.01, g_contract = 100.0;
double   g_vstep = 0.01, g_vmin = 0.01, g_vmax = 100.0;
int      g_vdigits = 2;
int      g_exp_mode = 0;
datetime g_extra_early[];
string   g_hb_name, g_skip_name;
string   g_log_tag[];
datetime g_log_time[];

//+------------------------------------------------------------------+
//| logging                                                          |
//+------------------------------------------------------------------+
void Log(const string msg) { Print("[ARB ", _Symbol, " #", InpMagic, "] ", msg); }
void LogV(const string msg) { if(InpVerbose) Log(msg); }
void LogT(const string tag, const string msg, const int every_sec)
  {
   datetime now = TimeCurrent();
   int n = ArraySize(g_log_tag);
   for(int i = 0; i < n; i++)
      if(g_log_tag[i] == tag)
        {
         if(now - g_log_time[i] < every_sec)
            return;
         g_log_time[i] = now;
         Log(msg);
         return;
        }
   ArrayResize(g_log_tag, n + 1);
   ArrayResize(g_log_time, n + 1);
   g_log_tag[n] = tag;
   g_log_time[n] = now;
   Log(msg);
  }
string Px(const double v) { return DoubleToString(v, g_digits); }
string TS(const datetime t) { return TimeToString(t, TIME_DATE | TIME_MINUTES); }
string HM(const long sec)
  {
   long s = sec;
   string sign = "";
   if(s < 0) { sign = "-"; s = -s; }
   return StringFormat("%s%02d:%02d", sign, (int)(s / 3600), (int)((s % 3600) / 60));
  }

//+------------------------------------------------------------------+
//| calendar helpers (datetime = seconds since 1970, no time zone)   |
//+------------------------------------------------------------------+
datetime DayStart(const datetime t)    { return (datetime)(((long)t / 86400) * 86400); }
datetime MinuteStart(const datetime t) { return (datetime)(((long)t / 60) * 60); }
int      DowOf(const datetime t)       { return (int)((((long)t / 86400) + 4) % 7); } // 0 = Sunday
long     LMin(const long a, const long b) { return a < b ? a : b; }
long     LMax(const long a, const long b) { return a > b ? a : b; }

datetime MakeDate(const int y, const int m, const int d)
  {
   MqlDateTime s;
   s.year = y; s.mon = m; s.day = d; s.hour = 0; s.min = 0; s.sec = 0;
   s.day_of_week = 0; s.day_of_year = 0;
   return StructToTime(s);
  }
int DaysInMonth(const int y, const int m)
  {
   int ny = y, nm = m + 1;
   if(nm > 12) { nm = 1; ny++; }
   return (int)(((long)MakeDate(ny, nm, 1) - (long)MakeDate(y, m, 1)) / 86400);
  }
// n-th (1-based) weekday wd (0 = Sunday) of a month
datetime NthWeekday(const int y, const int m, const int wd, const int n)
  {
   datetime first = MakeDate(y, m, 1);
   int add = (wd - DowOf(first) + 7) % 7;
   return (datetime)((long)first + (long)(add + 7 * (n - 1)) * 86400);
  }
datetime LastWeekday(const int y, const int m, const int wd)
  {
   datetime last = MakeDate(y, m, DaysInMonth(y, m));
   int sub = (DowOf(last) - wd + 7) % 7;
   return (datetime)((long)last - (long)sub * 86400);
  }

//--- DST boundaries (UTC instants), cached per year -------------------
int      g_dst_y = -1;
datetime g_y_s = 0, g_y_e = 0, g_uk_s = 0, g_uk_e = 0, g_us_s = 0, g_us_e = 0;
void DstFor(const datetime t)
  {
   if(g_dst_y > 0 && t >= g_y_s && t < g_y_e)
      return;
   MqlDateTime s;
   TimeToStruct(t, s);
   int y = s.year;
   g_dst_y = y;
   g_y_s = MakeDate(y, 1, 1);
   g_y_e = MakeDate(y + 1, 1, 1);
   // UK / EU: last Sunday of March 01:00 UTC .. last Sunday of October 01:00 UTC
   g_uk_s = (datetime)((long)LastWeekday(y, 3, 0) + 3600);
   g_uk_e = (datetime)((long)LastWeekday(y, 10, 0) + 3600);
   if(y >= 2007)
     {
      // US: second Sunday of March 02:00 EST (07:00 UTC) .. first Sunday of November 02:00 EDT (06:00 UTC)
      g_us_s = (datetime)((long)NthWeekday(y, 3, 0, 2) + 7 * 3600);
      g_us_e = (datetime)((long)NthWeekday(y, 11, 0, 1) + 6 * 3600);
     }
   else
     {
      g_us_s = (datetime)((long)NthWeekday(y, 4, 0, 1) + 7 * 3600);
      g_us_e = (datetime)((long)LastWeekday(y, 10, 0) + 6 * 3600);
     }
  }
bool IsUKDST(const datetime utc) { DstFor(utc); return utc >= g_uk_s && utc < g_uk_e; }
bool IsUSDST(const datetime utc) { DstFor(utc); return utc >= g_us_s && utc < g_us_e; }

//--- server <-> UTC <-> London -----------------------------------------
long ServerOffsetForUTC(const datetime utc)
  {
   if(g_clock == ARB_CLOCK_GMT2_US) return 7200 + (IsUSDST(utc) ? 3600 : 0);
   if(g_clock == ARB_CLOCK_GMT2_EU) return 7200 + (IsUKDST(utc) ? 3600 : 0);
   if(g_clock == ARB_CLOCK_FIXED)   return g_fixed_off;
   return g_auto_off;
  }
datetime ServerToUTC(const datetime s)
  {
   if(g_clock == ARB_CLOCK_FIXED) return (datetime)((long)s - g_fixed_off);
   if(g_clock == ARB_CLOCK_AUTO)  return (datetime)((long)s - g_auto_off);
   datetime u3 = (datetime)((long)s - 10800);
   if(ServerOffsetForUTC(u3) == 10800)
      return u3;
   return (datetime)((long)s - 7200);
  }
datetime UTCToServer(const datetime u) { return (datetime)((long)u + ServerOffsetForUTC(u)); }
datetime UTCToLondon(const datetime u) { return (datetime)((long)u + (IsUKDST(u) ? 3600 : 0)); }
datetime LondonToUTC(const datetime l)
  {
   datetime u1 = (datetime)((long)l - 3600);
   if(IsUKDST(u1))
      return u1;
   return l;
  }
datetime ServerToLondon(const datetime s) { return UTCToLondon(ServerToUTC(s)); }
datetime LondonToServer(const datetime l) { return UTCToServer(LondonToUTC(l)); }

datetime NowServer()
  {
   if(g_tester) return TimeCurrent();
   datetime t = TimeTradeServer();
   datetime c = TimeCurrent();
   return t > c ? t : c;
  }

//+------------------------------------------------------------------+
//| holidays                                                         |
//+------------------------------------------------------------------+
datetime ObservedFixed(const int y, const int m, const int d)
  {
   datetime t = MakeDate(y, m, d);
   int w = DowOf(t);
   if(w == 6) return (datetime)((long)t - 86400);
   if(w == 0) return (datetime)((long)t + 86400);
   return t;
  }
datetime EasterSunday(const int y)
  {
   int a = y % 19, b = y / 100, c = y % 100, d = b / 4, e = b % 4;
   int f = (b + 8) / 25, g = (b - f + 1) / 3;
   int h = (19 * a + b - d - g + 15) % 30;
   int i = c / 4, k = c % 4;
   int l = (32 + 2 * e + 2 * i - h - k) % 7;
   int m = (a + 11 * h + 22 * l) / 451;
   int month = (h + l - 7 * m + 114) / 31;
   int day = ((h + l - 7 * m + 114) % 31) + 1;
   return MakeDate(y, month, day);
  }
int YearOf(const datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.year; }
int DomOf(const datetime t)  { MqlDateTime s; TimeToStruct(t, s); return s.day; }

// US (CME metals) early-close days: trading halts ~13:00-13:45 ET, i.e. ~18:00-18:45 London
bool IsUSEarlyClose(const datetime key)
  {
   int y = YearOf(key);
   if(key == NthWeekday(y, 1, 1, 3)) return true;                        // Martin Luther King Day
   if(key == NthWeekday(y, 2, 1, 3)) return true;                        // Presidents Day
   if(key == LastWeekday(y, 5, 1))   return true;                        // Memorial Day
   if(y >= 2022 && key == ObservedFixed(y, 6, 19)) return true;          // Juneteenth
   if(key == ObservedFixed(y, 7, 4)) return true;                        // Independence Day
   if(key == NthWeekday(y, 9, 1, 1)) return true;                        // Labor Day
   datetime tg = NthWeekday(y, 11, 4, 4);
   if(key == tg) return true;                                            // Thanksgiving
   if(key == (datetime)((long)tg + 86400)) return true;                  // day after Thanksgiving
   datetime xe = MakeDate(y, 12, 24);
   if(key == xe && DowOf(xe) >= 1 && DowOf(xe) <= 5) return true;       // Christmas Eve
   return false;
  }
bool IsExtraEarlyClose(const datetime key)
  {
   for(int i = 0; i < ArraySize(g_extra_early); i++)
      if(g_extra_early[i] == key) return true;
   return false;
  }
bool IsFullHoliday(const datetime key)
  {
   int y = YearOf(key);
   if(key == MakeDate(y, 12, 25)) return true;
   if(key == MakeDate(y, 1, 1))   return true;
   datetime xm = MakeDate(y, 12, 25), ny = MakeDate(y, 1, 1);
   if(DowOf(xm) == 0 && key == (datetime)((long)xm + 86400)) return true; // Christmas observed on Monday
   if(DowOf(ny) == 0 && key == (datetime)((long)ny + 86400)) return true; // New Year observed on Monday
   if(key == (datetime)((long)EasterSunday(y) - 2 * 86400)) return true; // Good Friday
   return false;
  }

//+------------------------------------------------------------------+
//| broker session end (server time) of the session containing srv   |
//+------------------------------------------------------------------+
datetime SessionEndServer(const datetime srv)
  {
   datetime d0 = DayStart(srv);
   long sf[], st[];
   int ns = 0;
   for(int k = 0; k < 3; k++)
     {
      int dw = DowOf((datetime)((long)d0 + (long)k * 86400));
      datetime f, t;
      for(uint idx = 0; idx < 16; idx++)
        {
         if(!SymbolInfoSessionTrade(_Symbol, (ENUM_DAY_OF_WEEK)dw, idx, f, t))
            break;
         ArrayResize(sf, ns + 1);
         ArrayResize(st, ns + 1);
         sf[ns] = (long)f + (long)k * 86400;
         st[ns] = (long)t + (long)k * 86400;
         ns++;
        }
     }
   if(ns == 0)
      return 0;
   long tod = (long)srv - (long)d0;
   long end = -1;
   for(int i = 0; i < ns; i++)
      if(tod >= sf[i] && tod < st[i]) { end = st[i]; break; }
   if(end < 0)
      return 0;
   // sessions separated by <= 15 min are treated as continuous
   for(int it = 0; it < 10; it++)
     {
      bool ext = false;
      for(int i = 0; i < ns; i++)
         if(sf[i] <= end + 900 && st[i] > end) { end = st[i]; ext = true; }
      if(!ext) break;
     }
   return (datetime)((long)d0 + end);
  }

//+------------------------------------------------------------------+
//| flatten time (seconds on today's London clock)                   |
//+------------------------------------------------------------------+
datetime g_flat_min = 0, g_flat_key = 0;
long     g_flat_val = 0;
long FlattenSec(const datetime srv, const datetime key)
  {
   datetime mn = MinuteStart(srv);
   if(mn == g_flat_min && key == g_flat_key) return g_flat_val;   // cached per minute
   long f = g_ex_sec;
   if((InpUseUSHolidayCalendar && IsUSEarlyClose(key)) || IsExtraEarlyClose(key))
      f = LMin(f, g_early_sec);
   if(DowOf(key) == 5)
      f = LMin(f, g_fri_sec);
   datetime se = SessionEndServer(srv);
   if(se > 0)
     {
      long sl = (long)ServerToLondon(se) - (long)key - (long)InpSessionEndBufferMin * 60;
      f = LMin(f, sl);
     }
   g_flat_min = mn; g_flat_key = key; g_flat_val = f;
   return f;
  }

//+------------------------------------------------------------------+
//| price / volume helpers                                           |
//+------------------------------------------------------------------+
double NormPrice(const double p)
  {
   if(g_tick <= 0) return NormalizeDouble(p, g_digits);
   return NormalizeDouble(MathRound(p / g_tick) * g_tick, g_digits);
  }
double StopsDist()
  {
   long sl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   return (double)sl * g_point;
  }
double FreezeDist()
  {
   long fl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   return (double)fl * g_point;
  }
bool TradingAllowed()
  {
   if(g_tester) return true;
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
     {
      LogT("notrade", "Algo trading is disabled (terminal/EA/account) - no orders sent", 300);
      return false;
     }
   return true;
  }

// value of a 1.0 price move for 1 lot, in account currency
double ValuePerPriceLot()
  {
   double p = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double profit = 0.0;
   if(p > 1.0 && OrderCalcProfit(ORDER_TYPE_BUY, _Symbol, 1.0, p, p - 1.0, profit) && profit < 0.0)
      return -profit;
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv > 0.0 && ts > 0.0) return tv / ts;
   return g_contract;
  }

// lots for a planned SL distance; 0 (with why) if the trade must be skipped
double CalcVolume(const double dist, string &why)
  {
   why = "";
   double vpl = ValuePerPriceLot();
   g_d.val_per_price_lot = vpl;
   double loss_lot = dist * vpl + InpCommissionPerLot;
   if(loss_lot <= 0.0) { why = "cannot evaluate the loss per lot"; return 0.0; }
   double vol, money = 0.0;
   if(InpFixedLots > 0.0)
      vol = InpFixedLots;
   else
     {
      double base = (InpRiskBase == ARB_RISK_EQUITY) ? AccountInfoDouble(ACCOUNT_EQUITY) : AccountInfoDouble(ACCOUNT_BALANCE);
      money = base * InpRiskPercent / 100.0;
      vol = money / loss_lot;
     }
   double raw = vol;
   vol = MathFloor(vol / g_vstep + 1e-9) * g_vstep;              // round DOWN, never over-risk
   if(vol > g_vmax) vol = MathFloor(g_vmax / g_vstep + 1e-9) * g_vstep;
   if(InpMaxLots > 0.0 && vol > InpMaxLots) vol = MathFloor(InpMaxLots / g_vstep + 1e-9) * g_vstep;
   vol = NormalizeDouble(vol, g_vdigits);
   if(vol < g_vmin - 1e-12)
     {
      why = StringFormat("volume %.4f lots (risk %.2f / loss per lot %.2f) is below the minimum %.2f - trade skipped instead of over-risking",
                         raw, money, loss_lot, g_vmin);
      return 0.0;
     }
   double margin = 0.0;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, vol, ask, margin) && margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
     {
      why = StringFormat("insufficient free margin for %.2f lots (need %.2f, free %.2f)", vol, margin,
                         AccountInfoDouble(ACCOUNT_MARGIN_FREE));
      return 0.0;
     }
   return vol;
  }

//+------------------------------------------------------------------+
//| trade wrappers with retcode handling                             |
//+------------------------------------------------------------------+
bool RcOk(const uint rc)
  {
   return rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL ||
          rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_NO_CHANGES;
  }
bool RcRetry(const uint rc)
  {
   return rc == TRADE_RETCODE_REQUOTE || rc == TRADE_RETCODE_PRICE_CHANGED || rc == TRADE_RETCODE_PRICE_OFF ||
          rc == TRADE_RETCODE_TIMEOUT || rc == TRADE_RETCODE_CONNECTION || rc == TRADE_RETCODE_TOO_MANY_REQUESTS ||
          rc == TRADE_RETCODE_LOCKED || rc == TRADE_RETCODE_REJECT || rc == 0;
  }
string RcText() { return StringFormat("%u %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()); }

// TRADE_RETCODE_INVALID_FILL: switch the CTrade filling policy to the next one the symbol allows
// (SetTypeFillingBySymbol picks one for market orders; some servers want another one for stop orders)
bool NextFilling()
  {
   static int tried = 0;
   int fm = (int)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   ENUM_ORDER_TYPE_FILLING cand[3] = {ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN};
   for(int k = tried; k < 3; k++)
     {
      tried = k + 1;
      bool ok = (k == 0 && (fm & SYMBOL_FILLING_FOK) != 0) || (k == 1 && (fm & SYMBOL_FILLING_IOC) != 0) || k == 2;
      if(!ok || cand[k] == g_trade.RequestTypeFilling()) continue;
      g_trade.SetTypeFilling(cand[k]);
      Log(StringFormat("unsupported filling mode: switching to %s", EnumToString(cand[k])));
      return true;
     }
   return false;
  }

bool OpMarket(const int dir, const double vol, double sl, const string cmt, uint &rc)
  {
   rc = 0;
   if(!TradingAllowed()) return false;
   for(int a = 0; a <= InpMaxRetries; a++)
     {
      if(a > 0) Sleep(300);
      bool sent = (dir > 0) ? g_trade.Buy(vol, _Symbol, 0.0, sl, 0.0, cmt)
                            : g_trade.Sell(vol, _Symbol, 0.0, sl, 0.0, cmt);
      rc = g_trade.ResultRetcode();
      if(sent && RcOk(rc)) return true;
      Log(StringFormat("market %s %.2f attempt %d failed: %s", dir > 0 ? "BUY" : "SELL", vol, a + 1, RcText()));
      if(rc == TRADE_RETCODE_INVALID_STOPS && sl != 0.0) { sl = 0.0; continue; } // SL is set after the fill
      if(rc == TRADE_RETCODE_INVALID_FILL && NextFilling()) continue;
      if(!RcRetry(rc)) break;
     }
   return false;
  }
bool OpPending(const int dir, const double vol, const double price, double sl, ENUM_ORDER_TYPE_TIME tt,
               datetime expiry, const string cmt, uint &rc)
  {
   rc = 0;
   if(!TradingAllowed()) return false;
   for(int a = 0; a <= InpMaxRetries; a++)
     {
      if(a > 0) Sleep(300);
      bool sent = (dir > 0) ? g_trade.BuyStop(vol, price, _Symbol, sl, 0.0, tt, expiry, cmt)
                            : g_trade.SellStop(vol, price, _Symbol, sl, 0.0, tt, expiry, cmt);
      rc = g_trade.ResultRetcode();
      if(sent && RcOk(rc)) return true;
      Log(StringFormat("%s at %s attempt %d failed: %s", dir > 0 ? "BUY STOP" : "SELL STOP", Px(price), a + 1, RcText()));
      if(rc == TRADE_RETCODE_INVALID_STOPS && sl != 0.0) { sl = 0.0; continue; }
      if(rc == TRADE_RETCODE_INVALID_FILL && NextFilling()) continue;
      if(rc == TRADE_RETCODE_INVALID_EXPIRATION)
        {
         // fall back SPECIFIED -> GTC -> DAY (DAY ends at the broker's day end, after entry_end)
         if(tt == ORDER_TIME_SPECIFIED && (g_exp_mode & SYMBOL_EXPIRATION_GTC) != 0) { tt = ORDER_TIME_GTC; expiry = 0; continue; }
         if(tt != ORDER_TIME_DAY && (g_exp_mode & SYMBOL_EXPIRATION_DAY) != 0)      { tt = ORDER_TIME_DAY; expiry = 0; continue; }
        }
      if(!RcRetry(rc)) break;
     }
   return false;
  }
bool OpModify(const ulong ticket, const double sl, const double tp)
  {
   if(!TradingAllowed()) return false;
   for(int a = 0; a <= InpMaxRetries; a++)
     {
      if(a > 0) Sleep(300);
      bool sent = g_trade.PositionModify(ticket, sl, tp);
      uint rc = g_trade.ResultRetcode();
      if(sent && RcOk(rc)) return true;
      Log(StringFormat("modify #%I64u SL %s TP %s attempt %d failed: %s", ticket, Px(sl), Px(tp), a + 1, RcText()));
      if(!RcRetry(rc)) break;
     }
   return false;
  }
bool OpClose(const ulong ticket, const string why)
  {
   if(!TradingAllowed()) return false;
   for(int a = 0; a <= InpMaxRetries; a++)
     {
      if(a > 0) Sleep(300);
      if(!PositionSelectByTicket(ticket)) return true;          // already gone
      bool sent = g_trade.PositionClose(ticket, (ulong)InpDeviationPoints);
      uint rc = g_trade.ResultRetcode();
      if(sent && RcOk(rc)) { Log(StringFormat("closed #%I64u (%s) at %s", ticket, why, Px(g_trade.ResultPrice()))); return true; }
      LogT("close" + IntegerToString((long)ticket), StringFormat("close #%I64u (%s) attempt %d failed: %s", ticket, why, a + 1, RcText()), 30);
      if(!RcRetry(rc)) break;
     }
   return false;
  }
bool OpDelete(const ulong ticket)
  {
   if(!TradingAllowed()) return false;
   for(int a = 0; a <= InpMaxRetries; a++)
     {
      if(a > 0) Sleep(300);
      if(!OrderSelect(ticket)) return true;
      bool sent = g_trade.OrderDelete(ticket);
      uint rc = g_trade.ResultRetcode();
      if(sent && RcOk(rc)) return true;
      LogT("del" + IntegerToString((long)ticket), StringFormat("delete order #%I64u attempt %d failed: %s", ticket, a + 1, RcText()), 30);
      if(!RcRetry(rc)) break;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| our orders / positions / deals                                   |
//+------------------------------------------------------------------+
bool IsOurOrder()
  {
   return OrderGetString(ORDER_SYMBOL) == _Symbol && OrderGetInteger(ORDER_MAGIC) == InpMagic;
  }
// finds our live pending stop orders (0 if none)
void FindPendings(ulong &buy_tk, ulong &sell_tk, double &buy_px, double &sell_px)
  {
   buy_tk = 0; sell_tk = 0; buy_px = 0; sell_px = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong tk = OrderGetTicket(i);
      if(tk == 0 || !IsOurOrder()) continue;
      ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(ot == ORDER_TYPE_BUY_STOP)  { buy_tk = tk;  buy_px = OrderGetDouble(ORDER_PRICE_OPEN); }
      if(ot == ORDER_TYPE_SELL_STOP) { sell_tk = tk; sell_px = OrderGetDouble(ORDER_PRICE_OPEN); }
     }
  }
bool HasPendings()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong tk = OrderGetTicket(i);
      if(tk != 0 && IsOurOrder()) return true;
     }
   return false;
  }
// pending orders placed on an earlier London day (EA was offline at entry_end and the broker has no expiry)
void DeleteStalePendings()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0 || !IsOurOrder()) continue;
      datetime st = (datetime)OrderGetInteger(ORDER_TIME_SETUP);
      if(DayStart(ServerToLondon(st)) != g_d.key)
        {
         if(OpDelete(t)) Log(StringFormat("deleted stale pending #%I64u from %s", t, TS(st)));
        }
     }
  }
// deletes all our pending orders; false if one could not be deleted now (e.g. freeze level)
bool DeletePendings(const string why)
  {
   bool all = true;
   MqlTick tk;
   bool have = SymbolInfoTick(_Symbol, tk);
   double fz = FreezeDist();
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0 || !IsOurOrder()) continue;
      double op = OrderGetDouble(ORDER_PRICE_OPEN);
      ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(have && fz > 0.0)
        {
         double ref = (ot == ORDER_TYPE_BUY_STOP || ot == ORDER_TYPE_BUY_LIMIT) ? tk.ask : tk.bid;
         if(MathAbs(ref - op) <= fz)
           {
            LogT("freeze", StringFormat("order #%I64u at %s is inside the freeze level - retry delete later", t, Px(op)), 30);
            all = false;
            continue;
           }
        }
      if(OpDelete(t))
        {
         if(ot == ORDER_TYPE_BUY_STOP)  g_d.seen_l = 0;
         if(ot == ORDER_TYPE_SELL_STOP) g_d.seen_s = 0;
         LogV(StringFormat("deleted pending #%I64u at %s (%s)", t, Px(op), why));
        }
      else
         all = false;
     }
   return all;
  }
// our positions (today_only: opened on the current London day g_d.key)
int OurPositions(ulong &tks[], const bool today_only = false)
  {
   ArrayResize(tks, 0);
   long tms[];
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(today_only && DayStart(ServerToLondon((datetime)PositionGetInteger(POSITION_TIME))) != g_d.key) continue;
      ArrayResize(tks, n + 1);
      ArrayResize(tms, n + 1);
      tks[n] = tk;
      tms[n] = PositionGetInteger(POSITION_TIME_MSC);
      n++;
     }
   // sort by open time (earliest first)
   for(int a = 1; a < n; a++)
      for(int b = a; b > 0 && tms[b] < tms[b - 1]; b--)
        {
         long tt = tms[b]; tms[b] = tms[b - 1]; tms[b - 1] = tt;
         ulong kk = tks[b]; tks[b] = tks[b - 1]; tks[b - 1] = kk;
        }
   return n;
  }
// today's (London day) deals of this EA
void ResetDeals(SDeals &d)
  {
   d.entries = 0; d.long_used = false; d.short_used = false; d.first_dir = 0;
   d.entry_px = 0; d.exit_px = 0; d.vol = 0; d.pnl = 0; d.entry_t = 0; d.exit_t = 0; d.closed = false;
  }
void ScanDeals(const datetime key, SDeals &d)
  {
   ResetDeals(d);
   datetime from = LondonToServer(key);
   datetime to = (datetime)((long)NowServer() + 86400);
   if(!HistorySelect(from, to)) return;
   int n = HistoryDealsTotal();
   long pids[];
   long ords[];
   int np = 0, no = 0;
   for(int i = 0; i < n; i++)
     {
      ulong dt = HistoryDealGetTicket(i);
      if(dt == 0) continue;
      if(HistoryDealGetString(dt, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(dt, DEAL_MAGIC) != InpMagic) continue;
      ENUM_DEAL_ENTRY en = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dt, DEAL_ENTRY);
      if(en != DEAL_ENTRY_IN && en != DEAL_ENTRY_INOUT) continue;
      long pid = HistoryDealGetInteger(dt, DEAL_POSITION_ID);
      long ord = HistoryDealGetInteger(dt, DEAL_ORDER);
      bool seen_p = false, seen_o = false;
      for(int k = 0; k < np; k++) if(pids[k] == pid) seen_p = true;
      for(int k = 0; k < no; k++) if(ords[k] == ord) seen_o = true;
      if(!seen_p) { ArrayResize(pids, np + 1); pids[np++] = pid; }
      if(!seen_o) { ArrayResize(ords, no + 1); ords[no++] = ord; d.entries++; }
      ENUM_DEAL_TYPE ty = (ENUM_DEAL_TYPE)HistoryDealGetInteger(dt, DEAL_TYPE);
      if(ty == DEAL_TYPE_BUY)  d.long_used = true;
      if(ty == DEAL_TYPE_SELL) d.short_used = true;
      if(d.first_dir == 0)
        {
         d.first_dir = (ty == DEAL_TYPE_BUY) ? 1 : -1;
         d.entry_px = HistoryDealGetDouble(dt, DEAL_PRICE);
         d.entry_t = (datetime)HistoryDealGetInteger(dt, DEAL_TIME);
        }
     }
   if(np == 0) return;
   // all deals (entries and exits, whatever their magic) of those positions
   for(int i = 0; i < n; i++)
     {
      ulong dt = HistoryDealGetTicket(i);
      if(dt == 0) continue;
      long pid = HistoryDealGetInteger(dt, DEAL_POSITION_ID);
      bool mine = false;
      for(int k = 0; k < np; k++) if(pids[k] == pid) mine = true;
      if(!mine) continue;
      d.pnl += HistoryDealGetDouble(dt, DEAL_PROFIT) + HistoryDealGetDouble(dt, DEAL_COMMISSION) +
               HistoryDealGetDouble(dt, DEAL_SWAP) + HistoryDealGetDouble(dt, DEAL_FEE);
      ENUM_DEAL_ENTRY en = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dt, DEAL_ENTRY);
      if(en == DEAL_ENTRY_IN) d.vol += HistoryDealGetDouble(dt, DEAL_VOLUME);
      if(en == DEAL_ENTRY_OUT || en == DEAL_ENTRY_OUT_BY)
        {
         d.exit_px = HistoryDealGetDouble(dt, DEAL_PRICE);
         d.exit_t = (datetime)HistoryDealGetInteger(dt, DEAL_TIME);
         d.closed = true;
        }
     }
  }

//+------------------------------------------------------------------+
//| daily summary                                                    |
//+------------------------------------------------------------------+
void FinishDay(const string why)
  {
   if(g_d.summary_done || g_d.key == 0) return;
   g_d.summary_done = true;
   if(g_d.reason == "") g_d.reason = why;
   SDeals dd;
   ScanDeals(g_d.key, dd);
   string head = StringFormat("DAILY SUMMARY %s %s | %s", TimeToString(g_d.key, TIME_DATE),
                              StringSubstr("SunMonTueWedThuFriSat", DowOf(g_d.key) * 3, 3), P.name);
   string rng = g_d.computed ? StringFormat("range H %s L %s W %s (%d bars) ATR14 %s W/ATR %.3f regime %s",
                                            Px(g_d.rh), Px(g_d.rl), Px(g_d.width), g_d.n_range, Px(g_d.atr), g_d.wa,
                                            P.atr_regime_n > 0 ? StringFormat("%.3f", g_d.reg_mean > 0 ? g_d.atr / g_d.reg_mean : 0.0) : "off")
                             : "range not computed";
   string tr;
   if(dd.entries > 0)
     {
      double r_money = g_d.risk * dd.vol * (g_d.val_per_price_lot > 0 ? g_d.val_per_price_lot : ValuePerPriceLot());
      tr = StringFormat("TRADE %s vol %.2f entry %s (%s) exit %s (%s) %s P/L %.2f %s = %.2fR",
                        dd.first_dir > 0 ? "LONG" : "SHORT", dd.vol, Px(dd.entry_px), TS(dd.entry_t),
                        dd.closed ? Px(dd.exit_px) : "-", dd.closed ? TS(dd.exit_t) : "open",
                        g_d.exit_reason, dd.pnl, AccountInfoString(ACCOUNT_CURRENCY),
                        r_money > 0 ? dd.pnl / r_money : 0.0);
      if(dd.entries > 1) tr += StringFormat(" [WARNING %d entries]", dd.entries);
     }
   else
      tr = "NO TRADE: " + g_d.reason;
   Log(head + " | " + rng + " | " + tr);
  }

void Skip(const string why)
  {
   g_d.reason = why;
   g_d.state = DS_DONE;
   GlobalVariableSet(g_skip_name, (double)(long)g_d.key);
   DeletePendings("day skipped");
   Log("SKIP " + TimeToString(g_d.key, TIME_DATE) + ": " + why);
   FinishDay(why);
  }

//+------------------------------------------------------------------+
//| daily features: ATR14_prev and regime mean                       |
//| returns 1 ok, -1 data not ready / insufficient                   |
//+------------------------------------------------------------------+
double AtrEnd(const double &tr[], const int k)
  {
   double s = 0;
   for(int j = k - 13; j <= k; j++) s += tr[j];
   return s / 14.0;
  }
int DailyFeatures(const datetime key, double &atr, double &mean, int &cnt, string &why)
  {
   atr = 0; mean = 0; cnt = 0;
   int need = 15 + (P.atr_regime_n > 1 ? P.atr_regime_n : 1);
   int look_cal = (int)MathCeil((need + 5) * 7.0 / 5.0) + 14;
   double H[], L[], C[];
   int m = 0;
   MqlRates r[];
   ResetLastError();
   if(InpAtrSource == ARB_ATR_LONDON)
     {
      datetime from_s = LondonToServer((datetime)((long)key - (long)look_cal * 86400));
      datetime to_s = (datetime)((long)LondonToServer(key) - 1);
      int n = CopyRates(_Symbol, PERIOD_M1, from_s, to_s, r);
      if(n <= 0) { why = StringFormat("M1 history for London-day ATR not available (CopyRates %d, err %d)", n, GetLastError()); return -1; }
      ArrayResize(H, look_cal + 2); ArrayResize(L, look_cal + 2); ArrayResize(C, look_cal + 2);
      datetime cur = 0;
      for(int i = 0; i < n; i++)
        {
         datetime dk = DayStart(ServerToLondon(r[i].time));
         if(dk >= key) continue;
         int dw = DowOf(dk);
         if(dw == 0 || dw == 6) continue;                      // engine drops weekend London dates
         if(dk != cur)
           {
            if(m >= ArraySize(H)) { ArrayResize(H, m + 16); ArrayResize(L, m + 16); ArrayResize(C, m + 16); }
            H[m] = r[i].high; L[m] = r[i].low; C[m] = r[i].close;
            m++;
            cur = dk;
           }
         else
           {
            if(r[i].high > H[m - 1]) H[m - 1] = r[i].high;
            if(r[i].low < L[m - 1])  L[m - 1] = r[i].low;
            C[m - 1] = r[i].close;
           }
        }
     }
   else
     {
      datetime d0 = DayStart(LondonToServer((datetime)((long)key + g_re_sec)));   // broker day of the entry window
      int n = CopyRates(_Symbol, PERIOD_D1, (datetime)((long)d0 - (long)look_cal * 86400), (datetime)((long)d0 - 1), r);
      if(n <= 0) { why = StringFormat("D1 history not available (CopyRates %d, err %d)", n, GetLastError()); return -1; }
      ArrayResize(H, n); ArrayResize(L, n); ArrayResize(C, n);
      for(int i = 0; i < n; i++)
        {
         int dw = DowOf(r[i].time);
         if(dw == 0 || dw == 6) continue;
         H[m] = r[i].high; L[m] = r[i].low; C[m] = r[i].close;
         m++;
        }
     }
   if(m < 15) { why = StringFormat("only %d completed daily bars before today (need >= 15 for ATR14)", m); return -1; }
   double tr[];
   ArrayResize(tr, m);
   tr[0] = 0;
   for(int k = 1; k < m; k++)
      tr[k] = MathMax(H[k] - L[k], MathMax(MathAbs(H[k] - C[k - 1]), MathAbs(L[k] - C[k - 1])));
   atr = AtrEnd(tr, m - 1);                                     // ATR14 as of the end of the last completed day
   if(P.atr_regime_n > 0)
     {
      double s = 0;
      for(int j = 0; j < P.atr_regime_n; j++)
        {
         int k = m - 1 - j;                                     // atr14_prev of day (today - j) = AtrEnd(k)
         if(k < 14) break;
         s += AtrEnd(tr, k);
         cnt++;
        }
      mean = cnt > 0 ? s / cnt : 0.0;
     }
   return 1;
  }

//+------------------------------------------------------------------+
//| range + filters for London day `key`                             |
//| returns 1 trade, 0 no trade (why), -1 retry later (why)          |
//+------------------------------------------------------------------+
int ComputeDay(const datetime key, string &why)
  {
   why = "";
   g_d.computed = false;
   datetime rs_s = LondonToServer((datetime)((long)key + g_rs_sec));
   datetime re_s = LondonToServer((datetime)((long)key + g_re_sec));
   MqlRates r[];
   ResetLastError();
   int n = CopyRates(_Symbol, PERIOD_M1, rs_s, (datetime)((long)re_s - 1), r);
   if(n < 0) { why = StringFormat("M1 range data not ready (err %d)", GetLastError()); return -1; }
   double expected = (double)(g_re_sec - g_rs_sec) / 60.0;
   if(n < 0.6 * expected)
     {
      if(!g_tester && !SeriesInfoInteger(_Symbol, PERIOD_M1, SERIES_SYNCHRONIZED))
        { why = "M1 history not synchronized yet"; return -1; }
      why = StringFormat("incomplete range: %d of %.0f M1 bars (< 60%%)", n, expected);
      g_d.n_range = n;
      return 0;
     }
   double hi = -DBL_MAX, lo = DBL_MAX;
   for(int i = 0; i < n; i++)
     {
      if(r[i].high > hi) hi = r[i].high;
      if(r[i].low < lo)  lo = r[i].low;
     }
   g_d.rh = hi; g_d.rl = lo; g_d.width = hi - lo; g_d.n_range = n;
   double atr, mean;
   int cnt;
   string w2;
   int fr = DailyFeatures(key, atr, mean, cnt, w2);
   if(fr < 0) { why = w2; return -1; }
   g_d.atr = atr; g_d.reg_mean = mean; g_d.reg_cnt = cnt;
   g_d.computed = true;
   if(!(atr > 0.0)) { why = "ATR14 undefined"; return 0; }
   if(!(g_d.width > 0.0)) { why = "zero range width"; return 0; }
   g_d.wa = g_d.width / atr;
   // levels and risk (computed even for no-trade days, for the log)
   g_d.buf = P.buf_k * g_d.width + P.buf_atr * atr;
   g_d.lvl_l = NormPrice(g_d.rh + g_d.buf);
   g_d.lvl_s = NormPrice(g_d.rl - g_d.buf);
   double risk;
   if(P.sl_ref == 0)      risk = MathMax(P.sl_k * g_d.width, 0.3);
   else if(P.sl_ref == 1) risk = MathMax(P.sl_k * atr, 0.3);
   else                   risk = MathMax(g_d.width + 2.0 * g_d.buf, 0.1);   // planned, from the level
   g_d.risk_plan = risk;
   if(g_d.wa < P.min_w_atr || g_d.wa > P.max_w_atr)
     {
      why = StringFormat("W/ATR %.3f outside [%.2f, %.2f]", g_d.wa, P.min_w_atr, P.max_w_atr);
      return 0;
     }
   if(P.atr_regime_n > 0)
     {
      int mp60 = (int)(P.atr_regime_n * 0.6);
      int mp = (mp60 > 5) ? mp60 : 5;
      if(mp > P.atr_regime_n) mp = P.atr_regime_n;             // engine: min(n, max(5, int(0.6 n)))
      if(cnt < mp) { why = StringFormat("ATR regime undefined (%d of min %d values)", cnt, mp); return 0; }
      if(!(atr <= P.atr_regime_max * mean))
        {
         why = StringFormat("ATR regime: ATR14 %s > %.2f x mean%d %s (ratio %.3f)", Px(atr), P.atr_regime_max,
                            P.atr_regime_n, Px(mean), atr / mean);
         return 0;
        }
     }
   return 1;
  }

//+------------------------------------------------------------------+
//| arm the day at/after range_end                                   |
//+------------------------------------------------------------------+
void Setup(const datetime srv, const datetime key, const MqlTick &tk)
  {
   int dw = DowOf(key);
   if(!P.dow[dw - 1]) { Skip("day-of-week mask"); return; }
   if(P.skip_nfp && dw == 5 && DomOf(key) <= 7) { Skip("first Friday of the month (skip_nfp)"); return; }
   if(InpSkipFullHolidays && IsFullHoliday(key)) { Skip("full market holiday (Dec 25 / Jan 1 / Good Friday)"); return; }
   ENUM_SYMBOL_TRADE_MODE tm = (ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(tm != SYMBOL_TRADE_MODE_FULL) { Skip("symbol trade mode is not FULL (long and short needed)"); return; }
   if(srv < g_d.next_setup_try) return;
   // Live, OnTimer runs on TimeTradeServer(): wait for the first real tick at/after range_end, so the
   // last range bar is complete (late ticks stamped before range_end) and the heavy ComputeDay is not
   // repeated every second while no bar exists yet. Engine: no bar within 30 min -> invalid day.
   datetime re_s = LondonToServer((datetime)((long)key + g_re_sec));
   if((long)tk.time < (long)re_s)
     {
      if((long)srv - (long)re_s >= 1800) Skip("no tick within 30 min after range_end (session gap)");
      return;
     }
   string why;
   int rc = ComputeDay(key, why);
   if(rc < 0)
     {
      g_d.next_setup_try = (datetime)((long)srv + 60);
      g_d.reason = why;
      LogT("setup", "setup retry: " + why, 300);
      return;
     }
   if(rc == 0) { Skip(why); return; }
   // engine: the first bar at/after range_end must start < 30 min after range_end (same session)
   MqlRates b[];
   int nb = CopyRates(_Symbol, PERIOD_M1, re_s, srv, b);
   if(nb < 0) { g_d.next_setup_try = (datetime)((long)srv + 10); return; }
   if(nb == 0)
     {
      if((long)srv - (long)re_s >= 1800) Skip("no M1 bar within 30 min after range_end (session gap)");
      return;
     }
   if((long)b[0].time - (long)re_s >= 1800) { Skip("first bar after range_end is >= 30 min late (engine: invalid day)"); return; }
   // breakout already happened on bars the EA did not watch (late start / restart / data delay)
   datetime cur_bar = MinuteStart(srv);
   for(int i = 0; i < nb; i++)
     {
      if(b[i].time >= cur_bar) continue;
      bool xl = b[i].high + b[i].spread * g_point >= g_d.lvl_l;  // ASK high ~ BID high + bar spread
      bool xs = b[i].low <= g_d.lvl_s;
      if(xl || xs)
        {
         Skip(StringFormat("breakout already happened at %s (server) before the EA could arm - missed, not chased",
                           TS(b[i].time)));
         return;
        }
     }
   double spread = tk.ask - tk.bid;
   if(spread > InpMaxSpread && InpWideSpreadAtPlacement == ARB_WS_SKIP)
     {
      Skip(StringFormat("spread %s > max %s at placement", Px(spread), Px(InpMaxSpread)));
      return;
     }
   string vwhy;
   double vol = CalcVolume(g_d.risk_plan, vwhy);
   if(vol <= 0.0) { Skip(vwhy); return; }
   g_d.volume = vol;
   g_d.decision = true;
   g_d.armed_l = true;
   g_d.armed_s = true;
   g_d.state = DS_ARMED;
   g_d.reason = "";
   Log(StringFormat("ARMED %s | range %s-%s London H %s L %s W %s (%d bars) | ATR14 %s W/ATR %.3f | regime %s | BUY STOP %s SELL STOP %s | SL dist %s | %.2f lots | spread %s",
                    TimeToString(key, TIME_DATE), HM(g_rs_sec), HM(g_re_sec), Px(g_d.rh), Px(g_d.rl), Px(g_d.width), g_d.n_range,
                    Px(g_d.atr), g_d.wa,
                    P.atr_regime_n > 0 ? StringFormat("%s/%s=%.3f", Px(g_d.atr), Px(g_d.reg_mean), g_d.atr / g_d.reg_mean) : "off",
                    Px(g_d.lvl_l), Px(g_d.lvl_s), Px(g_d.risk_plan), vol, Px(spread)));
  }

//+------------------------------------------------------------------+
//| pending placement / virtual triggers                             |
//+------------------------------------------------------------------+
string Cmt(const int dir) { return StringFormat("ARB %s %s", dir > 0 ? "L" : "S", TimeToString(g_d.key, TIME_DATE)); }

void TryPlace(const int dir, const datetime srv, const MqlTick &tk)
  {
   double price = dir > 0 ? g_d.lvl_l : g_d.lvl_s;
   double stops = MathMax(StopsDist(), FreezeDist());
   bool too_close = dir > 0 ? (price - tk.ask <= stops + 0.5 * g_tick) : (tk.bid - price <= stops + 0.5 * g_tick);
   if(too_close)
     {
      // closer than the broker allows: the EA watches the level itself and sends a market order on the touch
      if(dir > 0 && !g_d.virt_logged_l) { LogV(StringFormat("BUY level %s within stops level of ASK %s: EA-side trigger", Px(price), Px(tk.ask))); g_d.virt_logged_l = true; }
      if(dir < 0 && !g_d.virt_logged_s) { LogV(StringFormat("SELL level %s within stops level of BID %s: EA-side trigger", Px(price), Px(tk.bid))); g_d.virt_logged_s = true; }
      return;
     }
   double sl = 0.0;
   if(P.sl_ref == 2) sl = dir > 0 ? g_d.rl - g_d.buf : g_d.rh + g_d.buf;
   else              sl = price - dir * g_d.risk_plan;
   sl = NormPrice(sl);
   if(MathAbs(price - sl) <= StopsDist()) sl = 0.0;          // provisional SL only; the real one is set after the fill
   ENUM_ORDER_TYPE_TIME tt = ORDER_TIME_GTC;
   if((g_exp_mode & SYMBOL_EXPIRATION_GTC) == 0 && (g_exp_mode & SYMBOL_EXPIRATION_DAY) != 0)
      tt = ORDER_TIME_DAY;
   datetime expiry = 0;
   if((g_exp_mode & SYMBOL_EXPIRATION_SPECIFIED) != 0)
     {
      long cut = LMin(g_ee_sec, FlattenSec(srv, g_d.key));
      expiry = LondonToServer((datetime)((long)g_d.key + cut));
      if((long)expiry > (long)srv + 120) tt = ORDER_TIME_SPECIFIED;   // broker-side backstop for entry_end
      else expiry = 0;
     }
   uint rc;
   if(OpPending(dir, g_d.volume, price, sl, tt, expiry, Cmt(dir), rc))
      Log(StringFormat("placed %s %.2f at %s (provisional SL %s)%s", dir > 0 ? "BUY STOP" : "SELL STOP", g_d.volume,
                       Px(price), Px(sl), tt == ORDER_TIME_SPECIFIED ? " expiry " + TS(expiry) : ""));
  }

void MarketEntry(const int dir, const MqlTick &tk)
  {
   if(g_d.entry_sent_at > 0 && (long)NowServer() - (long)g_d.entry_sent_at < 10) return;
   double ref = dir > 0 ? tk.ask : tk.bid;
   double sl = (P.sl_ref == 2) ? (dir > 0 ? g_d.rl - g_d.buf : g_d.rh + g_d.buf) : ref - dir * g_d.risk_plan;
   sl = NormPrice(sl);
   if(MathAbs(ref - sl) <= StopsDist()) sl = 0.0;
   uint rc;
   g_d.entry_sent_at = NowServer();
   Log(StringFormat("EA-side trigger: %s level %s touched (ASK %s BID %s) -> market order", dir > 0 ? "BUY" : "SELL",
                    Px(dir > 0 ? g_d.lvl_l : g_d.lvl_s), Px(tk.ask), Px(tk.bid)));
   if(!OpMarket(dir, g_d.volume, sl, Cmt(dir), rc))
     {
      if(rc == TRADE_RETCODE_MARKET_CLOSED || RcRetry(rc)) { g_d.entry_sent_at = 0; return; }   // try again next tick
      Skip("market entry failed: " + RcText());
     }
  }

void ManageArmed(const datetime srv, const MqlTick &tk)
  {
   ulong btk, stk;
   double bpx, spx;
   FindPendings(btk, stk, bpx, spx);
   if(btk != 0) g_d.seen_l = srv;
   if(stk != 0) g_d.seen_s = srv;
   // a restored pending whose price does not match today's level is replaced
   if(btk != 0 && MathAbs(bpx - g_d.lvl_l) > 0.5 * g_tick) { DeletePendings("level mismatch"); return; }
   if(stk != 0 && MathAbs(spx - g_d.lvl_s) > 0.5 * g_tick) { DeletePendings("level mismatch"); return; }
   double spread = tk.ask - tk.bid;
   bool cross_l = g_d.armed_l && tk.ask >= g_d.lvl_l;
   bool cross_s = g_d.armed_s && tk.bid <= g_d.lvl_s;
   if(spread > InpMaxSpread)
     {
      if(btk != 0 || stk != 0) DeletePendings("spread wide");
      if(!g_d.paused) { Log(StringFormat("spread %s > max %s: orders paused", Px(spread), Px(InpMaxSpread))); g_d.paused = true; }
      if(cross_l || cross_s) Skip(StringFormat("breakout while spread %s > max %s (engine skips the day)", Px(spread), Px(InpMaxSpread)));
      return;
     }
   if(g_d.paused) { LogV("spread back to normal: re-arming"); g_d.paused = false; g_d.next_place_try = 0; }
   if(cross_l && cross_s) { Skip("both levels crossed at once"); return; }
   // Live race: a broker-side stop that has just triggered leaves the order list before the position
   // (or its deal) shows up. Do not send a second (market) entry for it; wait for the fill to sync.
   if((cross_l && btk == 0 && g_d.seen_l > 0 && (long)srv - (long)g_d.seen_l < 10) ||
      (cross_s && stk == 0 && g_d.seen_s > 0 && (long)srv - (long)g_d.seen_s < 10))
     {
      g_deal_flag = true;
      LogT("trigwait", "stop order left the order list at the level - waiting for the fill to sync (no second entry)", 30);
      return;
     }
   if(cross_l && btk == 0) { if(stk != 0 && !DeletePendings("OCO before market entry")) return; MarketEntry(1, tk); return; }
   if(cross_s && stk == 0) { if(btk != 0 && !DeletePendings("OCO before market entry")) return; MarketEntry(-1, tk); return; }
   if(cross_l || cross_s) return;                 // a live stop order is being triggered by the server
   if(!InpUsePendingOrders || !g_stop_orders_ok) return;
   if(srv < g_d.next_place_try) return;
   bool need = (g_d.armed_l && btk == 0) || (g_d.armed_s && stk == 0);
   if(!need) return;
   g_d.next_place_try = (datetime)((long)srv + InpReplaceThrottleSec);
   if(g_d.armed_l && btk == 0) TryPlace(1, srv, tk);
   if(g_d.armed_s && stk == 0) TryPlace(-1, srv, tk);
  }

//+------------------------------------------------------------------+
//| position management                                              |
//+------------------------------------------------------------------+
void OnFilled(const ulong ticket, const datetime srv)
  {
   if(!PositionSelectByTicket(ticket)) return;
   int dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double fill = PositionGetDouble(POSITION_PRICE_OPEN);
   double cur_sl = PositionGetDouble(POSITION_SL);
   datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
   if(!g_d.computed)
     {
      string why;
      ComputeDay(g_d.key, why);                  // deterministic: same range / ATR as when armed
     }
   double risk = 0.0;
   if(g_d.computed && g_d.width > 0.0)
     {
      if(P.sl_ref == 2)
         risk = MathMax(dir > 0 ? fill - (g_d.rl - g_d.buf) : (g_d.rh + g_d.buf) - fill, 0.1);
      else
         risk = g_d.risk_plan;                   // 0 if ATR14 was undefined (sl_ref 1) or not computed
     }
   if(!(risk > 0.0) && cur_sl > 0.0)
      risk = MathAbs(fill - cur_sl);             // fallback: keep the stop the position already has
   if(g_d.val_per_price_lot <= 0) g_d.val_per_price_lot = ValuePerPriceLot();
   g_d.pos_ticket = ticket;
   g_d.dir = dir;
   g_d.fill = fill;
   g_d.risk = risk;
   g_d.entry_bar = MinuteStart(ot);
   g_d.best = fill;
   g_d.best_upto = 0;
   bool was = (g_d.state == DS_INPOS);
   g_d.state = DS_INPOS;
   if(dir > 0) g_d.armed_l = false; else g_d.armed_s = false;
   DeletePendings("OCO: position open");
   if(!was)
      Log(StringFormat("FILLED %s #%I64u %.2f lots at %s (level %s, slippage %s) %s | SL from fill: %s (risk %s)",
                       dir > 0 ? "LONG" : "SHORT", ticket, PositionGetDouble(POSITION_VOLUME), Px(fill),
                       Px(dir > 0 ? g_d.lvl_l : g_d.lvl_s), Px(dir * (fill - (dir > 0 ? g_d.lvl_l : g_d.lvl_s))),
                       TS(ot), Px(fill - dir * risk), Px(risk)));
  }

void UpdateBest(const datetime srv)
  {
   if(P.be_r <= 0.0 && P.trail_r <= 0.0) return;
   datetime cur_bar = MinuteStart(srv);
   datetime from = (datetime)LMax((long)g_d.entry_bar + 60, (long)g_d.best_upto);   // entry bar excluded (engine)
   if(cur_bar <= from) return;
   MqlTick t[];
   int n = CopyTicksRange(_Symbol, t, COPY_TICKS_INFO, (ulong)from * 1000, (ulong)cur_bar * 1000 - 1);
   if(n > 0)
     {
      for(int i = 0; i < n; i++)
        {
         if(g_d.dir > 0 && t[i].bid > 0 && t[i].bid > g_d.best) g_d.best = t[i].bid;
         if(g_d.dir < 0 && t[i].ask > 0 && t[i].ask < g_d.best) g_d.best = t[i].ask;
        }
     }
   else
     {
      MqlRates r[];
      int nr = CopyRates(_Symbol, PERIOD_M1, from, (datetime)((long)cur_bar - 1), r);
      if(nr < 0) return;                              // retry on the next call
      for(int i = 0; i < nr; i++)
        {
         if(g_d.dir > 0 && r[i].high > g_d.best) g_d.best = r[i].high;               // BID high
         double al = r[i].low + r[i].spread * g_point;                                 // ASK low (approx.)
         if(g_d.dir < 0 && al < g_d.best) g_d.best = al;
        }
     }
   g_d.best_upto = cur_bar;
  }

double TargetSL()
  {
   int dir = g_d.dir;
   double sl = g_d.fill - dir * g_d.risk;
   if(P.be_r > 0.0 || P.trail_r > 0.0)
     {
      double gain = dir * (g_d.best - g_d.fill) / g_d.risk;
      bool be = (P.be_r > 0.0 && gain >= P.be_r);
      if(be) sl = dir > 0 ? MathMax(sl, g_d.fill + 0.05) : MathMin(sl, g_d.fill - 0.05);
      if(P.trail_r > 0.0 && (P.be_r <= 0.0 || be))
         sl = dir > 0 ? MathMax(sl, g_d.best - P.trail_r * g_d.risk) : MathMin(sl, g_d.best + P.trail_r * g_d.risk);
     }
   return NormPrice(sl);
  }

void ManagePosition(const datetime srv, const MqlTick &tk)
  {
   // OCO / one trade per day: the opposite stop must not survive a failed delete in OnFilled
   if(srv >= g_d.next_place_try && HasPendings())
     {
      g_d.next_place_try = (datetime)((long)srv + 5);
      DeletePendings("OCO: position open (retry)");
     }
   if(!PositionSelectByTicket(g_d.pos_ticket)) return;
   if(g_d.risk <= 0.0)
     {
      LogT("norisk", "position without a known risk distance (history not ready) - retrying", 60);
      if(srv < g_d.next_setup_try) return;
      g_d.next_setup_try = (datetime)((long)srv + 30);
      string why;
      ComputeDay(g_d.key, why);
      OnFilled(g_d.pos_ticket, srv);
      return;
     }
   double cur_sl = PositionGetDouble(POSITION_SL);
   double cur_tp = PositionGetDouble(POSITION_TP);
   UpdateBest(srv);
   double tsl = TargetSL();
   double ttp = 0.0;
   if(P.tp_r > 0.0 && MinuteStart(srv) > g_d.entry_bar)            // engine: TP not checked on the entry bar
      ttp = NormPrice(g_d.fill + g_d.dir * P.tp_r * g_d.risk);
   bool sl_ok = MathAbs(cur_sl - tsl) < 0.5 * g_tick;
   bool tp_ok = (ttp == 0.0 && cur_tp == 0.0) || (ttp > 0.0 && MathAbs(cur_tp - ttp) < 0.5 * g_tick);
   // EA-side backstops while the broker-side level is not in place
   if(g_d.dir > 0)
     {
      if(!sl_ok && tk.bid <= tsl) { g_d.exit_reason = "SL (EA-side)"; OpClose(g_d.pos_ticket, "EA-side stop"); return; }
      if(ttp > 0.0 && !tp_ok && tk.bid >= ttp) { g_d.exit_reason = "TP (EA-side)"; OpClose(g_d.pos_ticket, "EA-side TP"); return; }
     }
   else
     {
      if(!sl_ok && tk.ask >= tsl) { g_d.exit_reason = "SL (EA-side)"; OpClose(g_d.pos_ticket, "EA-side stop"); return; }
      if(ttp > 0.0 && !tp_ok && tk.ask <= ttp) { g_d.exit_reason = "TP (EA-side)"; OpClose(g_d.pos_ticket, "EA-side TP"); return; }
     }
   if((sl_ok && tp_ok) || srv < g_d.next_modify_try) return;
   double stops = StopsDist();
   double fz = FreezeDist();
   // freeze level: existing SL/TP too close to price cannot be modified now
   if(fz > 0.0)
     {
      double ref = g_d.dir > 0 ? tk.bid : tk.ask;
      if((cur_sl > 0.0 && MathAbs(ref - cur_sl) <= fz) || (cur_tp > 0.0 && MathAbs(ref - cur_tp) <= fz))
        { g_d.next_modify_try = (datetime)((long)srv + 2); return; }
     }
   bool sl_valid = g_d.dir > 0 ? (tk.bid - tsl > stops) : (tsl - tk.ask > stops);
   bool tp_valid = (ttp == 0.0) || (g_d.dir > 0 ? (ttp - tk.bid > stops) : (tk.ask - ttp > stops));
   double send_sl = sl_valid ? tsl : cur_sl;
   double send_tp = tp_valid ? ttp : cur_tp;
   if(MathAbs(send_sl - cur_sl) < 0.5 * g_tick && MathAbs(send_tp - cur_tp) < 0.5 * g_tick)
     { g_d.next_modify_try = (datetime)((long)srv + 2); return; }
   if(OpModify(g_d.pos_ticket, send_sl, send_tp))
      LogV(StringFormat("position #%I64u SL %s -> %s, TP %s -> %s", g_d.pos_ticket, Px(cur_sl), Px(send_sl), Px(cur_tp), Px(send_tp)));
   else
      g_d.next_modify_try = (datetime)((long)srv + 5);
  }

bool CloseAll(const string why)
  {
   ulong tks[];
   int n = OurPositions(tks);
   bool ok = true;
   for(int i = 0; i < n; i++)
      if(!OpClose(tks[i], why)) ok = false;
   return ok;
  }

// positions opened on an earlier London day (outage, restart, weekend) are closed at once
void CloseStale()
  {
   ulong tks[];
   int n = OurPositions(tks);
   for(int i = 0; i < n; i++)
     {
      if(!PositionSelectByTicket(tks[i])) continue;
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
      if(DayStart(ServerToLondon(ot)) != g_d.key)
         OpClose(tks[i], "stale position from an earlier London day");
     }
  }

//+------------------------------------------------------------------+
//| broker state -> day state                                        |
//+------------------------------------------------------------------+
void SyncFromBroker(const datetime srv)
  {
   ulong tks[];
   int np = OurPositions(tks, true);
   bool scan = g_deal_flag || ((g_d.state == DS_ARMED || g_d.state == DS_INPOS) && srv >= g_next_deal_scan);
   SDeals dd;
   ResetDeals(dd);
   if(scan)
     {
      ScanDeals(g_d.key, dd);
      g_deal_flag = false;
      g_next_deal_scan = (datetime)((long)srv + 10);
     }
   // OCO race: both stop orders filled before the EA could delete the second one
   if(np > 1)
     {
      Log(StringFormat("OCO race: %d positions open - keeping the first, closing the rest", np));
      for(int i = 1; i < np; i++) OpClose(tks[i], "OCO race (second fill)");
      np = OurPositions(tks, true);
     }
   if(scan && dd.entries >= 2 && !g_hedging && np > 0)
     {
      Log("OCO race on a netting account: both sides filled - flattening");
      g_d.exit_reason = "OCO race";
      CloseAll("OCO race (netting)");
      g_d.state = DS_DONE;
      DeletePendings("OCO race");
      return;
     }
   if(np >= 1)
     {
      if(g_d.state != DS_INPOS || g_d.pos_ticket != tks[0]) OnFilled(tks[0], srv);
      return;
     }
   if(g_d.state == DS_INPOS)
     {
      g_d.state = DS_DONE;
      if(g_d.exit_reason == "") g_d.exit_reason = "SL/TP";
      DeletePendings("position closed");
      g_deal_flag = true;
      FinishDay("position closed");
      return;
     }
   if(g_d.state == DS_ARMED && scan && dd.entries > 0)
     {
      // opened and closed between two checks (e.g. stopped out on the entry bar)
      g_d.state = DS_DONE;
      g_d.exit_reason = "SL/TP (fast)";
      DeletePendings("OCO after a fast round trip");
      FinishDay("traded");
     }
  }

void RestoreDay(const datetime srv)
  {
   SDeals dd;
   ScanDeals(g_d.key, dd);
   ulong tks[];
   int np = OurPositions(tks, true);
   DeleteStalePendings();
   bool pend = HasPendings();
   if(np > 0 || dd.entries > 0 || pend)
     {
      string why;
      int rc = ComputeDay(g_d.key, why);
      if(rc == 1) { g_d.decision = true; string vw; g_d.volume = CalcVolume(g_d.risk_plan, vw); }
      if(np > 0)
        {
         OnFilled(tks[0], srv);
         Log("restored: open position from today");
         return;
        }
      if(dd.entries > 0)
        {
         g_d.state = DS_DONE;
         g_d.reason = "already traded today";
         if(pend) DeletePendings("restored: already traded");
         Log("restored: already traded today");
         return;
        }
      if(pend)
        {
         if(rc == 1 && g_d.volume > 0.0)
           {
            g_d.state = DS_ARMED; g_d.armed_l = true; g_d.armed_s = true;
            Log(StringFormat("restored: armed with pending orders (BUY %s / SELL %s)", Px(g_d.lvl_l), Px(g_d.lvl_s)));
           }
         else if(rc == 0)
           {
            DeletePendings("restored: filters say no trade");
            g_d.state = DS_DONE; g_d.reason = why;
           }
         // rc < 0: stays IDLE, pending orders are kept until Setup succeeds or the window closes
         return;
        }
     }
   if(GlobalVariableCheck(g_skip_name) && (long)GlobalVariableGet(g_skip_name) == (long)g_d.key)
     {
      g_d.state = DS_DONE;
      g_d.reason = "skipped earlier today (restart)";
      g_d.summary_done = true;
      LogV("restored: day was skipped earlier");
     }
  }

void NewDay(const datetime key, const datetime srv)
  {
   if(g_d.key != 0 && !g_d.summary_done && DowOf(g_d.key) >= 1 && DowOf(g_d.key) <= 5)
      FinishDay(g_d.state == DS_IDLE ? "day ended before setup" : "day ended");
   g_d.Reset(key);
   int dw = DowOf(key);
   if(dw == 0 || dw == 6) return;
   RestoreDay(srv);
   datetime s0 = LondonToServer((datetime)((long)key + g_rs_sec));
   datetime s1 = LondonToServer((datetime)((long)key + g_re_sec));
   datetime s2 = LondonToServer((datetime)((long)key + g_ee_sec));
   datetime s3 = LondonToServer((datetime)((long)key + FlattenSec(srv, key)));
   LogV(StringFormat("new London day %s: range %s-%s, entry_end %s, flat %s (server clock)%s",
                     TimeToString(key, TIME_DATE), TS(s0), TS(s1), TS(s2), TS(s3),
                     ((InpUseUSHolidayCalendar && IsUSEarlyClose(key)) || IsExtraEarlyClose(key)) ? " [US early close]" : ""));
  }

//+------------------------------------------------------------------+
//| main loop                                                        |
//+------------------------------------------------------------------+
void Process()
  {
   if(!g_init_ok) return;
   if(g_clock_halt) { LogT("clockhalt", "trading halted: server clock rule disagrees with TimeGMT() (see init log)", 600); return; }
   datetime srv = NowServer();
   datetime lon = ServerToLondon(srv);
   datetime key = DayStart(lon);
   if(key != g_d.key) NewDay(key, srv);
   long tod = (long)lon - (long)key;
   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk) || tk.bid <= 0.0 || tk.ask <= 0.0) return;
   if(!g_price_checked)
     {
      if(tk.bid < 200.0 || tk.bid > 50000.0)
        {
         Log(StringFormat("price %s does not look like XAUUSD in USD/oz - EA disabled", Px(tk.bid)));
         g_init_ok = false;
         return;
        }
      g_price_checked = true;
     }
   CloseStale();
   int dw = DowOf(key);
   if(dw == 0 || dw == 6) return;
   SyncFromBroker(srv);
   long flat = FlattenSec(srv, key);
   long cut = LMin(g_ee_sec, flat);
   switch(g_d.state)
     {
      case DS_IDLE:
         if(tod >= cut)
           {
            g_d.state = DS_DONE;
            if(HasPendings()) DeletePendings("entry window closed");
            FinishDay(g_d.reason != "" ? "entry window closed before setup: " + g_d.reason : "entry window closed before setup");
           }
         else if(tod >= g_re_sec)
            Setup(srv, key, tk);
         break;
      case DS_ARMED:
         if(tod >= cut)
           {
            if(DeletePendings("entry_end"))
              {
               g_d.state = DS_DONE;
               FinishDay(StringFormat("no breakout before %s London", HM(cut)));
              }
           }
         else
            ManageArmed(srv, tk);
         break;
      case DS_INPOS:
         if(tod >= flat)
           {
            if(g_d.exit_reason == "")
               g_d.exit_reason = (flat < g_ex_sec) ? StringFormat("early flat %s London (session end / holiday / Friday)", HM(flat))
                                                   : StringFormat("time exit %s London", HM(flat));
            CloseAll(g_d.exit_reason);
           }
         else
            ManagePosition(srv, tk);
         break;
      default:
         if(HasPendings()) DeletePendings("day done");
         break;
     }
  }

//+------------------------------------------------------------------+
//| clock setup / checks                                             |
//+------------------------------------------------------------------+
string ClockName(const int c)
  {
   if(c == ARB_CLOCK_GMT2_US) return "GMT+2/+3 (US DST)";
   if(c == ARB_CLOCK_GMT2_EU) return "GMT+2/+3 (EU DST)";
   if(c == ARB_CLOCK_FIXED)   return StringFormat("fixed GMT%+.2f", (double)g_fixed_off / 3600.0);
   return StringFormat("auto (measured GMT%+.2f)", (double)g_auto_off / 3600.0);
  }
void RefreshAutoOffset()
  {
   long d = (long)TimeTradeServer() - (long)TimeGMT();
   g_auto_off = (long)MathRound((double)d / 900.0) * 900;
  }
void CheckClock()
  {
   if(g_tester) return;
   if(g_clock == ARB_CLOCK_AUTO) { RefreshAutoOffset(); return; }
   long diff = (long)ServerToUTC(TimeTradeServer()) - (long)TimeGMT();
   if(MathAbs((double)diff) > 120.0)
     {
      Log(StringFormat("CLOCK CHECK FAILED: rule %s gives UTC %s but TimeGMT() is %s (diff %d s). Fix InpServerClock (or the PC clock).",
                       ClockName(g_clock), TS(ServerToUTC(TimeTradeServer())), TS(TimeGMT()), (int)diff));
      g_clock_halt = InpHaltOnClockMismatch;
     }
   else
      g_clock_halt = false;
  }

void LoadParams()
  {
   // frozen values from final/candidates.json
   P.range_start = 0.0; P.range_end = 5.0; P.entry_end = 12.0; P.exit_time = 20.0;
   P.buf_k = 0.0; P.buf_atr = 0.0; P.sl_ref = 0; P.sl_k = 1.0; P.tp_r = 0.0; P.be_r = 0.0; P.trail_r = 0.0;
   P.max_w_atr = 99.0; P.atr_regime_max = 1.0; P.skip_nfp = false;
   for(int i = 0; i < 5; i++) P.dow[i] = true;
   if(InpPreset == ARB_PRESET_PRIMARY)
     {
      P.name = "PRIMARY re5_w030_a20_W1.00";
      P.min_w_atr = 0.30; P.atr_regime_n = 20;
     }
   else if(InpPreset == ARB_PRESET_FALLBACK)
     {
      P.name = "FALLBACK re5_w035_nor_W1.00";
      P.min_w_atr = 0.35; P.atr_regime_n = 0;
     }
   else
     {
      P.name = "CUSTOM";
      P.range_start = InpRangeStart; P.range_end = InpRangeEnd; P.entry_end = InpEntryEnd; P.exit_time = InpExitTime;
      P.buf_k = InpBufK; P.buf_atr = InpBufAtr; P.sl_ref = InpSlRef; P.sl_k = InpSlK;
      P.tp_r = InpTpR; P.be_r = InpBeR; P.trail_r = InpTrailR;
      P.min_w_atr = InpMinWAtr; P.max_w_atr = InpMaxWAtr;
      P.atr_regime_n = InpAtrRegimeN; P.atr_regime_max = InpAtrRegimeMax;
      P.dow[0] = InpTradeMon; P.dow[1] = InpTradeTue; P.dow[2] = InpTradeWed; P.dow[3] = InpTradeThu; P.dow[4] = InpTradeFri;
      P.skip_nfp = InpSkipNfp;
     }
  }
long HoursToSec(const double h) { return (long)MathRound(h * 60.0) * 60; }   // engine rounds to whole minutes

bool ValidateParams(string &why)
  {
   if(P.range_end <= 0.0)                          { why = "range_end must be > 0 (evening ranges are not supported)"; return false; }
   if(P.range_start < -6.0 || P.range_start >= P.range_end) { why = "need -6 <= range_start < range_end"; return false; }
   if(P.entry_end <= P.range_end)                  { why = "entry_end must be after range_end"; return false; }
   if(P.exit_time < P.entry_end || P.exit_time > 23.5) { why = "need entry_end <= exit_time <= 23.5"; return false; }
   if(P.sl_ref < 0 || P.sl_ref > 2)                { why = "sl_ref must be 0, 1 or 2"; return false; }
   if(P.sl_k <= 0.0)                               { why = "sl_k must be > 0"; return false; }
   if(P.tp_r < 0.0 || P.be_r < 0.0 || P.trail_r < 0.0) { why = "tp_r / be_r / trail_r must be >= 0"; return false; }
   if(P.min_w_atr > P.max_w_atr)                   { why = "min_w_atr > max_w_atr"; return false; }
   if(P.atr_regime_n < 0 || P.atr_regime_n > 250)  { why = "atr_regime_n must be 0..250"; return false; }
   if(InpFixedLots <= 0.0 && (InpRiskPercent <= 0.0 || InpRiskPercent > 10.0)) { why = "risk % must be in (0, 10]"; return false; }
   if(InpMaxSpread <= 0.0)                         { why = "max spread must be > 0"; return false; }
   return true;
  }

//+------------------------------------------------------------------+
//| init / deinit / events                                           |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_tester = (bool)MQLInfoInteger(MQL_TESTER);
   LoadParams();
   string why;
   if(!ValidateParams(why)) { Log("invalid parameters: " + why); return INIT_PARAMETERS_INCORRECT; }
   g_rs_sec = HoursToSec(P.range_start);
   g_re_sec = HoursToSec(P.range_end);
   g_ee_sec = HoursToSec(P.entry_end);
   g_ex_sec = HoursToSec(P.exit_time);
   g_early_sec = HoursToSec(InpEarlyCloseFlatten);
   g_fri_sec = HoursToSec(InpFridayFlatten);

   //--- symbol sanity
   string up = _Symbol;
   StringToUpper(up);
   if(InpRequireGoldSymbol && StringFind(up, "XAU") < 0 && StringFind(up, "GOLD") < 0)
     { Log("symbol " + _Symbol + " is not gold (XAU/GOLD) - refusing (InpRequireGoldSymbol)"); return INIT_FAILED; }
   g_digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   g_point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(g_tick <= 0.0) g_tick = g_point;
   g_contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(g_digits < 1 || g_digits > 3)
     { Log(StringFormat("digits %d look wrong for XAUUSD quoted in USD/oz (expect 2 or 3) - refusing", g_digits)); return INIT_FAILED; }
   if(g_contract <= 0.0 || (InpExpectedContractSize > 0.0 && MathAbs(g_contract - InpExpectedContractSize) > 1e-6))
     { Log(StringFormat("contract size %.4f differs from the expected %.4f oz - refusing (set InpExpectedContractSize)", g_contract, InpExpectedContractSize)); return INIT_FAILED; }
   string pc = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT);
   if(pc != "USD")
      Log("WARNING: profit currency is " + pc + ", not USD. Engine thresholds (0.30 SL floor, 0.05 BE offset, max spread) are USD/oz.");
   if((ENUM_SYMBOL_CHART_MODE)SymbolInfoInteger(_Symbol, SYMBOL_CHART_MODE) != SYMBOL_CHART_MODE_BID)
      Log("WARNING: this symbol's bars are built from LAST prices, not BID. The engine range / ATR are BID-based; results will differ.");
   g_vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   g_vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   g_vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(g_vstep <= 0.0) g_vstep = 0.01;
   g_vdigits = 0;
   double s = g_vstep;
   while(g_vdigits < 8 && MathAbs(s - MathRound(s)) > 1e-9) { s *= 10.0; g_vdigits++; }
   g_exp_mode = (int)SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
   int om = (int)SymbolInfoInteger(_Symbol, SYMBOL_ORDER_MODE);
   g_stop_orders_ok = (om & SYMBOL_ORDER_STOP) != 0;
   if(!g_stop_orders_ok) Log("broker does not allow stop orders on this symbol: EA-side triggers + market orders are used");
   g_hedging = ((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);

   //--- single instance guard
   g_hb_name = StringFormat("ARB_HB_%s_%I64d", _Symbol, InpMagic);
   g_skip_name = StringFormat("ARB_SKIP_%s_%I64d", _Symbol, InpMagic);
   if(!g_tester)
     {
      if(!InpAllowMultipleInstances)
        {
         string me = MQLInfoString(MQL_PROGRAM_NAME);
         long id = ChartFirst();
         int guard = 0;
         while(id >= 0 && guard++ < 1000)
           {
            if(id != ChartID() && ChartSymbol(id) == _Symbol && ChartGetString(id, CHART_EXPERT_NAME) == me)
              { Log("another chart already runs this EA on " + _Symbol + " - refusing (one instance per symbol)"); return INIT_FAILED; }
            id = ChartNext(id);
           }
        }
      if(GlobalVariableCheck(g_hb_name) && (double)TimeLocal() - GlobalVariableGet(g_hb_name) < 10.0)
        { Log("another instance with the same magic number is alive on " + _Symbol + " - refusing"); return INIT_FAILED; }
      GlobalVariableSet(g_hb_name, (double)TimeLocal());
     }

   //--- extra early-close dates
   ArrayResize(g_extra_early, 0);
   if(StringLen(InpExtraEarlyCloseDates) > 0)
     {
      string parts[];
      int np = StringSplit(InpExtraEarlyCloseDates, ',', parts);
      for(int i = 0; i < np; i++)
        {
         string p = parts[i];
         StringTrimLeft(p);
         StringTrimRight(p);
         if(StringLen(p) < 8) continue;
         datetime d = StringToTime(p);
         if(d <= 0) { Log("cannot parse early-close date '" + p + "'"); continue; }
         int k = ArraySize(g_extra_early);
         ArrayResize(g_extra_early, k + 1);
         g_extra_early[k] = DayStart(d);
        }
     }

   //--- clock
   g_clock = (int)InpServerClock;
   g_fixed_off = (long)MathRound(InpFixedOffsetHours * 3600.0);
   if(g_clock == ARB_CLOCK_AUTO)
     {
      if(g_tester)
        {
         Log("WARNING: auto clock is not available in the Strategy Tester (TimeGMT() = server time there). Using GMT+2/+3 US DST.");
         g_clock = ARB_CLOCK_GMT2_US;
        }
      else
         RefreshAutoOffset();
     }
   CheckClock();
   g_next_clock_check = 0;

   //--- trade object
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints((ulong)(InpDeviationPoints > 0 ? InpDeviationPoints : 0));
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.SetMarginMode();
   g_trade.SetAsyncMode(false);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);

   //--- init log
   datetime srv = NowServer();
   datetime utc = ServerToUTC(srv);
   datetime lon = ServerToLondon(srv);
   Log(StringFormat("init %s | %s | clock %s | server %s -> UTC %s (offset %+.1f h) -> London %s (%s)%s",
                    P.name, g_tester ? "TESTER" : "LIVE", ClockName(g_clock), TS(srv), TS(utc),
                    (double)((long)srv - (long)utc) / 3600.0, TS(lon), IsUKDST(utc) ? "BST" : "GMT",
                    (!g_tester) ? " | TimeGMT " + TS(TimeGMT()) : ""));
   Log(StringFormat("params: range %s-%s entry_end %s exit %s London | buf_k %.2f buf_atr %.2f | sl_ref %d sl_k %.2f tp_r %.2f be_r %.2f trail_r %.2f | W/ATR [%.2f, %.2f] | regime n %d max %.2f | dow %d%d%d%d%d | skip_nfp %s | ATR from %s",
                    HM(g_rs_sec), HM(g_re_sec), HM(g_ee_sec), HM(g_ex_sec), P.buf_k, P.buf_atr, P.sl_ref, P.sl_k, P.tp_r, P.be_r, P.trail_r,
                    P.min_w_atr, P.max_w_atr, P.atr_regime_n, P.atr_regime_max,
                    (int)P.dow[0], (int)P.dow[1], (int)P.dow[2], (int)P.dow[3], (int)P.dow[4], P.skip_nfp ? "yes" : "no",
                    InpAtrSource == ARB_ATR_LONDON ? "London-day M1 bars" : "broker D1 bars"));
   Log(StringFormat("symbol: digits %d tick %s contract %.2f vol [%.2f..%.2f step %.2f] stops %d pts freeze %d pts | %s account | risk %s",
                    g_digits, DoubleToString(g_tick, g_digits), g_contract, g_vmin, g_vmax, g_vstep,
                    (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL), (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL),
                    g_hedging ? "hedging" : "netting",
                    InpFixedLots > 0 ? StringFormat("fixed %.2f lots", InpFixedLots) : StringFormat("%.2f%% of %s", InpRiskPercent, InpRiskBase == ARB_RISK_EQUITY ? "equity" : "balance")));
   Log("CAVEAT: the edge is not statistically established (DSR 0.18-0.35, VAL t 0.16). Trade small; see the header.");

   g_d.Reset(0);
   g_init_ok = true;
   if(!g_tester) EventSetTimer(1);
   Process();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(!g_tester)
     {
      EventKillTimer();
      if(GlobalVariableCheck(g_hb_name)) GlobalVariableDel(g_hb_name);
      GlobalVariablesFlush();
     }
   Log(StringFormat("deinit (reason %d). Pending orders and positions are left to the broker-side SL / expiry; state is recovered on restart.", reason));
  }

void OnTick()
  {
   Process();
  }

void OnTimer()
  {
   if(!g_tester)
     {
      GlobalVariableSet(g_hb_name, (double)TimeLocal());
      datetime now = TimeLocal();
      if(now >= g_next_clock_check)
        {
         CheckClock();
         g_next_clock_check = (datetime)((long)now + 3600);
        }
     }
   Process();
  }

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD && trans.symbol == _Symbol)
     {
      g_deal_flag = true;
      Process();
     }
  }
//+------------------------------------------------------------------+
