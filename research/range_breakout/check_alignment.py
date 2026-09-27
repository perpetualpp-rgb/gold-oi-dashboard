"""Verify the UTC alignment and coverage of the built M1 dataset.

1. Daily-halt test: COMEX/OTC gold halts 17:00-18:00 New York every day, so after conversion
   every reopen (gap of 30-180 min) should land at 18:00-18:05 New York time.
2. Dukascopy test: for every Dukascopy day in data_cache/raw, the best hour shift between the
   feeds must be 0 with a small median close difference.
3. Coverage: live M1 bars per weekday, per year (a full day is ~1380).
Exits non-zero if any test fails.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

import engine as E


def main():
    full = pd.read_parquet(os.path.join(E.CACHE, "XAUUSD_M1_BID.parquet"))
    bid = full["close"]
    fails = 0

    # Dukascopy-patched days (volume == -1) quote through the halt, so test HistData bars only
    patched = full.index[full["volume"] < 0].normalize().unique()
    t = full.index[full["volume"] >= 0].to_series()
    gap = t.diff().dt.total_seconds() / 60
    near_patch = t.dt.normalize().isin(patched) | t.shift(1).dt.normalize().isin(patched)
    reopen = t[(gap >= 30) & (gap <= 180) & ~near_patch].dt.tz_convert("America/New_York")
    ok = (reopen.dt.hour == 18) & (reopen.dt.minute <= 5)
    rate = ok.groupby(reopen.dt.year).mean().round(3)
    print("daily-halt reopen at 18:00 NY, share by year:\n", rate.to_string())
    fails += int((rate < 0.9).sum())

    bad = 0
    n = 0
    for f in sorted(glob.glob(os.path.join(E.CACHE, "raw", "XAUUSD_BID_*.npy"))):
        day = pd.Timestamp(os.path.basename(f)[11:19], tz="UTC")
        r = np.load(f)
        if len(r) == 0:
            continue
        ts = day + pd.to_timedelta(r[:, 0].astype(np.int64), unit="s")
        dk = pd.Series(r[:, 2] / 1000, index=ts)[r[:, 5] > 0]
        hd = bid[day - pd.Timedelta(hours=3): day + pd.Timedelta(hours=27)]
        errs = {}
        for sh in (-2, -1, 0, 1, 2):
            x = hd.reindex(dk.index - pd.Timedelta(hours=sh))
            m = np.isfinite(x.values)
            if m.sum() > 300:
                errs[sh] = np.median(np.abs(dk.values[m] - x.values[m]))
        if not errs:
            continue
        n += 1
        best = min(errs, key=errs.get)
        if best != 0 or errs[0] > 0.5:
            bad += 1
            print("MISMATCH", day.date(), "best_shift", best, "err@0", round(errs.get(0, np.nan), 3))
    print(f"dukascopy days checked: {n}, mismatches: {bad}")
    fails += bad

    lt = bid.index.tz_convert("Europe/London")
    per_day = pd.Series(1, index=lt.normalize()).groupby(level=0).size()
    per_day = per_day[per_day.index.dayofweek < 5]
    cov = per_day.groupby(per_day.index.year).agg(["count", "median", lambda s: (s < 1000).sum()])
    cov.columns = ["weekdays", "median_bars", "days_lt_1000_bars"]
    print("coverage:\n", cov.to_string())
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
