"""
plan_stats.py — fetch CME OI/Vol data and compute the deterministic numbers a
daily gold plan is built from (walls, tails, magnet, sigma range, two-screen
confirmation, P/C, IV skew, regime, futures->spot basis).

Used by the scheduled "AI plan" agent: it runs this to get exact figures, then
writes plan.json following methodology_invisible_money.md + methodology_oi_real.md.

Usage:
  python plan_stats.py            # prints a JSON stats block to stdout

Requires: standard library only.
"""

import sys
import os
import json
import math
import re
import urllib.request
from datetime import datetime, timezone, timedelta

# UTF-8 console so Thai prints correctly on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OI_URL = "https://raw.githubusercontent.com/pageth/Vol2VolData/main/OIData.txt"
IN_URL = "https://raw.githubusercontent.com/pageth/Vol2VolData/main/IntradayData.txt"
# Our own mirror of pageth's files (kept fresh by mirror.yml) — used automatically
# if pageth is unreachable/deleted, so the dashboard never goes dataless.
OI_MIRROR = "https://raw.githubusercontent.com/perpetualpp-rgb/gold-oi-dashboard/main/data/mirror/OIData.txt"
IN_MIRROR = "https://raw.githubusercontent.com/perpetualpp-rgb/gold-oi-dashboard/main/data/mirror/IntradayData.txt"
MIRROR = {OI_URL: OI_MIRROR, IN_URL: IN_MIRROR}

BASIS = 30.0   # approx Gold futures premium over XAUUSD spot (book: ~$30; ->0 near expiry)


def tz_bkk():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Bangkok")
    except Exception:
        return timezone(timedelta(hours=7), name="ICT")


def fetch(url):
    """Fetch a data file; try primary (pageth) then our mirror, each with a couple of retries so a
    transient GitHub 429 (rate-limit) doesn't kill the whole run. NO cache-buster — GitHub's CDN
    cache (~5 min) is fresh enough for OI/intraday and stops us hammering the rate-limited origin
    (the old `?t=<ts>` forced a cache MISS on every call → 429 → plan failed, e.g. 2026-07-08 13:00)."""
    import time as _t
    last = ""
    for u in (url, MIRROR.get(url)):
        if not u:
            continue
        for attempt in range(3):
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "gold-oi-dashboard"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    txt = r.read().decode("utf-8")
                if txt.strip():
                    return txt
                last = u + ": empty body"
            except Exception as e:
                last = f"{u}: {e}"
            if attempt < 2:
                _t.sleep(6 * (attempt + 1))       # 6s, 12s backoff — ride out a brief 429
    txt = _git_mirror_text(url)                        # tier 3: git protocol (immune to raw-CDN 429)
    if txt and txt.strip():
        return txt
    raise RuntimeError("fetch failed (primary + mirror + git): " + url + " · " + last)


_GIT_FETCHED = False


def _repo_dir():
    d = os.path.dirname(os.path.abspath(__file__))
    for c in (d, os.path.join(d, "gold-oi-dashboard")):   # Actions: script inside repo · local: repo is a subdir
        if os.path.isdir(os.path.join(c, ".git")):
            return c
    return None


def _git_mirror_text(url):
    """Last-resort data source: read data/mirror/<file> from origin/main over the GIT protocol.
    raw.githubusercontent.com rate-limits per-IP (HTTP 429, sustained — killed the 2026-07-09 13:00
    slot even through retries, and the mirror URL shares the same host so it 429s too). git fetch/show
    goes through a different service and keeps working; mirror.yml keeps the file ≤ a few hours old,
    which matches pageth's own update cadence anyway."""
    repo = _repo_dir()
    if not repo:
        return None
    import subprocess
    global _GIT_FETCHED
    name = url.rsplit("/", 1)[-1]
    try:
        if not _GIT_FETCHED:
            subprocess.run(["git", "-C", repo, "fetch", "origin", "-q"],
                           check=False, capture_output=True, timeout=60)
            _GIT_FETCHED = True
        r = subprocess.run(["git", "-C", repo, "show", f"origin/main:data/mirror/{name}"],
                           check=False, capture_output=True, timeout=30)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", "replace")
    except Exception:
        pass
    return None


def parse(text):
    lines = text.replace("\r", "").split("\n")
    head = lines[0] if lines else ""
    summ = lines[1] if len(lines) > 1 else ""

    def g(pat, s, d=0.0):
        m = re.search(pat, s)
        return float(m.group(1).replace(",", "")) if m else d

    fx = re.search(r"vs\s+([\d.]+)\s+\(([+-]?[\d.]+)\)", head)
    cm = re.search(r"Gold\s*\(OG\|GC\)\s*(\S+)", head)
    meta = {
        "contract": cm.group(1) if cm else "",
        "dte": g(r"\(([\d.]+)\s*DTE\)", head),
        "future": float(fx.group(1)) if fx else 0.0,
        "futureChg": float(fx.group(2)) if fx else 0.0,
        "totalPut": g(r"Put:\s*([\d,]+)", summ),
        "totalCall": g(r"Call:\s*([\d,]+)", summ),
        "iv": g(r"Vol:\s*([\d.]+)", summ),
        "ivChg": g(r"Vol Chg:\s*([+-]?[\d.]+)", summ),
    }
    rows = []
    for ln in lines[3:]:
        p = ln.split(",")
        if len(p) < 4:
            continue
        try:
            strike = float(p[0])
        except ValueError:
            continue
        if not strike:
            continue
        rows.append({
            "strike": strike,
            "call": int(float(p[1] or 0)),
            "put": int(float(p[2] or 0)),
            "iv": float(p[3] or 0),
        })
    meta["rows"] = rows
    return meta


def sigma(d):
    if not (d["future"] and d["iv"] and d["dte"]):
        return 0.0
    return d["future"] * (d["iv"] / 100.0) * math.sqrt(d["dte"] / 365.0)


def top_walls(rows, side, ref, above, volmap, volmax, n=3):
    mx = max((r[side] for r in rows), default=0)
    thr = max(mx * 0.20, 1)
    cand = [r for r in rows if ((r["strike"] > ref) == above) and r[side] >= thr]
    cand.sort(key=lambda r: r[side], reverse=True)
    out = []
    for r in cand[:n]:
        v = volmap.get(r["strike"], {}).get(side, 0)
        out.append({
            "strike": r["strike"],
            "oi": r[side],
            "intraday_vol": v,
            "two_screen_confirm": bool(volmax and v >= 0.20 * volmax and v > 0),
        })
    return out


def tail(rows, side, ref, above):
    mx = max((r[side] for r in rows), default=0)
    thr = max(mx * 0.20, 1)
    cand = [r for r in rows if ((r["strike"] > ref) == above) and r[side] >= thr]
    if not cand:
        return None
    pick = max(cand, key=lambda r: r["strike"]) if above else min(cand, key=lambda r: r["strike"])
    return {"strike": pick["strike"], "oi": pick[side]}


def oi_weighted_mean(rows):
    wsum = w = 0.0
    for r in rows:
        v = r["call"] + r["put"]
        wsum += r["strike"] * v
        w += v
    return (wsum / w) if w else 0.0


def regime(iv):
    # heuristic bands for gold ATM IV (annualised %). The AI may override with judgment.
    if iv < 20:
        return "low"
    if iv <= 32:
        return "normal"
    return "high"


def compute_stats():
    oi = parse(fetch(OI_URL))
    intr = parse(fetch(IN_URL))

    fut = oi["future"]
    sd = sigma(oi)
    rows = oi["rows"]
    volmap = {v["strike"]: v for v in intr["rows"]}
    callvolmax = max((v["call"] for v in intr["rows"]), default=0)
    putvolmax = max((v["put"] for v in intr["rows"]), default=0)

    # IV skew: average per-strike IV below (puts) vs above (calls) the future
    below = [r["iv"] for r in rows if r["strike"] < fut and r["iv"] > 0]
    above = [r["iv"] for r in rows if r["strike"] > fut and r["iv"] > 0]
    put_avg = sum(below) / len(below) if below else 0.0
    call_avg = sum(above) / len(above) if above else 0.0
    if put_avg > call_avg * 1.02:
        skew_dir = "put"   # downside fear
    elif call_avg > put_avg * 1.02:
        skew_dir = "call"  # upside FOMO
    else:
        skew_dir = "flat"

    # intraday "hot" strikes (where today's volume concentrates)
    hot = sorted(intr["rows"], key=lambda r: r["call"] + r["put"], reverse=True)[:5]

    magnet = max(rows, key=lambda r: r["call"] + r["put"]) if rows else None
    oimean = oi_weighted_mean(rows)

    stats = {
        "ts_bkk": datetime.now(tz_bkk()).isoformat(timespec="minutes"),
        "contract": oi["contract"],
        "future": fut,
        "future_chg": oi["futureChg"],
        "dte": oi["dte"],
        "atm_iv": oi["iv"],
        "atm_iv_chg": oi["ivChg"],
        "regime_heuristic": regime(oi["iv"]),
        "sigma_points": round(sd, 1),
        "sd_levels": {f"{m:+d}sigma": round(fut + m * sd, 1) for m in (-3, -2, -1, 1, 2, 3)},
        "basis_to_spot": BASIS,
        "spot_note": f"XAUUSD spot ≈ futures − ~${BASIS:.0f} (basis ลดลงเข้าใกล้ 0 เมื่อใกล้หมดอายุ; DTE={oi['dte']})",
        "pcr_oi": round(oi["totalPut"] / oi["totalCall"], 2) if oi["totalCall"] else None,
        "pcr_intraday": round(intr["totalPut"] / intr["totalCall"], 2) if intr["totalCall"] else None,
        "oi_totals": {"call": int(oi["totalCall"]), "put": int(oi["totalPut"])},
        "intraday_totals": {"call": int(intr["totalCall"]), "put": int(intr["totalPut"])},
        "resistance_call_walls": top_walls(rows, "call", fut, True, volmap, callvolmax),
        "support_put_walls": top_walls(rows, "put", fut, False, volmap, putvolmax),
        "call_tail": tail(rows, "call", fut, True),
        "put_tail": tail(rows, "put", fut, False),
        "magnet_strike": {"strike": magnet["strike"], "oi": magnet["call"] + magnet["put"]} if magnet else None,
        "oi_weighted_mean": round(oimean, 1),
        "z_vs_oi_mean": round((fut - oimean) / sd, 2) if sd else None,
        "iv_skew": {"put_side_avg": round(put_avg * 100, 1), "call_side_avg": round(call_avg * 100, 1), "direction": skew_dir},
        "intraday_hot_strikes": [{"strike": r["strike"], "call": r["call"], "put": r["put"]} for r in hot],
    }
    return stats


def main():
    print(json.dumps(compute_stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
