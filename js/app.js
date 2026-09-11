/* ============================================================
   app.js v22 — three sections only:
   (1) CME-style chart: Put/Call per strike (OI or intraday volume), IV smile,
       exact futures marker, the day's tradeable SD zones as shaded bands
   (2) the OI trade plan (plan.json)
   (3) the day's tradeable SD zones (sd_ladder.json)
   Data: data/live/* published by the Barchart→GoldOI bridge (~every 30 min).
   ============================================================ */

const state = {
  view: localStorage.getItem('view') || 'intraday',     // 'intraday' | 'oi' | 'both'
  data: { oi: null, intraday: null },
  status: null,                                          // data/live/status.json (bridge provenance)
  sdl: null,                                             // sd_ladder.json (locked from her sheet)
  plan: null,
  theme: localStorage.getItem('theme') || 'light',
  timer: null,
  priceMode: localStorage.getItem('priceMode') || 'cfd', // 'fut' | 'cfd'
  basis: 10,                                             // futures − CFD gap; refreshed from plan/sd_ladder
  fallback: false,
};

const $ = (id) => document.getElementById(id);
const fmt = {
  int: (n) => (n || 0).toLocaleString('en-US'),
  px:  (n) => (n == null ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })),
  px0: (n) => (n == null ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 })),
};
const esc = (s) => String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const toUnit = (fut) => state.priceMode === 'cfd' ? fut - state.basis : fut;   // futures → displayed unit
const unitName = () => state.priceMode === 'cfd' ? 'CFD' : 'Futures';

function setStatus(msg, cls = '') {
  $('status').textContent = msg;
  $('pulse').className = 'pulse' + (cls ? ' ' + cls : '');
}

// ═══════════════════════════════════════════════════════════════
// 1. CHART
// ═══════════════════════════════════════════════════════════════
const chartGeom = {};             // per panel: geometry + rows for the hover tooltip

function niceMax(v) {
  if (!(v > 0)) return 10;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const f = v / p;
  const n = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 4 ? 4 : f <= 5 ? 5 : 10;
  return n * p;
}

// SD levels in FUTURES terms (the chart's x axis is the strike axis)
function sdFut() {
  const s = state.sdl;
  if (!s || !s.levels) return null;
  if (s.levels_fut) return s.levels_fut;
  const b = typeof s.basis === 'number' ? s.basis : state.basis;
  const o = {};
  for (const k of Object.keys(s.levels)) o[k] = s.levels[k] + b;
  return o;
}

// split sorted IV points where consecutive strikes are unusually far apart (no silent bridging)
function splitGaps(pts) {
  if (pts.length < 2) return [pts];
  const gaps = [];
  for (let i = 1; i < pts.length; i++) gaps.push(pts[i].strike - pts[i - 1].strike);
  const med = gaps.slice().sort((a, b) => a - b)[Math.floor(gaps.length / 2)] || 1;
  const segs = [[pts[0]]];
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].strike - pts[i - 1].strike > 3 * med && pts[i].strike - pts[i - 1].strike > 50) segs.push([pts[i]]);
    else segs[segs.length - 1].push(pts[i]);
  }
  return segs;
}

// PCHIP (Fritsch–Carlson shape-preserving cubic Hermite) through (strike, iv) points → SVG path.
// Both axes are linear, so cubic Hermite in data space maps exactly to cubic Béziers in pixels.
function pchipPath(pts, xf, yf) {
  const n = pts.length;
  const X = pts.map((p) => p.strike), Y = pts.map((p) => p.iv);
  const h = [], d = [];
  for (let i = 0; i < n - 1; i++) { h.push(X[i + 1] - X[i]); d.push((Y[i + 1] - Y[i]) / (X[i + 1] - X[i])); }
  const m = new Array(n).fill(0);
  if (n === 2) { m[0] = m[1] = d[0]; }
  else {
    for (let i = 1; i < n - 1; i++) {
      if (d[i - 1] * d[i] <= 0) m[i] = 0;
      else { const w1 = 2 * h[i] + h[i - 1], w2 = h[i] + 2 * h[i - 1]; m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]); }
    }
    const end = (h0, h1, d0, d1) => {
      let s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
      if (Math.sign(s) !== Math.sign(d0)) s = 0;
      else if (Math.sign(d0) !== Math.sign(d1) && Math.abs(s) > Math.abs(3 * d0)) s = 3 * d0;
      return s;
    };
    m[0] = end(h[0], h[1], d[0], d[1]);
    m[n - 1] = end(h[n - 2], h[n - 3], d[n - 2], d[n - 3]);
  }
  let path = `M${xf(X[0]).toFixed(1)},${yf(Y[0]).toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const hh = h[i];
    const c1x = X[i] + hh / 3, c1y = Y[i] + m[i] * hh / 3;
    const c2x = X[i + 1] - hh / 3, c2y = Y[i + 1] - m[i + 1] * hh / 3;
    path += ` C${xf(c1x).toFixed(1)},${yf(c1y).toFixed(1)} ${xf(c2x).toFixed(1)},${yf(c2y).toFixed(1)} ${xf(X[i + 1]).toFixed(1)},${yf(Y[i + 1]).toFixed(1)}`;
  }
  return path;
}

function ivLabel() {
  const s = state.status;
  if (!s || s.iv_source !== 'quikstrike') return 'IV unavailable — ไม่มี IV ราย strike ที่ตรวจสอบได้ (ไม่สร้างเส้นแทน)';
  let when = '';
  try { when = new Date(s.iv_at).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' }); } catch (e) {}
  const kind = s.iv_kind === 'settlement' ? 'Settlement IV Smile' : 'IV Smile (QuikStrike Pricing Sheet)';
  return `${kind} · ${esc(s.iv_code || '')} · ค่า ณ ${when} · เส้นระหว่างจุด = Interpolated (PCHIP)`;
}

function volSourceLabel(src) {
  if (!src) return '';
  if (src === 'sd_lock') return 'ชีตครูวันนี้';
  if (src.startsWith('sd_lock_prev')) return 'ชีตครูล่าสุด ' + src.replace('sd_lock_prev(', '').replace(')', '');
  return 'Barchart (ประมาณ)';
}

function chartPanel(d, kind) {
  const rows = d.rows || [];
  const F = (state.status && state.status.future) || d.future || 0;
  const L = sdFut();
  const sd1 = state.sdl ? Number(state.sdl.sd1) || 0 : 0;
  const half = Math.max(sd1 ? 3.3 * sd1 : 0, 180);
  const xmin = F - half, xmax = F + half;
  const vis = rows.filter((r) => r.strike >= xmin && r.strike <= xmax);
  const title = `${esc(d.contract || '')} ${kind === 'oi' ? 'Open Interest' : 'Intraday Volume'}`;
  if (!F || !vis.length) {
    return `<div class="chart-panel"><div class="chart-head"><span class="chart-title">${title}</span></div><div class="chart-empty">ไม่มีข้อมูลในช่วงราคา</div></div>`;
  }
  const W = 1000, H = 440, ML = 56, MR = 56, MT = 30, MB = 40;
  const pw = W - ML - MR, ph = H - MT - MB;
  const x = (s) => ML + (s - xmin) / (xmax - xmin) * pw;
  const vmax = Math.max(1, ...vis.map((r) => Math.max(r.call, r.put)));
  const top = niceMax(vmax * 1.08);
  const y = (v) => MT + ph - (v / top) * ph;
  const strikes = vis.map((r) => r.strike).sort((a, b) => a - b);
  let gap = Infinity;
  for (let i = 1; i < strikes.length; i++) gap = Math.min(gap, strikes[i] - strikes[i - 1]);
  if (!isFinite(gap) || gap <= 0) gap = 5;
  const bw = Math.max(1.6, Math.min(9, (pw / ((xmax - xmin) / gap)) * 0.42));

  let svg = '';
  // shaded SD zones (from the locked ladder) — only the tradeable ones, plus the mean line
  if (L) {
    const clip = (a, b) => [Math.max(xmin, Math.min(a, b)), Math.min(xmax, Math.max(a, b))];
    const [b0, b1] = clip(L.m3, L.m2), [s0, s1] = clip(L.p2, L.p3);
    if (b1 > b0) svg += `<rect class="band-buy" x="${x(b0).toFixed(1)}" y="${MT}" width="${(x(b1) - x(b0)).toFixed(1)}" height="${ph}"/>` +
      `<text class="band-lbl buy" x="${(x(b0) + 4).toFixed(1)}" y="${MT + 13}">BUY zone</text>`;
    if (s1 > s0) svg += `<rect class="band-sell" x="${x(s0).toFixed(1)}" y="${MT}" width="${(x(s1) - x(s0)).toFixed(1)}" height="${ph}"/>` +
      `<text class="band-lbl sell" x="${(x(s0) + 4).toFixed(1)}" y="${MT + 13}">SELL zone</text>`;
    if (L.mean >= xmin && L.mean <= xmax) svg += `<line class="mean-line" x1="${x(L.mean).toFixed(1)}" y1="${MT}" x2="${x(L.mean).toFixed(1)}" y2="${MT + ph}"/>`;
  }
  // horizontal grid + left ticks (contracts)
  for (let i = 0; i <= 5; i++) {
    const v = top * i / 5, yy = y(v).toFixed(1);
    svg += `<line class="grid" x1="${ML}" y1="${yy}" x2="${ML + pw}" y2="${yy}"/>` +
      `<text class="tick" x="${ML - 6}" y="${(+yy + 4).toFixed(1)}" text-anchor="end">${fmt.int(Math.round(v))}</text>`;
  }
  // x ticks (strike axis, numeric spacing) in the chosen unit
  const step = half <= 220 ? 25 : 50;
  const first = Math.ceil(xmin / step) * step;
  for (let s = first; s <= xmax; s += step) {
    svg += `<line class="axis" x1="${x(s).toFixed(1)}" y1="${MT + ph}" x2="${x(s).toFixed(1)}" y2="${MT + ph + 4}"/>` +
      `<text class="tick" x="${x(s).toFixed(1)}" y="${MT + ph + 18}" text-anchor="middle">${fmt.px0(toUnit(s))}</text>`;
  }
  svg += `<line class="axis" x1="${ML}" y1="${MT + ph}" x2="${ML + pw}" y2="${MT + ph}"/>`;
  // bars (put left / call right of the strike)
  for (const r of vis) {
    const cx = x(r.strike);
    if (r.put > 0) svg += `<rect class="bar-put" x="${(cx - bw - 0.6).toFixed(1)}" y="${y(r.put).toFixed(1)}" width="${bw.toFixed(1)}" height="${(y(0) - y(r.put)).toFixed(1)}"/>`;
    if (r.call > 0) svg += `<rect class="bar-call" x="${(cx + 0.6).toFixed(1)}" y="${y(r.call).toFixed(1)}" width="${bw.toFixed(1)}" height="${(y(0) - y(r.call)).toFixed(1)}"/>`;
  }
  // IV smile — ONLY from a verified per-strike source (QuikStrike Pricing Sheet via the bridge, same
  // series/expiry as the bars). Source points are the data; the pink dashed curve between them is
  // PCHIP-interpolated (shape-preserving: no overshoot, no forced U, no extrapolation beyond the
  // first/last strike; gaps wider than 3x the median strike gap are left open). Barchart's
  // last-trade IVs never qualify → "IV unavailable" instead of a substitute curve.
  const ivOk = !!(state.status && state.status.iv_source === 'quikstrike');
  const ivp = ivOk ? vis.filter((r) => r.iv >= 0.02 && r.iv <= 2).sort((a, b) => a.strike - b.strike) : [];
  if (ivp.length >= 3) {
    const ivs = ivp.map((r) => r.iv);
    let lo = Math.min(...ivs), hi = Math.max(...ivs);
    if (hi - lo < 0.02) { lo -= 0.01; hi += 0.01; }
    const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
    const yiv = (v) => MT + ph - (v - lo) / (hi - lo) * ph;
    for (const seg of splitGaps(ivp)) {
      if (seg.length >= 2) svg += `<path class="iv-line" d="${pchipPath(seg, (s) => x(s), (v) => yiv(v))}"/>`;
    }
    if (state.showIvPts) svg += ivp.map((r) => `<circle class="iv-dot" cx="${x(r.strike).toFixed(1)}" cy="${yiv(r.iv).toFixed(1)}" r="2.4"/>`).join('');
    for (let i = 0; i <= 4; i++) {
      const v = lo + (hi - lo) * i / 4;
      svg += `<text class="tick r" x="${ML + pw + 6}" y="${(yiv(v) + 4).toFixed(1)}">${(v * 100).toFixed(1)}</text>`;
    }
  }
  // exact futures marker
  if (F >= xmin && F <= xmax) {
    svg += `<line class="fut-line" x1="${x(F).toFixed(1)}" y1="${MT - 6}" x2="${x(F).toFixed(1)}" y2="${MT + ph}"/>` +
      `<text class="fut-lbl" x="${(x(F) + 5).toFixed(1)}" y="${MT - 10}">Future: ${fmt.px(toUnit(F))}</text>`;
  }
  svg += `<line class="hover-line" id="hl-${kind}" x1="0" y1="${MT}" x2="0" y2="${MT + ph}"/>`;

  chartGeom[kind] = { xmin, xmax, ML, pw, W, rows: vis, F };
  const vol = (state.status && state.status.vol) || d.iv;
  const volSrc = volSourceLabel(state.status && state.status.vol_source);
  const ivAtm = ivOk && state.status.iv_atm != null ? ` &nbsp; <span class="st-vol">IV ATM: ${Number(state.status.iv_atm).toFixed(2)}</span> <span style="color:var(--fg2)">(QuikStrike)</span>` : '';
  const stats = `<span class="st-put">Put: ${fmt.int(d.totalPut)}</span> &nbsp; <span class="st-call">Call: ${fmt.int(d.totalCall)}</span> &nbsp; ` +
    `<span class="st-vol">Vol: ${vol ? Number(vol).toFixed(2) : '—'}</span>${volSrc ? ` <span style="color:var(--fg2)">(${esc(volSrc)})</span>` : ''}${ivAtm}`;
  return `<div class="chart-panel"><div class="chart-head"><span class="chart-title">${title}</span><span class="chart-stats">${stats}</span></div>` +
    `<svg viewBox="0 0 ${W} ${H}" class="chart-svg" data-kind="${kind}" preserveAspectRatio="xMidYMid meet">${svg}</svg></div>`;
}

function renderChart() {
  const el = $('chart-panels');
  const kinds = state.view === 'both' ? ['oi', 'intraday'] : [state.view];
  const html = kinds.map((k) => {
    const d = state.data[k];
    return d ? chartPanel(d, k) : `<div class="chart-panel"><div class="chart-empty">ยังไม่มีข้อมูล ${k === 'oi' ? 'Open Interest' : 'Intraday Volume'}</div></div>`;
  }).join('');
  el.innerHTML = html;
  el.querySelectorAll('svg.chart-svg').forEach(attachHover);
  const lg = $('lg-iv');
  if (lg) lg.textContent = (state.status && state.status.iv_source === 'quikstrike')
    ? `┄ ${state.status.iv_kind === 'settlement' ? 'Settlement IV' : 'IV Smile (QuikStrike)'}`
    : '┄ IV unavailable';
  renderChartFoot();
  const d = state.data.oi || state.data.intraday;
  if (d) {
    const pcr = d.totalCall ? (d.totalPut / d.totalCall) : 0;
    const F = (state.status && state.status.future) || d.future;
    $('contract-line').textContent = `${d.contract || '—'} · fut ${fmt.px(F)}${state.basis ? ` · CFD ≈ ${fmt.px(F - state.basis)}` : ''} · P/C OI ${pcr ? pcr.toFixed(2) : '—'}`;
  }
}

function attachHover(svg) {
  const kind = svg.dataset.kind;
  const tip = $('chart-tip');
  const move = (ev) => {
    const g = chartGeom[kind];
    if (!g) return;
    const rect = svg.getBoundingClientRect();
    const px = (ev.clientX - rect.left) / rect.width * g.W;
    const s = g.xmin + (px - g.ML) / g.pw * (g.xmax - g.xmin);
    let best = null, bd = Infinity;
    for (const r of g.rows) { const dd = Math.abs(r.strike - s); if (dd < bd) { bd = dd; best = r; } }
    if (!best) return;
    const hl = svg.querySelector('#hl-' + kind);
    if (hl) { const xx = g.ML + (best.strike - g.xmin) / (g.xmax - g.xmin) * g.pw; hl.setAttribute('x1', xx); hl.setAttribute('x2', xx); hl.style.opacity = 0.5; }
    tip.style.display = 'block';
    tip.innerHTML = `<b>${fmt.px0(toUnit(best.strike))}</b> <span style="color:var(--fg2)">(${unitName()}${state.priceMode === 'cfd' ? ` · fut ${best.strike}` : ''})</span><br>` +
      `<span class="tc">Call ${fmt.int(best.call)}</span> · <span class="tp">Put ${fmt.int(best.put)}</span>` +
      (best.iv > 0 ? ` · IV ${(best.iv * 100).toFixed(1)}%` : '') +
      (g.F ? `<br><span style="color:var(--fg2)">${best.strike > g.F ? '+' : ''}${(best.strike - g.F).toFixed(1)} จาก future</span>` : '');
    const tw = tip.offsetWidth || 160, th = tip.offsetHeight || 50;
    let tx = ev.clientX + 14, ty = ev.clientY - th - 10;
    if (tx + tw > window.innerWidth - 8) tx = ev.clientX - tw - 14;
    if (ty < 8) ty = ev.clientY + 16;
    tip.style.left = tx + 'px'; tip.style.top = ty + 'px';
  };
  const leave = () => { tip.style.display = 'none'; const hl = svg.querySelector('#hl-' + kind); if (hl) hl.style.opacity = 0; };
  svg.addEventListener('mousemove', move);
  svg.addEventListener('touchstart', (e) => { if (e.touches[0]) move(e.touches[0]); }, { passive: true });
  svg.addEventListener('touchmove', (e) => { if (e.touches[0]) move(e.touches[0]); }, { passive: true });
  svg.addEventListener('mouseleave', leave);
  svg.addEventListener('touchend', leave);
}

function renderChartFoot() {
  const el = $('chart-foot');
  const s = state.status;
  const parts = [];
  if (s) {
    let ageMin = null, asof = '';
    try { const t = Date.parse(s.at); ageMin = Math.round((Date.now() - t) / 60000); asof = new Date(t).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' }); } catch (e) {}
    const stale = ageMin != null && ageMin > 75;
    parts.push(`ข้อมูล ณ ${asof}${ageMin != null ? (stale ? ` <span class="warn">(อายุ ${ageMin} นาที — bridge อาจหยุดส่ง)</span>` : ` (อายุ ${ageMin} นาที)`) : ''}`);
    parts.push(`${esc(s.source || 'Barchart (CME)')}`);
    let exp = '';
    try { exp = new Date(s.expiry).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' }); } catch (e) {}
    parts.push(`series ${esc(s.series)} (${esc(s.underlying)}) หมดอายุ ${exp} · DTE ${Number(s.dte).toFixed(2)} · ${s.strikes} strikes`);
    parts.push(`Vol ${Number(s.vol).toFixed(2)} จาก ${esc(volSourceLabel(s.vol_source))}`);
    parts.push(`<span style="color:var(--iv-line)">${ivLabel()}</span>`);
  } else {
    parts.push('ไม่มี status.json — ข้อมูลอาจเป็นชุดสำรอง');
  }
  if (state.fallback) parts.push('<span class="warn">⚠ ใช้ไฟล์สำรองเก่า (data/mirror) — bridge ยังไม่เผยแพร่ข้อมูลสด</span>');
  parts.push(`แกนราคา: ${unitName()}${state.priceMode === 'cfd' ? ` (basis −${fmt.px(state.basis)})` : ''} · โซนสี = BUY/SELL zone ของวัน (ชีตครู) · ราคา Barchart ดีเลย์ ~10-15 นาที`);
  el.innerHTML = parts.join(' · ');
}

// ═══════════════════════════════════════════════════════════════
// 2. PLAN (plan.json — OI walls per the books, ⭐ OI×SD confluence, one order per side)
// ═══════════════════════════════════════════════════════════════
const _thaiYMD = (ms) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(ms));
const _thaiWeekday = (ms) => new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Bangkok', weekday: 'short' }).format(new Date(ms));
const PLAN_SLOTS = [[21, 30], [19, 0], [13, 0]];
function expectedSlotTs(graceMin) {
  const nowMs = Date.now(), cutoff = nowMs - graceMin * 60000;
  for (let back = 0; back < 6; back++) {
    const dayMs = nowMs - back * 86400000;
    for (const [hh, mm] of PLAN_SLOTS) {
      const hs = hh < 10 ? '0' + hh : '' + hh, ms = mm < 10 ? '0' + mm : '' + mm;
      const ts = Date.parse(`${_thaiYMD(dayMs)}T${hs}:${ms}:00+07:00`);
      if (ts <= cutoff) { const wd = _thaiWeekday(ts); if (wd !== 'Sat' && wd !== 'Sun') return ts; }
    }
  }
  return null;
}
function planFreshness(p) {
  try {
    const planTs = Date.parse(p.updated_at);
    const expected = expectedSlotTs(30);
    if (expected && !isNaN(planTs) && planTs < expected - 45 * 60000) {
      return { stale: true, hrs: Math.max(1, Math.round((Date.now() - planTs) / 3600000)) };
    }
  } catch (e) {}
  return { stale: false };
}

function renderPlan(p) {
  const el = $('plan');
  if (!p || !p.updated_at) {
    el.innerHTML = `<div class="plan-head"><span class="plan-title">📋 แผนเทรดจาก OI</span></div>` +
      `<div class="plan-empty">${esc((p && p.headline) || 'ยังไม่มีแผน — ระบบสร้างแผนอัตโนมัติ 13:00 / 19:00 / 21:30 เมื่อมีข้อมูลสด')}</div>`;
    return;
  }
  state.plan = p;
  const biasMap = { long: ['ขึ้น · Long', 'b-long'], short: ['ลง · Short', 'b-short'], neutral: ['ไซด์เวย์ · Neutral', 'b-neutral'] };
  const [biasTxt, biasCls] = biasMap[p.bias] || biasMap.neutral;
  const futMode = state.priceMode === 'fut';
  const b = p.basis || 0;
  const futOf = (cfdVal) => Math.round((cfdVal + b) * 10) / 10;
  const unitTag = futMode ? 'Futures · Topstep' : 'CFD · XAUUSD';
  const lvls = (arr, cls, label) => (arr && arr.length)
    ? `<div class="plan-lvls"><span class="plan-lbl ${cls}">${label}</span>${arr.map((l) => {
        const main = futMode ? l.price : (l.cfd != null ? fmt.px(l.cfd) : fmt.px(l.price));
        const sub  = futMode ? (l.cfd != null ? `cfd ${fmt.px(l.cfd)}` : '') : (l.cfd != null ? `fut ${l.price}` : '');
        return `<span class="plan-lvl ${cls}">${main}${sub ? ` <i>${sub}</i>` : ''}${l.note ? ` <i>· ${esc(l.note)}</i>` : ''}</span>`;
      }).join('')}</div>`
    : '';
  const sigLine = (label, cls, e, sl, tp) =>
    `<div class="entry-nums"><span class="sig-tag ${cls}">${label}</span> เข้า <b>${fmt.px(e)}</b> · SL <b class="c-sl">${fmt.px(sl)}</b> · TP <b class="c-tp">${tp.map((t) => fmt.px(t)).join(' / ')}</b></div>`;
  const entries = (p.entries && p.entries.length)
    ? `<div class="plan-entries"><div class="plan-eh">🎯 จุดเข้า · ฝั่งละ 1 ไม้หลัก</div>${p.entries.map((en) => {
        const tp = en.tp || [];
        return `<div class="entry"><span class="entry-side ${en.side === 'short' ? 'b-short' : 'b-long'}">${en.side === 'short' ? 'SHORT' : 'LONG'}</span>` +
          `<div class="entry-body"><div class="entry-title">${esc(en.title || '')} <span class="c-rr">${esc(en.rr || '')}</span></div>` +
          sigLine('Topstep·fut', 'ts', futOf(en.entry), futOf(en.sl), tp.map(futOf)) +
          sigLine('CFD·MT5', 'cfd', en.entry, en.sl, tp) +
          (en.add_on ? `<div class="entry-addon">↳ จุดเติม ไม้ 2 (${esc(en.add_on.label || '')}): เข้า <b>${fmt.px(en.add_on.entry)}</b> · SL <b class="c-sl">${fmt.px(en.add_on.sl)}</b> <span class="c-mut">(fut ${fmt.px(futOf(en.add_on.entry))})</span></div>` : '') +
          (en.note ? `<div class="entry-note">${esc(en.note)}</div>` : '') +
          `</div></div>`;
      }).join('')}</div>`
    : '';
  const planB = (p.plan_b && p.plan_b.length)
    ? `<div class="plan-b"><div class="plan-eh">🅱 แผนสำรอง · รอเงื่อนไข (ไม่ใช่ออเดอร์)</div>${p.plan_b.map((x) => `<div class="plan-b-row">• ${esc(x)}</div>`).join('')}</div>`
    : '';
  let when = '';
  try { when = new Date(p.updated_at).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' }); } catch (e) {}
  const fresh = planFreshness(p);
  const staleTxt = fresh.stale ? ` · <span class="plan-stale">⚠ ค้าง ${fresh.hrs} ชม.</span>` : '';
  const oic = p.oi_change;
  let oicHtml = '';
  if (oic && oic.contract_changed) {
    oicHtml = `<div class="plan-oic"><div class="plan-eh">📊 OI เปลี่ยนจากวันก่อน</div><div class="oic-row"><i>เปลี่ยนสัญญาใหม่ (rollover) — เทียบวันต่อวันไม่ได้</i></div></div>`;
  } else if (oic && oic.top && oic.top.length) {
    oicHtml = `<div class="plan-oic"><div class="plan-eh">📊 OI เปลี่ยนจากวันก่อน (เทียบ ${esc(oic.vs_date)})</div>` +
      oic.top.map((c) => `<div class="oic-row"><b>${c.strike}</b> <span class="oic-c">C ${c.dcall >= 0 ? '+' : ''}${fmt.int(c.dcall)}</span> · <span class="oic-p">P ${c.dput >= 0 ? '+' : ''}${fmt.int(c.dput)}</span> <i>${esc(c.read)}</i></div>`).join('') + `</div>`;
  }
  el.innerHTML =
    `<div class="plan-head">
       <span class="plan-title">📋 แผนเทรดจาก OI <span class="plan-bias ${biasCls}">${biasTxt}</span></span>
       <span class="plan-time"><span class="pdot ${fresh.stale ? 'stale' : 'ok'}"></span>รอบ ${esc(p.session || '')} · ${when}${staleTxt}</span>
     </div>` +
    (p.spot_cfd != null ? `<div class="plan-cfd">💱 CFD/XAUUSD ≈ <b>${fmt.px(p.spot_cfd)}</b> · futures ${fmt.px(p.future)} · basis −${fmt.px(p.basis)} · <b class="plan-unit">หน่วย: ${unitTag}</b></div>` : '') +
    (p.headline ? `<div class="plan-headline">${esc(p.headline)}</div>` : '') +
    lvls(p.resistance, 'res', 'แนวต้าน') +
    lvls(p.support, 'sup', 'แนวรับ') +
    entries + planB + oicHtml +
    (p.scenarios && p.scenarios.length ? `<ul class="plan-scen">${p.scenarios.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>` : '') +
    (p.risk ? `<div class="plan-risk">⚠️ ${esc(p.risk)}</div>` : '') +
    `<div class="plan-src">ที่มา: ${esc(p.source || 'The Invisible Money + OI มีอยู่จริง')} · สร้างอัตโนมัติ ไม่ใช่คำแนะนำการลงทุน</div>`;
}

// ═══════════════════════════════════════════════════════════════
// 3. TRADEABLE SD ZONES (sd_ladder.json — teacher-sheet formula, locked once a day)
// ═══════════════════════════════════════════════════════════════
function renderSdZones(s) {
  const el = $('sdz');
  if (!s || !s.levels) { el.style.display = 'none'; el.innerHTML = ''; return; }
  state.sdl = s;
  if (typeof s.basis === 'number') state.basis = s.basis;
  const L = s.levels, LF = s.levels_fut || sdFut();
  const f = fmt.px;
  const todayKey = (() => { const d = new Date(Date.now() - 5 * 3600 * 1000); return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Bangkok' }); })();
  const stale = s.day && s.day < todayKey;
  el.style.display = '';
  el.innerHTML =
    `<div class="sdz-head">📏 โซน SD ที่น่าเทรดวันนี้ <span class="sdz-sub">ล็อกจากชีตครู ${esc(s.day || '')} · Vol ${s.vol} · DTE ${s.dte} · 1SD $${s.sd1}${typeof s.basis === 'number' ? ` · basis −${s.basis}` : ''}${s.locked ? '' : ' · <b class="sdz-warn">ค่าสด — ยังไม่ได้ล็อก</b>'}</span></div>` +
    (stale ? `<div class="sdz-stale">⏳ ยังเป็นค่าของ ${esc(s.day)} — ส่งชีตเช้าวันนี้เพื่อล็อกใหม่</div>` : '') +
    `<div class="sdz-rows">` +
      `<div class="sdz-row sell"><span class="sdz-lab">🔴 SELL zone</span><span class="sdz-px">${f(L.p2)} – ${f(L.p3)}</span><span class="sdz-fut">fut ${f(LF.p2)} – ${f(LF.p3)}</span></div>` +
      `<div class="sdz-row mean"><span class="sdz-lab">Mean</span><span class="sdz-px">${f(L.mean)}</span><span class="sdz-fut">fut ${f(LF.mean)}</span></div>` +
      `<div class="sdz-row buy"><span class="sdz-lab">🟢 BUY zone</span><span class="sdz-px">${f(L.m2)} – ${f(L.m3)}</span><span class="sdz-fut">fut ${f(LF.m2)} – ${f(LF.m3)}</span></div>` +
    `</div>` +
    `<div class="sdz-note">ราคา CFD (โบรกคุณ) · โซน = +2..+3SD และ −2..−3SD · ในโซน ±1SD (${f(L.m1)} – ${f(L.p1)}) ห้ามสวน/เฮด · เข้าเฉพาะจุดที่โซนทับกำแพง OI (⭐ ในแผน) และรอไส้ H1 ยืนยัน</div>`;
}

function fetchSdLock() {
  return fetch('sd_ladder.json?t=' + Date.now(), { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : null))
    .then((s) => { if (s && s.levels) renderSdZones(s); else if (state.plan && state.plan.sd_ladder) renderSdZones(state.plan.sd_ladder); })
    .catch(() => { if (state.plan && state.plan.sd_ladder) renderSdZones(state.plan.sd_ladder); });
}

// ── "plan is updating" banner during the GitHub-Pages rebuild lag after a slot ──
function ictParts() {
  const d = new Date();
  const t = d.toLocaleTimeString('en-GB', { timeZone: 'Asia/Bangkok', hour12: false, hour: '2-digit', minute: '2-digit' });
  const [h, m] = t.split(':').map(Number);
  return { date: d.toLocaleDateString('en-CA', { timeZone: 'Asia/Bangkok' }), wd: d.toLocaleDateString('en-US', { timeZone: 'Asia/Bangkok', weekday: 'short' }), hm: h * 60 + m };
}
const SLOT_ORDER = { '13:00': 1, '19:00': 2, '21:30': 3 };
const SLOT_MIN = { '13:00': 780, '19:00': 1140, '21:30': 1290 };
function expectedSlot(t) {
  if (t.wd === 'Sat' || t.wd === 'Sun') return null;
  if (t.hm >= 1290) return '21:30';
  if (t.hm >= 1140) return '19:00';
  if (t.hm >= 780) return '13:00';
  return null;
}
function staleSlot(plan) {
  const now = ictParts();
  const exp = expectedSlot(now);
  if (!exp) return null;
  const planDate = (plan.updated_at || '').slice(0, 10);
  const behind = planDate < now.date || (planDate === now.date && SLOT_ORDER[plan.session] < SLOT_ORDER[exp]);
  if (!behind) return null;
  if (now.hm - SLOT_MIN[exp] > 20) return null;
  return exp;
}
let _stalePoll = null;
function updateStaleBanner(plan) {
  const el = $('stale-banner');
  const sess = plan ? staleSlot(plan) : null;
  if (sess) {
    el.style.display = '';
    el.innerHTML = `⏳ <b>รอบ ${sess} กำลังอัปเดต</b> — เว็บกำลัง build (~1–2 นาที) เดี๋ยวขึ้นเอง`;
    if (!_stalePoll) _stalePoll = setTimeout(() => { _stalePoll = null; loadPlan(); }, 25000);
  } else {
    el.style.display = 'none';
    if (_stalePoll) { clearTimeout(_stalePoll); _stalePoll = null; }
  }
}

async function loadPlan() {
  try {
    const res = await fetch('plan.json?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error('no plan');
    const p = await res.json();
    if (typeof p.basis === 'number' && p.basis > -5 && p.basis < 80) state.basis = p.basis;
    renderPlan(p);
    updateStaleBanner(p);
  } catch (e) {
    renderPlan(null);
    updateStaleBanner(null);
  }
  await fetchSdLock();
  renderChart();                                   // basis / SD zones may have changed
}

// ── data load ──
async function load() {
  setStatus('กำลังโหลด…');
  try {
    const [oiR, inR, st] = await Promise.all([
      fetchText(DATA_SOURCE.oi, DATA_FALLBACK.oi),
      fetchText(DATA_SOURCE.intraday, DATA_FALLBACK.intraday),
      fetchStatus(),
    ]);
    state.data.oi = parseVol2Vol(oiR.text);
    state.data.intraday = parseVol2Vol(inR.text);
    state.fallback = oiR.fb || inR.fb;
    state.status = st;
    const now = new Date().toLocaleTimeString('th-TH');
    if (state.fallback) setStatus('⚠ ใช้ไฟล์สำรองเก่า — bridge ยังไม่ส่งข้อมูลสด · ' + now, 'err');
    else setStatus('อัปเดตล่าสุด ' + now, 'live');
    $('data-stamp').textContent = 'sync ' + now;
  } catch (e) {
    setStatus('ดึงข้อมูลไม่สำเร็จ: ' + e.message, 'err');
  }
  await loadPlan();                                 // plan → sd zones → chart
}

// ── theme / view / unit / auto ──
function applyTheme() { document.documentElement.setAttribute('data-theme', state.theme); localStorage.setItem('theme', state.theme); }
function toggleTheme() { state.theme = state.theme === 'dark' ? 'light' : 'dark'; applyTheme(); }
function setView(v) {
  state.view = v; localStorage.setItem('view', v);
  ['oi', 'intraday', 'both'].forEach((k) => $('seg-' + k).classList.toggle('active', k === v));
  renderChart();
}
function setPriceMode(mode) {
  state.priceMode = mode; localStorage.setItem('priceMode', mode);
  $('px-fut').classList.toggle('active', mode === 'fut');
  $('px-cfd').classList.toggle('active', mode === 'cfd');
  renderChart();
  if (state.plan) renderPlan(state.plan);
}
function setAuto(on) {
  localStorage.setItem('auto', on ? 'on' : 'off');
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  if (on) state.timer = setInterval(load, 60000);
}

function init() {
  applyTheme();
  $('btn-theme').addEventListener('click', toggleTheme);
  $('btn-refresh').addEventListener('click', load);
  $('seg-oi').addEventListener('click', () => setView('oi'));
  $('seg-intraday').addEventListener('click', () => setView('intraday'));
  $('seg-both').addEventListener('click', () => setView('both'));
  $('px-fut').addEventListener('click', () => setPriceMode('fut'));
  $('px-cfd').addEventListener('click', () => setPriceMode('cfd'));
  ['oi', 'intraday', 'both'].forEach((k) => $('seg-' + k).classList.toggle('active', k === state.view));
  $('px-fut').classList.toggle('active', state.priceMode === 'fut');
  $('px-cfd').classList.toggle('active', state.priceMode === 'cfd');
  state.showIvPts = (localStorage.getItem('ivpts') || 'off') === 'on';
  const ip = $('chk-ivpts');
  if (ip) { ip.checked = state.showIvPts; ip.addEventListener('change', (e) => { state.showIvPts = e.target.checked; localStorage.setItem('ivpts', e.target.checked ? 'on' : 'off'); renderChart(); }); }
  $('chk-auto').addEventListener('change', (e) => setAuto(e.target.checked));
  const autoOn = (localStorage.getItem('auto') || 'on') === 'on';
  $('chk-auto').checked = autoOn;
  setAuto(autoOn);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  load();
}

document.addEventListener('DOMContentLoaded', init);
