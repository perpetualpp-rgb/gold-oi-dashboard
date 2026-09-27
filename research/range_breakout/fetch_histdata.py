"""Download XAUUSD M1 BID bars from HistData.com and build a spread model from Dukascopy samples.

HistData timestamps turn out to be New York local time (DST-aware, verified against Dukascopy).
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
    # HistData documents "EST without DST", but cross-checking against Dukascopy shows the XAUUSD
    # files are New York local time WITH DST (summer bars match Dukascopy only at UTC-4).
    t = pd.to_datetime(df["t"], format="%Y%m%d %H%M%S")
    t = t.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    df.index = t
    df = df[df.index.notna()]
    df.index = df.index.tz_convert("UTC")
    return df[["open", "high", "low", "close", "volume"]]


def spread_model(s, years):
    """Median ASK-BID close spread per (year, London hour) from sampled Dukascopy days."""
    rows = []
    for y in years:
        # 8 sample days per year, spread over the year, weekdays only
        cands = [dt.date(y, m, d) for m in (1, 3, 5, 6, 8, 9, 10, 11) for d in (10,)]
        for day in cands:
            while day.weekday() >= 5:
                day += dt.timedelta(1)
            if day >= dt.date.today():
                continue
            pb = fetch_day("XAUUSD", "BID", day, s)
            pa = fetch_day("XAUUSD", "ASK", day, s)
            if not pb or not pa:
                continue
            b, a = np.load(pb), np.load(pa)
            if len(b) == 0 or len(a) == 0 or len(a) != len(b):
                continue
            ts = pd.Timestamp(day, tz="UTC") + pd.to_timedelta(b[:, 0].astype(np.int64), unit="s")
            live = b[:, 5] > 0
            spr = (a[:, 2] - b[:, 2]) / 1000.0
            hr = ts.tz_convert("Europe/London").hour
            rows.append(pd.DataFrame({"year": y, "hour": hr[live], "spread": spr[live]}))
        print("spread sample", y, flush=True)
    sp = pd.concat(rows)
    m = sp.groupby(["year", "hour"])["spread"].median().unstack()
    return m


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
