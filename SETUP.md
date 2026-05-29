# Setup on a Fresh Machine

This document walks through getting the Ichimoku Daily Screener running from scratch on a new machine — including creating the Cowork dashboard artifact and the daily refresh scheduled task. Works on **Windows** and **macOS** (Linux too, with the same general flow as macOS).

The Python code itself is cross-platform — only the **paths**, the **`python` vs `python3` command**, and the **scheduled-task shell tool** differ between operating systems. `config.py` uses script-relative paths by default, so you don't need to edit it unless you want data written somewhere unusual.

## Prerequisites (all platforms)

- **Python 3.10+** (3.13 recommended). The project uses only the stdlib — no `pip install` step.
- **Git** — to clone the repo.
- **Cowork (Claude desktop app)** — installed and signed in. The artifact and scheduled task rely on Cowork's tool calls.

## Cloud deployment (recommended) — GitHub Actions + Pages

The most reliable way to run this is **not** on your own machine at all. The repo
ships with `.github/workflows/daily-scan.yml`, which runs the scanner on GitHub's
servers each weekday after the US close and publishes the dashboard to GitHub
Pages as a permanent URL. Benefits over the local approach:

- Runs even when your computer is off.
- GitHub runners have full internet access — no proxy/firewall issues reaching Yahoo.
- No local shell tool, no scheduled-task permission dance, no Cowork artifact required.
- You get a bookmarkable live URL that refreshes itself.

### One-time enable

1. Push the repo to GitHub (it already lives at `eswarperla/ichimoku-daily-screener`).
2. In the repo on GitHub: **Settings → Pages → Build and deployment → Source → "GitHub Actions"**.
3. (Optional) Trigger the first run manually: **Actions tab → "Daily Ichimoku Scan" → "Run workflow"**.

After the first successful run, your dashboard is live at:
`https://eswarperla.github.io/ichimoku-daily-screener/`

The workflow's schedule is `0 22 * * 1-5` (22:00 UTC, Mon–Fri) — after the US market
close, so each run has settled end-of-day data. The scanner aborts (and the old
dashboard stays live) if the data feed is degraded — see `MIN_DATA_COVERAGE` in `config.py`.

The rest of this document covers the **local** workflow, which is still fully
supported if you'd rather run it on your own machine.

---

## 1. Clone the repository

```sh
# pick any folder you like
git clone https://github.com/eswarperla/ichimoku-daily-screener.git
cd ichimoku-daily-screener
```

The directory name doesn't have to match the repo name. Wherever you put it, `config.py` will pick it up automatically.

## 2. (Optional) Edit `config.py`

Open `config.py`. Most settings have sensible defaults — only touch them if you know what you're tweaking. The one section that often deserves a glance:

```python
# Liquidity floor — increase for stricter, fewer-but-cleaner signals
MIN_AVG_DOLLAR_VOL_M = 20.0

# Toggle off if you want only the original 6 Chartink filters (no future-cloud-green check)
REQUIRE_FUTURE_CLOUD_GREEN = True
```

You should not need to set `PROJECT_DIR` — it now defaults to the directory containing `config.py` itself.

## 3. Generate the first snapshot and dashboard locally

### Windows (PowerShell)

```powershell
cd 'D:\path\to\ichimoku-daily-screener'
python scanner.py
python build_dashboard.py
```

### macOS / Linux (Terminal)

```sh
cd ~/ichimoku-daily-screener
python3 scanner.py
python3 build_dashboard.py
```

Expected output: `Done in 10–15s — N stocks passing (BREAKOUT=…, RESUMPTION=…, MIXED=…, MATURE=…)` and a `dashboard.html` file in the project directory. Open it in a browser to sanity-check.

If you see "Could not fetch …" for every ticker, your machine can't reach `query1.finance.yahoo.com` — check VPN, firewall, or corporate proxy settings.

## 4. Create the Cowork dashboard artifact

Open Cowork and **select the project folder as the workspace folder** (Cowork → folder picker).

Then tell Claude (the exact wording matters less than the parameters):

> Create a Cowork artifact from the file at `<PATH_TO>/dashboard.html` with id `ichimoku-daily-scanner` and the description below.

Where `<PATH_TO>` is:
- Windows: `D:\path\to\ichimoku-daily-screener`
- macOS: `/Users/YOURNAME/ichimoku-daily-screener` (or wherever you cloned)

The literal `mcp__cowork__create_artifact` payload:

```json
{
  "id": "ichimoku-daily-scanner",
  "html_path": "<absolute path to dashboard.html>",
  "description": "Daily Ichimoku scanner for US mid/large-cap stocks. Shows fresh BREAKOUT/RESUMPTION triggers along with MIXED and MATURE setups. Candlestick patterns, TradingView links, volume confirmation, S&P 500 ∪ NASDAQ-100 universe, daily refresh via scheduled task."
}
```

The artifact will appear in Cowork's sidebar.

## 5. Create the daily refresh scheduled task

This is the only step that's meaningfully different between Windows and macOS, because the scheduled task needs to run shell commands on your local machine — and Cowork exposes different shell tools per OS.

### Windows version

Tell Claude:

> Create a scheduled task with id `ichimoku-daily-scan`, cron `0 7 * * 2-6` (7 AM local time, Tue-Sat), running this prompt:

```
You are running the daily Ichimoku scanner.

STEP 1: PowerShell (mcp__Windows-MCP__PowerShell):
  cd 'D:\path\to\ichimoku-daily-screener'; python scanner.py

STEP 2: PowerShell:
  cd 'D:\path\to\ichimoku-daily-screener'; python build_dashboard.py

STEP 3: Call mcp__cowork__update_artifact with:
  - id: ichimoku-daily-scanner
  - html_path: D:\path\to\ichimoku-daily-screener\dashboard.html
  - update_summary: "Daily refresh — <N> stocks passing as of <asOfDate>"
  (Read snapshots/latest.json for N and asOfDate.)

STEP 4: PowerShell archive snapshot for the day:
  $d = (Get-Content 'D:\path\to\ichimoku-daily-screener\snapshots\latest.json' | ConvertFrom-Json).asOfDate; Copy-Item -Force 'D:\path\to\ichimoku-daily-screener\snapshots\latest.json' "D:\path\to\ichimoku-daily-screener\snapshots\$d.json"

STEP 5: Reply: "Scanner refreshed: <N> stocks passing as of <date>. Top 3 by streak: …"

If any step fails, stop and report which step + the error. Do NOT update the artifact if scanner output shows 0 stocks passing or any error.
```

### macOS version

On macOS, Cowork's local shell tool is typically named something like `mcp__cowork__bash` or similar (the exact name may vary by Cowork version). The first time you set this up on Mac, ask Claude:

> What MCP tool can you use to execute shell commands on my local Mac (not the sandbox)?

Claude will tell you the exact tool name. Substitute it for `<MAC_SHELL_TOOL>` below.

Tell Claude:

> Create a scheduled task with id `ichimoku-daily-scan`, cron `0 7 * * 2-6` (7 AM local time, Tue-Sat), running this prompt:

```
You are running the daily Ichimoku scanner. Replace <PROJECT_DIR> with /Users/YOURNAME/ichimoku-daily-screener (or wherever you cloned).

STEP 1: Shell (<MAC_SHELL_TOOL>):
  cd '<PROJECT_DIR>' && python3 scanner.py

STEP 2: Shell:
  cd '<PROJECT_DIR>' && python3 build_dashboard.py

STEP 3: Call mcp__cowork__update_artifact with:
  - id: ichimoku-daily-scanner
  - html_path: <PROJECT_DIR>/dashboard.html
  - update_summary: "Daily refresh — <N> stocks passing as of <asOfDate>"
  (Read snapshots/latest.json for N and asOfDate.)

STEP 4: Archive snapshot for the day:
  cd '<PROJECT_DIR>' && D=$(python3 -c "import json; print(json.load(open('snapshots/latest.json'))['asOfDate'])") && cp snapshots/latest.json "snapshots/$D.json"

STEP 5: Reply: "Scanner refreshed: <N> stocks passing as of <date>. Top 3 by streak: …"

If any step fails, stop and report which step + the error. Do NOT update the artifact if scanner output shows 0 stocks passing or any error.
```

The cron `0 7 * * 2-6` is in **your machine's local timezone**. It runs at 7 AM Tue-Sat — catches each Mon-Fri US trading day's close (the US market closes 1:30 AM IST the next morning; a 7 AM run reliably has settled EOD data). Adjust the hour if your timezone or preference differs.

## 6. Pre-approve permissions

The very first scheduled run will pause asking you to approve the shell tool and the artifact-update tool. **Run the task manually once** from Cowork's Scheduled section by clicking "Run now" — approve the prompts — and from then on the task runs unattended.

## 7. Verify

```sh
python3 verify_ticker.py AAPL 12   # macOS / Linux
python   verify_ticker.py AAPL 12   # Windows
```

You should see a clean day-by-day table showing every one of the 7 daily filter conditions. The artifact should be visible in Cowork's sidebar and reload-able.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Could not fetch <TICKER>` for every ticker | Network can't reach Yahoo Finance | Check VPN, firewall, corporate proxy |
| Scanner runs but 0 stocks passing | Could be legit (bear market) or `MIN_AVG_DOLLAR_VOL_M` too high | Drop liquidity floor in `config.py` to verify |
| Artifact shows stale data | Scheduled task hasn't run | Run task manually once from Scheduled section to grant approvals |
| `ImportError: No module named config` | Running from wrong directory | `cd` into the project root before running |
| Tradingview link opens wrong symbol | Exchange code missing from `TV_EXCHANGE_MAP` | Add the Yahoo exchange code → TradingView prefix in `config.py` |
| Scheduled task fails on Mac with "tool not found" | Wrong shell-tool name in prompt | Ask Claude what local shell tool is available, substitute it |

## Updating universe / thresholds

All tunable values live in `config.py`. Common edits:

- **Stricter liquidity** — bump `MIN_AVG_DOLLAR_VOL_M` higher (e.g., 50, 100)
- **Drop future-cloud-green** to use only the original 6 Chartink filters — set `REQUIRE_FUTURE_CLOUD_GREEN = False`
- **Broader fresh-trigger window** — bump `MAX_FRESH_STREAK` from 3 to 5
- **Reshape breakout vs resumption** — adjust `BREAKOUT_PRIOR_MAX` and `RESUMPTION_PRIOR_MIN`
- **Add/remove universe tickers** — edit `UNIVERSE` directly

After any config change, re-run `python scanner.py && python build_dashboard.py` (or `python3` on Mac) and refresh the artifact (Cowork's Reload button or ask Claude to update it).

## Moving between machines (Windows ↔ macOS)

The repo itself is fully portable. The things that DON'T travel with the repo and must be recreated on each machine:

1. **The Cowork dashboard artifact** — recreate via Step 4 above
2. **The daily scheduled task** — recreate via Step 5 (use the platform-appropriate version)
3. **Historical snapshots** in `snapshots/*.json` — these are gitignored, so each machine builds its own history from the first scan onward. If you want to seed a new machine with the old history, manually copy the JSON files over.
