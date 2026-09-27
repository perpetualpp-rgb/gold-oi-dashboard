"""Verify HistData timestamps against Dukascopy sample days (data_cache/raw) for every year.

For each sampled day, the best-matching hour shift between the two feeds must be 0 and the
median absolute close difference small. Prints one line per day; exits non-zero on mismatch.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

import engine as E

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    bid = pd.read_parquet(os.path.join(E.CACHE, "XAUUSD_M1_BID.parquet"))["close"]
    bad = 0
    for f in sorted(glob.glob(os.path.join(E.CACHE, "raw", "XAUUSD_BID_*.npy"))):
        day = os.path.basename(f)[11:19]
        r = np.load(f)
        if len(r) == 0:
            continue
        ts = pd.Timestamp(day, tz="UTC") + pd.to_timedelta(r[:, 0].astype(np.int64), unit="s")
        dk = pd.Series(r[:, 2] / 1000, index=ts)[r[:, 5] > 0]
        errs = {}
        for sh in (-2, -1, 0, 1, 2):
            h = bid.copy()
            h.index = h.index + pd.Timedelta(hours=sh)
            j = pd.concat([dk, h], axis=1, join="inner").dropna()
            if len(j) > 300:
                errs[sh] = (j.iloc[:, 0] - j.iloc[:, 1]).abs().median()
        if not errs:
            continue
        best = min(errs, key=errs.get)
        ok = best == 0 and errs[0] < 0.5
        bad += not ok
        print(day, "best_shift", best, "median_abs_diff@0", round(errs.get(0, np.nan), 3), "OK" if ok else "MISMATCH")
    print("mismatches:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
