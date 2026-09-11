"""
barchart_bridge.py — local receiver for the "Barchart → GoldOI Bridge" userscript.

pageth (the old OI data feed) died 2026-09-04. Barchart serves the same CME option data through
its own page API, but only to a real browser (bot-wall: plain Python gets HTTP 403). So the split is:
  * Tampermonkey userscript in HER Chrome (any barchart.com tab kept open) — every 10 min asks this
    bridge which series to fetch (GET /wanted), pulls them from Barchart's page API, POSTs them here.
  * this bridge (runs at logon via task GoldOIBarchartBridge, pythonw) — picks the nearest live weekly
    series (like pageth did) and writes pageth-format files into data/manual/ that generate_plan.py
    already reads by default. Scheduled plan slots then publish automatically (their "new data
    since last plan" guard passes because the files are fresh).
Also: Telegram warning if the browser stops sending for > STALE_MIN during trading hours.

Run:  pythonw barchart_bridge.py        (listens on 127.0.0.1:8765)
Test: curl http://127.0.0.1:8765/status
"""

import os
import sys
import json
import time
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from zoneinfo import ZoneInfo
    TZ_NY = ZoneInfo("America/New_York")
    TZ_BKK = ZoneInfo("Asia/Bangkok")
except Exception:                                   # pragma: no cover
    TZ_NY = timezone(timedelta(hours=-4))
    TZ_BKK = timezone(timedelta(hours=7))

HOST, PORT = "127.0.0.1", 8765
ROOT = os.path.dirname(os.path.abspath(__file__))
MANUAL_DIR = os.path.join(ROOT, "data", "manual")
ARCHIVE_DIR = os.path.join(ROOT, "data", "barchart")
STATUS_PATH = os.path.join(MANUAL_DIR, "barchart_status.json")
SD_PATH = os.path.join(ROOT, "gold-oi-dashboard", "sd_ladder.json")
LOG_PATH = os.path.join(ROOT, "barchart_bridge.log")
HORIZON_DAYS = 9          # how far ahead to list weekly series for the userscript
MIN_DTE = 0.15            # drop a series in its last ~3.5 h (pageth also rolled at expiry)
MIN_OI = 300              # ignore brand-new/empty series
STALE_MIN = 60            # Telegram warning when the browser stops sending for this long
REPO_DIR = os.path.join(ROOT, "gold-oi-dashboard")
LIVE_DIR = os.path.join(REPO_DIR, "data", "live")   # published to the website (GitHub Pages)
PUBLISH_MIN = 30          # git push the live files at most this often (Pages rebuild budget)
import subprocess
PUB_LOCK = threading.Lock()

# Barchart weekly gold option codes (decoded from the site's own dropdowns, 2026-09-09):
# code = PREFIX + WEEKCHAR + MONTHCODE + YY ; "Week n" = n-th <weekday> of that month.
WEEKLY = {
    0: ("IY", lambda w: str(w)),                    # Monday    IY1..IY5
    1: ("I0", lambda w: chr(ord("A") + w)),         # Tuesday   I0B..I0F
    2: ("IY", lambda w: str((5 + w) % 10)),         # Wednesday IY6,IY7,IY8,IY9,IY0
    3: ("I0", lambda w: chr(ord("F") + w)),         # Thursday  I0G..I0K
    4: ("IG", lambda w: str(w)),                    # Friday    IG1..IG5
}
MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M", 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
GC_ACTIVE = [2, 4, 6, 8, 10, 12]                    # GC contract months (G J M Q V Z)


def log(msg):
    line = f"{datetime.now(TZ_BKK).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line)
    except Exception:
        pass


def underlying_for(month, year):
    """Weekly options on a month settle into the NEXT active GC contract (Sep->GCV, Oct->GCZ, Dec->GCG+1)."""
    for m in GC_ACTIVE:
        if m > month:
            return f"GC{MONTH_CODE[m]}{str(year)[2:]}"
    return f"GCG{str(year + 1)[2:]}"


def expiry_dt(d):
    """Weekly gold options expire ~12:30 New York time on the expiry date (matches her DTE convention)."""
    return datetime(d.year, d.month, d.day, 12, 30, tzinfo=TZ_NY)


def upcoming_series(now=None):
    """All weekly series expiring within HORIZON_DAYS, nearest first: [{code, underlying, expiry, dte}]."""
    now = now or datetime.now(timezone.utc)
    out = []
    d = now.astimezone(TZ_NY).date()
    for i in range(HORIZON_DAYS + 1):
        day = d + timedelta(days=i)
        wd = day.weekday()
        if wd not in WEEKLY:
            continue
        exp = expiry_dt(day)
        dte = (exp - now).total_seconds() / 86400.0
        if dte <= 0:
            continue
        prefix, wc = WEEKLY[wd]
        week_n = (day.day - 1) // 7 + 1
        code = f"{prefix}{wc(week_n)}{MONTH_CODE[day.month]}{str(day.year)[2:]}"
        out.append({"code": code, "underlying": underlying_for(day.month, day.year),
                    "expiry": exp.isoformat(), "dte": round(dte, 3)})
    return out


QS_PATH = os.path.join(MANUAL_DIR, "quikstrike_iv.json")
CME_WD = {"M": 0, "T": 1, "W": 2, "R": 3, "H": 3}     # G{w}M/T/W/R = Mon/Tue/Wed/Thu weeklies; OG{w} = Friday
MONTH_FROM_CODE = {v: k for k, v in MONTH_CODE.items()}


def cme_code_expiry(code):
    """'OG2U6' -> 2026-09-11 (2nd Friday of Sep), 'G2TU6' -> 2nd Tuesday, 'G3WQ6' -> 3rd Wednesday. None if unknown."""
    import re
    code = (code or "").strip().upper()
    m = re.match(r"^OG(\d)([FGHJKMNQUVXZ])(\d)$", code)
    if m:
        w, mc, y, wd = int(m.group(1)), m.group(2), int(m.group(3)), 4
    else:
        m = re.match(r"^G(\d)([MTWRH])([FGHJKMNQUVXZ])(\d)$", code)
        if not m:
            return None
        w, mc, y, wd = int(m.group(1)), m.group(3), int(m.group(4)), CME_WD[m.group(2)]
    now_y = datetime.now(TZ_NY).year
    year = (now_y // 10) * 10 + y
    if year < now_y - 1:
        year += 10
    month = MONTH_FROM_CODE.get(mc)
    if not month:
        return None
    d = datetime(year, month, 1).date()
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (w - 1))


def load_qs():
    try:
        return json.load(open(QS_PATH, encoding="utf-8"))
    except Exception:
        return None


def save_qs(payload):
    """POST /iv from the QuikStrike pricing sheet: {code, rows:[[strike, volPct],...], atm: volPct|null}."""
    if payload.get("debug"):                          # userscript could not parse the page: keep evidence
        log(f"quikstrike debug: {json.dumps(payload.get('debug'), ensure_ascii=False)[:900]}")
    rows = [(float(r[0]), float(r[1])) for r in (payload.get("rows") or []) if r and r[1] not in (None, "", 0)]
    if len(rows) < 5:
        return None, "too few IV rows"
    exp = cme_code_expiry(payload.get("code"))
    d = {"code": payload.get("code"), "expiry_date": exp.isoformat() if exp else None,
         "atm": payload.get("atm"), "rows": rows, "kind": payload.get("kind") or "pricing_sheet",
         "page": payload.get("page"), "header": (payload.get("header") or "")[:300],
         "at": datetime.now(TZ_BKK).isoformat(timespec="seconds")}
    os.makedirs(MANUAL_DIR, exist_ok=True)
    json.dump(d, open(QS_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    return d, "ok"


def _sd_vol_today():
    """ATM Vol for the header. Barchart's per-strike IV is computed from stale last trades (read 33-55%
    when QuikStrike said 22.6 on 2026-09-09) — it must NEVER drive regime/SD. Order: her teacher-sheet
    Vol locked today (sd_ladder.json) -> the most recent locked Vol (previous day, flagged) -> None."""
    try:
        d = json.load(open(SD_PATH, encoding="utf-8"))
        if d.get("locked") and d.get("vol"):
            today = datetime.now(TZ_BKK).strftime("%Y-%m-%d")
            return float(d["vol"]), ("sd_lock" if d.get("day") == today else f"sd_lock_prev({d.get('day')})")
    except Exception:
        pass
    return None, None


def _leg(rows, k, side):
    v = rows[k].get(side) or [0, 0, 0]
    return [float(v[0] or 0), float(v[1] or 0), float(v[2] or 0)]


def build_files(payload):
    """Pick the nearest live series with real OI and write pageth-format OIData/IntradayData files."""
    series = payload.get("series") or {}
    futures = payload.get("futures") or {}
    now = datetime.now(timezone.utc)
    chosen = None
    for s in upcoming_series(now):
        rows = (series.get(s["code"]) or {}).get("rows") or {}
        tot_oi = sum(_leg(rows, k, "c")[1] + _leg(rows, k, "p")[1] for k in rows)
        if s["dte"] >= MIN_DTE and rows and tot_oi >= MIN_OI:
            chosen = dict(s, rows=rows, tot_oi=tot_oi)
            break
    if not chosen:
        return None, "no live series with OI in payload"
    fq = futures.get(chosen["underlying"]) or {}
    fut = float(fq.get("last") or 0)
    chg = float(fq.get("chg") or 0)
    if not fut:
        return None, f"no futures quote for {chosen['underlying']}"
    rows = chosen["rows"]
    strikes = sorted(rows, key=lambda k: float(k))
    put_oi = int(sum(_leg(rows, k, "p")[1] for k in strikes))
    call_oi = int(sum(_leg(rows, k, "c")[1] for k in strikes))
    put_vol = int(sum(_leg(rows, k, "p")[0] for k in strikes))
    call_vol = int(sum(_leg(rows, k, "c")[0] for k in strikes))
    vol, vol_src = _sd_vol_today()
    if (vol is None or str(vol_src).startswith("sd_lock_prev")) and qs and qs.get("atm") and iv_source == "quikstrike":
        try:
            if datetime.fromisoformat(qs["at"]).date() == datetime.now(TZ_BKK).date():
                vol, vol_src = round(float(qs["atm"]), 2), "quikstrike_atm"
        except Exception:
            pass
    if vol is None:                                   # fallback: median Barchart IV around the money (noisy!)
        near = sorted(strikes, key=lambda k: abs(float(k) - fut))[:6]
        ivs = sorted(x for k in near for x in (_leg(rows, k, "c")[2], _leg(rows, k, "p")[2]) if x)
        vol = round(ivs[len(ivs) // 2], 2) if ivs else 0.0
        vol_src = "barchart_iv_median"
    dte = chosen["dte"]
    qs = load_qs()
    qs_map, iv_source = {}, "barchart"
    if qs and qs.get("rows"):
        same = (qs.get("expiry_date") == chosen["expiry"][:10])
        fresh = True
        try:
            fresh = (datetime.now(TZ_BKK) - datetime.fromisoformat(qs["at"])).total_seconds() < 14 * 3600
        except Exception:
            pass
        if same and fresh:
            qs_map = {round(k, 1): v for k, v in qs["rows"]}
            iv_source = "quikstrike"
    hdr = f"Gold (OG|GC) {chosen['code']} ({dte:.2f} DTE) vs {fut:g} ({chg:+g})"
    os.makedirs(MANUAL_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    def write(name, kind, idx, tp, tc):
        lines = [f"{hdr} - {kind}",
                 f"Put: {tp:,}  Call: {tc:,}  Vol: {vol:.2f}  Vol Chg: 0.00  Future Chg: {chg:+g}",
                 "Strike,Call,Put,Vol Settle"]
        for k in strikes:
            c, p = _leg(rows, k, "c"), _leg(rows, k, "p")
            if qs_map:                                    # CME settlement smile (QuikStrike) wins; else 0 = n/a
                iv = qs_map.get(round(float(k), 1), 0.0)
            else:
                iv = 0.0                                  # Barchart last-trade IV is noise — never publish it as a smile
            lines.append(f"{float(k):g},{int(c[idx])},{int(p[idx])},{round(iv / 100.0, 4)}")
        text = "\n".join(lines) + "\n"
        with open(os.path.join(MANUAL_DIR, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        stamp = datetime.now(TZ_BKK).strftime("%Y-%m-%d_%H%M")
        with open(os.path.join(ARCHIVE_DIR, f"{stamp}_{name}"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return text

    texts = {"OIData.txt": write("OIData.txt", "Open Interest", 1, put_oi, call_oi),
             "IntradayData.txt": write("IntradayData.txt", "Intraday Volume", 0, put_vol, call_vol)}
    status = {"at": datetime.now(TZ_BKK).isoformat(timespec="seconds"), "series": chosen["code"],
              "underlying": chosen["underlying"], "expiry": chosen["expiry"], "dte": dte, "future": fut,
              "chg": chg, "put_oi": put_oi, "call_oi": call_oi, "strikes": len(strikes),
              "vol": vol, "vol_source": vol_src, "iv_source": iv_source,
              "iv_at": (qs or {}).get("at") if iv_source == "quikstrike" else None,
              "iv_code": (qs or {}).get("code") if iv_source == "quikstrike" else None}
    json.dump(status, open(STATUS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        publish_live(status, texts)
    except Exception as e:
        log(f"publish_live error: {e}")
    return status, "ok"


def publish_live(status, texts):
    """Copy the live files into the website repo (data/live/) and git-push them at most every
    PUBLISH_MIN minutes, so the dashboard chart follows the market during the day (not only at
    the 3 plan slots). The push runs in a background thread; generate_plan's own push at slot
    time also carries data/live (its git_push stages the data/ folder)."""
    os.makedirs(LIVE_DIR, exist_ok=True)
    for name, text in texts.items():
        with open(os.path.join(LIVE_DIR, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    pub = dict(status, source="Barchart (CME data, ~10-15 min delay)")
    qs = load_qs() if status.get("iv_source") == "quikstrike" else None
    if qs:
        pub["iv_kind"] = qs.get("kind"); pub["iv_atm"] = qs.get("atm"); pub["iv_n"] = len(qs.get("rows") or [])
    json.dump(pub, open(os.path.join(LIVE_DIR, "status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if time.time() - STATE.get("last_publish", 0) < PUBLISH_MIN * 60:
        return
    STATE["last_publish"] = time.time()
    threading.Thread(target=_git_publish, args=(status.get("series"),), daemon=True).start()


def _git_publish(series):
    if not PUB_LOCK.acquire(blocking=False):
        return
    try:
        def git(*a, timeout=90):
            return subprocess.run(["git", "-C", REPO_DIR, *a], capture_output=True, text=True, timeout=timeout)
        git("add", "data/live")
        c = git("commit", "-q", "-m", f"live data {series} {datetime.now(TZ_BKK).strftime('%m-%d %H:%M')}")
        if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr):
            return
        git("pull", "--rebase", "-X", "theirs", "origin", "main", "-q")
        r = git("push", "-q", "origin", "main")
        log(f"live publish: {'ok' if r.returncode == 0 else 'FAILED ' + (r.stderr or '')[-160:]}")
    except Exception as e:
        log(f"live publish error: {e}")
    finally:
        PUB_LOCK.release()


def tg_send(text):
    """Telegram warning (same env vars generate_plan uses). Silently skipped when not configured."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception as e:
        log(f"telegram failed: {e}")
        return False


STATE = {"last_ingest": None, "last_status": None, "warned": False, "errors": 0, "started": time.time()}


def stale_watch():
    while True:
        time.sleep(300)
        try:
            now = datetime.now(TZ_BKK)
            trading = now.weekday() < 5 and (now.hour >= 6 or now.hour < 2)
            last = STATE["last_ingest"] or STATE["started"]      # never-ingested since start counts too
            gap = (time.time() - last) / 60
            if trading and gap is not None and gap > STALE_MIN and not STATE["warned"]:
                tg_send(f"⚠️ Barchart bridge เงียบ {gap:.0f} นาที — เปิดแท็บ barchart.com ค้างไว้อยู่ไหมคะ? "
                        f"(แผนรอบถัดไปจะข้ามถ้าไม่มีข้อมูลใหม่)")
                STATE["warned"] = True
                log(f"stale warning sent (gap {gap:.0f} min)")
        except Exception as e:
            log(f"stale_watch error: {e}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")   # Chrome PNA preflight
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):                        # keep the console quiet
        pass

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        if self.path.startswith("/wanted"):
            ser = upcoming_series()
            self._send(200, {"symbols": [s["code"] for s in ser][:6],
                             "futures": sorted({s["underlying"] for s in ser}),
                             "series": ser[:6]})
        elif self.path.startswith("/iv"):
            self._send(200, load_qs() or {"rows": [], "msg": "no QuikStrike IV received yet"})
        elif self.path.startswith("/status"):
            self._send(200, {"last_ingest": STATE["last_ingest"], "status": STATE["last_status"],
                             "errors": STATE["errors"], "wanted": [s["code"] for s in upcoming_series()][:6]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.startswith("/iv"):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n).decode("utf-8"))
                d, msg = save_qs(payload)
                if d:
                    log(f"quikstrike iv: {d['code']} exp {d['expiry_date']} rows {len(d['rows'])} atm {d.get('atm')}")
                return self._send(200, {"ok": bool(d), "msg": msg, "expiry_date": (d or {}).get("expiry_date")})
            except Exception as e:
                return self._send(500, {"ok": False, "msg": str(e)})
        if not self.path.startswith("/ingest"):
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            status, msg = build_files(payload)
            STATE["last_ingest"] = time.time()
            STATE["warned"] = False
            if status:
                STATE["last_status"] = status
                log(f"ingest ok: {status['series']} fut {status['future']} DTE {status['dte']} "
                    f"OI P/C {status['put_oi']}/{status['call_oi']} strikes {status['strikes']} "
                    f"vol {status['vol']} ({status['vol_source']})")
            else:
                log(f"ingest rejected: {msg}")
            self._send(200, {"ok": bool(status), "msg": msg, "status": status})
        except Exception as e:
            STATE["errors"] += 1
            log(f"ingest error: {e}")
            self._send(500, {"ok": False, "msg": str(e)})


def main():
    threading.Thread(target=stale_watch, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    log(f"bridge listening on http://{HOST}:{PORT}  wanted={[s['code'] for s in upcoming_series()][:6]}")
    srv.serve_forever()


if __name__ == "__main__":
    if "--wanted" in sys.argv:
        print(json.dumps(upcoming_series(), indent=1))
    else:
        main()
