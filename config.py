"""
config.py — single source of truth for all scanner settings, paths, thresholds,
and the ticker universe. Edit anything here and re-run scanner.py / build_dashboard.py
to apply changes. No other file should hardcode these values.
"""

from __future__ import annotations
import os

# ---------------------------------------------------------------------------
# 1. PATHS
# ---------------------------------------------------------------------------
# PROJECT_DIR defaults to the directory containing this config.py file.
# Works cross-platform out of the box — Windows, macOS, Linux — wherever you
# clone the repo, that's where the project operates. Only override this if
# you want data files written somewhere else.
PROJECT_DIR    = os.path.dirname(os.path.abspath(__file__))

SNAPSHOTS_DIR  = os.path.join(PROJECT_DIR, "snapshots")
LATEST_JSON    = os.path.join(SNAPSHOTS_DIR, "latest.json")
DASHBOARD_HTML = os.path.join(PROJECT_DIR, "dashboard.html")

# Daily history archive — a compact, version-controlled record of how many
# stocks fell into each setup bucket per day, so the dashboard can chart how
# the BREAKOUT/RESUMPTION/MIXED/MATURE mix shifts over time. Unlike the full
# snapshots (gitignored, ephemeral), this small file IS committed to the repo
# by the GitHub Actions workflow so history accrues across runs.
HISTORY_DIR    = os.path.join(PROJECT_DIR, "history")
HISTORY_JSON   = os.path.join(HISTORY_DIR, "history.json")
HISTORY_MAX_DAYS = 365   # keep at most this many of the most recent days

# Cowork artifact id (must match the id used when create_artifact was called)
ARTIFACT_ID    = "ichimoku-daily-scanner"

# ---------------------------------------------------------------------------
# 2. DATA SOURCE — Yahoo Finance chart API
# ---------------------------------------------------------------------------
YAHOO_CHART_URL_TEMPLATE = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range={range}&interval={interval}&events=div%2Csplit"
)
FETCH_RANGE      = "1y"     # how much history to pull (need >=78 daily bars)
FETCH_INTERVAL   = "1d"     # daily bars
FETCH_TIMEOUT_S  = 15
PARALLEL_WORKERS = 12

# Retry/backoff for transient fetch failures (Yahoo rate-limits under load).
# Total attempts = FETCH_RETRIES + 1. Backoff grows linearly per attempt.
FETCH_RETRIES    = 2
FETCH_BACKOFF_S  = 1.5

# Data-coverage guard. A run is only trustworthy if we successfully fetched
# data for at least this fraction of the universe. Below this, the scan refuses
# to publish (exits non-zero) so a half-fetched universe never overwrites a
# good dashboard — distinguishes "quiet market" from "data feed broken".
MIN_DATA_COVERAGE = 0.90
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# 3. ICHIMOKU FILTER + LIQUIDITY THRESHOLDS
# ---------------------------------------------------------------------------
# Ichimoku parameters — classic 9/26/52 settings
TENKAN_PERIOD = 9
KIJUN_PERIOD  = 26
SENKOU_B_PERIOD = 52
CLOUD_SHIFT   = 26   # leading-span projection (and chikou lag) in bars

# Toggle the future-cloud-green requirement (Span A_raw > Span B_raw today).
# This is filter #7 on top of the 6 original Chartink conditions.
REQUIRE_FUTURE_CLOUD_GREEN = True

# Liquidity filter — minimum 20-day average dollar volume (in millions $)
MIN_AVG_DOLLAR_VOL_M = 20.0
LIQUIDITY_WINDOW_BARS = 20

# Minimum bars of clean data required to evaluate a ticker (78 = TENKAN(9) +
# KIJUN(26) + SENKOU_B(52); we keep a generous buffer at 80)
MIN_BARS = 80

# ---------------------------------------------------------------------------
# 4. SETUP-TYPE CLASSIFICATION THRESHOLDS
# ---------------------------------------------------------------------------
# Stocks with current streak <= MAX_FRESH_STREAK are classified by the prior-17-day
# history into BREAKOUT / RESUMPTION / MIXED. Beyond that, MATURE.
MAX_FRESH_STREAK     = 3
PRIOR_WINDOW_SIZE    = 17
BREAKOUT_PRIOR_MAX   = 4    # <= this many prior passes => BREAKOUT  (fresh from non-trending)
RESUMPTION_PRIOR_MIN = 10   # >= this many prior passes => RESUMPTION (continuation after pullback)
# Anything in between (5-9) => MIXED. Anything with prior window < 5 bars => MIXED.

# ---------------------------------------------------------------------------
# 5. CANDLESTICK PATTERN DETECTION THRESHOLDS
# ---------------------------------------------------------------------------
DOJI_BODY_PCT_MAX       = 0.08   # body < 8% of range = Doji
MARUBOZU_BODY_PCT_MIN   = 0.92   # body > 92% of range = Marubozu
HAMMER_SHAPE_BODY_PCT   = 0.35   # body < 35% with long single wick
HAMMER_WICK_MULT        = 2.0    # wick at least 2x body
HAMMER_OTHER_WICK_PCT   = 0.10   # other wick < 10% of range
SPINNING_TOP_BODY_PCT   = 0.30   # body < 30% with both wicks larger than body
SPINNING_TOP_WICK_RATIO = (0.5, 2.0)  # upper/lower wick ratio range

# Pattern-specific reliability boosters
ENGULFING_PREV_BODY_PCT = 0.30
ENGULFING_CUR_BODY_PCT  = 0.50
PIERCING_BODY_PCT       = 0.50
TRIPLE_BAR_BODY_PCT     = 0.60
STAR_OUTER_BODY_PCT     = 0.50
STAR_INNER_BODY_PCT     = 0.35

# Volume confirmation — flag a pattern as "vol-confirmed" when today's volume
# exceeds this multiple of the 20-day average
VOLUME_CONFIRM_MULT     = 1.5

# ---------------------------------------------------------------------------
# 6. TRADINGVIEW LINK
# ---------------------------------------------------------------------------
# interval=D forces daily timeframe in TradingView regardless of last-viewed
TV_CHART_URL_TEMPLATE = "https://www.tradingview.com/chart/?symbol={sym}&interval=D"
TV_EXCHANGE_MAP = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NAS": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE",   "NYS": "NYSE",
    "ASE": "AMEX",   "AMX": "AMEX",
    "BTS": "BATS",   "PCX": "AMEX",
}

# ---------------------------------------------------------------------------
# 7. SCHEDULED TASK
# ---------------------------------------------------------------------------
SCHEDULED_TASK_ID   = "ichimoku-daily-scan"
SCHEDULED_CRON      = "0 7 * * 2-6"   # 7 AM IST, Tue-Sat (catches Mon-Fri US trading days)

# ---------------------------------------------------------------------------
# 8. UNIVERSE — S&P 500 ∪ NASDAQ-100 (~520 US large/mid caps, all >$2B)
# ---------------------------------------------------------------------------
# This is the practical operating proxy for "Russell 1000 mid+large cap".
# Constituents change periodically; missing tickers are silently skipped at
# scan time.
UNIVERSE: list[str] = sorted(set("""
A AAPL ABBV ABNB ABT ACGL ACN ADBE ADI ADM ADP ADSK AEE AEP AES AFL AIG AIZ AJG AKAM
ALB ALGN ALL ALLE AMAT AMCR AMD AME AMGN AMP AMT AMZN ANET ANSS AON AOS APA APD APH
APO APP APTV ARE ARM ASML ATO AVB AVGO AVY AWK AXON AXP AZO BA BAC BALL BAX BBY BDX
BEN BF.B BG BIIB BK BKNG BKR BLDR BLK BMY BR BRK.B BRO BSX BX BXP C CAG CAH CARR
CAT CB CBOE CBRE CCI CCL CDNS CDW CE CEG CF CFG CHD CHRW CHTR CI CINF CL CLX CMCSA
CME CMG CMI CMS CNC CNP COF COIN COO COP COR COST CPAY CPB CPRT CPT CRH CRM CRWD CSCO
CSGP CSX CTAS CTRA CTSH CTVA CVNA CVS CVX CZR D DAL DAY DD DDOG DE DECK DELL DFS DG
DGX DHI DHR DIS DLR DLTR DOC DOV DOW DPZ DRI DTE DUK DVA DVN DXCM EA EBAY ECL ED EFX
EG EIX EL ELV EMN EMR ENPH EOG EPAM EQIX EQR EQT ERIE ES ESS ETN ETR EVRG EW EXC EXE
EXPD EXPE EXR F FANG FAST FCX FDS FDX FE FFIV FI FICO FIS FITB FOXA FOX FRT FSLR FTNT
FTV GD GDDY GE GEHC GEN GEV GILD GIS GL GLW GM GNRC GOOG GOOGL GPC GPN GRMN GS GWW
HAL HAS HBAN HCA HD HES HIG HII HLT HOLX HON HOOD HPE HPQ HRL HSIC HST HSY HUBB HUM
HWM IBM ICE IDXX IEX IFF INCY INTC INTU INVH IP IPG IQV IR IRM ISRG IT ITW IVZ J JBHT
JBL JCI JD JKHY JNJ JNPR JPM K KDP KEY KEYS KHC KIM KKR KLAC KMB KMI KMX KO KR KVUE
L LDOS LEN LH LHX LIN LKQ LLY LMT LNT LOW LRCX LULU LUV LVS LW LYB LYV MA MAA MAR MAS
MCD MCHP MCK MCO MDB MDLZ MDT MELI MET META MGM MHK MKC MKTX MLM MMC MMM MNST MO MOH
MOS MPC MPWR MRK MRNA MRVL MS MSCI MSFT MSI MSTR MTB MTCH MTD MU NCLH NDAQ NDSN NEE
NEM NFLX NI NKE NOC NOW NRG NSC NTAP NTRS NUE NVDA NVR NWS NWSA NXPI O ODFL OKE OMC
ON ORCL ORLY OTIS OXY PANW PARA PAYC PAYX PCAR PCG PDD PEG PEP PFE PFG PG PGR PH PHM
PKG PLD PLTR PM PNC PNR PNW PODD POOL PPG PPL PRU PSA PSX PTC PWR PYPL QCOM QQQ RCL
REG REGN RF RIVN RJF RL RMD ROK ROL ROP ROST RSG RTX RVTY SBAC SBUX SCHW SHW SJM SLB
SMCI SNA SNDK SNPS SO SOLV SPG SPGI SRE STE STLD STT STX STZ SW SWK SWKS SYF SYK
SYY T TAP TDG TDY TEAM TECH TEL TER TFC TFX TGT TJX TMO TMUS TPL TPR TRGP TRMB TROW
TRV TSCO TSLA TSN TT TTD TTWO TXN TXT TYL UAL UBER UDR UHS ULTA UNH UNP UPS URI USB V
VICI VLO VLTO VMC VRSK VRSN VRTX VST VTR VTRS VZ WAB WAT WBA WBD WDAY WDC WEC WELL
WFC WM WMB WMT WRB WSM WST WTW WY WYNN XEL XOM XYL YUM ZBH ZBRA ZS ZTS
""".split()))
