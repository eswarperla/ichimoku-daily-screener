# Setup on a Fresh Machine

This document walks through getting the Ichimoku Daily Screener running from scratch on a new Windows machine — including creating the Cowork dashboard artifact and the daily refresh scheduled task.

## Prerequisites

- **Windows 10/11** with PowerShell
- **Python 3.10+** (3.13 recommended; the project uses only the stdlib so no `pip install` step is needed)
- **Git** — install from https://git-scm.com/ if you don't have it
- **Cowork (Claude desktop app)** — installed and signed in. The artifact and scheduled task rely on Cowork's tool calls.

## 1. Clone the repository

```powershell
cd D:\                              # or wherever you want the project
git clone https://github.com/eswarperla/ichimoku-daily-screener.git
cd ichimoku-daily-screener
```

You can clone into any folder — the directory name doesn't have to match the repo name.

## 2. Point the config at your install location

Open `config.py` and update **`PROJECT_DIR`** to wherever you just cloned. All other paths are derived from it.

```python
PROJECT_DIR = r"D:\ichimoku-daily-screener"   # <-- match your clone location
```

Everything else in `config.py` is reasonable defaults — only change if you know what you're tweaking.

## 3. Generate the first snapshot and dashboard locally

```powershell
python scanner.py                  # ~13 seconds; pulls Yahoo data, builds snapshot
python build_dashboard.py          # generates dashboard.html
```

You should see output like `Done in 13.5s — N stocks passing (BREAKOUT=…, RESUMPTION=…, MIXED=…, MATURE=…)`. Open `dashboard.html` in a browser to sanity-check the table.

If the scanner fails with "Could not fetch …" errors for *every* ticker, your machine can't reach `query1.finance.yahoo.com` — check VPN, firewall, or corporate proxy settings.

## 4. Create the Cowork dashboard artifact

Open Cowork and **make sure the same folder you cloned into is selected as the workspace folder** (Cowork → Settings → Workspace, or use the folder picker).

Then tell Claude:

> Create a Cowork artifact from the file at `D:\ichimoku-daily-screener\dashboard.html` with id `ichimoku-daily-scanner` and description "Daily Ichimoku scanner for US mid/large-cap stocks. Setup-type classification (BREAKOUT/RESUMPTION/MIXED/MATURE), candlestick patterns, TradingView links."

Claude will invoke `mcp__cowork__create_artifact` with those parameters and the artifact will appear in the Cowork sidebar.

If you want to do it explicitly via the tool call, the literal payload is:

```json
{
  "id": "ichimoku-daily-scanner",
  "html_path": "D:\\ichimoku-daily-screener\\dashboard.html",
  "description": "Daily Ichimoku scanner for US mid/large-cap stocks. Shows fresh BREAKOUT/RESUMPTION triggers along with MIXED and MATURE setups. Candlestick patterns, TradingView links, volume confirmation, S&P 500 ∪ NASDAQ-100 universe, daily refresh via scheduled task."
}
```

## 5. Create the daily refresh scheduled task

Tell Claude:

> Create a scheduled task with id `ichimoku-daily-scan`, cron `0 7 * * 2-6` (7 AM IST Tue-Sat), running this prompt:
>
> ```
> Run the Ichimoku scanner. Steps:
>
> 1. PowerShell: cd 'D:\ichimoku-daily-screener'; python scanner.py
> 2. PowerShell: cd 'D:\ichimoku-daily-screener'; python build_dashboard.py
> 3. Call mcp__cowork__update_artifact with:
>    - id: ichimoku-daily-scanner
>    - html_path: D:\ichimoku-daily-screener\dashboard.html
>    - update_summary: "Daily refresh — <N> stocks passing as of <asOfDate>"
>    (Read snapshots/latest.json for N and asOfDate.)
> 4. PowerShell: $d = (Get-Content 'D:\ichimoku-daily-screener\snapshots\latest.json' | ConvertFrom-Json).asOfDate; Copy-Item -Force 'D:\ichimoku-daily-screener\snapshots\latest.json' "D:\ichimoku-daily-screener\snapshots\$d.json"
> 5. Reply with: "Scanner refreshed: <N> stocks passing as of <date>. Top 3 by streak: …"
>
> If any step fails, stop and report which step + the error.
> ```

The literal `mcp__scheduled-tasks__create_scheduled_task` payload is:

```json
{
  "taskId": "ichimoku-daily-scan",
  "cronExpression": "0 7 * * 2-6",
  "description": "Daily Ichimoku scanner — refresh the US mid/large-cap dashboard with last-closed-day data",
  "prompt": "<full prompt above, with paths matching YOUR install location>"
}
```

The cron `0 7 * * 2-6` is **local time** (set up in your Windows timezone). It runs at 7 AM Tue-Sat, which catches each Mon-Fri US trading day's close.

## 6. Pre-approve permissions

The very first scheduled run will pause asking you to approve PowerShell access and the artifact-update tool. **Run the task manually once** from Cowork's Scheduled section by clicking "Run now" — approve the prompts — and from then on the task runs unattended.

## 7. Verify

```powershell
# After the first scheduled run finishes:
python verify_ticker.py AAPL 12        # spot-check Ichimoku math on a known ticker
```

You should see a clean day-by-day table. The artifact should be visible in Cowork's sidebar and reload-able.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Could not fetch <TICKER>` for every ticker | Network can't reach Yahoo Finance | Check VPN, firewall, corporate proxy |
| Scanner runs but 0 stocks passing | Could be legit (bear market) or `MIN_AVG_DOLLAR_VOL_M` too high | Drop liquidity floor in `config.py` to verify |
| Artifact shows stale data | Scheduled task hasn't run | Run task manually once from Scheduled section to grant approvals |
| `ImportError: No module named config` | Running from wrong directory | `cd` into the project root before running |
| Tradingview link opens wrong symbol | Exchange code missing from `TV_EXCHANGE_MAP` | Add the Yahoo exchange code → TradingView prefix in `config.py` |

## Updating universe / thresholds

All tunable values live in `config.py`. Common edits:

- **Stricter liquidity** — bump `MIN_AVG_DOLLAR_VOL_M` higher (e.g., 50, 100)
- **Drop future-cloud-green** to use only the original 6 Chartink filters — set `REQUIRE_FUTURE_CLOUD_GREEN = False`
- **Broader fresh-trigger window** — bump `MAX_FRESH_STREAK` from 3 to 5
- **Reshape breakout vs resumption** — adjust `BREAKOUT_PRIOR_MAX` and `RESUMPTION_PRIOR_MIN`
- **Add/remove universe tickers** — edit `UNIVERSE` directly

After any config change, re-run `python scanner.py && python build_dashboard.py` and refresh the artifact (Cowork's Reload button or ask Claude to update it).
