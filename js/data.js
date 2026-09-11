/* ============================================================
   data.js — fetch + parse the live option data files
   Source (2026-09): the Barchart → GoldOI bridge publishes CME weekly gold option
   OI / intraday volume (per strike) into data/live/ every ~30 min while her Barchart
   tab is open. Same text format the old pageth feed used:

     line 0: Gold (OG|GC) IG2U26 (1.05 DTE) vs 4362.6 (-64.1) - Open Interest
     line 1: Put: 5,421  Call: 5,054  Vol: 31.31  Vol Chg: 0.00  Future Chg: -64.1
     line 2: Strike,Call,Put,Vol Settle
     line 3+: 4350,2,561,0.359          (Vol Settle = per-strike IV as a FRACTION)
   ============================================================ */

const DATA_SOURCE = {
  oi:       'data/live/OIData.txt',
  intraday: 'data/live/IntradayData.txt',
  status:   'data/live/status.json',
};
// last-resort copies (may be days old) — only if data/live is missing
const DATA_FALLBACK = {
  oi:       'data/mirror/OIData.txt',
  intraday: 'data/mirror/IntradayData.txt',
};

async function fetchOne(url) {
  const res = await fetch(url + (url.includes('?') ? '&' : '?') + 't=' + Date.now(), { cache: 'no-store' });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const txt = await res.text();
  if (!txt.trim()) throw new Error('empty');
  return txt;
}

// fetch raw text; try the live file first, fall back to the old mirror. Returns { text, fb }.
async function fetchText(primary, fallback) {
  try { return { text: await fetchOne(primary), fb: false }; }
  catch (e) {
    if (fallback) return { text: await fetchOne(fallback), fb: true };
    throw e;
  }
}

async function fetchStatus() {
  try {
    const res = await fetch(DATA_SOURCE.status + '?t=' + Date.now(), { cache: 'no-store' });
    return res.ok ? await res.json() : null;
  } catch (e) { return null; }
}

function parseVol2Vol(text) {
  const lines = text.replace(/\r/g, '').split('\n');
  const head = lines[0] || '';
  const sum  = lines[1] || '';

  const grab = (re, src, dflt = 0) => {
    const m = src.match(re);
    return m ? parseFloat(m[1].replace(/,/g, '')) : dflt;
  };

  const fxMatch = head.match(/vs\s+([\d.]+)\s+\(([+-]?[\d.]+)\)/);

  const meta = {
    contract:  (head.match(/Gold\s*\(OG\|GC\)\s*(\S+)/) || [, ''])[1],
    dte:       grab(/\(([\d.]+)\s*DTE\)/, head),
    future:    fxMatch ? parseFloat(fxMatch[1]) : 0,
    futureChg: fxMatch ? parseFloat(fxMatch[2]) : 0,
    kind:      (head.split(' - ')[1] || '').trim(),
    totalPut:  grab(/Put:\s*([\d,]+)/, sum),
    totalCall: grab(/Call:\s*([\d,]+)/, sum),
    iv:        grab(/Vol:\s*([\d.]+)/, sum),
    ivChg:     grab(/Vol Chg:\s*([+-]?[\d.]+)/, sum),
  };

  const rows = [];
  for (let i = 3; i < lines.length; i++) {
    const p = lines[i].split(',');
    if (p.length < 4) continue;
    const strike = parseFloat(p[0]);
    if (!strike) continue;
    rows.push({
      strike,
      call: parseInt(p[1], 10) || 0,
      put:  parseInt(p[2], 10) || 0,
      iv:   parseFloat(p[3]) || 0,   // per-strike IV (decimal); 0 = not available
    });
  }
  meta.rows = rows;
  return meta;
}
