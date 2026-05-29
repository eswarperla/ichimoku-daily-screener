"""
Build the Ichimoku scanner dashboard HTML from snapshots/latest.json.

Outputs a self-contained HTML file with the snapshot data embedded as a JS
constant. Loads Grid.js v5 from the approved CDN for a sortable/filterable
table. Designed to render inside the Cowork artifact sandbox.

The dashboard classifies each passing stock as:
  BREAKOUT   — fresh signal from a previously non-trending state (best fresh entry)
  RESUMPTION — trend continuation after a brief 1-3 day pullback
  MIXED      — choppy/transitional, recent history is in the gray zone
  MATURE     — already in a sustained run (e.g. streak >= 4 days; later entry)
"""

from __future__ import annotations
import json
import os
import sys
from html import escape

import config

# Paths come from config — override via argv if you really need to
SNAP_PATH = config.LATEST_JSON
OUT_PATH  = config.DASHBOARD_HTML

HTML_TEMPLATE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Ichimoku Daily Scanner</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    color: #1a1a1a;
    background: #ffffff;
    font-size: 14px;
    line-height: 1.45;
  }
  .container { max-width: 1280px; margin: 0 auto; padding: 20px 24px 40px; }
  h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
  .subtitle { color: #6b6b6b; margin: 0 0 18px; font-size: 13px; }
  .stat-row {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .stat-card {
    flex: 1 1 140px;
    background: #f7f8fa;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 10px 12px;
  }
  .stat-card .label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #6b6b6b;
    margin-bottom: 2px;
  }
  .stat-card .value {
    font-size: 22px;
    font-weight: 600;
    color: #1a1a1a;
  }
  .stat-card .sub {
    font-size: 12px;
    color: #6b6b6b;
    margin-top: 2px;
  }
  .type-stats {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .type-chip {
    border: 1px solid;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    cursor: pointer;
    user-select: none;
    transition: filter 0.1s;
  }
  .type-chip:hover { filter: brightness(0.97); }
  .type-chip.active { box-shadow: 0 0 0 2px #1a1a1a inset; }
  .type-chip .chip-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; display: block; margin-bottom: 2px; }
  .type-chip .chip-value { font-size: 18px; font-weight: 600; }
  .type-breakout   { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }
  .type-resumption { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
  .type-mixed      { background: #fffbeb; color: #92400e; border-color: #fde68a; }
  .type-mature     { background: #f3f4f6; color: #4b5563; border-color: #d1d5db; }
  .type-all        { background: #fafafa; color: #1a1a1a; border-color: #d1d5db; }
  .controls {
    display: flex;
    gap: 14px;
    margin-bottom: 12px;
    align-items: center;
    flex-wrap: wrap;
    font-size: 13px;
  }
  .controls label {
    color: #4a4a4a;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .controls input[type="number"], .controls input[type="text"] {
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 13px;
    width: 90px;
  }
  .controls input[type="text"] { width: 200px; }
  .controls button {
    border: 1px solid #d1d5db;
    background: #fff;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    cursor: pointer;
  }
  .controls button:hover { background: #f7f8fa; }
  .filter-list {
    background: #f7f8fa;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 18px 0 12px;
    font-size: 12.5px;
    color: #4a4a4a;
  }
  .filter-list h3 {
    margin: 0 0 6px;
    font-size: 13px;
    font-weight: 600;
    color: #1a1a1a;
  }
  .filter-list ol { margin: 4px 0 8px 18px; padding: 0; }
  .filter-list li { margin: 2px 0; }
  .filter-list .key-defs { font-size: 12px; margin-top: 8px; }
  .filter-list .key-defs span { display: inline-block; margin-right: 14px; }
  .badge {
    display: inline-block;
    border: 1px solid;
    border-radius: 999px;
    padding: 1px 8px;
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    line-height: 1.6;
  }
  .badge-breakout   { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }
  .badge-resumption { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
  .badge-mixed      { background: #fffbeb; color: #92400e; border-color: #fde68a; }
  .badge-mature     { background: #f3f4f6; color: #4b5563; border-color: #d1d5db; }
  .pattern-pill {
    display: inline-block;
    border: 1px solid;
    border-radius: 6px;
    padding: 1px 7px;
    font-size: 11.5px;
    font-weight: 500;
    line-height: 1.5;
  }
  .pattern-bullish { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }
  .pattern-bearish { background: #fef2f2; color: #b91c1c; border-color: #fecaca; }
  .pattern-neutral { background: #f3f4f6; color: #4b5563; border-color: #d1d5db; }
  .pattern-none    { color: #c4c4c4; }
  .vol-tick { color: #047857; font-weight: 700; margin-left: 3px; font-size: 11px; }
  .ticker-link {
    color: #1a1a1a;
    text-decoration: none;
    font-weight: 600;
    border-bottom: 1px dashed #c4c4c4;
    cursor: pointer;
  }
  .ticker-link:hover {
    color: #1d4ed8;
    border-bottom-color: #1d4ed8;
  }
  .streak-pill {
    display: inline-block;
    background: #f3f4f6;
    border-radius: 6px;
    padding: 1px 6px;
    font-size: 12px;
    font-weight: 600;
    color: #1a1a1a;
    min-width: 22px;
    text-align: center;
  }
  #grid-host .gridjs-wrapper { box-shadow: none; border-radius: 8px; }
  #grid-host .gridjs-th, #grid-host .gridjs-td { padding: 8px 10px; }
  #grid-host .gridjs-th { background: #f7f8fa; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.03em; }
  #grid-host .gridjs-td { font-size: 13px; }
  .pos { color: #047857; }
  .ticker-cell { font-weight: 600; }
  .empty-state {
    background: #f7f8fa;
    border: 1px dashed #d1d5db;
    border-radius: 8px;
    padding: 32px;
    text-align: center;
    color: #6b6b6b;
  }
  .footnote { font-size: 11.5px; color: #8a8a8a; margin-top: 18px; line-height: 1.55; }
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/gridjs@5.0.2/dist/theme/mermaid.min.css" integrity="sha384-jZvDSsmGB9oGGT/4l9bHXGoAv1OxvG/cFmSo0dZaSqmBgvQTKDBFAMftlXTmMbNW" crossorigin="anonymous">
</head>
<body>
<div class="container">

  <h1>Ichimoku Daily Scanner — US Mid &amp; Large Cap</h1>
  <p class="subtitle">__SUBTITLE__</p>

  <div class="stat-row">
    <div class="stat-card">
      <div class="label">As of (close)</div>
      <div class="value">__ASOF__</div>
      <div class="sub">Last completed US trading day</div>
    </div>
    <div class="stat-card">
      <div class="label">Stocks passing all filters</div>
      <div class="value">__PASSING__</div>
      <div class="sub">out of __SCANNED__ scanned</div>
    </div>
    <div class="stat-card">
      <div class="label">Generated</div>
      <div class="value" style="font-size:13px;">__GENERATED__</div>
      <div class="sub">Re-runs each trading day (07:00 IST)</div>
    </div>
  </div>

  <div class="type-stats" id="typeStats">
    <div class="type-chip type-all active" data-type="ALL">
      <span class="chip-label">All</span>
      <span class="chip-value">__PASSING__</span>
    </div>
    <div class="type-chip type-breakout" data-type="BREAKOUT" title="Streak ≤ 3 days, ≤ 4 of prior 17 days passed — fresh bullish signal from a non-trending state">
      <span class="chip-label">Breakout</span>
      <span class="chip-value">__N_BREAKOUT__</span>
    </div>
    <div class="type-chip type-resumption" data-type="RESUMPTION" title="Streak ≤ 3 days, ≥ 10 of prior 17 days passed — continuation after brief pullback in an existing trend">
      <span class="chip-label">Resumption</span>
      <span class="chip-value">__N_RESUMPTION__</span>
    </div>
    <div class="type-chip type-mixed" data-type="MIXED" title="Streak ≤ 3 days, 5-9 of prior 17 days passed — choppy/transitional, ambiguous setup">
      <span class="chip-label">Mixed</span>
      <span class="chip-value">__N_MIXED__</span>
    </div>
    <div class="type-chip type-mature" data-type="MATURE" title="Streak ≥ 4 days — already in a sustained run; later entry, lower upside">
      <span class="chip-label">Mature</span>
      <span class="chip-value">__N_MATURE__</span>
    </div>
  </div>

  <div class="controls">
    <label>Search: <input id="searchBox" type="text" placeholder="ticker or company name"></label>
    <label>Min streak: <input id="minStreak" type="number" min="1" value="1"></label>
    <label>Min $M vol: <input id="minVol" type="number" min="0" value="20"></label>
    <button id="resetBtn">Reset</button>
  </div>

  <div id="grid-host"></div>

  <div class="filter-list">
    <h3>Filter logic (all 8 must hold for the last closed daily bar):</h3>
    <ol>
      <li>Daily Ichimoku Conversion (Tenkan, 9) &gt; Daily Ichimoku Base (Kijun, 26)</li>
      <li>Daily Ichimoku Base &gt; Daily Ichimoku Cloud Top (max of visible Span A, Span B)</li>
      <li>Daily Base &gt; 1-day-ago Base (Kijun rising)</li>
      <li>Daily Conversion &gt; 1-day-ago Conversion (Tenkan rising)</li>
      <li>Daily Close &gt; Daily Conversion</li>
      <li>Daily Close &gt; 26-days-ago Close</li>
      <li><b>Future cloud is green</b> — today's leading Span A &gt; today's leading Span B (Kumo plotted 26 bars ahead is bullish)</li>
      <li><b>Liquidity</b> — 20-day average dollar volume ≥ $20M</li>
    </ol>
    <div class="key-defs">
      <span><b>Streak</b>: consecutive days passing all 8 filters (today included).</span>
      <span><b>Prior</b>: how many of the 17 days <i>before</i> the streak also passed — drives the setup-type label.</span>
      <span><b>Pattern</b>: most significant candlestick pattern on the last 1–3 bars. <b style="color:#047857">Green</b> = bullish confirmation, <b style="color:#b91c1c">red</b> = bearish warning, gray = neutral indecision. "✓ vol" means today's volume was &gt; 1.5× the 20-day average — patterns with volume confirmation are more reliable.</span>
      <span><b>Ticker</b>: click to open TradingView's chart for this symbol.</span>
    </div>
  </div>

  <p class="footnote">
    Universe: S&amp;P 500 ∪ NASDAQ-100 (~520 tickers, all US mid/large-cap, ≥ $2B market cap).
    Data source: Yahoo Finance daily OHLC via the official chart API.
    Setup type classification is descriptive, not predictive — breakouts have higher false-start rates, resumptions have higher hit rates, mature trends are already running.
    Built for trading research only — not investment advice.
  </p>
</div>

<script src="https://cdn.jsdelivr.net/npm/gridjs@5.0.2/dist/gridjs.umd.js" integrity="sha384-/XXDzxe4FsGiAe50i/u9pY/Vy/uX654MHB1xoc1BJNnH1WXHhqHga9g3q5tF4gj7" crossorigin="anonymous"></script>

<script>
  const SNAPSHOT = __SNAPSHOT_JSON__;

  const TYPE_RANK = { BREAKOUT: 0, RESUMPTION: 1, MIXED: 2, MATURE: 3 };

  // Map Yahoo exchange codes -> TradingView exchange prefixes (injected from config)
  const TV_EXCHANGE = __TV_EXCHANGE_MAP_JSON__;
  const TV_URL_TEMPLATE = __TV_URL_TEMPLATE_JSON__;
  function tvUrl(ticker, exch) {
    const ex = TV_EXCHANGE[(exch || "").toUpperCase()];
    const sym = ex ? `${ex}:${ticker}` : ticker;
    return TV_URL_TEMPLATE.replace("{sym}", encodeURIComponent(sym));
  }
  function tickerLink(ticker, exch) {
    return `<a class="ticker-link" href="${tvUrl(ticker, exch)}" target="_blank" rel="noopener noreferrer">${ticker}</a>`;
  }

  function typeBadge(t) {
    const cls = "badge badge-" + (t || "").toLowerCase();
    return `<span class="${cls}">${t || "—"}</span>`;
  }
  function streakPill(d) {
    return `<span class="streak-pill">${d}</span>`;
  }
  function priorCell(r) {
    if (r.priorWindow == null) return '<span style="color:#9ca3af">—</span>';
    return `${r.priorPasses}/${r.priorWindow}`;
  }
  // Sort weight for the Pattern column — bullish > neutral > none > bearish
  // (bearish goes last so the strongest confirming bullish patterns sit at top
  //  when sorted descending, and bearish warnings sit clearly at the bottom)
  const PATTERN_RANK = { BULLISH: 0, NEUTRAL: 1, NONE: 2, BEARISH: 3 };
  function patternCell(r) {
    if (!r.pattern) {
      return '<span class="pattern-pill pattern-none">—</span>';
    }
    const lean = (r.patternLean || "NEUTRAL").toLowerCase();
    const vol = r.volConfirmed ? '<span class="vol-tick" title="Volume-confirmed: today’s volume > 1.5x 20-day avg">✓ vol</span>' : '';
    return `<span class="pattern-pill pattern-${lean}">${r.pattern}</span>${vol}`;
  }

  const rows = (SNAPSHOT.results || []).map(r => ([
    r.setupType,
    r.ticker,                     // raw ticker (column 1)
    r.name || "",
    r.exchange || "",
    r.close,
    r.daysPassing,
    priorCell(r),
    r.avgDollarVolM,
    r.pctAboveConv,
    r.pct26d,
    r,                            // full result object for pattern column (column 10)
  ]));

  let activeType = "ALL";
  let grid = null;
  const host = document.getElementById('grid-host');

  function applyFilters() {
    const min = Number(document.getElementById('minStreak').value) || 1;
    const minV = Number(document.getElementById('minVol').value) || 0;
    const q = (document.getElementById('searchBox').value || '').trim().toLowerCase();
    const filtered = rows.filter(r => {
      if (activeType !== "ALL" && r[0] !== activeType) return false;
      if (r[5] < min) return false;
      if (r[7] < minV) return false;
      if (q && !String(r[1]).toLowerCase().includes(q)
            && !String(r[2]).toLowerCase().includes(q)) return false;
      return true;
    });
    render(filtered);
  }

  function render(data) {
    if (grid) grid.destroy();
    if (!data.length) {
      host.innerHTML = '<div class="empty-state">No stocks match your filters today.</div>';
      grid = null;
      return;
    }
    host.innerHTML = '';
    grid = new gridjs.Grid({
      columns: [
        { name: 'Setup',
          sort: { compare: (a, b) => (TYPE_RANK[a] ?? 9) - (TYPE_RANK[b] ?? 9) },
          formatter: (cell) => gridjs.html(typeBadge(cell)) },
        { name: 'Ticker',
          // sort by raw ticker string
          formatter: (cell, row) => {
              const exch = row.cells[3].data;
              return gridjs.html(tickerLink(cell, exch));
          } },
        { name: 'Company' },
        { name: 'Exch.' },
        { name: 'Close',  formatter: (cell) => `$${Number(cell).toFixed(2)}` },
        { name: 'Streak',
          sort: { compare: (a, b) => a - b },  // ascending = freshest first
          formatter: (cell) => gridjs.html(streakPill(cell)) },
        { name: 'Prior',
          sort: { compare: (a, b) => {
              const p = (s) => { const m = String(s).match(/^(\d+)/); return m ? +m[1] : -1; };
              return p(b) - p(a);
            }
          }
        },
        { name: '20d $M vol',
          sort: { compare: (a, b) => b - a },
          formatter: (cell) => `$${Number(cell).toLocaleString(undefined, {maximumFractionDigits:0})}M` },
        { name: '% > Conv',
          formatter: (cell) => gridjs.html(`<span class="pos">+${Number(cell).toFixed(2)}%</span>`) },
        { name: '% vs 26d',
          formatter: (cell) => gridjs.html(`<span class="pos">+${Number(cell).toFixed(2)}%</span>`) },
        { name: 'Yesterday’s pattern',
          sort: { compare: (a, b) => {
              const k = (x) => PATTERN_RANK[(x && x.patternLean) || (x && x.pattern ? 'NEUTRAL' : 'NONE')] ?? 9;
              return k(a) - k(b);
            }
          },
          formatter: (cell) => gridjs.html(patternCell(cell)) },
      ],
      data: data,
      sort: true,
      search: false,
      pagination: { limit: 100, summary: true },
      style: { table: { 'font-size': '13px' } },
    }).render(host);
  }

  function setActiveType(t) {
    activeType = t;
    document.querySelectorAll('.type-chip').forEach(el => {
      el.classList.toggle('active', el.dataset.type === t);
    });
    saveFilters();
    applyFilters();
  }

  document.getElementById('typeStats').addEventListener('click', (e) => {
    const chip = e.target.closest('.type-chip');
    if (chip) setActiveType(chip.dataset.type);
  });

  try {
    const saved = JSON.parse(localStorage.getItem('ichimoku-filters-v2') || '{}');
    if (saved.minStreak)    document.getElementById('minStreak').value = saved.minStreak;
    if (saved.minVol != null) document.getElementById('minVol').value  = saved.minVol;
    if (saved.search)       document.getElementById('searchBox').value = saved.search;
    if (saved.activeType)   activeType = saved.activeType;
    document.querySelectorAll('.type-chip').forEach(el => {
      el.classList.toggle('active', el.dataset.type === activeType);
    });
  } catch (_) {}

  function saveFilters() {
    try {
      localStorage.setItem('ichimoku-filters-v2', JSON.stringify({
        minStreak: document.getElementById('minStreak').value,
        minVol:    document.getElementById('minVol').value,
        search:    document.getElementById('searchBox').value,
        activeType,
      }));
    } catch (_) {}
  }

  document.getElementById('minStreak').addEventListener('input', () => { applyFilters(); saveFilters(); });
  document.getElementById('minVol').addEventListener('input',    () => { applyFilters(); saveFilters(); });
  document.getElementById('searchBox').addEventListener('input', () => { applyFilters(); saveFilters(); });
  document.getElementById('resetBtn').addEventListener('click', () => {
    document.getElementById('minStreak').value = 1;
    document.getElementById('minVol').value    = 20;
    document.getElementById('searchBox').value = '';
    setActiveType('ALL');
  });

  applyFilters();
</script>
</body>
</html>
"""


def build_dashboard(snap_path: str = SNAP_PATH, out_path: str = OUT_PATH) -> str:
    with open(snap_path, "r", encoding="utf-8") as f:
        snap = json.load(f)

    by_type = snap.get("byType", {})
    asof_pretty = snap.get("asOfDate") or "—"
    generated = snap.get("generatedAt", "")[:19].replace("T", " ") + " UTC"

    subtitle = (
        "Find Day-1 trigger events, not established trends. "
        "Each passing stock is classified as a fresh BREAKOUT, a RESUMPTION after pullback, "
        "a MIXED transitional signal, or a MATURE already-running trend. "
        "Click a chip below to filter."
    )

    snapshot_json = json.dumps(snap, separators=(",", ":"))

    html = (HTML_TEMPLATE
        .replace("__SUBTITLE__", escape(subtitle))
        .replace("__ASOF__", escape(asof_pretty))
        .replace("__PASSING__", str(snap.get("passing", 0)))
        .replace("__SCANNED__", str(snap.get("scanned", 0)))
        .replace("__GENERATED__", escape(generated))
        .replace("__N_BREAKOUT__",   str(by_type.get("BREAKOUT", 0)))
        .replace("__N_RESUMPTION__", str(by_type.get("RESUMPTION", 0)))
        .replace("__N_MIXED__",      str(by_type.get("MIXED", 0)))
        .replace("__N_MATURE__",     str(by_type.get("MATURE", 0)))
        .replace("__TV_EXCHANGE_MAP_JSON__", json.dumps(config.TV_EXCHANGE_MAP))
        .replace("__TV_URL_TEMPLATE_JSON__", json.dumps(config.TV_CHART_URL_TEMPLATE))
        .replace("__SNAPSHOT_JSON__", snapshot_json)
    )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out_path} ({len(html)} bytes, {snap.get('passing', 0)} rows)")
    return out_path


if __name__ == "__main__":
    snap_path = sys.argv[1] if len(sys.argv) > 1 else SNAP_PATH
    out_path  = sys.argv[2] if len(sys.argv) > 2 else OUT_PATH
    build_dashboard(snap_path, out_path)
