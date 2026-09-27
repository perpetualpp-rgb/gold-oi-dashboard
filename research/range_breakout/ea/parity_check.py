"""Parity check: Python port of the EA's decision logic (ea/XAU_AsianRangeBreakout.mq5) vs engine.py.

Only data up to engine.VAL_END (2023-12-31) is loaded (engine.load(until=VAL_END)); the holdout is never read.

Checks
 1. Clock: the EA's server<->UTC<->London functions (ported 1:1) vs zoneinfo for every 15 min, 2010-2030,
    for the 'GMT+2/+3 US DST' and 'GMT+2/+3 EU DST' conventions.
 2. Holidays: the EA's US early-close calendar vs the engine's ex_close days (no bar near 20:00 London).
 3. Day decisions for PRIMARY and FALLBACK: the data is re-stamped on a GMT+2/+3 US-DST server clock, then
    the EA algorithm (range from server-time M1 bars, 60% coverage, 30-min rule, London-day ATR14 built
    from M1 over a finite look-back window, regime mean, W/ATR filter, full-holiday skip) is run per
    London day and compared with the engine mask, range, ATR and SL distance.
 4. Same with broker D1 (NY-close) ATR, reported as agreement rate (not expected to be exact).
Usage: python3 ea/parity_check.py
"""
import datetime as dt
import math
import os
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import engine as E  # noqa: E402

# ---------------------------------------------------------------- EA port (seconds since epoch, naive)
EPOCH = dt.datetime(1970, 1, 1)


def make_date(y, m, d):
    return int((dt.datetime(y, m, d) - EPOCH).total_seconds())


def day_start(t):
    return (t // 86400) * 86400


def dow_of(t):                       # 0 = Sunday, like MqlDateTime.day_of_week
    return int(((t // 86400) + 4) % 7)


def days_in_month(y, m):
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (make_date(ny, nm, 1) - make_date(y, m, 1)) // 86400


def nth_weekday(y, m, wd, n):
    first = make_date(y, m, 1)
    add = (wd - dow_of(first) + 7) % 7
    return first + (add + 7 * (n - 1)) * 86400


def last_weekday(y, m, wd):
    last = make_date(y, m, days_in_month(y, m))
    sub = (dow_of(last) - wd + 7) % 7
    return last - sub * 86400


def year_of(t):
    return (EPOCH + dt.timedelta(seconds=int(t))).year


def is_uk_dst(utc):
    y = year_of(utc)
    return last_weekday(y, 3, 0) + 3600 <= utc < last_weekday(y, 10, 0) + 3600


def is_us_dst(utc):
    y = year_of(utc)
    if y >= 2007:
        s, e = nth_weekday(y, 3, 0, 2) + 7 * 3600, nth_weekday(y, 11, 0, 1) + 6 * 3600
    else:
        s, e = nth_weekday(y, 4, 0, 1) + 7 * 3600, last_weekday(y, 10, 0) + 6 * 3600
    return s <= utc < e


class Clock:
    def __init__(self, mode):
        self.mode = mode             # "US" or "EU"

    def off(self, utc):
        return 7200 + (3600 if (is_us_dst(utc) if self.mode == "US" else is_uk_dst(utc)) else 0)

    def server_to_utc(self, s):
        u3 = s - 10800
        return u3 if self.off(u3) == 10800 else s - 7200

    def utc_to_server(self, u):
        return u + self.off(u)


def utc_to_london(u):
    return u + (3600 if is_uk_dst(u) else 0)


def london_to_utc(l):
    u1 = l - 3600
    return u1 if is_uk_dst(u1) else l


def observed_fixed(y, m, d):
    t = make_date(y, m, d)
    w = dow_of(t)
    return t - 86400 if w == 6 else (t + 86400 if w == 0 else t)


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return make_date(y, month, day)


def is_us_early_close(key):
    y = year_of(key)
    tg = nth_weekday(y, 11, 4, 4)
    xe = make_date(y, 12, 24)
    return key in (nth_weekday(y, 1, 1, 3), nth_weekday(y, 2, 1, 3), last_weekday(y, 5, 1),
                   observed_fixed(y, 7, 4), nth_weekday(y, 9, 1, 1), tg, tg + 86400) \
        or (y >= 2022 and key == observed_fixed(y, 6, 19)) or (key == xe and 1 <= dow_of(xe) <= 5)


def is_full_holiday(key):
    y = year_of(key)
    xm, ny = make_date(y, 12, 25), make_date(y, 1, 1)
    obs = [d + 86400 for d in (xm, ny) if dow_of(d) == 0]
    return key in [xm, ny, easter(y) - 2 * 86400] + obs


# ---------------------------------------------------------------- 1. clock check
def check_clock():
    ny, ldn = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
    bad = {"US": 0, "EU": 0, "london": 0}
    n = 0
    t0 = make_date(2010, 1, 1)
    t1 = make_date(2030, 12, 31)
    for u in range(t0, t1, 900):
        n += 1
        ud = dt.datetime.fromtimestamp(u, dt.timezone.utc)
        us_off = 7200 + (3600 if ud.astimezone(ny).dst() else 0)
        eu_off = 7200 + (3600 if ud.astimezone(ldn).dst() else 0)
        lon = u + int(ud.astimezone(ldn).utcoffset().total_seconds())
        for mode, off in (("US", us_off), ("EU", eu_off)):
            c = Clock(mode)
            s = u + off
            if c.utc_to_server(u) != s:
                bad[mode] += 1
            elif c.server_to_utc(s) != u and dow_of(s) not in (0, 6):   # ambiguity only on weekend switch hours
                bad[mode] += 1
        if utc_to_london(u) != lon:
            bad["london"] += 1
        elif london_to_utc(lon) != u and dow_of(lon) != 0:
            bad["london"] += 1
    print(f"[1] clock: {n} instants 2010-2030 every 15 min; mismatches {bad} (weekday instants)")
    return all(v == 0 for v in bad.values())


# ---------------------------------------------------------------- data on a server clock
def _sec(idx):
    """seconds since epoch of a (naive or tz-aware) DatetimeIndex, whatever its unit"""
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.values.astype("datetime64[s]").astype(np.int64)


def server_times(D, clock):
    u = _sec(D["index"])
    # vectorised equivalent of Clock.utc_to_server (validated in check 1)
    tz = "America/New_York" if clock.mode == "US" else "Europe/London"
    loc = D["index"].tz_convert(tz)
    std = -5 * 3600 if clock.mode == "US" else 0
    is_dst = (loc.tz_localize(None).values.astype("datetime64[s]").astype(np.int64) - u) != std
    return u + 7200 + 3600 * is_dst.astype(np.int64)


def london_of_server(s_arr, clock):
    # vectorised Clock.server_to_utc + utc_to_london (validated in check 1)
    u3 = s_arr - 10800
    idx = pd.to_datetime(u3, unit="s", utc=True)
    tz = "America/New_York" if clock.mode == "US" else "Europe/London"
    std = -5 * 3600 if clock.mode == "US" else 0
    loc = idx.tz_convert(tz).tz_localize(None).values.astype("datetime64[s]").astype(np.int64) - u3
    u = np.where(loc != std, u3, s_arr - 7200)
    lidx = pd.to_datetime(u, unit="s", utc=True).tz_convert("Europe/London").tz_localize(None)
    return lidx.values.astype("datetime64[s]").astype(np.int64)


# ---------------------------------------------------------------- 3. EA decisions
def ea_daily_features(key, lday_keys, H, L, C, look_cal, regime_n):
    """DailyFeatures(): London-day bars (arrays over all completed London weekdays, ascending)."""
    lo = np.searchsorted(lday_keys, key - look_cal * 86400)
    hi = np.searchsorted(lday_keys, key)
    h, l_, c = H[lo:hi], L[lo:hi], C[lo:hi]
    m = len(h)
    if m < 15:
        return None, None, 0
    tr = np.zeros(m)
    tr[1:] = np.maximum(h[1:] - l_[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l_[1:] - c[:-1])))

    def atr_end(k):
        return tr[k - 13:k + 1].sum() / 14.0
    atr = atr_end(m - 1)
    s, cnt = 0.0, 0
    for j in range(regime_n):
        k = m - 1 - j
        if k < 14:
            break
        s += atr_end(k)
        cnt += 1
    return atr, (s / cnt if cnt else 0.0), cnt


def run_ea(D, p, clock, atr_source="london"):
    srv = server_times(D, clock)
    lon = london_of_server(srv, clock)
    lkey = (lon // 86400) * 86400
    bh, bl, bc = D["bh"], D["bl"], D["bc"]
    # London-day OHLC (weekdays only), as the EA builds them from M1
    g = pd.DataFrame({"k": lkey, "h": bh, "l": bl, "c": bc})
    g = g[((g["k"] // 86400 + 4) % 7).between(1, 5)]
    agg = g.groupby("k").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    if atr_source == "d1":
        sday = (srv // 86400) * 86400
        g2 = pd.DataFrame({"k": sday, "h": bh, "l": bl, "c": bc})
        g2 = g2[((g2["k"] // 86400 + 4) % 7).between(1, 5)]
        dagg = g2.groupby("k").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    need = 15 + max(p.atr_regime_n, 1)
    look_cal = math.ceil((need + 5) * 7.0 / 5.0) + 14
    rs, re_ = int(round(p.range_start * 60)) * 60, int(round(p.range_end * 60)) * 60
    keys = agg.index.values
    out = {}
    for key in keys:
        key = int(key)
        dw = dow_of(key)
        rec = dict(dec=False, rh=np.nan, rl=np.nan, atr=np.nan, mean=np.nan, risk=np.nan, why="")
        out[key] = rec
        if not p.dow_mask[dw - 1]:
            rec["why"] = "dow"; continue
        if is_full_holiday(key):
            rec["why"] = "holiday"; continue
        rs_s = clock.utc_to_server(london_to_utc(key + rs))
        re_s = clock.utc_to_server(london_to_utc(key + re_))
        a, b = np.searchsorted(srv, rs_s), np.searchsorted(srv, re_s)      # [rs_s, re_s - 1]
        n = b - a
        if n < 0.6 * (re_ - rs) / 60:
            rec["why"] = "coverage"; continue
        if b >= len(srv) or srv[b] - re_s >= 1800:
            rec["why"] = "30min"; continue
        rh, rl = bh[a:b].max(), bl[a:b].min()
        rec.update(rh=rh, rl=rl)
        if atr_source == "london":
            atr, mean, cnt = ea_daily_features(key, keys, agg["h"].values, agg["l"].values, agg["c"].values,
                                               look_cal, p.atr_regime_n)
        else:
            d0 = (re_s // 86400) * 86400
            atr, mean, cnt = ea_daily_features(d0, dagg.index.values, dagg["h"].values, dagg["l"].values,
                                               dagg["c"].values, look_cal, p.atr_regime_n)
        if atr is None:
            rec["why"] = "history"; continue
        rec.update(atr=atr, mean=mean)
        w = rh - rl
        if not (atr > 0 and w > 0):
            rec["why"] = "zero"; continue
        rec["risk"] = max(p.sl_k * w, 0.3) if p.sl_ref == 0 else max(p.sl_k * atr, 0.3)
        wa = w / atr
        if wa < p.min_w_atr or wa > p.max_w_atr:
            rec["why"] = "w_atr"; continue
        if p.atr_regime_n > 0:
            mp = min(p.atr_regime_n, max(5, int(p.atr_regime_n * 0.6)))
            if cnt < mp or not (atr <= p.atr_regime_max * mean):
                rec["why"] = "regime"; continue
        rec["dec"] = True
    return out


def engine_mask(D, p):
    days = D["days"]
    i_rs, i_re, i_ee, i_ex, rh, rl, valid, ex_close = E._windows_full(D, p.range_start, p.range_end,
                                                                        p.entry_end, p.exit_time)
    width = rh - rl
    atr = days["atr14_prev"].values
    mask = valid & np.isfinite(atr) & (width > 0)
    wa = width / atr
    mask &= (wa >= p.min_w_atr) & (wa <= p.max_w_atr)
    if p.atr_regime_n > 0:
        n = p.atr_regime_n
        mp = min(n, max(5, int(n * 0.6)))
        ma = pd.Series(atr).rolling(n, min_periods=mp).mean().values
        mask &= np.isfinite(ma) & (atr <= p.atr_regime_max * ma)
    mask &= np.array(p.dow_mask, dtype=bool)[days.index.dayofweek.values]
    keys = (days.index.values.astype("datetime64[s]").astype(np.int64))
    return keys, mask, rh, rl, atr, ex_close


def compare(D, name, p, clock, source="london", start="2014-03-01"):
    ea = run_ea(D, p, clock, source)
    keys, mask, rh, rl, atr, _ = engine_mask(D, p)
    s0 = int(pd.Timestamp(start).value // 10**9)
    sel = keys >= s0                      # skip the first weeks (ATR / regime warm-up differs by design)
    both = only_e = only_ea = 0
    lvl_bad = atr_bad = 0
    diffs = []
    for k, m, h, l_, a in zip(keys[sel], mask[sel], rh[sel], rl[sel], atr[sel]):
        r = ea.get(int(k))
        d = bool(r and r["dec"])
        if m and d:
            both += 1
            if abs(r["rh"] - h) > 1e-9 or abs(r["rl"] - l_) > 1e-9:
                lvl_bad += 1
            if abs(r["atr"] - a) > 1e-6:
                atr_bad += 1
        elif m:
            only_e += 1
            diffs.append((pd.Timestamp(int(k), unit="s").date(), "engine only", r["why"] if r else "no EA day"))
        elif d:
            only_ea += 1
            diffs.append((pd.Timestamp(int(k), unit="s").date(), "EA only", ""))
    tot = both + only_e + only_ea
    print(f"[3] {name} ATR={source}: armed days both {both}, engine-only {only_e}, EA-only {only_ea} "
          f"(agreement {both / max(tot, 1):.4f}); range mismatches {lvl_bad}, ATR mismatches {atr_bad}")
    for x in diffs[:12]:
        print("     ", x)
    return only_e, only_ea, lvl_bad, atr_bad, diffs


def check_holidays(D):
    p = E.Params(range_end=5)
    keys, _, _, _, _, ex_close = engine_mask(D, p)
    days = D["days"]
    sel = (days.index >= "2014-01-01") & (days.index <= E.VAL_END)
    ex = set(int(k) for k in keys[sel & ex_close])
    cal = set(int(k) for k in keys[sel] if is_us_early_close(int(k)))
    fri = set(k for k in ex if dow_of(k) == 5 and k not in cal)
    print(f"[2] early close: engine ex_close days {len(ex)}, EA calendar days {len(cal)}, both {len(ex & cal)}")
    print("     engine-only:", sorted(str(pd.Timestamp(k, unit='s').date()) for k in ex - cal))
    print("     EA-calendar-only (market open at 20:00 in the data):",
          sorted(str(pd.Timestamp(k, unit='s').date()) for k in cal - ex))
    # last bar before 20:00 London on calendar days (engine flat time) vs EA default 17:45
    lmin = D["lmin"]
    lasts = []
    for k in sorted(cal & ex):
        t_ex = k // 60 + 20 * 60
        i = np.searchsorted(lmin, t_ex) - 1
        lasts.append((lmin[i] - k // 60) / 60.0)
    if lasts:
        print(f"     engine flat time on those days (last bar before 20:00, London h): min {min(lasts):.2f} "
              f"median {np.median(lasts):.2f} max {max(lasts):.2f}  (EA default 17.50)")
    return ex, cal


def main():
    ok_clock = check_clock()
    D = E.load(until=E.VAL_END)
    assert D["index"].max().tz_convert("Europe/London").date().isoformat() <= E.VAL_END
    check_holidays(D)
    clock = Clock("US")
    prim = E.Params(range_end=5, min_w_atr=0.30, atr_regime_n=20, atr_regime_max=1.0)
    fb = E.Params(range_end=5, min_w_atr=0.35, atr_regime_n=0)
    res = {}
    for name, p in (("PRIMARY", prim), ("FALLBACK", fb)):
        res[name] = compare(D, name, p, clock, "london")
    for name, p in (("PRIMARY", prim), ("FALLBACK", fb)):
        compare(D, name, p, clock, "d1")
    # engine trades must all be on EA-armed days
    for name, p in (("PRIMARY", prim), ("FALLBACK", fb)):
        t = E.run(p, start="2014-03-01", end=E.VAL_END, D=D)
        ea = run_ea(D, p, clock, "london")
        ks = (t["date"].values.astype("datetime64[s]").astype(np.int64))
        miss = [str(pd.Timestamp(int(k), unit="s").date()) for k in ks if not ea.get(int(k), {}).get("dec")]
        print(f"[3] {name}: engine trades {len(t)} (2014-03..2023), on EA non-armed days: {len(miss)} {miss[:10]}")
    print("clock ok:", ok_clock)


if __name__ == "__main__":
    main()
