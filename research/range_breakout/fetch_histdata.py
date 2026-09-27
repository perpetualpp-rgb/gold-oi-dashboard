"""Download XAUUSD M1 BID bars from HistData.com and build a spread model from Dukascopy samples.

HistData timestamps are not the documented fixed EST; see hd_to_utc() for the calibrated rule.
Output is converted to UTC.
HistData only provides BID, so ASK = BID + modelled spread, where the spread is the median
Dukascopy spread for the same (year, London hour), measured on sampled days, with a floor.

Outputs (data_cache/):
  XAUUSD_M1_BID.parquet, XAUUSD_M1_ASK.parquet  (the files engine.load() reads)
  spread_model.csv                             (year x London-hour median spread, USD)
"""
import datetime as dt
import io
import os
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from fetch_dukascopy import fetch_day, RAW

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data_cache")
HD = os.path.join(CACHE, "histdata")
PAGE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/xauusd/{p}"
SPREAD_FLOOR = 0.15  # USD; never assume a tighter spread than this


def get_hd(period, s):
    path = os.path.join(HD, f"{period.replace('/', '_')}.zip")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    for attempt in range(5):
        try:
            page = PAGE.format(p=period)
            h = s.get(page, timeout=60).text
            form = dict(re.findall(r'<input type="hidden" name="(\w+)" id="\w+" value="([^"]*)"', h))
            if "tk" not in form:
                return None
            r = s.post("https://www.histdata.com/get.php", data=form, headers={"Referer": page}, timeout=300)
            if r.status_code == 200 and r.content[:2] == b"PK":
                open(path, "wb").write(r.content)
                return path
        except requests.RequestException:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def read_hd(path):
    z = zipfile.ZipFile(path)
    name = [n for n in z.namelist() if n.endswith(".csv")][0]
    df = pd.read_csv(io.BytesIO(z.read(name)), sep=";", header=None,
                     names=["t", "open", "high", "low", "close", "volume"])
    df.index = hd_to_utc(pd.to_datetime(df["t"], format="%Y%m%d %H%M%S"))
    df = df[df.index.notna()]
    return df[["open", "high", "low", "close", "volume"]]


def hd_to_utc(raw):
    """HistData documents "EST without DST", which is wrong for XAUUSD. Calibrated on the daily
    17:00-18:00 New York trading halt (and cross-checked against Dukascopy):
      - through 2018 the clock is New York local time (US DST rules);
      - from 2019 it is UTC-5, shifted +1h while *UK/EU* DST is in force.
    The two differ only in the ~3 weeks a year when US and EU DST disagree.
    """
    raw = pd.Series(pd.DatetimeIndex(raw))
    ny = raw.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    u0 = (raw + pd.Timedelta(hours=5)).dt.tz_localize("UTC")
    eu_dst = u0.dt.tz_convert("Europe/London").map(lambda x: x.dst() != pd.Timedelta(0)).astype(int)
    eu = u0 - pd.to_timedelta(eu_dst, unit="h")
    return pd.DatetimeIndex(ny.where(raw.dt.year < 2019, eu))


def _sample_days(years):
    """6 weekdays per year (both DST regimes)."""
    out = []
    for y in years:
        for m in (1, 3, 5, 7, 9, 11):
            day = dt.date(y, m, 10)
            while day.weekday() >= 5:
                day += dt.timedelta(1)
            if day < dt.date.today():
                out.append(day)
    return out


def spread_model(s, years):
    """Median ASK-BID close spread per (year, London hour) from sampled Dukascopy days."""
    days = _sample_days(years)
    jobs = [(side, d) for d in days for side in ("BID", "ASK")]
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda j: fetch_day("XAUUSD", j[0], j[1], s), jobs))
    rows = []
    for day in days:
        pb = os.path.join(RAW, f"XAUUSD_BID_{day:%Y%m%d}.npy")
        pa = os.path.join(RAW, f"XAUUSD_ASK_{day:%Y%m%d}.npy")
        if not (os.path.exists(pb) and os.path.exists(pa)):
            print("spread sample missing", day, flush=True)
            continue
        b, a = np.load(pb), np.load(pa)
        if len(b) == 0 or len(a) != len(b):
            continue
        ts = pd.Timestamp(day, tz="UTC") + pd.to_timedelta(b[:, 0].astype(np.int64), unit="s")
        live = b[:, 5] > 0
        spr = (a[:, 2] - b[:, 2]) / 1000.0
        hr = ts.tz_convert("Europe/London").hour
        rows.append(pd.DataFrame({"year": day.year, "hour": hr[live], "spread": spr[live]}))
    sp = pd.concat(rows)
    print("spread sample days per year:", {y: n // 1000 for y, n in sp.groupby("year").size().items()}, flush=True)
    return sp.groupby(["year", "hour"])["spread"].median().unstack()


def patch_holes(bid, s, min_bars=1000, min_bars_by_year={2023: 1340}):
    """Replace weekdays (UTC) with too few bars by Dukascopy BID bars, when Dukascopy has more.

    HistData 2023 is full of holes (~66 days missing ~7 hours, many more with 1-hour gaps), so
    2023 uses a stricter threshold. Dukascopy and HistData agree to ~0.07 USD median on
    overlapping minutes (see check_alignment.py).
    """
    per_day = pd.Series(1, index=bid.index.normalize()).groupby(level=0).size()
    per_day = per_day[per_day.index.dayofweek < 5]
    thr = np.array([min_bars_by_year.get(y, min_bars) for y in per_day.index.year])
    days = [d.date() for d in per_day[per_day.values < thr].index]
    if not days:
        return bid
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda d: fetch_day("XAUUSD", "BID", d, s), days))
    patched = 0
    for d in days:
        p = os.path.join(RAW, f"XAUUSD_BID_{d:%Y%m%d}.npy")
        if not os.path.exists(p):
            continue
        r = np.load(p)
        r = r[r[:, 5] > 0] if len(r) else r
        if len(r) <= per_day[pd.Timestamp(d, tz="UTC")]:
            continue
        ts = pd.Timestamp(d, tz="UTC") + pd.to_timedelta(r[:, 0].astype(np.int64), unit="s")
        dk = pd.DataFrame({"open": r[:, 1], "high": r[:, 4], "low": r[:, 3], "close": r[:, 2]}, index=ts) / 1000.0
        dk["volume"] = -1  # marks Dukascopy-patched bars
        day0 = pd.Timestamp(d, tz="UTC")
        bid = pd.concat([bid[(bid.index < day0) | (bid.index >= day0 + pd.Timedelta(days=1))], dk])
        patched += 1
    print(f"patched {patched}/{len(days)} short days from Dukascopy", flush=True)
    return bid.sort_index()


def main():
    os.makedirs(HD, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    this_year = dt.date.today().year
    periods = [str(y) for y in range(2014, this_year)]
    periods += [f"{this_year}/{m}" for m in range(1, dt.date.today().month + 1)]
    frames = []
    for p in periods:
        path = get_hd(p, s)
        print("histdata", p, "ok" if path else "MISSING", flush=True)
        if path:
            frames.append(read_hd(path))
    bid = pd.concat(frames).sort_index()
    bid = bid[~bid.index.duplicated()]
    bid = patch_holes(bid, s)
    bid.index.name = "time"

    years = sorted(set(bid.index.year))
    m = spread_model(s, years)
    m = m.reindex(index=years, columns=range(24))
    m = m.T.interpolate(limit_direction="both").T.ffill().bfill()
    m.to_csv(os.path.join(CACHE, "spread_model.csv"))
    print(m.round(2).to_string(), flush=True)

    hr = bid.index.tz_convert("Europe/London").hour
    spr = np.maximum(m.values[np.searchsorted(years, bid.index.year), hr], SPREAD_FLOOR)
    ask = bid.copy()
    for c in ("open", "high", "low", "close"):
        ask[c] = bid[c] + spr
    bid.to_parquet(os.path.join(CACHE, "XAUUSD_M1_BID.parquet"))
    ask.to_parquet(os.path.join(CACHE, "XAUUSD_M1_ASK.parquet"))
    print("rows", len(bid), bid.index[0], bid.index[-1], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
