// ==UserScript==
// @name         Barchart → GoldOI Bridge
// @namespace    goldoi.bridge
// @version      1.0.0
// @description  ทุก 10 นาที ดึง OI/Volume/IV ของ weekly gold options + ราคา futures จาก API ของ Barchart แล้วส่งให้ barchart_bridge.py ในเครื่อง (127.0.0.1:8765) เพื่อสร้างแผน Gold OI อัตโนมัติ — เปิดแท็บ barchart.com ค้างไว้แท็บเดียวพอ
// @author       GoldOI
// @match        https://www.barchart.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// @noframes
// ==/UserScript==

(function () {
  'use strict';
  const BRIDGE = 'http://127.0.0.1:8765';
  const EVERY_MS = 10 * 60 * 1000;
  const FIELDS = 'optionType%2Cvolume%2CopenInterest%2CstrikePrice%2CoptImpliedVolatility';

  // ── tiny status badge (bottom-right) so she can see it working ──
  const badge = document.createElement('div');
  badge.style.cssText = 'position:fixed;right:10px;bottom:10px;z-index:99999;background:#1a1714;color:#f3ede0;' +
    'font:12px/1.4 ui-monospace,monospace;padding:6px 10px;border-radius:8px;opacity:.92;max-width:360px;' +
    'box-shadow:0 2px 8px rgba(0,0,0,.35);pointer-events:none';
  badge.textContent = 'GoldOI bridge: starting…';
  document.body.appendChild(badge);
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
        rows[k][r.optionType === 'Call' ? 'c' : 'p'] = [r.volume || 0, r.openInterest || 0, r.optImpliedVolatility || 0];
      }
    }
    return { n: Object.keys(rows).length, rows };
  }

  async function fetchFutures(symbols) {
    const j = await api('/proxies/core-api/v1/quotes/get?symbols=' + symbols.join('%2C') +
      '&fields=symbol%2ClastPrice%2CpriceChange%2CtradeTime&raw=1');
    const out = {};
    for (const o of (j.data || [])) {
      const r = o.raw || {};
      out[r.symbol] = { last: r.lastPrice, chg: r.priceChange, t: r.tradeTime };
    }
    return out;
  }

  let busy = false;
  async function cycle() {
    if (busy) return;
    busy = true;
    try {
      show('กำลังดึงข้อมูล…');
      const wanted = await gm('GET', BRIDGE + '/wanted');
      const series = {};
      for (const code of (wanted.symbols || [])) {
        try { series[code] = await fetchSeries(code); } catch (e) { series[code] = { n: 0, rows: {}, err: String(e) }; }
      }
      const futures = await fetchFutures(wanted.futures || ['GCV26', 'GCZ26']);
      const res = await gm('POST', BRIDGE + '/ingest', JSON.stringify({ at: Date.now(), page: location.pathname, series, futures }));
      const s = res.status || {};
      if (res.ok) {
        show(`${s.series} · fut ${s.future} · OI P/C ${s.put_oi}/${s.call_oi} · ${new Date().toLocaleTimeString('th-TH')} ✓`, true);
      } else {
        show('bridge ปฏิเสธ: ' + (res.msg || '?'), false);
      }
    } catch (e) {
      show(String(e.message || e), false);
    } finally {
      busy = false;
    }
  }

  cycle();
  setInterval(cycle, EVERY_MS);
})();
