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
  priceMode: localStorage.getItem('priceMode') || 'fut',   // 'fut' | 'cfd' — bell axis/tooltip unit
  basis: 30,                                   // futures − CFD gap; refreshed from plan.json
};

// convert a futures price to the displayed unit
const toPx = (v) => state.priceMode === 'cfd' ? v - state.basis : v;

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
    return `<span style="left:${pos}%">${lbl}<br><i>${Math.round(toPx(mean + m * sd))}</i></span>`;
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

// ── plan freshness: is the shown plan the most recent expected 13:00/19:00 weekday run? ──
// (Thailand has no DST, so +07:00 is constant — slot timestamps are exact.)
const _thaiYMD = (ms) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(ms));
const _thaiWeekday = (ms) => new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Bangkok', weekday: 'short' }).format(new Date(ms));

const PLAN_SLOTS = [[21, 30], [19, 0], [13, 0]];      // Thai-time daily slots, newest first
function expectedSlotTs(graceMin) {
  const nowMs = Date.now(), cutoff = nowMs - graceMin * 60000;
  for (let back = 0; back < 6; back++) {              // walk back far enough to clear a weekend
    const dayMs = nowMs - back * 86400000;
    for (const [hh, mm] of PLAN_SLOTS) {
      const hs = hh < 10 ? '0' + hh : '' + hh, ms = mm < 10 ? '0' + mm : '' + mm;
      const ts = Date.parse(`${_thaiYMD(dayMs)}T${hs}:${ms}:00+07:00`);
      if (ts <= cutoff) {
        const wd = _thaiWeekday(ts);
        if (wd !== 'Sat' && wd !== 'Sun') return ts;   // only weekday slots are "expected"
      }
    }
  }
  return null;
}

function planFreshness(p) {
  try {
    const planTs = Date.parse(p.updated_at);
    const expected = expectedSlotTs(30);              // 30-min grace: run + push + Pages rebuild
    if (expected && !isNaN(planTs) && planTs < expected - 45 * 60000) {
      return { stale: true, hrs: Math.max(1, Math.round((Date.now() - planTs) / 3600000)) };
    }
  } catch (e) { /* ignore */ }
  return { stale: false };
}

function renderPlan(p) {
  const el = $('plan');
  if (!p || !p.updated_at) {
    el.innerHTML =
      `<div class="plan-head"><span class="plan-title">📋 แผนวันนี้</span></div>` +
      `<div class="plan-empty">${esc((p && p.headline) || 'ยังไม่มีแผน — ระบบจะสร้างแผนอัตโนมัติเวลา 13:00 และ 19:00 (เวลาไทย)')}</div>`;
    return;
  }
  state.plan = p;
  const biasMap = { long: ['ขึ้น · Long', 'b-long'], short: ['ลง · Short', 'b-short'], neutral: ['ไซด์เวย์ · Neutral', 'b-neutral'] };
  const [biasTxt, biasCls] = biasMap[p.bias] || biasMap.neutral;

  // price unit follows the Futures/CFD toggle. Entries/levels are stored in CFD; add basis for futures.
  const futMode = state.priceMode === 'fut';
  const b = p.basis || 0;
  const conv = (cfdVal) => futMode ? Math.round((cfdVal + b) * 10) / 10 : cfdVal;
  const unitTag = futMode ? 'Futures · Topstep' : 'CFD · XAUUSD';

  // levels carry both price(=futures strike) and cfd → show the active unit primary, other in ()
  const lvls = (arr, cls, label) => (arr && arr.length)
    ? `<div class="plan-lvls"><span class="plan-lbl ${cls}">${label}</span>${arr.map((l) => {
        const main = futMode ? l.price : (l.cfd != null ? fmt.px(l.cfd) : fmt.px(l.price));
        const sub  = futMode ? (l.cfd != null ? `cfd ${fmt.px(l.cfd)}` : '') : (l.cfd != null ? `fut ${l.price}` : '');
        return `<span class="plan-lvl ${cls}">${main}${sub ? ` <i>${sub}</i>` : ''}${l.note ? ` <i>· ${esc(l.note)}</i>` : ''}</span>`;
      }).join('')}</div>`
    : '';

  const futOf = (cfdVal) => Math.round((cfdVal + b) * 10) / 10;   // CFD → futures (Topstep)
  const sigLine = (label, cls, e, sl, tp) =>
    `<div class="entry-nums"><span class="sig-tag ${cls}">${label}</span> เข้า <b>${fmt.px(e)}</b> · SL <b class="c-sl">${fmt.px(sl)}</b> · TP <b class="c-tp">${tp.map((t) => fmt.px(t)).join(' / ')}</b></div>`;
  const entries = (p.entries && p.entries.length)
    ? `<div class="plan-entries"><div class="plan-eh">🎯 จุดเข้า · Signal</div>${p.entries.map((en) => {
        const tp = en.tp || [];
        return `<div class="entry"><span class="entry-side ${en.side === 'short' ? 'b-short' : 'b-long'}">${en.side === 'short' ? 'SHORT' : 'LONG'}</span>` +
          `<div class="entry-body"><div class="entry-title">${esc(en.title || '')} <span class="c-rr">${esc(en.rr || '')}</span></div>` +
          sigLine('Topstep·fut', 'ts', futOf(en.entry), futOf(en.sl), tp.map(futOf)) +
          sigLine('CFD·MT5', 'cfd', en.entry, en.sl, tp) +
          (en.note ? `<div class="entry-note">${esc(en.note)}</div>` : '') +
          `</div></div>`;
      }).join('')}</div>`
    : '';

  // Topstep position-size calculator (gold futures: GC = $100/point, MGC = $10/point)
  const calcRows = (risk) => (p.entries || []).map((en) => {
    const dist = Math.abs(en.entry - en.sl);
    const gc = dist > 0 ? Math.floor(risk / (dist * 100)) : 0;
    const mgc = dist > 0 ? Math.floor(risk / (dist * 10)) : 0;
    return `<div class="calc-row"><b class="${en.side === 'short' ? 'b-short' : 'b-long'}">${en.side === 'short' ? 'SHORT' : 'LONG'}</b> SL ${dist.toFixed(0)} จุด → <span class="c-mgc">MGC ${mgc}</span> / <span class="c-gc">GC ${gc}</span> ไม้</div>`;
  }).join('');
  const risk0 = +(localStorage.getItem('topstepRisk') || 300);
  const calc = (p.entries && p.entries.length)
    ? `<div class="plan-calc"><div class="plan-eh">📐 ขนาดไม้ Topstep (Futures)</div>` +
      `<label class="calc-risk">เสี่ยงต่อไม้ $ <input id="ts-risk" type="number" value="${risk0}" min="10" step="10"></label>` +
      `<div id="ts-rows" class="calc-rows">${calcRows(risk0)}</div>` +
      `<div class="calc-note">MGC (ทองไมโคร) $10/จุด · GC (ทองเต็ม) $100/จุด · ปัดลง — ใส่ลิมิตขาดทุนต่อไม้ของบัญชี Topstep คุณ</div></div>`
    : '';

  let when = '';
  try { when = new Date(p.updated_at).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' }); } catch (e) {}
  const fresh = planFreshness(p);
  const staleTxt = fresh.stale ? ` · <span class="plan-stale">⚠ ค้าง ${fresh.hrs} ชม. (push อาจพลาด)</span>` : '';

  // day-over-day OI structure shifts (per the book's OI-change reading)
  const oic = p.oi_change;
  let oicHtml = '';
  if (oic && oic.contract_changed) {
    oicHtml = `<div class="plan-oic"><div class="plan-eh">📊 OI เปลี่ยนจากวันก่อน</div><div class="oic-row"><i>เปลี่ยนสัญญาใหม่ (rollover) — เทียบวันต่อวันไม่ได้</i></div></div>`;
  } else if (oic && oic.top && oic.top.length) {
    oicHtml = `<div class="plan-oic"><div class="plan-eh">📊 OI เปลี่ยนจากวันก่อน (เทียบ ${esc(oic.vs_date)})</div>` +
      oic.top.map((c) =>
        `<div class="oic-row"><b>${c.strike}</b> <span class="oic-c">C ${c.dcall >= 0 ? '+' : ''}${fmt.int(c.dcall)}</span> · <span class="oic-p">P ${c.dput >= 0 ? '+' : ''}${fmt.int(c.dput)}</span> <i>${esc(c.read)}</i></div>`
      ).join('') + `</div>`;
  }

  el.innerHTML =
    `<div class="plan-head">
       <span class="plan-title">📋 แผนวันนี้ <span class="plan-bias ${biasCls}">${biasTxt}</span></span>
       <span class="plan-time"><span class="pdot ${fresh.stale ? 'stale' : 'ok'}"></span>รอบ ${esc(p.session || '')} · ${when}${staleTxt}</span>
     </div>` +
    (p.spot_cfd != null ? `<div class="plan-cfd">💱 CFD/XAUUSD ≈ <b>${fmt.px(p.spot_cfd)}</b> · futures ${fmt.px(p.future)} · basis −${fmt.px(p.basis)}${p.basis_live ? '' : ' <i>(ประมาณ)</i>'} · <b class="plan-unit">หน่วย: ${unitTag}</b></div>` : '') +
    (p.headline ? `<div class="plan-headline">${esc(p.headline)}</div>` : '') +
    lvls(p.resistance, 'res', 'แนวต้าน') +
    lvls(p.support, 'sup', 'แนวรับ') +
    entries +
    calc +
    oicHtml +
    (p.scenarios && p.scenarios.length ? `<ul class="plan-scen">${p.scenarios.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>` : '') +
    (p.risk ? `<div class="plan-risk">⚠️ ${esc(p.risk)}</div>` : '') +
    `<div class="plan-src">ที่มา: ${esc(p.source || 'The Invisible Money + OI/Vol')} · AI สร้างอัตโนมัติ ไม่ใช่คำแนะนำการลงทุน</div>`;

  const ri = $('ts-risk');
  if (ri) ri.addEventListener('input', () => {
    const r = Math.max(0, +ri.value || 0);
    localStorage.setItem('topstepRisk', r);
    const rows = $('ts-rows');
    if (rows) rows.innerHTML = calcRows(r);
  });
}

// ── track record: auto-evaluated plan outcomes (approx via PAXG H1) ──
async function loadTrack() {
  const el = $('track');
  if (!el) return;
  try {
    const r = await fetch('data/track_record.json?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) { el.innerHTML = ''; el.style.display = 'none'; return; }
    const t = await r.json();
    const s = t.stats || {};
    el.style.display = '';
    el.innerHTML =
      `<div class="track-head">📈 ผลแผนย้อนหลัง <span class="track-sub">ประเมินอัตโนมัติจากราคา PAXG H1 ≈ XAUUSD · TP/SL = เป้าแรกของแต่ละ setup</span></div>` +
      `<div class="track-stats">` +
        `<span class="ts-item tp">✓ TP ${s.tp || 0}</span>` +
        `<span class="ts-item sl">✗ SL ${s.sl || 0}</span>` +
        `<span class="ts-item">ไม่ถึงจุดเข้า ${s.no_entry || 0}</span>` +
        `<span class="ts-item">รอผล ${s.open || 0}</span>` +
        (t.win_rate != null ? `<span class="ts-item wr">winrate ${t.win_rate}%</span>` : '') +
        `<span class="ts-item mut">จาก ${t.n_plans || 0} แผน</span>` +
      `</div>`;
  } catch (e) { el.innerHTML = ''; el.style.display = 'none'; }
}

// ── $50 Grid: round Block-Trade levels (book Ch6) in their own clear section ──
function renderGrid(p) {
  const el = $('grid');
  if (!el) return;
  if (!p || !Array.isArray(p.grid) || !p.grid.length) { el.innerHTML = ''; el.style.display = 'none'; return; }
  const fut = p.future;
  const rows = p.grid.slice().sort((a, b) => b.price - a.price);   // high → low
  let inner = '', marked = false;
  rows.forEach((g) => {
    if (!marked && g.price <= fut) {
      inner += `<div class="g-now">— ราคาปัจจุบัน ≈ ${fut} (CFD ${(fut - p.basis).toFixed(1)}) —</div>`;
      marked = true;
    }
    const tags = (g.oi ? '<span class="g-oi">★ กำแพง OI</span>' : '') + (g.r100 ? '<span class="g-100">$100</span>' : '');
    inner += `<div class="g-row g-${g.price > fut ? 'res' : 'sup'}">` +
      `<span class="g-px">${g.price}</span><span class="g-cfd">CFD ${g.cfd}</span><span class="g-tags">${tags}</span></div>`;
  });
  if (!marked) inner += `<div class="g-now">— ราคาปัจจุบัน ≈ ${fut} —</div>`;
  el.style.display = '';
  el.innerHTML =
    `<div class="grid-head">🎯 $50 Grid <span class="grid-sub">ด่าน Block Trade · เลขกลม $50/$100 = แนวรับต้านธรรมชาติ (★ = ตรงกำแพง OI ยิ่งแข็ง) · CFD = −basis ${p.basis}</span></div>` +
    `<div class="grid-rows">${inner}</div>`;
}

// ── COT (CFTC weekly positioning): smart money + fade retail (book Ch3) ──
function renderCot(p) {
  const el = $('cot');
  if (!el) return;
  const c = p && p.cot;
  if (!c) { el.innerHTML = ''; el.style.display = 'none'; return; }
  const fmt = (n) => (n >= 0 ? '+' : '') + n.toLocaleString();
  const arrow = (chg) => chg > 0 ? `<span class="c-up">▲ ${fmt(chg)}</span>` : chg < 0 ? `<span class="c-dn">▼ ${fmt(chg)}</span>` : '—';
  const lean = { down: 'long → สวน = น้ำหนักลง', up: 'short → สวน = น้ำหนักขึ้น', flat: 'กลางๆ' }[c.retail_lean];
  const rows = [
    ['เงินฉลาด · Commercials', c.comm, 'ผู้ผลิต/hedge · ดูตอนสุดขั้ว'],
    ['กองทุน · Large Specs', c.spec, 'ตามเทรนด์'],
    ['รายย่อย · Small Specs', c.retail, lean],
  ];
  el.style.display = '';
  el.innerHTML =
    `<div class="cot-head">🏛️ COT · Commitment of Traders <span class="cot-sub">CFTC รายสัปดาห์ · ${c.date} · รายย่อยมักผิด → สวน</span></div>` +
    `<div class="cot-rows">` +
    rows.map(([label, g, note]) =>
      `<div class="cot-row"><span class="cot-label">${label}</span>` +
      `<span class="cot-net ${g.net >= 0 ? 'c-long' : 'c-short'}">${fmt(g.net)}</span>` +
      `<span class="cot-chg">${arrow(g.chg)}</span>` +
      `<span class="cot-note">${note}</span></div>`
    ).join('') +
    `</div>`;
}

async function loadPlan() {
  try {
    const res = await fetch('plan.json?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error('no plan');
    const p = await res.json();
    renderPlan(p);
    renderGrid(p);
    renderCot(p);
    // adopt the plan's live basis for the bell-chart CFD mode
    if (typeof p.basis === 'number' && p.basis > -5 && p.basis < 80) {
      const changed = Math.abs(p.basis - state.basis) > 0.01;
      state.basis = p.basis;
      if (changed && state.priceMode === 'cfd') rerenderBell();
    }
  } catch (e) {
    renderPlan(null);
    renderGrid(null);
    renderCot(null);
  }
}

function rerenderBell() {
  const d = state.view === 'intraday' ? state.data.intraday : state.data.oi;
  if (d) renderBell(d);
}

function setPriceMode(mode) {
  state.priceMode = mode;
  localStorage.setItem('priceMode', mode);
  $('px-fut').classList.toggle('active', mode === 'fut');
  $('px-cfd').classList.toggle('active', mode === 'cfd');
  rerenderBell();
  if (state.plan) renderPlan(state.plan);    // plan levels/entries follow the same unit
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
    const [oiR, inR] = await Promise.all([
      fetchText(DATA_SOURCE.oi, DATA_FALLBACK.oi),
      fetchText(DATA_SOURCE.intraday, DATA_FALLBACK.intraday),
    ]);
    state.data.oi = parseVol2Vol(oiR.text);
    state.data.intraday = parseVol2Vol(inR.text);
    state.dataFallback = oiR.fb || inR.fb;
    render();
    const now = new Date().toLocaleTimeString('th-TH');
    if (state.dataFallback) {
      setStatus('⚠ ใช้ข้อมูลสำรอง (pageth ล่ม) · ' + now, 'err');
    } else {
      setStatus('อัปเดตล่าสุด ' + now, 'live');
    }
    $('data-stamp').textContent = 'sync ' + now;
  } catch (e) {
    setStatus('ดึงข้อมูลไม่สำเร็จ (ทั้ง pageth + สำรอง): ' + e.message, 'err');
  }
  // source-data freshness: re-render relative time every cycle; re-fetch commit time every 3 min
  if (state.dataTimeIso) renderDataTime(state.dataTimeIso);
  if (Date.now() - state.lastDataTimeFetch > 180000) {
    state.lastDataTimeFetch = Date.now();
    fetchDataTime();
  }
  loadPlan();
  loadTrack();
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
    const cfdVal = (best.strike - state.basis).toFixed(1);
    const mainPx = state.priceMode === 'cfd' ? cfdVal : best.strike;
    const altPx  = state.priceMode === 'cfd' ? `fut ${best.strike}` : `cfd ${cfdVal}`;
    tip.innerHTML =
      `<b>${mainPx}</b> <span class="t-mut">${sdTxt} · ${altPx}</span><br>` +
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
  $('px-fut').addEventListener('click', () => setPriceMode('fut'));
  $('px-cfd').addEventListener('click', () => setPriceMode('cfd'));
  if (state.priceMode === 'cfd') { $('px-fut').classList.remove('active'); $('px-cfd').classList.add('active'); }

  // auto-refresh ON unless the user turned it off before
  const autoOn = (localStorage.getItem('auto') || 'on') === 'on';
  $('chk-auto').checked = autoOn;
  setAuto(autoOn);

  // always pull fresh data when the tab regains focus (open it daily → latest)
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });

  load();
}

document.addEventListener('DOMContentLoaded', init);
