# Master Prompt — Recreate the Ichimoku Daily Screener from Scratch

This is the prompt to give Claude (in Cowork mode, on a machine where Yahoo Finance is reachable) if you have nothing but this file and want the entire project reproduced from zero. Paste everything below the `---` line as one message.

You'll need to adjust two things at the bottom: your install path and your local timezone for the schedule.

---

I want you to build a daily Ichimoku stock screener for US mid/large-cap equities, end-to-end, as described below. The deliverable is a working Python project plus a Cowork dashboard artifact plus a daily scheduled task.

## Goal

A scanner that runs every weekday after the US market closes, screens for stocks meeting specific bullish Ichimoku conditions, classifies them into actionable buckets (BREAKOUT / RESUMPTION / MIXED / MATURE), and presents the results in a live, sortable HTML dashboard. The dashboard refreshes nightly via a scheduled task. Everything runs locally on my Windows machine using `mcp__Windows-MCP__PowerShell` — no third-party Python packages, only stdlib.

## Project layout to produce

```
ichimoku-daily-screener/
├── config.py              # ALL settings — paths, URLs, thresholds, universe
├── scanner.py             # Yahoo fetch + Ichimoku + classification + JSON output
├── build_dashboard.py     # HTML generator from snapshots/latest.json
├── verify_ticker.py       # day-by-day debug for any ticker
├── snapshots/             # JSON snapshots (gitignored)
├── README.md
├── SETUP.md
└── .gitignore
```

**`config.py` is the single source of truth.** No other file may hardcode paths, URLs, or thresholds — everything imports from `config`.

## Universe

S&P 500 ∪ NASDAQ-100 (~520 unique tickers, all comfortably > $2B market cap). Hardcode the ticker list in `config.UNIVERSE` as a sorted, deduplicated list. Use ticker symbols exactly as Yahoo Finance recognizes them (e.g. `BRK.B`, `BF.B` with the dot, not `BRK-B`). If any ticker fails to fetch, silently skip it.

## Data source

Yahoo Finance unofficial chart API. URL:

```
https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d&events=div%2Csplit
```

Fetch with a Chrome-like `User-Agent` header. No API key. Use 12 concurrent worker threads. 15-second timeout per request. Yahoo returns OHLC + volume in `chart.result[0].indicators.quote[0]` and timestamps in `chart.result[0].timestamp`. Drop any bar with a null OHLC value. Require at least 80 clean bars per ticker (need ≥ 78 for Ichimoku).

## Ichimoku indicators (classic 9/26/52)

For each ticker, compute at each bar `t`:

- **Tenkan (Conversion)** = (max High over last 9 bars + min Low over last 9 bars) / 2
- **Kijun (Base)** = (max High over last 26 bars + min Low over last 26 bars) / 2
- **Senkou Span B (raw)** at bar t = (max High over last 52 bars + min Low over last 52 bars) / 2
- **Senkou Span A (raw)** at bar t = (Tenkan[t] + Kijun[t]) / 2
- **Visible cloud at bar t**: `spanA_at[t] = spanA_raw[t-26]`, `spanB_at[t] = spanB_raw[t-26]`

The **raw** spans at bar t become the cloud plotted 26 bars in the future. The **at** spans are what's plotted underneath today's price.

## The 8 filter conditions (all must hold on the latest closed bar)

For a stock to make the list, **every one** of these must be true at bar `t = last_idx`:

1. `Conv[t] > Base[t]` — Tenkan above Kijun
2. `Base[t] > max(spanA_at[t], spanB_at[t])` — Kijun above the visible cloud top
3. `Base[t] > Base[t-1]` — Kijun is rising (strict `>`)
4. `Conv[t] > Conv[t-1]` — Tenkan is rising (strict `>`)
5. `Close[t] > Conv[t]` — close above Tenkan
6. `Close[t] > Close[t-26]` — chikou-style breakout above 26-day-ago close
7. `spanA_raw[t] > spanB_raw[t]` — **future cloud is green** (forward bias). Make this toggleable via `config.REQUIRE_FUTURE_CLOUD_GREEN`, default `True`.
8. 20-day average dollar volume (close × volume) ≥ $20M. Configurable via `config.MIN_AVG_DOLLAR_VOL_M`.

All inequalities are **strict** — flat lines do not count as rising.

## Setup-type classification

For each passing stock, compute the **pass history** by re-evaluating the same 7 daily filters at every prior bar (volume liquidity is stock-level, doesn't change per day). The **streak** = consecutive passes from the latest bar back. Then classify:

- **MATURE** if `streak > 3`
- Else look at the **17 days immediately before the current streak**:
  - Count how many of those 17 days were also passing → call this `prior_passes`
  - **BREAKOUT**: `prior_passes ≤ 4` (stock was NOT trending, today is a real fresh signal)
  - **RESUMPTION**: `prior_passes ≥ 10` (stock was trending, took a brief pullback, now back)
  - **MIXED**: anything in between (5–9), OR window < 5 bars

These thresholds are configurable: `MAX_FRESH_STREAK`, `PRIOR_WINDOW_SIZE`, `BREAKOUT_PRIOR_MAX`, `RESUMPTION_PRIOR_MIN`.

## Candlestick pattern detection

For each passing stock, detect the most significant pattern in the last 1–3 bars. **Context-aware**: every stock here is in an uptrend (passes a bullish filter), so:

- A hammer-shape candle (small body top, long lower wick, tiny upper wick) at the top of an uptrend is a **Hanging Man** (BEARISH reversal warning), not a Hammer.
- A shooting-star-shape candle (small body bottom, long upper wick, tiny lower wick) is a **Shooting Star** (BEARISH), not an Inverted Hammer.

Detect (in priority order, most specific first):

1. **Three White Soldiers** — 3 consecutive strong green closes, each higher; body > 60% of range each. BULLISH.
2. **Three Black Crows** — 3 consecutive strong red closes, each lower; body > 60%. BEARISH.
3. **Evening Star** — strong green, small body, strong red closing into day-1's body. BEARISH.
4. **Morning Star** — strong red, small body, strong green closing into day-1's body. BULLISH.
5. **Bullish Engulfing** — yesterday red, today green; today's body engulfs yesterday's. BULLISH.
6. **Bearish Engulfing** — yesterday green, today red; today's body engulfs yesterday's. BEARISH.
7. **Dark Cloud Cover** — yesterday strong green, today red opens above yesterday's close, closes below midpoint of yesterday's body. BEARISH.
8. **Piercing Line** — yesterday strong red, today green opens below yesterday's close, closes above midpoint. BULLISH.
9. **Doji** — body < 8% of range. NEUTRAL.
10. **Bullish Marubozu** — large green body, > 92% of range. BULLISH.
11. **Bearish Marubozu** — large red body, > 92% of range. BEARISH.
12. **Hanging Man** — body < 35%, lower wick ≥ 2× body, upper wick < 10% of range. BEARISH (uptrend context).
13. **Shooting Star** — body < 35%, upper wick ≥ 2× body, lower wick < 10% of range. BEARISH.
14. **Spinning Top** — body < 30%, both wicks > body, similar wick sizes. NEUTRAL.

If no pattern matches, record `null`.

**Volume confirmation**: also flag a pattern as `volConfirmed = True` if today's volume > 1.5× the 20-day average volume. Configurable via `VOLUME_CONFIRM_MULT`.

## Output schema — snapshots/latest.json

```json
{
  "generatedAt": "ISO-8601 timestamp",
  "asOfDate": "YYYY-MM-DD (last closed bar)",
  "universeSize": 520,
  "scanned": 520,
  "passing": 47,
  "byType": {"BREAKOUT": 18, "RESUMPTION": 5, "MIXED": 15, "MATURE": 9},
  "failed": 0,
  "results": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "exchange": "NMS",
      "close": 308.82,
      "asOf": "2026-05-22",
      "daysPassing": 4,
      "setupType": "MATURE",
      "priorPasses": null,
      "priorWindow": null,
      "avgDollarVolM": 13958.0,
      "pattern": "Doji" | null,
      "patternLean": "BULLISH" | "BEARISH" | "NEUTRAL" | null,
      "volConfirmed": false,
      "conv": 301.98,
      "base": 288.235,
      "cloudTop": 263.21,
      "futureSpanA": 295.11,
      "futureSpanB": 278.45,
      "close26ago": 263.4,
      "pctAboveConv": 2.27,
      "pct26d": 17.24
    }
  ],
  "filters": [ "...human-readable list..." ],
  "classification": { "BREAKOUT": "description", ... }
}
```

Sort results: BREAKOUT first, then RESUMPTION, then MIXED, then MATURE. Within each, freshest (smaller streak) first, ties broken by larger `pctAboveConv`.

## Dashboard — build_dashboard.py

Generates a self-contained `dashboard.html` from `snapshots/latest.json`. Designed for Cowork's sandboxed artifact iframe — no external network access except the three approved CDN libraries. Must include:

- Light mode (`color-scheme: light`)
- **Header stat cards**: As-of date, Stocks passing / scanned, Generated timestamp
- **Setup-type chips** — clickable, color-coded: green BREAKOUT, blue RESUMPTION, yellow MIXED, gray MATURE. Counts of each. Clicking a chip filters the table.
- **Controls row**: search box (ticker/name), min streak input, min $M volume input, reset button
- **Grid.js sortable table** with columns: Setup badge, Ticker (clickable link to TradingView), Company, Exch., Close, Streak (pill), Prior (X/Y format), 20d $M vol, % > Conv, % vs 26d, Yesterday's pattern (color-coded pill with optional `✓ vol` mark).
- **TradingView links** open in new tab to `https://www.tradingview.com/chart/?symbol={EXCHANGE}:{TICKER}&interval=D`. `interval=D` forces daily timeframe. Map Yahoo exchange codes (NMS, NGM, NYQ, etc.) to TradingView prefixes (NASDAQ, NYSE, AMEX, BATS) — configurable in `config.TV_EXCHANGE_MAP`.
- **Footer**: list the 8 filter conditions, define Streak/Prior/Pattern.
- **localStorage** persists user's filter selections across reloads.

Use only the three CDN libraries Cowork allows: Chart.js, Grid.js (with its theme CSS), Mermaid. No other external scripts or fetches.

## Verify_ticker.py

Standalone CLI debug helper. Usage: `python verify_ticker.py AAPL 12` prints a day-by-day table of the last 12 bars showing every one of the 7 daily conditions C1–C7 and which pass/fail. Also reports the current streak under both the 7-filter rule and the legacy 6-filter rule (without C7) for comparison.

## Daily scheduled task

Create a Cowork scheduled task with id `ichimoku-daily-scan`, cron `0 7 * * 2-6` (7 AM local time Tue-Sat — adjust to user's timezone; this catches each Mon-Fri US trading day's close). The task prompt should: (1) PowerShell-run scanner.py, (2) PowerShell-run build_dashboard.py, (3) call `mcp__cowork__update_artifact` with the new HTML, (4) PowerShell-copy `latest.json` to a dated archive `<asOfDate>.json`, (5) reply with a one-line summary of the top 3 stocks by streak.

## Acceptance tests

After you've built everything, prove it works by:

1. Running `python scanner.py` — expect "Done in 10-15s — N stocks passing (BREAKOUT=…, RESUMPTION=…, MIXED=…, MATURE=…)" with N typically in the 10-60 range during a normal market.
2. Running `python verify_ticker.py CRWD 12` — expect a clean day-by-day table.
3. Opening the artifact in Cowork — table renders, chips filter, TradingView links open daily charts.
4. Triggering the scheduled task once manually — it runs end-to-end without errors.

## Honest expectations to convey to the user as you go

- "Fresh breakouts have higher false-start rates than resumptions; resumptions have higher hit rates but smaller upside per trade."
- "Candlestick patterns are confirmation layers, not primary signals."
- "The filter is descriptive, not predictive. This is a research tool, not investment advice."

## My specifics (fill in for your machine)

- **Install path**: `D:\ichimoku-daily-screener` (Windows)
- **Local timezone**: India Standard Time (UTC+5:30). Schedule for 7 AM IST = `0 7 * * 2-6` in IST cron.
- **Workspace folder**: I'll select the install path as the Cowork workspace folder before you create the artifact.

Build it all, test it end-to-end, and show me the dashboard.
