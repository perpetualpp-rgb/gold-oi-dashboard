"""Shared helpers for the execution-realism verification (IS+VAL only; data loaded with until=VAL_END)."""
import glob, json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(FINAL, ".."))
for p in (ROOT, FINAL, os.path.join(ROOT, "explore", "filters"), os.path.join(ROOT, "explore", "null_costs")):
    if p not in sys.path:
        sys.path.insert(0, p)
import engine as E  # noqa
RAW = os.path.join(E.CACHE, "raw")
CUT = pd.Timestamp("2024-01-01", tz="UTC")


def data():
    D = E.load(until=E.VAL_END)
    assert D["index"].max() < CUT
    return D


def params(lab="primary", **kw):
    cand = json.load(open(os.path.join(FINAL, "candidates.json")))["candidates"][lab]
    d = {k: (tuple(v) if isinstance(v, list) else v) for k, v in cand.items()}
    d.update(kw)
    return E.Params(**d)


def spread_model():
    m = pd.read_csv(os.path.join(E.CACHE, "spread_model.csv"), index_col=0)
    m.columns = m.columns.astype(int)
    return m.loc[:2023]


def raw_side(day, side):
    p = os.path.join(RAW, f"XAUUSD_{side}_{day:%Y%m%d}.npy")
    if not os.path.exists(p):
        return None
    rec = np.load(p)
    if len(rec) == 0:
        return None
    base = pd.Timestamp(day, tz="UTC")
    idx = base + pd.to_timedelta(rec[:, 0].astype(np.int64), unit="s")
    return pd.DataFrame({"open": rec[:, 1] / 1e3, "close": rec[:, 2] / 1e3, "low": rec[:, 3] / 1e3,
                         "high": rec[:, 4] / 1e3, "volume": rec[:, 5]}, index=idx)


def raw_pairs():
    """All Dukascopy raw UTC days < 2024 that have both BID and ASK M1 files; returns merged frame."""
    days = sorted({os.path.basename(p)[-12:-4] for p in glob.glob(os.path.join(RAW, "XAUUSD_ASK_*.npy"))})
    fr = []
    for s in days:
        d = pd.Timestamp(s)
        if d >= pd.Timestamp("2024-01-01"):
            continue
        b, a = raw_side(d, "BID"), raw_side(d, "ASK")
        if b is None or a is None:
            continue
        m = b.join(a, lsuffix="_b", rsuffix="_a", how="inner")
        m = m[~((m.volume_b <= 0) & (m.high_b == m.low_b))]
        fr.append(m)
    o = pd.concat(fr).sort_index()
    o = o[~o.index.duplicated()]
    return o[o.index < CUT]
