"""
generate_plan.py — build the daily gold plan (plan.json) DETERMINISTICALLY from
the methodology of 'The Invisible Money' + 'OI มีอยู่จริง', then git-push it so the
dashboard updates. Designed to run at 13:00 & 19:00 ICT via Windows Task Scheduler
(no LLM, no app open, no tool approvals — just Python + git).

Usage:
  python generate_plan.py            # fetch -> build -> write plan.json -> git push
  python generate_plan.py --no-push  # build + write only (for testing)

Requires: standard library + plan_stats.py in the same folder; git authed.
"""

import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.parse
import plan_stats as ps

# Live gold spot. Prefer gold-api.com (real XAU/USD spot — closest to broker XAUUSD);
# fall back to PAXG (Pax Gold ≈ spot, but a few $ off) on Coinbase/Kraken/Binance so it
# still works if gold-api is down or a venue is geo-blocked from GitHub Actions runners.
SPOT_SOURCES = [
    ("https://api.gold-api.com/price/XAU",                          lambda j: float(j["price"])),
    ("https://api.exchange.coinbase.com/products/PAXG-USD/ticker",  lambda j: float(j["price"])),
    ("https://api.kraken.com/0/public/Ticker?pair=PAXGUSD",         lambda j: float(j["result"]["PAXGUSD"]["c"][0])),
    ("https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT", lambda j: float(j["price"])),
]
# History: ~18-20 mid-June 2026 (her ArmRiley GC1!−XAUUSD) → 12.5 on 07-09 near expiry → ~47 on
# 07-31 after GC1! rolled to Dec. Feed lag can make a raw fut−spot absurd (4.2/32.4 on the
# 06-18 crash; −32.6 on 07-09 when the pageth snapshot went stale mid-rally).
# ADAPTIVE (2026-07-31): the basis is only stable WITHIN one pageth contract series — it decays
# with carry and JUMPS on every roll (07-09: 19→12.5 near expiry; 07-31: GC1! rolled to Dec and the
# true pageth-basis leapt to ~47 while the stale static band kept forcing 12.5 → CFD $35 off until
# the user caught it). Same contract as the previous plan → accept a live fut−spot within
# ±BASIS_DRIFT of the previous basis; contract changed/unknown → accept anything inside
# BASIS_SANITY (wide: far-month carry can be $60+). No usable reading → prev basis / BASIS_DEFAULT.
BASIS_SANITY = (-5.0, 75.0)
BASIS_DRIFT = 3.0
BASIS_DEFAULT = 25.0   # last manual anchor: her LIVE ArmRiley vs Dec, 2026-07-31 22:00 (see BASIS_OVERRIDE note)
# MANUAL OVERRIDE (2026-07-31 22:00): during the violent month-end Friday session BOTH free spot
# feeds (gold-api AND Coinbase PAXG — independent sources!) lagged ~$30 behind her broker screen
# (feeds ~4044, her FOREX.com XAUUSD 4074). A "live" fut−spot from lagging inputs read 46 while her
# live-vs-live ArmRiley read 25 — HER SCREEN IS GROUND TRUTH. While set, this value is used verbatim
# (basis_live=false). **SET BACK TO None once feeds re-converge with her broker** (check: gold-api−4 ≈ her price).
BASIS_OVERRIDE = 17.5   # her teacher sheet 2026-08-27 06:59: GCV26 open 4614.3 - spot 4596.8 = 17.5 (20 on 08-24, 25 since 07-31)
# Calibration to the user's broker: free XAU spot feeds sit a few $ off any specific broker.
# Subtract this so spot_cfd ≈ her Pepperstone XAUUSD (gold-api ran ~$4 above it). Tune if it drifts.
SPOT_ADJUST = 4.0


def fetch_spot():
    """Return live gold spot (~XAUUSD via PAXG) as float, or None if all sources fail."""
    for url, pick in SPOT_SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gold-oi-dashboard"})
            with urllib.request.urlopen(req, timeout=10) as r:
                val = pick(json.load(r))
                if val and val > 0:
                    return val
        except Exception:
            continue
    return None


COT_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
COT_EXTREME = 60000   # |Small-Specs net| ≥ this = retail "สุดขั้ว" (rough fallback — no history fetched, not a true percentile). Fade only counts when extreme; comm/spec are mirror images (zero-sum) so they are ONE axis, not two votes.


def fetch_cot():
    """CFTC Commitments of Traders for COMEX gold (weekly, free, no auth — gov open data, reliable
    unlike retail-sentiment sites). Returns the 3 trader groups' NET positions + week-over-week
    change. Book Ch3 / 'OI มีอยู่จริง': FADE Small Specs (retail, usually wrong), watch Commercials
    (smart money) extremes, Large Specs = trend. Returns None on any failure (COT is optional)."""
    import urllib.parse
    q = ("?$where=market_and_exchange_names like 'GOLD%COMMODITY EXCHANGE%'"
         "&$order=report_date_as_yyyy_mm_dd DESC&$limit=2")
    try:
        req = urllib.request.Request(COT_URL + urllib.parse.quote(q, safe="?&=$"),
                                     headers={"User-Agent": "gold-oi-dashboard"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        if len(d) < 2:
            return None
        net = lambda row, p: int(float(row[p + "_positions_long_all"])) - int(float(row[p + "_positions_short_all"]))
        cur, prev = d[0], d[1]
        out = {"date": cur["report_date_as_yyyy_mm_dd"][:10]}
        for key, p in (("comm", "comm"), ("spec", "noncomm"), ("retail", "nonrept")):
            n = net(cur, p)
            out[key] = {"net": n, "chg": n - net(prev, p)}
        out["retail_lean"] = (("down" if out["retail"]["net"] > 0 else "up")
                              if abs(out["retail"]["net"]) >= COT_EXTREME else "flat")   # fade ONLY when retail is extreme
        return out
    except Exception as e:
        print("cot fetch failed:", e)
        return None

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Locate the dashboard repo (where plan.json + index.html live). Works whether the
# script sits NEXT TO the repo (local: EA OI/ with a gold-oi-dashboard/ subdir) or
# INSIDE it (GitHub Actions: script committed at the repo root).
if os.path.exists(os.path.join(SCRIPT_DIR, "index.html")):
    REPO_DIR = SCRIPT_DIR
elif os.path.exists(os.path.join(SCRIPT_DIR, "gold-oi-dashboard", "index.html")):
    REPO_DIR = os.path.join(SCRIPT_DIR, "gold-oi-dashboard")
else:
    REPO_DIR = SCRIPT_DIR
PLAN_PATH = os.path.join(REPO_DIR, "plan.json")
DATA_DIR = os.path.join(REPO_DIR, "data")
OI_ARCHIVE_DIR = os.path.join(DATA_DIR, "oi")
PLANS_LOG = os.path.join(DATA_DIR, "plans_log.jsonl")
TRACK_PATH = os.path.join(DATA_DIR, "track_record.json")


def _bkk_now():
    from datetime import datetime
    return datetime.now(ps.tz_bkk())


def _sigma_note(strike, fut, sd):
    if not sd:
        return ""
    z = round((strike - fut) / sd)
    if z == 0:
        return "≈ราคาปัจจุบัน"
    return f'{"+" if z > 0 else "−"}{abs(z)}σ'


def _prev_basis_contract():
    """Previous plan's basis + pageth contract label — the anchor for the adaptive basis logic."""
    try:
        p = json.load(open(PLAN_PATH, encoding="utf-8"))
        b = p.get("basis")
        return (float(b) if isinstance(b, (int, float)) else None), p.get("contract")
    except Exception:
        return None, None


def grid_levels(fut, sd, basis, walls):
    """Book 'The Invisible Money' Ch6 ($50 Grid): every round $50/$100 futures level is a natural
    S/R because big players cluster Block Trades there → OI builds up → Market Makers must
    delta-hedge around it. Returns the nearest levels around price (3 above, 3–4 below — the base
    rounds down), flagging ones that sit on a dense OI wall (those are the strongest)."""
    base = int(fut // 50 * 50)
    out = []
    for k in range(-3, 4):
        lvl = base + k * 50
        if lvl > 0:
            out.append({"price": lvl, "cfd": round(lvl - basis, 1),
                        "r100": lvl % 100 == 0, "oi": any(abs(lvl - w) <= 15 for w in walls)})
    return out


# ── KruJeab SD ladder (teacher-sheet formula, locked once per day at 05:00 ICT) ──
# 1SD = Center × (Vol/100) × √(DTE/365); 2SD/3SD = linear multiples. SAME convention as
# KruJeab_SD_Probability_Bands_v2.pine ("Vol + DTE (ตารางครู)" + Morning Anchor 05:00),
# KruJeab_2SD_Reversal.mq5 and KruJeab-SD-AutoFill.user.js — web == Telegram == indicator == EA.
# Verified vs the teacher's sheet 2026-08-04: spot 4054.9, Vol 20.98, DTE 0.607 → 1SD 34.70.
# The "05:00 value" = the last pageth IntradayData snapshot BEFORE today's 05:00 ICT, read from
# our git-mirror HISTORY, so the home PC and the cloud compute IDENTICAL ladders deterministically.
SD_ANCHOR_HOUR = 5


def _sd_anchor_dt():
    """Today's 05:00 ICT anchor; before 05:00 counts as the previous trading day (userscript rule)."""
    from datetime import timedelta
    now = _bkk_now()
    day = (now - timedelta(hours=SD_ANCHOR_HOUR)).date()
    return now.replace(year=day.year, month=day.month, day=day.day,
                       hour=SD_ANCHOR_HOUR, minute=0, second=0, microsecond=0)


def _dte_as_of_anchor(header_days, anchor):
    """Port of the AutoFill userscript's dteAsOfAnchor(): pageth decimal DTE → use directly;
    whole-number DTE → whole days + the fraction from the 05:00 anchor to the next 12:30 ET
    expiry. Clamped to 0.05..10 like the script."""
    if header_days is None:
        return None
    if abs(header_days - round(header_days)) >= 0.005:
        return max(0.05, min(float(header_days), 10.0))
    try:
        from zoneinfo import ZoneInfo
        et = anchor.astimezone(ZoneInfo("America/New_York"))
        anchor_min = et.hour * 60 + et.minute
    except Exception:
        anchor_min = ((SD_ANCHOR_HOUR - 11) % 24) * 60        # rough EDT (ICT−11) fallback
    diff = (12 * 60 + 30) - anchor_min
    if diff <= 0:
        diff += 24 * 60
    return max(0.05, min(round(header_days) + diff / (24 * 60.0), 10.0))


def sd_ladder(basis, s, manual=None):
    """Locked 05:00 SD ladder in CFD prices (BUY zone −2SD..−3SD / SELL zone +2SD..+3SD).
    `manual` = {"future","iv","dte"} read by the user from CME QuikStrike / the teacher sheet
    (used when pageth is down — src "manual"). Never raises — returns None if everything fails."""
    import math
    try:
        anchor = _sd_anchor_dt()
        if not manual:                                    # today already locked (git or --sd-manual)?
            try:                                          # reuse it VERBATIM — one ladder everywhere
                cur = json.load(open(SD_PATH, encoding="utf-8"))
                if cur.get("day") == anchor.strftime("%Y-%m-%d") and cur.get("locked") and cur.get("levels"):
                    return cur
            except Exception:
                pass
        meta, src, locked = None, "live", False
        repo = ps._repo_dir()
        if manual:
            meta, src, locked = dict(manual), "manual", True
            repo = None
        if repo:
            import subprocess
            from datetime import timezone as _tz
            try:
                subprocess.run(["git", "-C", repo, "fetch", "origin", "-q"],
                               check=False, capture_output=True, timeout=60)
                # The teacher locks with the FIRST FRESH data of the new morning (her 2026-08-10
                # sheet at 08:07 used the new series Vol 18/DTE 0.6, NOT Friday's dying series that
                # the last pre-05:00 snapshot still held). So: EARLIEST mirror commit AT/AFTER the
                # 05:00 anchor — deterministic forever once it exists (same commit for every run).
                # TZ MUST be explicit: a naive timestamp makes git assume LOCAL (ICT) time — that
                # bug shifted "after 05:00 today" to "after 22:00 last night" and locked Monday's
                # dying-series leftovers (DTE 0.07) on 2026-08-11. %z appends +0700.
                since = anchor.strftime("%Y-%m-%dT%H:%M:%S%z")
                r = subprocess.run(["git", "-C", repo, "log", "origin/main", "--since=" + since,
                                    "--reverse", "--format=%H", "--", "data/mirror/IntradayData.txt"],
                                   check=False, capture_output=True, text=True, timeout=30)
                cand, last = None, None
                for h in (r.stdout or "").strip().splitlines()[:20]:
                    r2 = subprocess.run(["git", "-C", repo, "show", f"{h}:data/mirror/IntradayData.txt"],
                                        check=False, capture_output=True, timeout=30)
                    if r2.returncode != 0:
                        continue
                    m = ps.parse(r2.stdout.decode("utf-8", "replace"))
                    if not (m.get("future") and m.get("iv")):
                        continue
                    last = m
                    # freshness guard: a real new-morning series shows DTE ≥ ~0.3 (next 12:30 ET is
                    # most of a day away); ≤0.2 = yesterday's dying series still cached — skip it.
                    if float(m.get("dte") or 0) >= 0.3:
                        cand = m
                        break
                if cand or last:
                    meta = cand or last                    # no fresh one all morning → freshest available
                    src, locked = ("first-after-05:00" if cand else "late-fallback"), True
            except Exception:
                meta = None
        if not meta or not meta.get("future") or not meta.get("iv"):
            if s is None:                                    # sd-only mode: no live fallback by design
                return None                                  # (never lock stale/live data — retry later)
            # fallback: current stats, clearly flagged as NOT the locked 05:00 value
            meta = {"future": s["future"], "iv": s["atm_iv"], "dte": s["dte"]}
            src, locked = "live", False
        vol = round(float(meta["iv"]), 2)
        dte = _dte_as_of_anchor(float(meta["dte"]), anchor)
        if not vol or not dte:
            return None
        dte = round(dte, 2)
        center = round(float(meta["future"]) - basis, 1)      # CFD center (teacher: GC close − basis)
        sd1 = center * (vol / 100.0) * math.sqrt(dte / 365.0)
        lv = lambda k: round(center + k * sd1, 1)
        lf = lambda k: round(lv(k) + basis, 1)               # same ladder shifted to futures prices
        return {"day": anchor.strftime("%Y-%m-%d"), "locked": locked, "src": src,
                "center": center, "center_fut": float(meta["future"]), "basis": basis,
                "vol": vol, "dte": dte, "sd1": round(sd1, 2),
                "levels": {"p3": lv(3), "p2": lv(2), "p1": lv(1), "mean": center,
                           "m1": lv(-1), "m2": lv(-2), "m3": lv(-3)},
                "levels_fut": {"p3": lf(3), "p2": lf(2), "p1": lf(1), "mean": round(center + basis, 1),
                               "m1": lf(-1), "m2": lf(-2), "m3": lf(-3)},
                "buy_zone": [lv(-3), lv(-2)], "sell_zone": [lv(2), lv(3)]}
    except Exception as e:
        print("sd_ladder failed:", e)
        return None


SD_PATH = os.path.join(REPO_DIR, "sd_ladder.json")


def sd_publish(no_push=False):
    """05:05 task (`--sd-only`): compute today's locked ladder and publish sd_ladder.json to the
    web IMMEDIATELY — the SD is fixed for the whole day (her rule), so the site shouldn't wait
    for the 13:00 plan. The web card reads this file directly; full plan runs re-write it too,
    and both come from the same 05:00 git-mirror lock, so all surfaces stay identical."""
    if BASIS_OVERRIDE is not None:
        basis = float(BASIS_OVERRIDE)
    else:
        b, _c = _prev_basis_contract()
        basis = b if b is not None else BASIS_DEFAULT
    today = _sd_anchor_dt().strftime("%Y-%m-%d")
    try:                                    # idempotent: the task repeats all morning until locked
        cur = json.load(open(SD_PATH, encoding="utf-8"))
        if cur.get("day") == today and cur.get("locked") and not any(a.startswith("--sd-manual=") for a in sys.argv):
            print(f"sd-only: already locked for {today} — no-op")
            return
    except Exception:
        pass
    manual = None
    for a in sys.argv:                          # --sd-manual=FUT,VOL,DTE  (pageth down → user-read CME values)
        if a.startswith("--sd-manual="):
            f_, v_, d_ = (float(x) for x in a.split("=", 1)[1].split(","))
            manual = {"future": f_, "iv": v_, "dte": d_}
    sdl = sd_ladder(basis, None, manual=manual)   # git-history lock ONLY — never lock live/stale data
    if not sdl or not sdl.get("locked"):
        print("sd-only: no fresh post-05:00 snapshot yet — will retry on the next repetition")
        return
    with open(SD_PATH, "w", encoding="utf-8") as f:
        json.dump(sdl, f, ensure_ascii=False, indent=1)
    print(f"sd_ladder.json: day={sdl['day']} locked={sdl['locked']} center={sdl['center']} 1SD=${sdl['sd1']}")
    if not no_push:
        git_push("05:00-SD")


def build_plan(s):
    fut = s["future"]
    sd = s["sigma_points"] or 1
    regime = s["regime_heuristic"]
    chg = s["future_chg"]
    magnet = s.get("magnet_strike") or {}
    call_tail = s.get("call_tail") or {}
    put_tail = s.get("put_tail") or {}

    # ── futures → CFD/XAUUSD via the futures-spot basis (ADAPTIVE — see constants block) ──
    # Same contract as the previous plan → basis may only drift ±BASIS_DRIFT; contract rolled →
    # re-learn from the live reading within BASIS_SANITY. Feed-lag garbage falls back to the
    # previous basis so the CFD levels stay ≈ her broker instead of swinging with feed noise.
    spot = fetch_spot()
    if spot is not None:
        spot -= SPOT_ADJUST                          # calibrate gold-api XAU → broker XAUUSD
    raw = (fut - spot) if spot is not None else None
    if BASIS_OVERRIDE is not None:                             # user-verified manual lock (see constants note)
        basis, basis_live = float(BASIS_OVERRIDE), False
        spot = round(fut - basis, 1)
    else:
        prev_b, prev_c = _prev_basis_contract()
        same_contract = bool(prev_c) and prev_c == s.get("contract")
        if same_contract and prev_b is not None and BASIS_SANITY[0] <= prev_b <= BASIS_SANITY[1]:
            lo, hi = prev_b - BASIS_DRIFT, prev_b + BASIS_DRIFT   # within a series the basis only drifts slowly
        else:
            lo, hi = BASIS_SANITY                                  # new/unknown series — re-learn from live
        if raw is not None and lo <= raw <= hi:
            basis, basis_live = round(raw, 1), True
        else:
            basis = prev_b if (same_contract and prev_b is not None) else BASIS_DEFAULT
            basis_live = False
            spot = round(fut - basis, 1)
    cfd = lambda x: round(x - basis, 1)

    # ── bias: blend the day's momentum with OI structure + an extreme-P/C contrarian flag,
    # weighted by Vol regime. Books: OI structure & σ-position pick the side; in HIGH vol follow
    # the trend / don't fade; a P/C ratio at an extreme = crowd all-in → contrarian reversal. ──
    dirword = "ขึ้น" if chg > 0 else "ลง" if chg < 0 else "ออกข้าง"   # the day's move (for headline)
    mom = chg / sd if sd else 0.0                       # today's move vs σ (trend/momentum)
    z_oi = s.get("z_vs_oi_mean") or 0.0                 # future vs OI centre of gravity
    oi_pull = -z_oi                                     # mean-reversion back toward the OI bulk
    pcr = s.get("pcr_oi")
    pcr_warn = ""
    if pcr is not None and pcr < 0.55:
        pcr_vote, pcr_warn = -0.8, f"P/C OI {pcr} ต่ำมาก (Call ล้น = ฝูงชนเชียร์ขึ้นหมดแล้ว) → ระวังกลับหัวลง"
    elif pcr is not None and pcr > 1.7:
        pcr_vote, pcr_warn = 0.8, f"P/C OI {pcr} สูงมาก (Put ล้น = แห่กลัวลงสุดขีด) → ระวังเด้งกลับขึ้น"
    else:
        pcr_vote = 0.0
    cot = fetch_cot()                                   # CFTC weekly positioning (book Ch3)
    cot_vote = 0.0
    if cot:
        # fade retail ONLY when genuinely extreme (retail_lean is extremity-gated, not merely net>0)
        cot_vote = -0.3 if cot["retail_lean"] == "down" else 0.3 if cot["retail_lean"] == "up" else 0.0
    if regime == "high":          # don't fade a volatile trend (กฎทอง)
        w_mom, w_oi, w_pcr = 1.0, 0.2, 0.4
    elif regime == "low":         # quiet range — mean-reversion toward the OI bulk dominates
        w_mom, w_oi, w_pcr = 0.6, 0.8, 0.8
    else:
        w_mom, w_oi, w_pcr = 0.8, 0.5, 0.7
    score = w_mom * mom + w_oi * oi_pull + w_pcr * pcr_vote + 0.4 * cot_vote
    bias = "short" if score <= -0.4 else "long" if score >= 0.4 else "neutral"
    # กฎทอง HARD GATE (book: "Vol ยังทำ New High → ห้ามสวนเทรนด์ ไม่ว่า OI จะหนาแค่ไหน"):
    # in HIGH regime while IV is still rising, the down-weighted blend can still flip
    # counter-trend on extreme z / P-C votes — and this bias feeds the EAs via gold_plan.csv,
    # so block it outright instead of merely discouraging it.
    golden_gate = ""
    iv_chg = s.get("atm_iv_chg") or 0.0
    if regime == "high" and iv_chg > 0 and chg != 0:
        trend = 1 if chg > 0 else -1
        bsign = 1 if bias == "long" else -1 if bias == "short" else 0
        if bsign and bsign != trend:
            bias = "neutral"
            golden_gate = (f"กฎทอง: IV ยังพุ่ง (+{iv_chg:g}) ห้ามสวนเทรนด์ → ล็อก bias เป็นกลาง "
                           f"(สูตรเดิมคำนวณได้ฝั่งสวน) เล่นได้เฉพาะตามเทรนด์ หรือรอ IV หักหัวลงก่อน")
    # which factors pushed it that way — shown in the headline so the call stays transparent
    sgn = -1 if bias == "short" else 1 if bias == "long" else 0
    why = []
    if sgn and mom * sgn > 0.2:
        why.append("โมเมนตัม" + ("ลง" if mom < 0 else "ขึ้น"))
    if sgn and oi_pull * sgn > 0.2:
        why.append("ราคา" + ("เหนือ" if z_oi > 0 else "ใต้") + " Mean OI")
    if sgn and pcr_vote * sgn > 0:
        why.append("P/C สุดขั้วสวนทาง")
    if sgn and cot_vote * sgn > 0:
        why.append("COT รายย่อยสวน")
    bias_why = " + ".join(why) if why else "ยังไม่เลือกข้าง"

    # ── resistance / support level objects with methodology notes ──
    def level(w, kind):
        strike = w["strike"]
        parts = []
        if magnet.get("strike") == strike:
            parts.append("Magnet (OI หนาสุด)")
        if kind == "res" and call_tail.get("strike") == strike:
            parts.append("ท้าย OI Call = เป้าบนสุด")
        if kind == "sup" and put_tail.get("strike") == strike:
            parts.append("ท้าย OI Put = แนวรับสุดท้าย")
        if w.get("two_screen_confirm"):
            parts.append("ยืนยัน 2 จอ")
        if not parts:
            parts.append("กำแพง " + ("Call" if kind == "res" else "Put"))
        zn = _sigma_note(strike, fut, sd)
        if zn:
            parts.append(zn)
        return {"price": int(strike), "cfd": cfd(strike), "note": " · ".join(parts)}   # +CFD-converted

    res = sorted((level(w, "res") for w in s["resistance_call_walls"]), key=lambda x: x["price"])
    sup = sorted((level(w, "sup") for w in s["support_put_walls"]), key=lambda x: -x["price"])

    res1 = res[0]["price"] if res else round(fut + sd)
    sup1 = sup[0]["price"] if sup else round(fut - sd)
    sup_last = int(put_tail["strike"]) if put_tail.get("strike") else (sup[-1]["price"] if sup else round(fut - 3 * sd))
    res_last = int(call_tail["strike"]) if call_tail.get("strike") else (res[-1]["price"] if res else round(fut + 3 * sd))
    m1, p1 = round(fut - sd), round(fut + sd)

    # ── scenarios (if-then, with real levels; honour "don't chase / wait for H1 wick") ──
    if bias == "short":
        scen = [
            f"เด้งขึ้นชนแนวต้าน {res1} แล้วเกิดไส้เทียน H1 reject → จังหวะ short ตามเทรนด์ลง เป้า {sup1} → {m1} (−1σ)",
            f"หลุด {sup1} + วอลุ่ม/OI ฝั่งลงเพิ่ม (ของจริง ห้ามสวน) → ไหลต่อหา {sup_last} (ท้าย OI / −σ ลึก)",
            f"รีบาวน์เฉพาะครบเงื่อนไข: ราคาแตะ {sup_last} + IV เริ่มหักหัวลง + ไส้เทียน H1 → long สั้นสวน (เสี่ยงสูง)",
        ]
    elif bias == "long":
        scen = [
            f"ย่อลงหาแนวรับ {sup1} แล้วเกิดไส้เทียน H1 reject (ทิ้งไส้ล่าง) → long ตามเทรนด์ขึ้น เป้า {res1} → {p1} (+1σ)",
            f"ทะลุ {res1} + วอลุ่ม/OI ฝั่งขึ้นเพิ่ม (Gamma squeeze ของจริง ห้ามสวน) → ไปต่อหา {res_last} (ท้าย OI)",
            f"กลับตัวลงเฉพาะครบเงื่อนไข: ราคาแตะ {res_last} + IV หักหัวลง + ไส้เทียน H1 → short สั้นสวน (เสี่ยงสูง)",
        ]
    else:
        scen = [
            f"กรอบหลัก {sup1}–{res1}: ชน {res1} + ไส้เทียน H1 → short สั้น / ลงแตะ {sup1} + ไส้เทียน H1 → long สั้น (เล่นในกรอบ RR ≥ 1:2)",
            f"ทะลุ {res1} + OI/วอลุ่มเพิ่ม (Gamma squeeze ของจริง ห้ามสวน) → ไปต่อหา {res_last}; หลุด {sup1} + OI/วอลุ่มเพิ่ม (ของจริง ห้ามสวน) → ลงหา {sup_last}",
            "ยังไม่เลือกข้างชัด — รอ breakout พร้อมวอลุ่มยืนยัน อย่าไล่กลางกรอบ",
        ]

    # ── concrete entry setups (entry / SL / TP in CFD + RR), per the H1-rejection method ──
    # SL buffer behind the wall, wider when volatile (book: high vol => widen SL)
    buf = max(round(0.6 * sd) if regime == "high" else round(0.4 * sd), 12)

    def setup(side, title, e, sl, tps, note):
        risk_pts = abs(sl - e) or 1
        rr = abs(e - tps[0]) / risk_pts
        rr_txt = ("≈1:" + f"{rr:.1f}".rstrip("0").rstrip("."))
        if rr < 2:      # book discipline RR ≥ 1:2 — flag it, don't silently assert it
            note += f" · ⚠ RR {rr_txt} ต่ำกว่าเป้า 1:2 (SL กว้างช่วง vol สูง) — ลดขนาดไม้ หรือข้าม setup นี้"
        return {"side": side, "title": title, "entry": cfd(e), "sl": cfd(sl),
                "tp": [cfd(t) for t in tps], "rr": rr_txt, "note": note}

    sup2 = sup[1]["price"] if len(sup) > 1 else round(fut - 2 * sd)
    res2 = res[1]["price"] if len(res) > 1 else round(fut + 2 * sd)
    if bias == "short":
        entries = [
            setup("short", "Short รีเจกต์แนวต้าน", res1, res1 + buf, [sup1, sup2],
                  f"รอเด้งขึ้น {cfd(res1)} (fut {res1}) + ไส้เทียน H1 reject แล้วค่อย Short"),
            setup("short", "Short ตามการหลุดแนว", sup1, sup1 + buf, [sup_last],
                  f"ถ้าปิด H1 ใต้ {cfd(sup1)} (fut {sup1}) + วอลุ่ม/OI ฝั่งลงเพิ่ม (ของจริง ห้ามสวน)"),
        ]
    elif bias == "long":
        entries = [
            setup("long", "Long รีเจกต์แนวรับ", sup1, sup1 - buf, [res1, res2],
                  f"รอย่อลง {cfd(sup1)} (fut {sup1}) + ไส้เทียน H1 reject (ทิ้งไส้ล่าง) แล้วค่อย Long"),
            setup("long", "Long ตามการทะลุ", res1, res1 - buf, [res_last],
                  f"ถ้าปิด H1 เหนือ {cfd(res1)} (fut {res1}) + วอลุ่ม/OI ฝั่งขึ้นเพิ่ม (Gamma squeeze)"),
        ]
    else:
        entries = [
            setup("short", "Short ขอบบนกรอบ", res1, res1 + buf, [sup1],
                  f"ชนแนวต้าน {cfd(res1)} (fut {res1}) + ไส้เทียน H1 → Short สั้น"),
            setup("long", "Long ขอบล่างกรอบ", sup1, sup1 - buf, [res1],
                  f"แตะแนวรับ {cfd(sup1)} (fut {sup1}) + ไส้เทียน H1 → Long สั้น"),
        ]

    # ── $50 Grid (book Ch6): round-level Block-Trade S/R, flag the ones on a dense OI wall ──
    walls = {w["strike"] for w in s["resistance_call_walls"]} | {w["strike"] for w in s["support_put_walls"]}
    for tw in (magnet, call_tail, put_tail):
        if tw.get("strike"):
            walls.add(tw["strike"])
    grid = grid_levels(fut, sd, basis, walls)
    g_up = next((g for g in grid if g["price"] > fut), None)
    g_dn = next((g for g in reversed(grid) if g["price"] < fut), None)
    sdl = sd_ladder(basis, s)                     # KruJeab 05:00 SD ladder (teacher-sheet formula)

    # ── ⭐ CONFLUENCE (her rule 2026-08-27): a KEY OI level (top wall / ท้าย OI / magnet) sitting
    # inside or near an SD reversal zone (BUY −2..−3SD / SELL +2..+3SD) = two INDEPENDENT systems
    # pointing at the same price → a high-significance entry. Promoted to the top of the plan.
    confluence = []
    if sdl:
        Lsd = sdl["levels"]
        tol = max(0.15 * sdl["sd1"], 5.0)                 # "ใกล้" = within this of the zone edge
        sell_rng = (Lsd["p2"] - tol, Lsd["p3"] + tol)
        buy_rng = (Lsd["m3"] - tol, Lsd["m2"] + tol)
        sig_name = {"p3": "+3σ", "p2": "+2σ", "p1": "+1σ", "mean": "Mean", "m1": "−1σ", "m2": "−2σ", "m3": "−3σ"}
        def _near_sigma(px):
            k, d = min(((k, abs(px - v)) for k, v in Lsd.items()), key=lambda x: x[1])
            return sig_name[k], round(d, 1)
        keys = [("res", w["strike"], w["oi"], "กำแพง Call") for w in s["resistance_call_walls"]]
        keys += [("sup", w["strike"], w["oi"], "กำแพง Put") for w in s["support_put_walls"]]
        if call_tail.get("strike"):
            keys.append(("res", call_tail["strike"], call_tail.get("oi", 0), "ท้าย OI Call"))
        if put_tail.get("strike"):
            keys.append(("sup", put_tail["strike"], put_tail.get("oi", 0), "ท้าย OI Put"))
        if magnet.get("strike"):
            keys.append(("res" if magnet["strike"] > fut else "sup", magnet["strike"],
                         magnet.get("oi", 0), "Magnet"))
        seen_k = set()
        for kind, strike, oi_ct, label in keys:
            if strike in seen_k:
                continue
            px = cfd(strike)
            if kind == "res" and sell_rng[0] <= px <= sell_rng[1]:
                sig, d = _near_sigma(px)
                confluence.append({"side": "short", "price": int(strike), "cfd": px, "oi": int(oi_ct or 0),
                                   "label": label, "sigma": sig, "dist": d})
                seen_k.add(strike)
            elif kind == "sup" and buy_rng[0] <= px <= buy_rng[1]:
                sig, d = _near_sigma(px)
                confluence.append({"side": "long", "price": int(strike), "cfd": px, "oi": int(oi_ct or 0),
                                   "label": label, "sigma": sig, "dist": d})
                seen_k.add(strike)
        confluence.sort(key=lambda x: (x["dist"], -x["oi"]))
        if confluence:
            b = confluence[0]                              # strongest → promoted to the FIRST entry
            ef = b["price"]
            if b["side"] == "short":
                entries.insert(0, setup("short", f"⭐ นัยยะสำคัญ OI×SD · {b['label']} {b['price']} ใน SELL zone",
                                        ef, ef + buf, [round(Lsd["p1"] + basis), round(Lsd["mean"] + basis)],
                                        f"{b['label']} (OI {b['oi']}) ทับ {b['sigma']} ของ SD Ladder (ห่าง ${b['dist']}) "
                                        f"— กำแพง MM + สถิติสุดขั้วชี้จุดเดียวกัน รอไส้ H1 reject แล้ว Short เป้ากลับหา Mean"))
            else:
                entries.insert(0, setup("long", f"⭐ นัยยะสำคัญ OI×SD · {b['label']} {b['price']} ใน BUY zone",
                                        ef, ef - buf, [round(Lsd["m1"] + basis), round(Lsd["mean"] + basis)],
                                        f"{b['label']} (OI {b['oi']}) ทับ {b['sigma']} ของ SD Ladder (ห่าง ${b['dist']}) "
                                        f"— กำแพง MM + สถิติสุดขั้วชี้จุดเดียวกัน รอไส้ H1 reject แล้ว Long เป้ากลับหา Mean"))

    # ── risk (regime-aware) ──
    bits = []
    if regime == "high":
        bits.append(f"ผันผวนสูงมาก (IV {s['atm_iv']}% = regime สูง) → กฎทอง 'Vol ยังทำ New High ห้ามสวนเทรนด์' ลดขนาดไม้ ≥ ครึ่ง ขยาย SL; ราคาทะลุแนว OI ไปไกลกว่าคำนวณ 2–3 เท่าได้")
        if golden_gate:
            bits.append(golden_gate)
    elif regime == "low":
        bits.append("ผันผวนต่ำ (regime เขียว) → Mean Reversion ตามแนว OI แม่นขึ้น แต่ระวัง breakout เงียบ ๆ")
    else:
        bits.append("ผันผวนปกติ → เทรดตามแนว OI ได้ แต่ยังต้องรอจังหวะยืนยัน")
    if pcr_warn:
        bits.append(pcr_warn + " — รอ price action ยืนยันก่อนสวน")
    bits.append("ทองลงแรงกว่าขึ้น + fat tails → RR ต้องเป็นบวก อย่าเติมไม้ตอนแพง")
    bits.append("รอไส้เทียน H1/H4 ยืนยันก่อนเข้า วาง SL หลังไส้/หลังกำแพง OI · เป้าวินัย RR ≥ 1:2 (setup ไหนต่ำกว่าจะมี ⚠ กำกับ)")
    if s["dte"] < 1:
        bits.append(f"ใกล้หมดอายุ (DTE {s['dte']}) → กำแพง OI บาง/แกว่งแรงช่วงหมดอายุ")
    bits.append(f"จุดเข้า/SL/TP + แนวรับต้าน = ราคา CFD/XAUUSD (แปลงจาก futures ด้วย basis −{basis:g}{' สด' if basis_live else ' ประมาณ'}); basis ขยับตามตลาด ควรเทียบกับราคาโบรกฯ ของคุณอีกที")
    if g_up and g_dn:
        bits.append(f"$50 Grid (Block Trade): ต้านใกล้สุด {g_up['price']} (CFD {g_up['cfd']}{' ★OI' if g_up['oi'] else ''}) / รับใกล้สุด {g_dn['price']} (CFD {g_dn['cfd']}{' ★OI' if g_dn['oi'] else ''}) — ทุกระดับ $50/$100 = ด่าน MM hedge")
    if confluence:
        cs = " · ".join(f"{c['label']} {c['price']} (CFD {c['cfd']:g}) ทับ {c['sigma']}" for c in confluence[:3])
        bits.append(f"⭐ นัยยะสำคัญ OI×SD: {cs} — จุดที่สองระบบชี้ตรงกัน เฝ้าเป็นพิเศษ")
    if cot:
        lean = {"down": "สุดขั้ว → สวน = น้ำหนักลง", "up": "สุดขั้ว → สวน = น้ำหนักขึ้น",
                "flat": "ยังไม่สุดขั้ว → แทบไม่มีน้ำหนัก (รอราคายืนยัน)"}[cot["retail_lean"]]
        bits.append(f"COT {cot['date']} (CFTC รายสัปดาห์): รายย่อย net {cot['retail']['net']:+,} {lean} · กองทุน(specs) net {cot['spec']['net']:+,} · Smart money(comm) net {cot['comm']['net']:+,} (comm+spec = แกนเดียว กระจกกัน)")
    risk = "; ".join(bits)

    # ── headline ──
    skew = s["iv_skew"]["direction"]
    skew_txt = {"put": "skew กลัวลง", "call": "skew กลัวตกรถ (FOMO)", "flat": "skew สมดุล"}[skew]
    chg_txt = f"{'+' if chg >= 0 else ''}{chg}"
    head = (f"ทอง{dirword} {chg_txt} มาที่ {fut} · IV {s['atm_iv']}% (regime {regime}) · "
            f"P/C OI {s.get('pcr_oi')} · {skew_txt} (Put {s['iv_skew']['put_side_avg']}% vs Call {s['iv_skew']['call_side_avg']}%). ")
    if bias == "short":
        head += f"มอง SHORT ({bias_why}) — รอเด้งชนแนวต้าน {res1} แล้วค่อยหาจังหวะ อย่าไล่"
    elif bias == "long":
        head += f"มอง LONG ({bias_why}) — รอย่อหาแนวรับ {sup1} แล้วค่อยหาจังหวะ อย่าไล่"
    else:
        head += f"มอง NEUTRAL — เล่นในกรอบ {sup1}–{res1} รอ breakout ยืนยัน"
        if golden_gate:
            head += " · กฎทอง: IV ยังพุ่ง งดสวนเทรนด์"
    if pcr_warn:
        head += f" · ⚠️ {pcr_warn}"

    now = _bkk_now()
    hm = now.hour * 60 + now.minute
    session = "13:00" if hm < 960 else "19:00" if hm < 1275 else "21:30"   # <16:00 / <21:15 / else
    return {
        "updated_at": now.isoformat(timespec="minutes"),
        "session": session,
        "future": fut,
        "contract": s["contract"],
        "spot_cfd": round(spot, 1),
        "basis": basis,
        "basis_live": basis_live,
        "regime": regime,
        "sigma": round(sd, 1),
        "atm_iv": s["atm_iv"],
        "dte": s["dte"],
        "bias": bias,
        "bias_score": round(score, 3),      # raw blend score (watchdog uses it for ±0.5 hysteresis)
        "headline": head,
        "resistance": res,
        "support": sup,
        "scenarios": scen,
        "entries": entries,
        "grid": grid,
        "sd_ladder": sdl,
        "confluence": confluence,
        "cot": cot,
        "risk": risk,
        "source": "The Invisible Money + OI มีอยู่จริง + OI/Vol (CME)",
    }


def git_push(session):
    date = _bkk_now().strftime("%Y-%m-%d")
    run = lambda *a: subprocess.run(["git", "-C", REPO_DIR, *a], check=False, capture_output=True, text=True)
    run("add", "plan.json", "data")
    run("add", "sd_ladder.json")     # separate call: tolerated if absent (a joint add would fail ALL paths)
    run("commit", "-m", f"Auto plan {session} {date}")
    for attempt in range(1, 4):
        r = run("push")
        if r.returncode == 0:
            print(f"git push: ok (attempt {attempt})")
            return
        print(f"git push attempt {attempt} failed: {((r.stderr or '') + (r.stdout or '')).strip()[:140]}")
        # remote moved (cloud/other runner pushed) — rebase our commit on top, preferring OUR
        # freshly-generated files. GOTCHA: in a REBASE the sides are SWAPPED, so "theirs" = our
        # replayed commit. -X theirs keeps our new plan.json (and auto-resolves so plan.json
        # never gets conflict markers). The old -X ours took ORIGIN's STALE plan instead —
        # that silently re-published yesterday's plan while Telegram had today's (2026-06-18).
        pr = run("pull", "--rebase", "-X", "theirs", "origin", "main")
        if pr.returncode != 0:                       # never leave a stuck/conflicted tree
            run("rebase", "--abort")
            run("reset", "--hard", "origin/main")
            print("git: rebase conflict — reset to origin (plan regenerates next run)")
            return
        time.sleep(5)
    print("git push: FAILED after 3 attempts")


# ── #4: daily OI archive + day-over-day change (book: "Put falling + Call rising" = shift) ──

def archive_oi_and_diff():
    """Save today's raw OIData.txt under data/oi/YYYY-MM-DD.txt (latest wins) and
    return day-over-day per-strike changes vs the most recent prior day, or None."""
    os.makedirs(OI_ARCHIVE_DIR, exist_ok=True)
    today = _bkk_now().strftime("%Y-%m-%d")
    raw = ps.fetch(ps.OI_URL)
    with open(os.path.join(OI_ARCHIVE_DIR, today + ".txt"), "w", encoding="utf-8") as f:
        f.write(raw)

    prior = sorted(d[:-4] for d in os.listdir(OI_ARCHIVE_DIR) if d.endswith(".txt") and d[:-4] < today)
    if not prior:
        return None
    prev_date = prior[-1]
    with open(os.path.join(OI_ARCHIVE_DIR, prev_date + ".txt"), encoding="utf-8") as f:
        prev = ps.parse(f.read())
    cur = ps.parse(raw)
    if cur.get("contract") != prev.get("contract"):
        return {"vs_date": prev_date, "contract_changed": True, "top": []}

    pmap = {r["strike"]: r for r in prev["rows"]}
    changes = []
    for r in cur["rows"]:
        p = pmap.get(r["strike"])
        if not p:
            continue
        dc, dp = r["call"] - p["call"], r["put"] - p["put"]
        if abs(dc) + abs(dp) < 10:        # ignore noise
            continue
        if dp < 0 and dc > 0:
            read = "Put ลด+Call เพิ่ม = โครงสร้างพลิกขึ้น"
        elif dc < 0 and dp > 0:
            read = "Call ลด+Put เพิ่ม = โครงสร้างพลิกลง"
        elif dc > 0 and dp > 0:
            read = "ทั้งคู่เพิ่ม = สนใจ strike นี้หนาแน่น"
        else:
            read = "ทั้งคู่ลด = ถอนความสนใจ"
        changes.append({"strike": int(r["strike"]), "dcall": dc, "dput": dp, "read": read})
    changes.sort(key=lambda c: abs(c["dcall"]) + abs(c["dput"]), reverse=True)
    return {"vs_date": prev_date, "contract_changed": False, "top": changes[:5]}


# ── #3: plan log + outcome evaluation (approx, PAXG 1h candles ≈ CFD/XAUUSD) ──

def _fetch_candles(start_iso, end_iso):
    """Coinbase PAXG-USD hourly candles [[t,low,high,open,close,vol]...] oldest-first, or None.
    CHUNKED: Coinbase caps one request at 300 candles — a single call for a >12-day window
    returns 400 and the whole evaluation silently stalled (stuck 2026-08: one perma-'open'
    plan from 07-02 stretched the window to ~56 days → nothing evaluated for weeks)."""
    from datetime import datetime, timedelta, timezone as _tz
    try:
        t0 = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except Exception:
        return None
    out, cur, got_any = {}, t0, False
    while cur < t1:
        nxt = min(cur + timedelta(hours=290), t1)
        url = ("https://api.exchange.coinbase.com/products/PAXG-USD/candles?granularity=3600"
               f"&start={urllib.parse.quote(cur.strftime('%Y-%m-%dT%H:%M:%SZ'))}"
               f"&end={urllib.parse.quote(nxt.strftime('%Y-%m-%dT%H:%M:%SZ'))}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gold-oi-dashboard"})
            with urllib.request.urlopen(req, timeout=15) as r:
                rows = json.load(r)
            if isinstance(rows, list):
                for c in rows:
                    out[c[0]] = c
                got_any = True
        except Exception:
            pass                                    # a failed chunk skips its span, rest still evaluate
        cur = nxt
        time.sleep(0.4)                             # stay well under Coinbase rate limits
    return sorted(out.values(), key=lambda x: x[0]) if got_any else None


def _judge_entry(en, candles, plan_ts):
    """Walk candles after plan_ts: did price reach entry, then SL or TP1 first?
    Conservative: same-candle SL+TP → 'sl'. Returns no_entry / tp / sl / open."""
    ENTRY_WINDOW_H, WATCH_H = 24, 72
    long_ = en["side"] == "long"
    entry, sl, tp1 = en["entry"], en["sl"], en["tp"][0]
    entered = False
    hours_seen = 0
    for c in candles:
        t, lo, hi = c[0], c[1], c[2]
        if t < plan_ts:
            continue
        hours_seen += 1
        if not entered:
            if hours_seen > ENTRY_WINDOW_H:
                return "no_entry"
            if lo <= entry <= hi:
                entered = True
                hit_sl = (lo <= sl) if long_ else (hi >= sl)
                hit_tp = (hi >= tp1) if long_ else (lo <= tp1)
                if hit_sl:
                    return "sl"           # conservative when both in entry candle
                if hit_tp:
                    return "tp"
            continue
        if hours_seen > WATCH_H:
            # TIME-STOP (daytrade discipline: flat by the watch window, never hold forever).
            # Judge at the boundary close — favorable = tp, else sl. Before this, an entered
            # trade that hit neither level stayed 'open' FOREVER and jammed the whole evaluator.
            close = c[4]
            win = (close > entry) if long_ else (close < entry)
            return "tp" if win else "sl"
        hit_sl = (lo <= sl) if long_ else (hi >= sl)
        hit_tp = (hi >= tp1) if long_ else (lo <= tp1)
        if hit_sl:
            return "sl"
        if hit_tp:
            return "tp"
    return "open" if entered else ("no_entry" if hours_seen > ENTRY_WINDOW_H else "open")


def log_plan_and_evaluate(plan):
    """Append this plan to plans_log.jsonl, re-evaluate unresolved past plans, write track_record.json."""
    os.makedirs(DATA_DIR, exist_ok=True)
    rows = []
    if os.path.exists(PLANS_LOG):
        with open(PLANS_LOG, encoding="utf-8") as f:
            rows = [json.loads(ln) for ln in f if ln.strip()]
    rows.append({"ts": plan["updated_at"], "session": plan["session"], "bias": plan["bias"],
                 "future": plan["future"], "spot_cfd": plan["spot_cfd"],
                 "entries": [{k: e[k] for k in ("side", "title", "entry", "sl", "tp")} for e in plan["entries"]],
                 "outcomes": None})

    now_ts = time.time()
    pending = [r for r in rows[:-1] if not r.get("outcomes") or "open" in r["outcomes"]]
    if pending:
        oldest = min(pending, key=lambda r: r["ts"])
        try:
            from datetime import datetime, timezone
            start_dt = datetime.fromisoformat(oldest["ts"])
            start_iso = datetime.fromtimestamp(start_dt.timestamp() - 3600, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            candles = _fetch_candles(start_iso, end_iso)
        except Exception:
            candles = None
        if candles:
            from datetime import datetime
            for r in pending:
                try:
                    pts = datetime.fromisoformat(r["ts"]).timestamp()
                    if now_ts - pts < 4 * 3600:      # too fresh to judge
                        continue
                    r["outcomes"] = [_judge_entry(e, candles, pts) for e in r["entries"]]
                except Exception:
                    continue

    with open(PLANS_LOG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    flat = [o for r in rows for o in (r.get("outcomes") or []) if o]
    stats = {"tp": flat.count("tp"), "sl": flat.count("sl"),
             "no_entry": flat.count("no_entry"), "open": flat.count("open")}
    closed = stats["tp"] + stats["sl"]
    track = {"updated_at": plan["updated_at"], "n_plans": len(rows), "stats": stats,
             "win_rate": round(stats["tp"] / closed * 100, 1) if closed else None,
             "recent": [{"ts": r["ts"][:16], "session": r["session"], "bias": r["bias"],
                         "outcomes": r.get("outcomes")} for r in rows[-10:]]}
    with open(TRACK_PATH, "w", encoding="utf-8") as f:
        json.dump(track, f, ensure_ascii=False, indent=1)
    print(f"track: plans={len(rows)} stats={stats}")


# ── bell-curve chart image for Telegram (English labels — server fonts lack Thai) ──

def render_chart_png(plan):
    """Draw the OI bell chart (distribution + Call/Put bars + IV smile + σ axis)
    to a temp PNG. Returns path, or None if matplotlib unavailable / data bad."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("chart: matplotlib not installed (pip install matplotlib) — text-only")
        return None
    try:
        import math
        import tempfile
        d = ps.parse(ps.fetch(ps.OI_URL))
        sd, mean = ps.sigma(d), d["future"]
        rows = [r for r in d["rows"] if abs(r["strike"] - mean) <= 3.6 * sd] if sd else []
        if not sd or len(rows) < 5:
            return None

        BG, CALL, PUT, CURVE, IVC, FUT = "#faf6ee", "#1a3a6b", "#c9920a", "#8a8378", "#3f8f8f", "#b08010"
        gaps = sorted(b["strike"] - a["strike"] for a, b in zip(rows, rows[1:]))
        gap = gaps[len(gaps) // 2] if gaps else 5
        w, off = gap * 0.32, gap * 0.18

        fig, ax = plt.subplots(figsize=(10, 5.2), dpi=130)
        fig.patch.set_facecolor(BG); ax.set_facecolor(BG)

        ymax = max(max(r["call"], r["put"]) for r in rows) * 1.28 or 1
        for k in (-3, -2, -1, 1, 2, 3):
            ax.axvline(mean + k * sd, color=CURVE, lw=0.7, ls=":", alpha=0.5)
        ax.axvline(mean, color=FUT, lw=1.1, ls="--", alpha=0.85)

        ax.bar([r["strike"] + off for r in rows], [r["call"] for r in rows], width=w, color=CALL, alpha=0.85, label="Call OI")
        ax.bar([r["strike"] - off for r in rows], [r["put"] for r in rows], width=w, color=PUT, alpha=0.85, label="Put OI")

        xs = [mean - 3.5 * sd + 7 * sd * i / 160 for i in range(161)]
        peak = 1 / (sd * math.sqrt(2 * math.pi))
        ax.plot(xs, [math.exp(-0.5 * ((x - mean) / sd) ** 2) / (sd * math.sqrt(2 * math.pi)) / peak * ymax * 0.86 for x in xs],
                color=CURVE, lw=1.3, label="Expected range")

        ivr = [(r["strike"], r["iv"]) for r in rows if r["iv"] > 0]
        if len(ivr) > 2:
            ivs = [v for _, v in ivr]
            lo, rng = min(ivs), (max(ivs) - min(ivs)) or 1
            ax.plot([s for s, _ in ivr], [ymax * (0.58 + 0.36 * (v - lo) / rng) for _, v in ivr],
                    color=IVC, lw=1.4, ls="--", label=f"IV smile {min(ivs)*100:.1f}–{max(ivs)*100:.1f}%")

        basis = plan.get("basis", 30)
        ticks = [mean + k * sd for k in range(-3, 4)]
        ax.set_xticks(ticks)
        ax.set_xticklabels([("μ" if k == 0 else f"{k:+d}σ") + f"\n{round(mean + k * sd):.0f}" for k in range(-3, 4)],
                           fontsize=8, color="#4a4338")
        ax.set_xlim(mean - 3.6 * sd, mean + 3.6 * sd); ax.set_ylim(0, ymax)
        ax.tick_params(axis="y", labelsize=7, colors="#8a8378")
        for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color("#ddd4c4")

        ax.set_title(f"Gold (OG|GC) Open Interest · {plan['session']} · {plan['updated_at'][:10]}\n"
                     f"future {mean:,.1f} · CFD ≈ {mean - basis:,.1f} (basis −{basis:g}) · 1σ = {sd:,.1f} pts",
                     fontsize=10, color="#1f1a14", loc="left", pad=10)
        ax.legend(loc="upper right", fontsize=7.5, frameon=False, labelcolor="#4a4338")

        out = os.path.join(tempfile.gettempdir(), "gold_oi_chart.png")
        fig.tight_layout(); fig.savefig(out, facecolor=BG); plt.close(fig)
        print("chart: rendered", out)
        return out
    except Exception as e:
        print("chart render failed:", e)
        return None


def _post_multipart(url, fields, file_bytes, filename):
    boundary = "----goldoi" + str(int(time.time()))
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode("utf-8")
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\n"
             f"Content-Type: image/png\r\n\r\n").encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def notify_telegram(plan, chart_path=None):
    """Send a Thai plan summary to Telegram. Reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    from environment (GitHub Secrets on Actions); silently skips when not configured."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("telegram: skipped (no TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return

    bias_icon = {"long": "🟢 LONG", "short": "🔴 SHORT", "neutral": "⚪ NEUTRAL"}.get(plan["bias"], plan["bias"])
    fmt1 = lambda x: f"{x:,.1f}"
    lv = lambda arr: " · ".join(fmt1(l["cfd"]) for l in arr)
    lines = [
        f"📋 แผนทอง GC · รอบ {plan['session']} · {plan['updated_at'][:10]}",
        f"{bias_icon}",
        f"💱 CFD ≈ {fmt1(plan['spot_cfd'])} (fut {fmt1(plan['future'])} · basis −{plan['basis']:g})",
        "",
        f"แนวต้าน: {lv(plan['resistance'])}",
        f"แนวรับ: {lv(plan['support'])}",
        "",
        "🎯 จุดเข้า (CFD/XAUUSD):",
    ]
    sdl = plan.get("sd_ladder")
    if sdl:
        L = sdl["levels"]
        lines[-2:-2] = [
            f"📏 SD Ladder ตี 5{'' if sdl['locked'] else ' (ค่าสด-ไม่ได้ล็อก)'}: Vol {sdl['vol']:g} · DTE {sdl['dte']:g} · 1SD ${sdl['sd1']:g}",
            f"SELL {fmt1(L['p2'])}–{fmt1(L['p3'])} · Mean {fmt1(L['mean'])} · BUY {fmt1(L['m2'])}–{fmt1(L['m3'])}",
            "",
        ]
    for en in plan["entries"]:
        side = "LONG" if en["side"] == "long" else "SHORT"
        tps = "/".join(fmt1(t) for t in en["tp"])
        lines.append(f"• {side} {en['title']}")
        lines.append(f"   เข้า {fmt1(en['entry'])} · SL {fmt1(en['sl'])} · TP {tps} · {en['rr']}")
    lines += [
        "",
        "⚠️ รอไส้เทียน H1/H4 ยืนยันก่อนเข้า · เทียบราคากับโบรกฯ ของคุณ",
        "ไม่ใช่คำแนะนำการลงทุน",
    ]
    text = "\n".join(lines)

    def send_text(body):
        data = urllib.parse.urlencode({"chat_id": chat, "text": body,
                                       "disable_web_page_preview": "true"}).encode("utf-8")
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r).get("ok")

    for attempt in (1, 2):
        try:
            if chart_path and os.path.exists(chart_path):
                with open(chart_path, "rb") as f:
                    png = f.read()
                if len(text) <= 1024:        # Telegram photo-caption limit
                    ok = _post_multipart(f"https://api.telegram.org/bot{token}/sendPhoto",
                                         {"chat_id": chat, "caption": text}, png, "chart.png").get("ok")
                else:
                    ok = _post_multipart(f"https://api.telegram.org/bot{token}/sendPhoto",
                                         {"chat_id": chat}, png, "chart.png").get("ok")
                    ok = send_text(text) and ok
                print(f"telegram: {'photo+plan sent' if ok else 'api returned not-ok'}")
            else:
                ok = send_text(text)
                print(f"telegram: {'sent' if ok else 'api returned not-ok'}")
            return
        except Exception as e:
            print(f"telegram attempt {attempt} failed: {e}")
            chart_path = None          # photo path failed once → retry as text-only
            time.sleep(5)


def plan_is_fresh():
    """True if plan.json was already generated for the current 13:00/19:00 slot.
    Lets a backup runner (late cron / local Task Scheduler) skip without double-sending."""
    try:
        from datetime import timedelta
        with open(PLAN_PATH, encoding="utf-8") as f:
            cur = json.load(f)
        from datetime import datetime
        plan_ts = datetime.fromisoformat(cur["updated_at"]).timestamp()
        now = _bkk_now()
        # most recent scheduled slot today that is already past (13:00 / 19:00 / 21:30)
        todays = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in [(13, 0), (19, 0), (21, 30)]]
        past = [s for s in todays if s <= now]
        slot = max(past) if past else (now - timedelta(days=1)).replace(hour=21, minute=30, second=0, microsecond=0)
        return plan_ts >= slot.timestamp()
    except Exception:
        return False


def _keep_awake(on):
    """Stop Windows sleeping mid-run. The scheduled task uses WakeToRun, so the PC can wake
    at 13:00/19:00/21:30, run us, then sleep again before we finish — killing the process
    after plan.json is pushed but before Telegram sends (seen 2026-06-17 19:00, exit 0xC000013A).
    No-op off Windows (e.g. GitHub Actions)."""
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(
            (ES_CONTINUOUS | ES_SYSTEM_REQUIRED) if on else ES_CONTINUOUS)
    except Exception:
        pass


def write_mt5_plan(plan):
    """Bridge the plan into every MT5 terminal's MQL5/Files/gold_plan.csv so GoldOI_AutoTrader.mq5
    can read it (same %APPDATA%\\MetaQuotes\\Terminal auto-discovery as parse_oi_pdf.py). Line format:
      META,<epoch_utc>,<session>,<bias>,<regime>,<basis>,<future>,<atm_iv>,<sigma>,<updated_at>
      ENTRY,<side>,<entry>,<sl>,<tp1>,<tp2>     (one per setup; prices are CFD/XAUUSD, tp2=0 if none)
    epoch_utc lets the EA reject a stale plan; only called on REAL runs (not --no-push tests) so a
    dry-run never feeds the live EA."""
    rows = ["META,{},{},{},{},{},{},{},{},{}".format(
        int(time.time()), plan["session"], plan["bias"], plan.get("regime", ""), plan["basis"],
        plan["future"], plan.get("atm_iv", ""), plan.get("sigma", ""), plan["updated_at"])]
    for e in plan.get("entries", []):
        tp = e.get("tp") or []
        rows.append("ENTRY,{},{},{},{},{}".format(
            e["side"], e["entry"], e["sl"], tp[0] if tp else 0, tp[1] if len(tp) > 1 else 0))
    for g in plan.get("grid", []):                          # $50 Grid for the SMC EA
        rows.append("GRID,{},{},{},{}".format(
            g["price"], g["cfd"], 1 if g["r100"] else 0, 1 if g["oi"] else 0))
    text = "\n".join(rows) + "\n"
    try:
        with open(os.path.join(DATA_DIR, "gold_plan.csv"), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
    base = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
    n = 0
    if os.path.isdir(base):
        for entry in os.listdir(base):
            fdir = os.path.join(base, entry, "MQL5", "Files")
            if os.path.isdir(fdir):
                try:
                    with open(os.path.join(fdir, "gold_plan.csv"), "w", encoding="utf-8") as f:
                        f.write(text)
                    n += 1
                except Exception:
                    pass
    print(f"mt5 bridge: wrote gold_plan.csv to {n} terminal(s)")


def main():
    no_push = "--no-push" in sys.argv
    no_telegram = "--no-telegram" in sys.argv
    mt5_only = "--mt5-only" in sys.argv      # VPS mode: feed the EA file only (no web/Telegram/track)
    if "--if-stale" in sys.argv and plan_is_fresh():
        print("plan already fresh for this slot — skipping (backup runner)")
        return
    _keep_awake(True)
    try:
        if "--sd-only" in sys.argv:              # 05:05 task: publish today's SD ladder right away
            sd_publish(no_push)
            return
        stats = ps.compute_stats()
        plan = build_plan(stats)
        if mt5_only:                                    # VPS: just write gold_plan.csv for the EA, then stop
            write_mt5_plan(plan)
            print(f"mt5-only: bias={plan['bias']} future={plan['future']} session={plan['session']} basis={plan['basis']}")
            return
        try:
            plan["oi_change"] = archive_oi_and_diff()          # #4 daily OI delta
        except Exception as e:
            print("oi_change failed:", e)
            plan["oi_change"] = None
        with open(PLAN_PATH, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"plan.json: bias={plan['bias']} future={plan['future']} session={plan['session']} "
              f"res={[r['price'] for r in plan['resistance']]} sup={[s_['price'] for s_ in plan['support']]}")
        # SD ladder: the 05:00 lock file is authoritative for the day. If today's locked ladder
        # already exists (git-lock or --sd-manual), EMBED IT into the plan (so Telegram == web)
        # instead of overwriting it with a live/unlocked recomputation.
        try:
            cur_sd = json.load(open(SD_PATH, encoding="utf-8"))
        except Exception:
            cur_sd = None
        today_sd = _sd_anchor_dt().strftime("%Y-%m-%d")
        if cur_sd and cur_sd.get("day") == today_sd and cur_sd.get("locked"):
            plan["sd_ladder"] = cur_sd
            with open(PLAN_PATH, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
        elif plan.get("sd_ladder") and plan["sd_ladder"].get("locked"):
            try:
                with open(SD_PATH, "w", encoding="utf-8") as f:
                    json.dump(plan["sd_ladder"], f, ensure_ascii=False, indent=1)
            except Exception:
                pass
        if not no_push:                                    # feed the live MT5 EA only on real runs
            try:
                write_mt5_plan(plan)
            except Exception as e:
                print("mt5 bridge failed:", e)
        try:
            log_plan_and_evaluate(plan)                        # #3 track record
        except Exception as e:
            print("track failed:", e)
        if no_push:
            print("(--no-push: skipped git)")
        else:
            git_push(plan["session"])
        # Telegram LAST so a fresh remote ≈ a sent message: the cloud backup's --if-stale
        # (remote-freshness) check then doubles as a "was it already sent?" guard, keeping
        # the resend dup-safe. _keep_awake stops the PC sleeping before we reach here.
        if no_telegram:
            print("(--no-telegram: skipped notify)")
        else:
            notify_telegram(plan, render_chart_png(plan))
    finally:
        _keep_awake(False)


if __name__ == "__main__":
    main()
