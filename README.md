# Ichimoku Daily Screener

A daily end-of-day stock screener for US mid/large-cap equities that finds **Day-1 trigger events** in the Ichimoku Kinko Hyo system. Instead of producing the usual list of "stocks already in established uptrends," it classifies each passing stock into one of four buckets so you can act on fresh signals and skip late entries.

The output is a live dashboard (Cowork artifact) that refreshes nightly via a scheduled task.

## What it does

For each scan it pulls daily OHLC from Yahoo Finance for ~520 US large/mid-cap tickers (S&P 500 ∪ NASDAQ-100), computes Ichimoku (9, 26, 52), and applies 8 filters. Each stock that passes is then **classified** by the prior 17-day history:

| Setup type | Streak | Prior-17 passes | Meaning |
|---|---|---|---|
| **BREAKOUT** | ≤ 3 | ≤ 4 | Fresh signal — stock was not trending, just triggered |
| **RESUMPTION** | ≤ 3 | ≥ 10 | Continuation — was trending, brief pullback, now back |
| **MIXED** | ≤ 3 | 5–9 | Choppy/transitional, ambiguous signal |
| **MATURE** | ≥ 4 | — | Already running for days — entries are late |

Each row also reports a context-aware **candlestick pattern** (Bullish Marubozu, Three White Soldiers, Hanging Man, Shooting Star, Doji, etc.) on the last 1–3 bars, with a `✓ vol` flag when today's volume exceeds 1.5× the 20-day average.

Tickers are clickable — they open TradingView's daily-timeframe chart in a new tab.

## The 8 filter conditions (all must hold for the latest closed daily bar)

1. Conversion (Tenkan, 9) > Base (Kijun, 26)
2. Base > Cloud Top (max of visible Span A, Span B at today's bar)
3. Base > 1-day-ago Base — Kijun is rising
4. Conversion > 1-day-ago Conversion — Tenkan is rising
5. Close > Conversion
6. Close > 26-day-ago Close (chikou-style breakout)
7. **Future cloud green** — today's leading Span A > today's leading Span B (forward bias)
8. **Liquidity** — 20-day average dollar volume ≥ $20M

## Project layout

```
ichimoku-daily-screener/
├── .github/workflows/
│   └── daily-scan.yml     # cloud schedule: runs scanner + deploys to GitHub Pages
├── config.py              # ALL settings — paths, URLs, thresholds, universe
├── scanner.py             # main scanner — Yahoo fetch + Ichimoku + classification
├── build_dashboard.py     # produces dashboard.html from snapshots/latest.json
├── verify_ticker.py       # debug: day-by-day pass/fail table for any ticker
├── snapshots/             # JSON snapshots (gitignored, regenerated)
├── README.md              # this file
├── SETUP.md               # setup instructions (cloud + local)
└── MASTER_PROMPT.md       # full spec to recreate the project from scratch
```

## Running it

Two supported ways to run the daily scan:

- **GitHub Actions + Pages (recommended)** — the included workflow runs the
  scanner in the cloud each weekday and publishes a live dashboard URL. No local
  machine needed. See [SETUP.md](SETUP.md#cloud-deployment-recommended--github-actions--pages).
- **Locally** — run `python scanner.py && python build_dashboard.py` and open
  `dashboard.html`, optionally wired to a Cowork artifact + scheduled task. See [SETUP.md](SETUP.md).

## Quick start

```powershell
# Pull data, build dashboard
python scanner.py
python build_dashboard.py

# Debug a specific ticker
python verify_ticker.py AAPL 12
```

For fresh-machine setup (cloning, creating the Cowork artifact, scheduling the daily task), see **[SETUP.md](SETUP.md)**.

## Universe & data source

- **Universe**: S&P 500 + NASDAQ-100 union — ~520 unique US tickers, all comfortably above $2B market cap. List lives in `config.py` and is sorted/deduplicated.
- **Data**: Yahoo Finance daily OHLC via the official chart endpoint, fetched with no API key over plain HTTPS from the user's machine.
- **No third-party Python packages** — stdlib only.

## Honest caveats

- The filter is descriptive, not predictive. Past performance of similar setups is not a guarantee of future returns.
- The setup-type classification is based on simple historical pass-rate windows. Different market regimes will shift the breakout-vs-resumption-vs-mature mix.
- Candlestick patterns are detected by simple body/wick rules and should be treated as confirmation/warning layers, not primary signals.
- This is a research tool. Not investment advice.
