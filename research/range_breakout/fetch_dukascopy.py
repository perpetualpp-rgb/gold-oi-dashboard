"""Download XAUUSD 1-minute BID/ASK candles from Dukascopy's public datafeed.

Output: data_cache/XAUUSD_M1_{BID,ASK}.parquet (UTC timestamps, prices in USD).
Files are fetched per day; a day with no file (holiday/weekend) is skipped.
Re-running resumes from the per-day cache in data_cache/raw/.
"""
import argparse
import datetime as dt
import lzma
import os
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/{side}_candles_min_1.bi5"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data_cache")
RAW = os.path.join(CACHE, "raw")
SCALE = 1000.0  # XAUUSD point size in the bi5 feed


def fetch_day(sym, side, day, session):
    path = os.path.join(RAW, f"{sym}_{side}_{day:%Y%m%d}.npy")
    if os.path.exists(path):
        return path
    url = URL.format(sym=sym, y=day.year, m=day.month - 1, d=day.day, side=side)
    delay = 2.0
    for attempt in range(8):
        try:
            r = session.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                if not r.content:
                    np.save(path, np.zeros((0, 6)))
                    return path
                raw = lzma.decompress(r.content)
                n = len(raw) // 24
                rec = np.array(struct.unpack(">" + "5if" * n, raw), dtype=np.float64).reshape(n, 6)
                np.save(path, rec)
                return path
            if r.status_code == 404:
                np.save(path, np.zeros((0, 6)))
                return path
        except (requests.RequestException, lzma.LZMAError):
            pass
        time.sleep(delay)
        delay = min(delay * 2, 60)
    return None


def build(sym, side, days):
    frames = []
    for day in days:
        path = os.path.join(RAW, f"{sym}_{side}_{day:%Y%m%d}.npy")
        if not os.path.exists(path):
            continue
        rec = np.load(path)
        if len(rec) == 0:
            continue
        base = pd.Timestamp(day, tz="UTC")
        idx = base + pd.to_timedelta(rec[:, 0].astype(np.int64), unit="s")
        df = pd.DataFrame(
            {"open": rec[:, 1] / SCALE, "close": rec[:, 2] / SCALE, "low": rec[:, 3] / SCALE,
             "high": rec[:, 4] / SCALE, "volume": rec[:, 5]},
            index=idx,
        )
        frames.append(df)
    out = pd.concat(frames).sort_index()
    # Dukascopy fills non-trading minutes with flat zero-volume bars; drop them.
    flat = (out["volume"] <= 0) & (out["high"] == out["low"])
    out = out[~flat]
    out.index.name = "time"
    out.to_parquet(os.path.join(CACHE, f"{sym}_M1_{side}.parquet"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="XAUUSD")
    ap.add_argument("--start", default="2014-01-01")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    days = [start + dt.timedelta(i) for i in range((end - start).days + 1)]
    days = [d for d in days if d.weekday() != 5]  # no Saturday trading
    jobs = [(side, d) for d in days for side in ("BID", "ASK")]
    session = requests.Session()
    failed = []
    with ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(fetch_day, args.sym, s, d, session): (s, d) for s, d in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            if f.result() is None:
                failed.append(futs[f])
            if i % 200 == 0:
                print(f"{i}/{len(jobs)} done, {len(failed)} failed", flush=True)
    print(f"finished, {len(failed)} failed", flush=True)
    for s, d in failed[:20]:
        print("FAILED", s, d, flush=True)
    for side in ("BID", "ASK"):
        df = build(args.sym, side, days)
        print(side, len(df), df.index[0], df.index[-1], flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
