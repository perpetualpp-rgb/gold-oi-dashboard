"""Fetch Dukascopy XAUUSD tick files (UTC hour) for the primary's IS+VAL entry hours, SL-exit hours and
a sample of time-exit hours. Raw .bi5 bytes are cached in ticks/. Only dates < 2024 are ever requested."""
import os, time, sys
import pandas as pd, requests
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ticks"); os.makedirs(OUT, exist_ok=True)
URL = "https://datafeed.dukascopy.com/datafeed/XAUUSD/{y:04d}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"
hours = set()
for lab in ("primary",):
    t = pd.read_csv(os.path.join(HERE, f"trades_{lab}.csv"))
    for col, sel in (("t_entry", slice(None)), ("t_exit", t.reason == "sl")):
        for ts in pd.to_datetime(t.loc[sel, col], utc=True):
            h = ts.floor("h"); hours.add(h)
            if ts.minute >= 58: hours.add(h + pd.Timedelta(hours=1))
    te = t[t.reason == "time"].sample(120, random_state=0)
    for ts in pd.to_datetime(te.t_exit, utc=True):
        hours.add(ts.floor("h"))
import random
hours = sorted(h for h in hours if h < pd.Timestamp("2024-01-01", tz="UTC"))
random.Random(1).shuffle(hours)          # any partial download is a random sample
print(len(hours), "hours", flush=True)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
bad = 0
for k, h in enumerate(hours):
    p = os.path.join(OUT, f"{h:%Y%m%d%H}.bi5")
    if os.path.exists(p):
        continue
    url = URL.format(y=h.year, m=h.month - 1, d=h.day, h=h.hour)
    delay = 2
    for a in range(8):
        try:
            r = s.get(url, timeout=12)
            if r.status_code == 200:
                open(p, "wb").write(r.content); break
            if r.status_code == 404:
                open(p, "wb").write(b""); break
        except requests.RequestException:
            pass
        time.sleep(delay); delay = min(delay * 1.5, 20)
    else:
        bad += 1
    time.sleep(0.2)
    if k % 50 == 0:
        print(k, h, bad, flush=True)
print("done bad", bad, flush=True)
