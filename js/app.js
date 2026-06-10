/* ============================================================
   app.js — UI wiring: summary stats, SD gauge, bell curve,
   OI ladder (OI / Intraday / Both), theme, refresh, TradingView
   ============================================================ */

const state = {
  view: 'oi',                                  // 'oi' | 'intraday' | 'both'
  data: { oi: null, intraday: null },
  theme: localStorage.getItem('theme') || 'light',
  timer: null,
  dataTimeIso: null,                           // when pageth last pushed the data (GitHub commit time)
  lastDataTimeFetch: 0,
};

const fmt = {
  int: (n) => (n || 0).toLocaleString('en-US'),
  px:  (n) => (n || 0).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  sig: (n) => (n >= 0 ? '+' : '') + n,
};

const $ = (id) => document.getElementById(id);

function setStatus(msg, cls = '') {
  $('status').textContent = msg;
  $('pulse').className = 'pulse' + (cls ? ' ' + cls : '');
}

function chgPill(v) {
  if (!v) return '';
  return `<span class="chg ${v > 0 ? 'up' : 'down'}">${fmt.sig(v)}</span>`;
}

function nearestStrike(rows, target) {
  let best = null, bd = Infinity;
  for (const r of rows) {
    const dd = Math.abs(r.strike - target);
    if (dd < bd) { bd = dd; best = r.strike; }
  }
  return best;
}

// nearest strike to each ±1/2/3σ level → { strike: '+1σ', ... }
function buildSdTags(rows, mean, sd) {
  const tags = {};
  if (sd > 0) {
    for (const m of [-3, -2, -1, 1, 2, 3]) {
      const s = nearestStrike(rows, mean + m * sd);
      if (s != null) tags[s] = (m > 0 ? '+' : '') + m + 'σ';
    }
  }
  return tags;
}

// ── summary cards (8): future / IV / DTE / 1σ + OI & Intraday call/put ──
function renderSummary(oi, intr) {
  const sd = sigmaOf(oi);
  const cards = [
    { label: 'Future',        value: `${fmt.px(oi.future)}${chgPill(oi.futureChg)}` },
    { label: 'ATM IV',        value: `${oi.iv.toFixed(2)}<small>%</small>${chgPill(oi.ivChg)}` },
    { label: 'DTE',           value: `${oi.dte}<small> วัน</small>` },
    { label: '1σ ±pts',       value: `±${fmt.px(sd)}` },
    { label: 'OI Call',       value: fmt.int(oi.totalCall),   cls: 'c-call' },
    { label: 'OI Put',        value: fmt.int(oi.totalPut),    cls: 'c-put'  },
    { label: 'Intraday Call', value: fmt.int(intr.totalCall), cls: 'c-call' },
    { label: 'Intraday Put',  value: fmt.int(intr.totalPut),  cls: 'c-put'  },
  ];
  $('summary').innerHTML = cards.map((c) =>
    `<div class="card ${c.cls || ''}"><div class="card-label">${c.label}</div><div class="card-value">${c.value}</div></div>`
  ).join('');

  const pcr = oi.totalCall ? (oi.totalPut / oi.totalCall) : 0;
  $('contract-line').textContent = `${oi.contract || '—'} · P/C ${pcr ? pcr.toFixed(2) : '—'}`;
}

// ── SD gauge: how far is price from the OI centre-of-gravity, in σ ──
function renderGauge(d) {
  const sd = sigmaOf(d);
  const meanOI = oiWeightedMean(d.rows);
  const z = sd ? (d.future - meanOI) / sd : 0;
  const az = Math.abs(z);
  const label = az < 1 ? 'ปกติ' : az < 2 ? 'เริ่มยืด' : az < 3 ? 'ยืดมาก' : 'สุดขั้ว';
  const tag   = az < 1 ? 'NO'   : az < 2 ? 'YES'      : az < 3 ? 'ALL IN' : 'WTF';
  const zc    = az < 1 ? 'g-no' : az < 2 ? 'g-yes'    : az < 3 ? 'g-allin' : 'g-wtf';
  const pos = Math.max(0, Math.min(100, (z + 3.5) / 7 * 100));
  $('gauge').innerHTML = `
    <div class="gauge-top">
      <span class="gauge-title">SD GAUGE · ราคา vs ศูนย์ OI</span>
      <span class="gauge-readout ${zc}">${z >= 0 ? '+' : ''}${z.toFixed(2)}σ · <b>${tag}</b> ${label}</span>
    </div>
    <div class="gauge-track"><div class="gauge-mid"></div><div class="gauge-needle ${zc}" style="left:${pos}%"></div></div>
    <div class="gauge-scale"><span>-3σ</span><span>-2σ</span><span>-1σ</span><span>μ</span><span>+1σ</span><span>+2σ</span><span>+3σ</span></div>
    <div class="gauge-sub">ราคา ${fmt.px(d.future)} · ศูนย์ถ่วง OI ${fmt.px(meanOI)} · σ ${fmt.px(sd)}</div>`;
}

// ── compact bell curve (SVG, full-width, fixed height = mobile friendly) ──
let bellData = { points: [] };   // {strike, xFrac, call, put} per bar, for hover/tap tooltips
function buildBell(d) {
  const sd = sigmaOf(d), mean = d.future;
  bellData = { points: [] };
  if (!sd || !d.rows.length) return '';
  const W = 1000, baseY = 186, topPad = 12;
  const xMin = mean - 3.5 * sd, span = 7 * sd;
  const xPx = (s) => (s - xMin) / span * W;
  const h = baseY - topPad;

  const peak = normalPDF(mean, mean, sd);
  let path = '';
  for (let i = 0; i <= 120; i++) {
    const x = xMin + span * i / 120;
    const y = baseY - (normalPDF(x, mean, sd) / peak) * h;
    path += (i ? 'L' : 'M') + xPx(x).toFixed(1) + ',' + y.toFixed(1) + ' ';
  }

  const rows = d.rows;
  const maxV = Math.max(1, ...rows.map((r) => Math.max(r.call, r.put)));
  const bw = Math.max(2, (W / (rows.length + 1)) * 0.34);
  let bars = '';
  for (const r of rows) {
    const cx = xPx(r.strike);
    const ch = (r.call / maxV) * h, ph = (r.put / maxV) * h;
    bars += `<rect x="${(cx - bw - 0.5).toFixed(1)}" y="${(baseY - ch).toFixed(1)}" width="${bw.toFixed(1)}" height="${ch.toFixed(1)}" class="bell-call"/>`;
    bars += `<rect x="${(cx + 0.5).toFixed(1)}" y="${(baseY - ph).toFixed(1)}" width="${bw.toFixed(1)}" height="${ph.toFixed(1)}" class="bell-put"/>`;
  }

  let grid = '';
  for (const m of [-3, -2, -1, 1, 2, 3]) {
    const gx = xPx(mean + m * sd).toFixed(1);
    grid += `<line x1="${gx}" y1="0" x2="${gx}" y2="${baseY}" class="bell-sig"/>`;
  }
  const mx = xPx(mean).toFixed(1);
  grid += `<line x1="${mx}" y1="0" x2="${mx}" y2="${baseY}" class="bell-mean"/>`;

  // per-strike data for the hover tooltip: position + Call/Put + σ-distance + %OI
  const totalOI = rows.reduce((a, r) => a + r.call + r.put, 0) || 1;
  bellData = { points: rows.map((r) => ({
    strike: r.strike, xFrac: xPx(r.strike) / W, call: r.call, put: r.put,
    sdist: sd ? (r.strike - mean) / sd : 0,
    pct: (r.call + r.put) / totalOI * 100,
  })) };

  // IV smile (Vol Settle) — per-strike implied vol, own-scaled into the upper band
  const ivRows = rows.filter((r) => r.iv > 0);
  let ivLine = '';
  if (ivRows.length > 1) {
    const ivs = ivRows.map((r) => r.iv);
    const ivMin = Math.min(...ivs), ivMax = Math.max(...ivs), ivRange = (ivMax - ivMin) || 1;
    const ivY = (v) => 14 + (1 - (v - ivMin) / ivRange) * 120;   // higher IV → nearer the top
    const pts = ivRows.map((r) => `${xPx(r.strike).toFixed(1)},${ivY(r.iv).toFixed(1)}`).join(' ');
    ivLine = `<polyline points="${pts}" class="bell-iv" vector-effect="non-scaling-stroke"/>`;
  }

  return `<svg viewBox="0 0 ${W} 200" preserveAspectRatio="none" class="bell-svg">
    ${grid}${bars}
    <path d="${path}" class="bell-curve" vector-effect="non-scaling-stroke"/>
    ${ivLine}
    <line x1="0" y1="${baseY}" x2="${W}" y2="${baseY}" class="bell-base"/>
  </svg>`;
}

function renderBell(d) {
  $('bell').innerHTML = buildBell(d);
  const sd = sigmaOf(d), mean = d.future;
  if (!sd) { $('bell-axis').innerHTML = ''; $('bell-cap').innerHTML = ''; return; }
  $('bell-axis').innerHTML = [-3, -2, -1, 0, 1, 2, 3].map((m) => {
    const pos = (3.5 + m) / 7 * 100;
    const lbl = m === 0 ? 'μ' : (m > 0 ? '+' : '') + m + 'σ';
    return `<span style="left:${pos}%">${lbl}<br><i>${Math.round(mean + m * sd)}</i></span>`;
  }).join('');

  const ivs = d.rows.map((r) => r.iv).filter((v) => v > 0);
  const ivTxt = ivs.length ? `${(Math.min(...ivs) * 100).toFixed(1)}–${(Math.max(...ivs) * 100).toFixed(1)}%` : '—';
  $('bell-cap').innerHTML =
    `<span>━ Distribution</span>` +
    `<span class="iv-key">┈ IV smile (Vol Settle) ${ivTxt}</span>` +
    `<span><b style="color:var(--call)">▮</b> Call · <b style="color:var(--put)">▮</b> Put</span>`;
}

// ── ladder: single dataset (OI or Intraday) ──
function renderLadder(d) {
  const el = $('ladder');
  if (!d || !d.rows.length) { el.innerHTML = '<div class="empty">ไม่มีข้อมูล</div>'; return; }
  const mean = d.future, sd = sigmaOf(d);
  const rows = [...d.rows].sort((a, b) => b.strike - a.strike);
  const maxVal = Math.max(1, ...rows.map((r) => Math.max(r.call, r.put)));
  const futStrike = nearestStrike(rows, mean);
  const sdTag = buildSdTags(rows, mean, sd);

  el.innerHTML = rows.map((r) => {
    const zoneN = sd > 0 ? Math.abs(r.strike - mean) / sd : 99;
    const zone = zoneN <= 1 ? 'z-in' : zoneN <= 2 ? 'z-1' : zoneN <= 3 ? 'z-2' : '';
    const isFut = r.strike === futStrike ? ' is-future' : '';
    const tag = sdTag[r.strike] ? `<span class="sd-tag">${sdTag[r.strike]}</span>` : '';
    const callW = (r.call / maxVal * 100).toFixed(1);
    const putW  = (r.put  / maxVal * 100).toFixed(1);
    return `<div class="row ${zone}${isFut}">
      <div class="cell put">${r.put ? `<span class="val">${fmt.int(r.put)}</span>` : ''}<span class="bar put-bar" style="width:${putW}%"></span></div>
      <div class="cell strike">${r.strike}${tag}</div>
      <div class="cell call"><span class="bar call-bar" style="width:${callW}%"></span>${r.call ? `<span class="val">${fmt.int(r.call)}</span>` : ''}</div>
    </div>`;
  }).join('');
  const fut = el.querySelector('.is-future');
  if (fut) fut.scrollIntoView({ block: 'center' });
}

// ── ladder: both datasets overlaid (OI solid · Intraday faded) ──
function renderLadderBoth(oi, intr) {
  const el = $('ladder');
  const merged = mergeBoth(oi.rows, intr.rows);
  if (!merged.length) { el.innerHTML = '<div class="empty">ไม่มีข้อมูล</div>'; return; }
  const mean = oi.future, sd = sigmaOf(oi);
  const rows = [...merged].sort((a, b) => b.strike - a.strike);
  const maxV = Math.max(1, ...rows.map((r) => Math.max(r.oiCall, r.oiPut, r.inCall, r.inPut)));
  const futStrike = nearestStrike(rows, mean);
  const sdTag = buildSdTags(rows, mean, sd);
  const w = (v) => (v / maxV * 100).toFixed(1);

  el.innerHTML = rows.map((r) => {
    const zoneN = sd > 0 ? Math.abs(r.strike - mean) / sd : 99;
    const zone = zoneN <= 1 ? 'z-in' : zoneN <= 2 ? 'z-1' : zoneN <= 3 ? 'z-2' : '';
    const isFut = r.strike === futStrike ? ' is-future' : '';
    const tag = sdTag[r.strike] ? `<span class="sd-tag">${sdTag[r.strike]}</span>` : '';
    return `<div class="row both ${zone}${isFut}">
      <div class="cell put col">
        <div class="bl">${r.oiPut ? `<span class="val">${fmt.int(r.oiPut)}</span>` : ''}<span class="bar put-bar" style="width:${w(r.oiPut)}%"></span></div>
        <div class="bl">${r.inPut ? `<span class="val">${fmt.int(r.inPut)}</span>` : ''}<span class="bar put-bar lite" style="width:${w(r.inPut)}%"></span></div>
      </div>
      <div class="cell strike">${r.strike}${tag}</div>
      <div class="cell call col">
        <div class="bl"><span class="bar call-bar" style="width:${w(r.oiCall)}%"></span>${r.oiCall ? `<span class="val">${fmt.int(r.oiCall)}</span>` : ''}</div>
        <div class="bl"><span class="bar call-bar lite" style="width:${w(r.inCall)}%"></span>${r.inCall ? `<span class="val">${fmt.int(r.inCall)}</span>` : ''}</div>
      </div>
    </div>`;
  }).join('');
  const fut = el.querySelector('.is-future');
  if (fut) fut.scrollIntoView({ block: 'center' });
}

// ── orchestration ──
function render() {
  const oi = state.data.oi, intr = state.data.intraday;
  if (!oi || !intr) return;
  renderSummary(oi, intr);
  const primary = state.view === 'intraday' ? intr : oi;   // gauge + bell reference
  renderGauge(primary);
  renderBell(primary);
  if (state.view === 'both') renderLadderBoth(oi, intr);
  else renderLadder(primary);
}

// ── AI plan (generated 13:00 & 19:00 from The Invisible Money method) ──
const esc = (s) => String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function renderPlan(p) {
  const el = $('plan');
  if (!p || !p.updated_at) {
    el.innerHTML =
      `<div class="plan-head"><span class="plan-title">📋 แผนวันนี้</span></div>` +
      `<div class="plan-empty">${esc((p && p.headline) || 'ยังไม่มีแผน — ระบบจะสร้างแผนอัตโนมัติเวลา 13:00 และ 19:00 (เวลาไทย)')}</div>`;
    return;
  }
  const biasMap = { long: ['ขึ้น · Long', 'b-long'], short: ['ลง · Short', 'b-short'], neutral: ['ไซด์เวย์ · Neutral', 'b-neutral'] };
  const [biasTxt, biasCls] = biasMap[p.bias] || biasMap.neutral;
  const lvls = (arr, cls, label) => (arr && arr.length)
    ? `<div class="plan-lvls"><span class="plan-lbl ${cls}">${label}</span>${arr.map((l) =>
        `<span class="plan-lvl ${cls}">${fmt.px(l.price)}${l.note ? ` <i>${esc(l.note)}</i>` : ''}</span>`).join('')}</div>`
    : '';
  let when = '';
  try { when = p.updated_at ? new Date(p.updated_at).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' }) : ''; } catch (e) {}
  el.innerHTML =
    `<div class="plan-head">
       <span class="plan-title">📋 แผนวันนี้ <span class="plan-bias ${biasCls}">${biasTxt}</span></span>
       <span class="plan-time">รอบ ${esc(p.session || '')} · ${when}</span>
     </div>` +
    (p.headline ? `<div class="plan-headline">${esc(p.headline)}</div>` : '') +
    lvls(p.resistance, 'res', 'แนวต้าน') +
    lvls(p.support, 'sup', 'แนวรับ') +
    (p.scenarios && p.scenarios.length ? `<ul class="plan-scen">${p.scenarios.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>` : '') +
    (p.risk ? `<div class="plan-risk">⚠️ ${esc(p.risk)}</div>` : '') +
    `<div class="plan-src">ที่มา: ${esc(p.source || 'The Invisible Money + OI/Vol')} · AI สร้างอัตโนมัติ ไม่ใช่คำแนะนำการลงทุน</div>`;
}

async function loadPlan() {
  try {
    const res = await fetch('plan.json?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error('no plan');
    renderPlan(await res.json());
  } catch (e) {
    renderPlan(null);
  }
}

// ── source-data freshness: when pageth last pushed OIData.txt (GitHub commit time) ──
const DATA_COMMIT_API = 'https://api.github.com/repos/pageth/Vol2VolData/commits?path=OIData.txt&per_page=1';

async function fetchDataTime() {
  try {
    const r = await fetch(DATA_COMMIT_API, { cache: 'no-store' });
    if (!r.ok) return;                            // rate-limited/offline → keep last known
    const j = await r.json();
    const iso = j && j[0] && j[0].commit && j[0].commit.committer && j[0].commit.committer.date;
    if (iso) { state.dataTimeIso = iso; renderDataTime(iso); }
  } catch (e) { /* keep last */ }
}

function renderDataTime(iso) {
  const el = $('data-time');
  if (!el || !iso) return;
  const t = new Date(iso);
  const ict = t.toLocaleString('th-TH', { timeZone: 'Asia/Bangkok', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  const mins = Math.round((Date.now() - t.getTime()) / 60000);
  let rel = '', dot = '';
  if (mins >= 0 && mins < 1440) {
    rel = mins < 1 ? ' · เมื่อสักครู่' : ` · ${mins} นาทีที่แล้ว`;
    dot = mins <= 15 ? 'fresh' : mins <= 60 ? 'ok' : 'stale';
  }
  el.innerHTML = `<span class="srcdot ${dot}"></span>ข้อมูล OI/Intraday จากต้นทาง (pageth) · อัปเดต ${ict} น.${rel}`;
}

async function load() {
  setStatus('กำลังโหลด…');
  try {
    const [oiTxt, inTxt] = await Promise.all([
      fetchText(DATA_SOURCE.oi),
      fetchText(DATA_SOURCE.intraday),
    ]);
    state.data.oi = parseVol2Vol(oiTxt);
    state.data.intraday = parseVol2Vol(inTxt);
    render();
    const now = new Date().toLocaleTimeString('th-TH');
    setStatus('อัปเดตล่าสุด ' + now, 'live');
    $('data-stamp').textContent = 'sync ' + now;
  } catch (e) {
    setStatus('ดึงข้อมูลไม่สำเร็จ: ' + e.message, 'err');
  }
  // source-data freshness: re-render relative time every cycle; re-fetch commit time every 3 min
  if (state.dataTimeIso) renderDataTime(state.dataTimeIso);
  if (Date.now() - state.lastDataTimeFetch > 180000) {
    state.lastDataTimeFetch = Date.now();
    fetchDataTime();
  }
  loadPlan();
}

// ── theme ──
function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  localStorage.setItem('theme', state.theme);
}
function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  applyTheme();
  mountTradingView();
}

// ── view switch ──
function setView(v) {
  state.view = v;
  ['oi', 'intraday', 'both'].forEach((k) => $('seg-' + k).classList.toggle('active', k === v));
  document.querySelector('.legend').innerHTML =
    '<span class="lg lg-call">■ Call</span><span class="lg lg-put">■ Put</span>' +
    (v === 'both' ? '<span class="lg-hint">เข้ม=OI · จาง=Intraday</span>' : '');
  render();
}

// ── TradingView advanced chart (responsive embed) ──
// NOTE: COMEX:GC1! (gold futures) needs a CME data subscription on TradingView and
// won't load in the free widget. Default to spot gold (OANDA:XAUUSD, ~tracks GC).
// allow_symbol_change is on, so you can switch to your own GC symbol in the chart.
const TV_SYMBOL = 'OANDA:XAUUSD';
function mountTradingView() {
  const c = $('tv');
  const dark = state.theme === 'dark';
  c.innerHTML =
    '<div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>' +
    '<div class="tradingview-widget-copyright">' +
      '<a href="https://www.tradingview.com/symbols/XAUUSD/" rel="noopener nofollow" target="_blank">' +
      '<span class="blue-text">XAU/USD</span></a><span class="trademark"> by TradingView</span></div>';
  const s = document.createElement('script');
  s.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  s.async = true;
  s.textContent = JSON.stringify({
    autosize: true,
    symbol: TV_SYMBOL,
    interval: 'D',
    range: '6M',                 // default to last 6 months (not all history → not squished)
    timezone: 'Asia/Bangkok',
    theme: dark ? 'dark' : 'light',
    style: '1',
    locale: 'th',
    allow_symbol_change: true,
    hide_side_toolbar: true,
    hide_top_toolbar: false,
    hide_legend: false,
    hide_volume: false,
    details: false,
    calendar: false,
    withdateranges: true,        // bottom range buttons (1D/1M/3M/6M/1Y) so user can rescale
    save_image: true,
    backgroundColor: dark ? '#0a0a0a' : '#faf6ee',
    gridColor: 'rgba(140, 131, 120, 0.08)',
    support_host: 'https://www.tradingview.com',
  });
  c.appendChild(s);
}

// ── auto-refresh (every 60s, persisted, ON by default) ──
function setAuto(on) {
  localStorage.setItem('auto', on ? 'on' : 'off');
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  if (on) state.timer = setInterval(load, 60000);
}

// ── bell-curve hover/tap tooltip: snaps to the nearest strike, shows Call/Put ──
function initBellHover() {
  const bell = $('bell'), wrap = document.querySelector('.bell-wrap');
  const cross = $('bell-cross'), tip = $('bell-tip');
  const move = (clientX) => {
    const svg = bell.querySelector('svg');
    if (!svg || !bellData.points.length) return;
    const sr = svg.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (clientX - sr.left) / sr.width));
    let best = bellData.points[0], bd = Infinity;
    for (const p of bellData.points) {
      const dd = Math.abs(p.xFrac - frac);
      if (dd < bd) { bd = dd; best = p; }
    }
    const x = (sr.left - wr.left) + best.xFrac * sr.width;
    cross.style.display = 'block';
    cross.style.left = x + 'px';
    cross.style.top = (sr.top - wr.top) + 'px';
    cross.style.height = sr.height + 'px';
    tip.style.display = 'block';
    const sdTxt = (best.sdist >= 0 ? '+' : '') + best.sdist.toFixed(1) + 'σ';
    const pctLbl = state.view === 'intraday' ? 'vol' : 'OI';
    tip.innerHTML =
      `<b>${best.strike}</b> <span class="t-mut">${sdTxt}</span><br>` +
      `<span style="color:var(--call)">C ${fmt.int(best.call)}</span> · ` +
      `<span style="color:var(--put)">P ${fmt.int(best.put)}</span> · ` +
      `<span class="t-mut">${best.pct.toFixed(1)}% ${pctLbl}</span>`;
    let tx = x + 10;
    if (tx + tip.offsetWidth > wr.width - 4) tx = x - tip.offsetWidth - 10;
    tip.style.left = Math.max(4, tx) + 'px';
    tip.style.top = (sr.top - wr.top + 6) + 'px';
  };
  const hide = () => { cross.style.display = 'none'; tip.style.display = 'none'; };
  bell.addEventListener('mousemove', (e) => move(e.clientX));
  bell.addEventListener('mouseleave', hide);
  bell.addEventListener('touchstart', (e) => { if (e.touches[0]) move(e.touches[0].clientX); }, { passive: true });
  bell.addEventListener('touchmove', (e) => { if (e.touches[0]) move(e.touches[0].clientX); }, { passive: true });
  bell.addEventListener('touchend', hide);
}

// ── init ──
function init() {
  applyTheme();
  mountTradingView();
  initBellHover();
  $('btn-theme').addEventListener('click', toggleTheme);
  $('btn-refresh').addEventListener('click', load);
  $('seg-oi').addEventListener('click', () => setView('oi'));
  $('seg-intraday').addEventListener('click', () => setView('intraday'));
  $('seg-both').addEventListener('click', () => setView('both'));
  $('chk-auto').addEventListener('change', (e) => setAuto(e.target.checked));

  // auto-refresh ON unless the user turned it off before
  const autoOn = (localStorage.getItem('auto') || 'on') === 'on';
  $('chk-auto').checked = autoOn;
  setAuto(autoOn);

  // always pull fresh data when the tab regains focus (open it daily → latest)
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });

  load();
}

document.addEventListener('DOMContentLoaded', init);
