// ==UserScript==
// @name         Barchart → GoldOI Bridge
// @namespace    goldoi.bridge
// @version      1.3.0
// @updateURL    https://raw.githubusercontent.com/perpetualpp-rgb/gold-oi-dashboard/main/tools/Barchart-GoldOI-Bridge.user.js
// @downloadURL  https://raw.githubusercontent.com/perpetualpp-rgb/gold-oi-dashboard/main/tools/Barchart-GoldOI-Bridge.user.js
// @description  ส่งข้อมูล OI/Volume/ราคา (Barchart), Vol2Vol (QuikStrike) และ IV ราย strike (Pricing Sheet) ให้ barchart_bridge.py ในเครื่อง (127.0.0.1:8765) ทุก 10 นาที — เปิดแท็บ barchart.com และแท็บ QuikStrike Vol2Vol ค้างไว้
// @author       GoldOI
// @match        https://www.barchart.com/*
// @match        https://cmegroup-sso.quikstrike.net/*
// @match        https://users.quikstrike.net/*
// @match        https://www.cmegroup.com/tools-information/quikstrike/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';
  const BRIDGE = 'http://127.0.0.1:8765';
  const EVERY_MS = 10 * 60 * 1000;
  const host = location.hostname;
  const isBarchart = host.endsWith('barchart.com');

  // ── status badge (bottom-right) ──
  const badge = document.createElement('div');
  badge.style.cssText = 'position:fixed;right:10px;bottom:10px;z-index:99999;background:#1a1714;color:#f3ede0;' +
    'font:12px/1.4 ui-monospace,monospace;padding:6px 10px;border-radius:8px;opacity:.92;max-width:420px;' +
    'box-shadow:0 2px 8px rgba(0,0,0,.35);pointer-events:none;white-space:pre-wrap';
  badge.textContent = 'GoldOI bridge: starting…';
  (document.body || document.documentElement).appendChild(badge);
  const show = (t, ok) => { badge.textContent = 'GoldOI bridge · ' + t; badge.style.background = ok === false ? '#7a1f1f' : '#1a1714'; };

  const gm = (method, url, data) => new Promise((resolve, reject) => {
    GM_xmlhttpRequest({
      method, url, data,
      headers: { 'Content-Type': 'application/json' },
      timeout: 20000,
      onload: (r) => (r.status < 300) ? resolve(JSON.parse(r.responseText || '{}')) : reject(new Error('bridge HTTP ' + r.status)),
      onerror: () => reject(new Error('bridge ไม่ตอบ (barchart_bridge.py รันอยู่ไหม?)')),
      ontimeout: () => reject(new Error('bridge timeout')),
    });
  });

  // ═══════════════════════════ Barchart: OI / volume / futures ═══════════════════════════
  // bid/ask are one delayed snapshot for every strike → the bridge computes a consistent IV smile from mids
  const FIELDS = 'optionType%2Cvolume%2CopenInterest%2CstrikePrice%2CoptImpliedVolatility%2CbidPrice%2CaskPrice';
  async function api(path) {
    const r = await fetch(path, { headers: { accept: 'application/json' }, credentials: 'include' });
    if (!r.ok) throw new Error('barchart HTTP ' + r.status);
    return r.json();
  }
  async function fetchSeries(code) {
    const j = await api('/proxies/core-api/v1/quotes/get?symbol=' + code + '&list=futures.options&fields=' + FIELDS +
      '&groupBy=strikePrice&orderBy=strikePrice&orderDir=asc&raw=1');
    const rows = {};
    for (const arr of Object.values(j.data || {})) {
      for (const o of arr) {
        const r = o.raw || {};
        if (r.strikePrice == null) continue;
        const k = String(r.strikePrice);
        rows[k] = rows[k] || {};
        rows[k][r.optionType === 'Call' ? 'c' : 'p'] = [r.volume || 0, r.openInterest || 0, r.optImpliedVolatility || 0, r.bidPrice || 0, r.askPrice || 0];
      }
    }
    return { n: Object.keys(rows).length, rows };
  }
  async function fetchFutures(symbols) {
    const j = await api('/proxies/core-api/v1/quotes/get?symbols=' + symbols.join('%2C') +
      '&fields=symbol%2ClastPrice%2CpriceChange%2CtradeTime&raw=1');
    const out = {};
    for (const o of (j.data || [])) { const r = o.raw || {}; out[r.symbol] = { last: r.lastPrice, chg: r.priceChange, t: r.tradeTime }; }
    return out;
  }
  async function cycleBarchart() {
    show('กำลังดึงข้อมูล Barchart…');
    const wanted = await gm('GET', BRIDGE + '/wanted');
    const series = {};
    for (const code of (wanted.symbols || [])) {
      try { series[code] = await fetchSeries(code); } catch (e) { series[code] = { n: 0, rows: {}, err: String(e) }; }
    }
    const futures = await fetchFutures(wanted.futures || ['GCV26', 'GCZ26']);
    const res = await gm('POST', BRIDGE + '/ingest', JSON.stringify({ at: Date.now(), page: location.pathname, series, futures }));
    const s = res.status || {};
    if (res.ok) show(`${s.series} · fut ${s.future} · OI P/C ${s.put_oi}/${s.call_oi} · IV ${s.iv_source} · ${new Date().toLocaleTimeString('th-TH')} ✓`, true);
    else show('bridge ปฏิเสธ: ' + (res.msg || '?'), false);
  }

  // ═══════════════════ QuikStrike: per-strike IV from the Pricing Sheet ═══════════════════
  // Parser rules (her spec): detect columns by HEADER TEXT (not fixed indexes); "45.07%" → 45.07;
  // empty / "—" / "N/A" → missing (never 0); synthetic ATM rows are NOT listed strikes (kept only
  // as the ATM vol); the series code is read from the page (selected expiration), never guessed.
  const CODE_RE = /\b(OG\d[FGHJKMNQUVXZ]\d|G\d[MTWRH][FGHJKMNQUVXZ]\d)\b/;
  const txt = (el) => (el ? (el.textContent || '').replace(/ /g, ' ').trim() : '');
  const num = (s) => {
    s = (s || '').replace(/,/g, '').replace(/%/g, '').replace(/[sS]$/, '').trim();
    if (!s || s === '—' || s === '-' || /^n\/?a$/i.test(s)) return null;
    return /^[+-]?(\d+(\.\d*)?|\.\d+)$/.test(s) ? Number(s) : null;
  };
  function findSheetTable() {
    const direct = document.querySelector('#pricing-sheet');
    if (direct) return direct.tagName === 'TABLE' ? direct : (direct.querySelector('table') || direct);
    for (const t of document.querySelectorAll('table')) {
      const h = txt(t.querySelector('thead') || t.querySelector('tr')).toLowerCase();
      if (h.includes('strike') && (h.includes('vol') || h.includes('iv'))) return t;
    }
    return null;
  }
  function selectedCode() {
    for (const sel of document.querySelectorAll('select')) {
      const o = sel.options && sel.options[sel.selectedIndex];
      const m = txt(o).match(CODE_RE) || (o && String(o.value).match(CODE_RE));
      if (m) return m[1];
    }
    const m = txt(document.body).match(CODE_RE);
    return m ? m[1] : null;
  }
  function parseSheet(table) {
    const headRow = table.querySelector('thead tr') || table.querySelector('tr');
    const heads = [...(headRow ? headRow.children : [])].map((c) => txt(c).toLowerCase());
    // the sheet lists Call columns (left) · Strike · Put columns (right); take the FIRST vol column
    const iStrike = heads.findIndex((h) => h.includes('strike'));
    let iVol = heads.findIndex((h) => /\bvol|iv\b|implied/.test(h));
    if (iStrike < 0 || iVol < 0) return { rows: [], atm: null, heads, reason: 'no strike/vol header' };
    const rows = [], seen = new Set();
    let atm = null;
    for (const tr of table.querySelectorAll('tbody tr, tr')) {
      const tds = tr.querySelectorAll('td');
      if (tds.length <= Math.max(iStrike, iVol)) continue;
      const strike = num(txt(tds[iStrike])), vol = num(txt(tds[iVol]));
      const cls = (tr.className || '').toLowerCase();
      if (cls.includes('atm')) { if (vol != null && atm == null) atm = vol; continue; }   // synthetic ATM row
      if (strike == null || vol == null || seen.has(strike)) continue;
      seen.add(strike);
      rows.push([strike, vol]);
    }
    rows.sort((a, b) => a[0] - b[0]);
    return { rows, atm, heads };
  }
  // ── QuikStrike Vol2Vol page (trial/paid): read the chart's own numbers (Intraday volume per strike,
  //    Vol + Vol Settle curves, ranges) straight from the page, plus the header line ──
  const W = (typeof unsafeWindow !== 'undefined') ? unsafeWindow : window;
  function vol2volHeader() {
    const t = txt(document.body);
    const h = t.match(/Gold\s*\(OG\|GC\)\s*(\S+)\s*\(([\d.]+)\s*DTE\)\s*vs\s*([\d,.]+)\s*\(([-+\d.]+)\)\s*-\s*(Intraday Volume|Open Interest Change|Open Interest|EOD Volume)/);
    const s = t.match(/Put:\s*([\d,]+)\s*Call:\s*([\d,]+)\s*Vol:\s*([\d.]+)\s*Vol Chg:\s*([-+\d.]+)\s*Future Chg:\s*([-+\d.]+)/);
    const r = t.match(/Ranges:\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
    return {
      code: h ? h[1] : null, dte: h ? +h[2] : null, future: h ? +h[3].replace(/,/g, '') : null, chg: h ? +h[4] : null, view: h ? h[5] : null,
      put: s ? +s[1].replace(/,/g, '') : null, call: s ? +s[2].replace(/,/g, '') : null, vol: s ? +s[3] : null, volChg: s ? +s[4] : null, futChg: s ? +s[5] : null,
      ranges: r ? r.slice(1, 7).map(Number) : null,
    };
  }
  function vol2volCharts() {
    const H = W.Highcharts;
    if (!H || !H.charts) return null;
    const out = [];
    for (const ch of H.charts) {
      if (!ch || !ch.series) continue;
      out.push({
        title: ch.title && ch.title.textStr, renderTo: ch.renderTo && ch.renderTo.id,
        xcats: ch.xAxis && ch.xAxis[0] && ch.xAxis[0].categories ? ch.xAxis[0].categories.slice(0, 400) : null,
        yaxes: (ch.yAxis || []).map((a) => (a.axisTitle && a.axisTitle.textStr) || (a.options && a.options.title && a.options.title.text) || ''),
        series: ch.series.map((s) => ({
          name: s.name, type: s.type, yAxis: s.yAxis && s.yAxis.options && s.yAxis.options.index, visible: s.visible,
          n: (s.data || []).length,
          points: (s.data || []).slice(0, 400).map((p) => [p.category != null ? p.category : p.x, p.y]),
        })),
      });
    }
    return out;
  }
  async function cycleVol2Vol() {
    const hdr = vol2volHeader();
    const charts = vol2volCharts();
    if (!charts || !charts.length) {
      const keys = Object.keys(W).filter((k) => /chart|highchart|kendo|dojo|plot|echart|d3|amchart|canvasjs/i.test(k)).slice(0, 40);
      await gm('POST', BRIDGE + '/qs', JSON.stringify({ kind: 'vol2vol_debug', page: location.href, header: hdr, libs: keys,
        svg: document.querySelectorAll('svg').length, canvas: document.querySelectorAll('canvas').length, tables: document.querySelectorAll('table').length }));
      show(`QuikStrike: ส่งโครงสร้างหน้าให้ bridge แล้ว (ยังไม่พบ chart lib) · ${hdr.code || '?'} ${hdr.view || ''}`, false);
      return true;
    }
    const res = await gm('POST', BRIDGE + '/qs', JSON.stringify({ kind: 'vol2vol', page: location.href, at: Date.now(), header: hdr, charts }));
    show(`QuikStrike Vol2Vol ✓ ${hdr.code || '?'} ${hdr.view || ''} · fut ${hdr.future} · Vol ${hdr.vol} · charts ${charts.length} · ${new Date().toLocaleTimeString('th-TH')}${res.msg ? ' · ' + res.msg : ''}`, true);
    return true;
  }

  async function cycleQuikStrike() {
    if (/QuikStrikeView|pid=40/i.test(location.href) && !findSheetTable()) { await cycleVol2Vol(); return; }
    const table = findSheetTable();
    if (!table) {
      show('QuikStrike: ยังไม่พบตาราง Pricing Sheet บนหน้านี้ — เปิดหน้า Pricing Sheet ค้างไว้', false);
      await gm('POST', BRIDGE + '/iv', JSON.stringify({ debug: { page: location.href, tables: document.querySelectorAll('table').length, title: document.title } }));
      return;
    }
    const p = parseSheet(table);
    const code = selectedCode();
    if (p.rows.length < 5 || !code) {
      show(`QuikStrike: อ่านตารางไม่ได้ (rows ${p.rows.length}, code ${code || '?'})`, false);
      await gm('POST', BRIDGE + '/iv', JSON.stringify({ debug: { page: location.href, heads: p.heads, reason: p.reason, code, sample: txt(table).slice(0, 400) } }));
      return;
    }
    const header = txt(table.parentElement).slice(0, 300);
    const res = await gm('POST', BRIDGE + '/iv', JSON.stringify({ code, rows: p.rows, atm: p.atm, kind: 'pricing_sheet', page: location.href, header }));
    if (res.ok) show(`QuikStrike IV ✓ ${code} · ${p.rows.length} strikes · ATM ${p.atm ?? '—'} · expiry ${res.expiry_date} · ${new Date().toLocaleTimeString('th-TH')}`, true);
    else show('bridge ปฏิเสธ IV: ' + (res.msg || '?'), false);
  }

  let busy = false;
  async function cycle() {
    if (busy) return;
    busy = true;
    try { if (isBarchart) await cycleBarchart(); else await cycleQuikStrike(); }
    catch (e) { show(String(e.message || e), false); }
    finally { busy = false; }
  }
  setTimeout(cycle, isBarchart ? 1500 : 4000);      // QuikStrike renders its sheet after load
  setInterval(cycle, EVERY_MS);
})();
