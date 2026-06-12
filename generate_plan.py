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

# Live gold spot proxy = PAXG (Pax Gold, 1 token ≈ 1oz, tracks XAU spot). Try several
# exchanges in order so it works both locally (Thailand) and from GitHub Actions
# (US/Azure runners — Binance is geo-blocked there, but Coinbase/Kraken are reachable).
SPOT_SOURCES = [
    ("https://api.exchange.coinbase.com/products/PAXG-USD/ticker", lambda j: float(j["price"])),
    ("https://api.kraken.com/0/public/Ticker?pair=PAXGUSD",        lambda j: float(j["result"]["PAXGUSD"]["c"][0])),
    ("https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT", lambda j: float(j["price"])),
]
DEFAULT_BASIS = 30.0   # fallback futures−spot gap (book's ~$30) if no source reachable


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


def build_plan(s):
    fut = s["future"]
    sd = s["sigma_points"] or 1
    regime = s["regime_heuristic"]
    chg = s["future_chg"]
    magnet = s.get("magnet_strike") or {}
    call_tail = s.get("call_tail") or {}
    put_tail = s.get("put_tail") or {}

    # ── futures → CFD/XAUUSD: basis = futures − live spot (fallback to book's ~$30) ──
    spot = fetch_spot()
    if spot is not None and -5 < (fut - spot) < 80:
        basis, basis_live = round(fut - spot, 1), True
    else:
        basis, basis_live = DEFAULT_BASIS, False
        spot = round(fut - basis, 1)
    cfd = lambda x: round(x - basis, 1)

    # ── bias: dominant signal = the day's move vs σ. High vol => follow the trend (don't fade). ──
    move = chg / sd if sd else 0
    if move <= -0.4:
        bias, dirword = "short", "ลง"
    elif move >= 0.4:
        bias, dirword = "long", "ขึ้น"
    else:
        bias, dirword = "neutral", "ออกข้าง"

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
            f"ทะลุ {res1} + OI/วอลุ่มเพิ่ม → ไปต่อหา {res_last}; หลุด {sup1} + OI/วอลุ่มเพิ่ม → ลงหา {sup_last}",
            "ยังไม่เลือกข้างชัด — รอ breakout พร้อมวอลุ่มยืนยัน อย่าไล่กลางกรอบ",
        ]

    # ── concrete entry setups (entry / SL / TP in CFD + RR), per the H1-rejection method ──
    # SL buffer behind the wall, wider when volatile (book: high vol => widen SL)
    buf = max(round(0.6 * sd) if regime == "high" else round(0.4 * sd), 12)

    def setup(side, title, e, sl, tps, note):
        risk_pts = abs(sl - e) or 1
        rr = abs(e - tps[0]) / risk_pts
        rr_txt = ("≈1:" + f"{rr:.1f}".rstrip("0").rstrip("."))
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

    # ── risk (regime-aware) ──
    bits = []
    if regime == "high":
        bits.append(f"ผันผวนสูงมาก (IV {s['atm_iv']}% = regime สูง) → กฎทอง 'Vol ยังทำ New High ห้ามสวนเทรนด์' ลดขนาดไม้ ≥ ครึ่ง ขยาย SL; ราคาทะลุแนว OI ไปไกลกว่าคำนวณ 2–3 เท่าได้")
    elif regime == "low":
        bits.append("ผันผวนต่ำ (regime เขียว) → Mean Reversion ตามแนว OI แม่นขึ้น แต่ระวัง breakout เงียบ ๆ")
    else:
        bits.append("ผันผวนปกติ → เทรดตามแนว OI ได้ แต่ยังต้องรอจังหวะยืนยัน")
    bits.append("ทองลงแรงกว่าขึ้น + fat tails → RR ต้องเป็นบวก อย่าเติมไม้ตอนแพง")
    bits.append("รอไส้เทียน H1/H4 ยืนยันก่อนเข้า วาง SL หลังไส้/หลังกำแพง OI · RR ≥ 1:2")
    if s["dte"] < 1:
        bits.append(f"ใกล้หมดอายุ (DTE {s['dte']}) → กำแพง OI บาง/แกว่งแรงช่วงหมดอายุ")
    bits.append(f"จุดเข้า/SL/TP + แนวรับต้าน = ราคา CFD/XAUUSD (แปลงจาก futures ด้วย basis −{basis:g}{' สด' if basis_live else ' ประมาณ'}); basis ขยับตามตลาด ควรเทียบกับราคาโบรกฯ ของคุณอีกที")
    risk = "; ".join(bits)

    # ── headline ──
    skew = s["iv_skew"]["direction"]
    skew_txt = {"put": "skew กลัวลง", "call": "skew กลัวตกรถ (FOMO)", "flat": "skew สมดุล"}[skew]
    chg_txt = f"{'+' if chg >= 0 else ''}{chg}"
    head = (f"ทอง{dirword} {chg_txt} มาที่ {fut} · IV {s['atm_iv']}% (regime {regime}) · "
            f"P/C OI {s.get('pcr_oi')} · {skew_txt} (Put {s['iv_skew']['put_side_avg']}% vs Call {s['iv_skew']['call_side_avg']}%). ")
    if bias == "short":
        head += f"มอง SHORT ตามเทรนด์ — รอเด้งชนแนวต้าน {res1} แล้วค่อยหาจังหวะ อย่าไล่"
    elif bias == "long":
        head += f"มอง LONG ตามเทรนด์ — รอย่อหาแนวรับ {sup1} แล้วค่อยหาจังหวะ อย่าไล่"
    else:
        head += f"มอง NEUTRAL — เล่นในกรอบ {sup1}–{res1} รอ breakout ยืนยัน"

    now = _bkk_now()
    return {
        "updated_at": now.isoformat(timespec="minutes"),
        "session": "13:00" if now.hour < 16 else "19:00",
        "future": fut,
        "spot_cfd": round(spot, 1),
        "basis": basis,
        "basis_live": basis_live,
        "bias": bias,
        "headline": head,
        "resistance": res,
        "support": sup,
        "scenarios": scen,
        "entries": entries,
        "risk": risk,
        "source": "The Invisible Money + OI มีอยู่จริง + OI/Vol (CME)",
    }


def git_push(session):
    date = _bkk_now().strftime("%Y-%m-%d")
    subprocess.run(["git", "-C", REPO_DIR, "add", "plan.json", "data"], check=False, capture_output=True, text=True)
    subprocess.run(["git", "-C", REPO_DIR, "commit", "-m", f"Auto plan {session} {date}"], check=False, capture_output=True, text=True)
    # Retry push to survive transient network failures (a silent failure would otherwise
    # strand the commit unpushed until the next run). Rebase between tries in case remote moved.
    for attempt in range(1, 4):
        r = subprocess.run(["git", "-C", REPO_DIR, "push"], check=False, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"git push: ok (attempt {attempt})")
            return
        print(f"git push attempt {attempt} failed: {((r.stderr or '') + (r.stdout or '')).strip()[:160]}")
        subprocess.run(["git", "-C", REPO_DIR, "pull", "--rebase"], check=False, capture_output=True, text=True)
        time.sleep(8)
    print("git push: FAILED after 3 attempts — commit stays local, next run will retry")


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
    """Coinbase PAXG-USD hourly candles [[t,low,high,open,close,vol]...] oldest-first, or None."""
    url = ("https://api.exchange.coinbase.com/products/PAXG-USD/candles?granularity=3600"
           f"&start={urllib.parse.quote(start_iso)}&end={urllib.parse.quote(end_iso)}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gold-oi-dashboard"})
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.load(r)
        return sorted(rows, key=lambda x: x[0]) if isinstance(rows, list) else None
    except Exception:
        return None


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
            return "open"
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


def notify_telegram(plan):
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
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": "\n".join(lines),
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
            with urllib.request.urlopen(req, timeout=15) as r:
                ok = json.load(r).get("ok")
            print(f"telegram: {'sent' if ok else 'api returned not-ok'}")
            return
        except Exception as e:
            print(f"telegram attempt {attempt} failed: {e}")
            time.sleep(5)


def main():
    no_push = "--no-push" in sys.argv
    no_telegram = "--no-telegram" in sys.argv
    stats = ps.compute_stats()
    plan = build_plan(stats)
    try:
        plan["oi_change"] = archive_oi_and_diff()          # #4 daily OI delta
    except Exception as e:
        print("oi_change failed:", e)
        plan["oi_change"] = None
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    try:
        log_plan_and_evaluate(plan)                        # #3 track record
    except Exception as e:
        print("track failed:", e)
    print(f"plan.json: bias={plan['bias']} future={plan['future']} session={plan['session']} "
          f"res={[r['price'] for r in plan['resistance']]} sup={[s_['price'] for s_ in plan['support']]}")
    if no_push:
        print("(--no-push: skipped git)")
    else:
        git_push(plan["session"])
    if no_telegram:
        print("(--no-telegram: skipped notify)")
    else:
        notify_telegram(plan)


if __name__ == "__main__":
    main()
