"""
Ichimoku Daily Scanner — US large/mid cap stocks.

Filters (all must be true for the latest closed daily bar):
  1. Daily Ichimoku Conversion (Tenkan, 9) > Daily Ichimoku Base (Kijun, 26)
  2. Daily Ichimoku Base > Daily Ichimoku Cloud Top (max of Span A, Span B at that bar)
  3. Daily Ichimoku Base > 1-day-ago Ichimoku Base (Kijun rising)
  4. Daily Ichimoku Conversion > 1-day-ago Conversion (Tenkan rising)
  5. Daily Close > Daily Ichimoku Conversion
  6. Daily Close > 26-day-ago Close (chikou-style breakout)
  7. Future cloud green (today's leading Span A > leading Span B)  [if enabled in config]
  8. 20-day average dollar volume >= MIN_AVG_DOLLAR_VOL_M (liquidity)

Outputs: JSON snapshot file consumed by the dashboard artifact.

This script uses ONLY the Python stdlib (urllib, json, ...) — no third-party
dependencies needed. All tunable settings live in config.py.
"""

from __future__ import annotations
import urllib.request
import urllib.error
import json
import os
import sys
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

# Universe + Yahoo settings all live in config.py
UNIVERSE = config.UNIVERSE

# ---------------------------------------------------------------------------
# Yahoo Finance fetch
# ---------------------------------------------------------------------------
def fetch_yahoo(symbol: str, period: str | None = None) -> dict | None:
    """Return {'ts':[...], 'open':[...], 'high':[...], 'low':[...], 'close':[...],
    'meta': {...}} or None on failure. Filters out bars with null OHLC."""
    # Yahoo uses '.' but URLs need '%2E' sometimes; keep as is for common cases.
    rng = period or config.FETCH_RANGE
    url = config.YAHOO_CHART_URL_TEMPLATE.format(
        symbol=symbol, range=rng, interval=config.FETCH_INTERVAL)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=config.FETCH_TIMEOUT_S) as r:
            j = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            ConnectionError, json.JSONDecodeError) as e:
        return None
    try:
        result = j["chart"]["result"][0]
        ts = result["timestamp"]
        q = result["indicators"]["quote"][0]
        opens, highs, lows, closes, vols = q["open"], q["high"], q["low"], q["close"], q.get("volume") or [None]*len(ts)
    except (KeyError, IndexError, TypeError):
        return None

    # Drop any bars with any null OHLC value (volume may be 0/None, we coerce to 0)
    clean_ts, clean_o, clean_h, clean_l, clean_c, clean_v = [], [], [], [], [], []
    for i in range(len(ts)):
        if None in (opens[i], highs[i], lows[i], closes[i]):
            continue
        clean_ts.append(ts[i]); clean_o.append(opens[i])
        clean_h.append(highs[i]); clean_l.append(lows[i])
        clean_c.append(closes[i])
        clean_v.append(vols[i] if vols[i] is not None else 0)
    if len(clean_ts) < config.MIN_BARS:  # need at least 78 bars for Ichimoku
        return None
    return {
        "ts": clean_ts,
        "open": clean_o, "high": clean_h, "low": clean_l, "close": clean_c, "volume": clean_v,
        "meta": {
            "symbol": result["meta"].get("symbol", symbol),
            "longName": result["meta"].get("longName") or result["meta"].get("shortName") or symbol,
            "exchange": result["meta"].get("exchangeName", ""),
            "currency": result["meta"].get("currency", "USD"),
            "regularMarketPrice": result["meta"].get("regularMarketPrice"),
        }
    }

# ---------------------------------------------------------------------------
# Ichimoku math (validated against ichimoku_validate.py)
# ---------------------------------------------------------------------------
def ichimoku(highs: list[float], lows: list[float]):
    """Return (conv, base, spanA_at, spanB_at, spanA_raw, spanB_raw).
    *_at values: cloud VISIBLE at bar t (computed CLOUD_SHIFT bars earlier).
    *_raw values: today's leading-span computation, which becomes the FUTURE
                  cloud plotted at bar t+CLOUD_SHIFT."""
    T, K, S, C = (config.TENKAN_PERIOD, config.KIJUN_PERIOD,
                  config.SENKOU_B_PERIOD, config.CLOUD_SHIFT)
    n = len(highs)
    conv, base = [None]*n, [None]*n
    spanA_raw, spanB_raw = [None]*n, [None]*n
    for t in range(n):
        if t >= T - 1:
            conv[t] = (max(highs[t-T+1:t+1]) + min(lows[t-T+1:t+1])) / 2
        if t >= K - 1:
            base[t] = (max(highs[t-K+1:t+1]) + min(lows[t-K+1:t+1])) / 2
        if t >= S - 1:
            spanB_raw[t] = (max(highs[t-S+1:t+1]) + min(lows[t-S+1:t+1])) / 2
        if conv[t] is not None and base[t] is not None:
            spanA_raw[t] = (conv[t] + base[t]) / 2
    spanA_at = [spanA_raw[t-C] if t >= C else None for t in range(n)]
    spanB_at = [spanB_raw[t-C] if t >= C else None for t in range(n)]
    return conv, base, spanA_at, spanB_at, spanA_raw, spanB_raw

def passes_at(idx: int, closes, conv, base, sA, sB,
              sA_raw=None, sB_raw=None, require_future_green: bool = False) -> bool:
    """Check the 6 base Ichimoku filters at bar `idx`. Optionally also require
    the FUTURE cloud (today's leading-span computation) to be green
    (spanA_raw > spanB_raw)."""
    C = config.CLOUD_SHIFT
    if idx < C:
        return False
    needed = [conv[idx], base[idx], sA[idx], sB[idx],
              conv[idx-1], base[idx-1], closes[idx-C]]
    if any(v is None for v in needed):
        return False
    cloud_top = max(sA[idx], sB[idx])
    base_ok = (conv[idx] > base[idx]
               and base[idx] > cloud_top
               and base[idx] > base[idx-1]
               and conv[idx] > conv[idx-1]
               and closes[idx] > conv[idx]
               and closes[idx] > closes[idx-C])
    if not base_ok:
        return False
    if require_future_green:
        if sA_raw is None or sB_raw is None:
            return False
        if sA_raw[idx] is None or sB_raw[idx] is None:
            return False
        if not (sA_raw[idx] > sB_raw[idx]):
            return False
    return True

def pass_history(closes, conv, base, sA, sB, sA_raw, sB_raw, require_future_green: bool):
    """Return list[bool] of length len(closes): pass/fail at each bar."""
    return [passes_at(t, closes, conv, base, sA, sB, sA_raw, sB_raw,
                      require_future_green=require_future_green)
            for t in range(len(closes))]

def streak_from_history(hist: list[bool]) -> int:
    s = 0
    for v in reversed(hist):
        if v: s += 1
        else: break
    return s

# ---------------------------------------------------------------------------
# Setup-type classification
# ---------------------------------------------------------------------------
def classify_setup(hist: list[bool]):
    """Classify TODAY's signal based on streak length and the prior window of
    days that immediately preceded the current streak.
      - BREAKOUT   : streak <= MAX_FRESH_STREAK AND <= BREAKOUT_PRIOR_MAX prior passes
                     (stock was NOT trending; today is a real new signal)
      - RESUMPTION : streak <= MAX_FRESH_STREAK AND >= RESUMPTION_PRIOR_MIN prior passes
                     (stock was trending, took a brief pullback, now back)
      - MIXED      : streak <= MAX_FRESH_STREAK AND prior window in gray zone
      - MATURE     : streak > MAX_FRESH_STREAK (already in a sustained run)
    Returns (label, prior_passes, prior_window_size)."""
    if not hist or not hist[-1]:
        return ("NONE", 0, 0)
    streak = streak_from_history(hist)
    if streak > config.MAX_FRESH_STREAK:
        return ("MATURE", None, None)
    start_of_streak = len(hist) - streak
    window_end = start_of_streak  # exclusive
    window_start = max(0, window_end - config.PRIOR_WINDOW_SIZE)
    prior = hist[window_start:window_end]
    prior_passes = sum(1 for v in prior if v)
    n = len(prior)
    if n < 5:
        return ("MIXED", prior_passes, n)
    if prior_passes <= config.BREAKOUT_PRIOR_MAX:
        return ("BREAKOUT", prior_passes, n)
    if prior_passes >= config.RESUMPTION_PRIOR_MIN:
        return ("RESUMPTION", prior_passes, n)
    return ("MIXED", prior_passes, n)

# ---------------------------------------------------------------------------
# Candlestick pattern detection (context-aware: we know stock is in uptrend)
# ---------------------------------------------------------------------------
# Lean values: 'BULLISH' (green) | 'BEARISH' (red) | 'NEUTRAL' (gray)
#
# Important context: every stock that reaches pattern-detection has already
# passed the bullish Ichimoku filter, so it's in an uptrend. That means:
#   - "Hammer-shape" candle at the top = Hanging Man (BEARISH reversal warning)
#   - "Inverted-hammer-shape" at the top = Shooting Star (BEARISH reversal warning)
# We never label a candle "Hammer" or "Inverted Hammer" in this scanner because
# those names require a downtrend context to be valid.

def _bar_metrics(o: float, h: float, l: float, c: float):
    """Return (body, rng, body_pct, upper_wick, lower_wick, is_green, is_red)."""
    rng = h - l
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    body_pct = (body / rng) if rng > 0 else 0
    return body, rng, body_pct, upper, lower, c > o, c < o

def detect_candle_pattern(opens, highs, lows, closes, volumes):
    """Detect the most significant candlestick pattern over the last 1-3 bars.

    Returns dict with keys: name (str | None), lean ('BULLISH'/'BEARISH'/'NEUTRAL' | None),
                            volConfirmed (bool).
    'name' is None when no recognizable pattern.
    """
    n = len(closes)
    if n < 3:
        return {"name": None, "lean": None, "volConfirmed": False}

    # Indexes: t0 = today, t1 = yesterday, t2 = day before
    t0, t1, t2 = n-1, n-2, n-3
    b0 = _bar_metrics(opens[t0], highs[t0], lows[t0], closes[t0])
    b1 = _bar_metrics(opens[t1], highs[t1], lows[t1], closes[t1])
    b2 = _bar_metrics(opens[t2], highs[t2], lows[t2], closes[t2])

    body0, rng0, bp0, up0, lo0, g0, r0 = b0
    body1, rng1, bp1, up1, lo1, g1, r1 = b1
    body2, rng2, bp2, up2, lo2, g2, r2 = b2

    # Skip ill-defined bars
    if rng0 <= 0:
        return {"name": None, "lean": None, "volConfirmed": False}

    # Volume confirmation: today's volume > VOLUME_CONFIRM_MULT * 20-day average
    look = min(config.LIQUIDITY_WINDOW_BARS, n)
    vols_window = volumes[n-look:n]
    avg_vol = sum(vols_window) / look if look else 0
    today_vol = volumes[t0] or 0
    vol_conf = (avg_vol > 0) and (today_vol > config.VOLUME_CONFIRM_MULT * avg_vol)

    # Pull thresholds from config
    TRI_BODY = config.TRIPLE_BAR_BODY_PCT
    STAR_OUT = config.STAR_OUTER_BODY_PCT
    STAR_IN  = config.STAR_INNER_BODY_PCT
    ENG_PREV = config.ENGULFING_PREV_BODY_PCT
    ENG_CUR  = config.ENGULFING_CUR_BODY_PCT
    PIERCE   = config.PIERCING_BODY_PCT
    DOJI_MAX = config.DOJI_BODY_PCT_MAX
    MARU_MIN = config.MARUBOZU_BODY_PCT_MIN
    HAM_BODY = config.HAMMER_SHAPE_BODY_PCT
    HAM_MULT = config.HAMMER_WICK_MULT
    HAM_OPP  = config.HAMMER_OTHER_WICK_PCT
    ST_BODY  = config.SPINNING_TOP_BODY_PCT
    ST_LO, ST_HI = config.SPINNING_TOP_WICK_RATIO

    name, lean = None, None

    # ----- 3-bar patterns (checked first, most specific) -----
    # Three White Soldiers: 3 strong green closes, each higher than the last
    if g0 and g1 and g2 and rng1 > 0 and rng2 > 0 \
       and bp0 > TRI_BODY and bp1 > TRI_BODY and bp2 > TRI_BODY \
       and closes[t0] > closes[t1] > closes[t2] \
       and opens[t0] > opens[t1] and opens[t1] > opens[t2]:
        name, lean = "Three White Soldiers", "BULLISH"

    # Three Black Crows: 3 strong red closes, each lower
    elif r0 and r1 and r2 and rng1 > 0 and rng2 > 0 \
         and bp0 > TRI_BODY and bp1 > TRI_BODY and bp2 > TRI_BODY \
         and closes[t0] < closes[t1] < closes[t2] \
         and opens[t0] < opens[t1] and opens[t1] < opens[t2]:
        name, lean = "Three Black Crows", "BEARISH"

    # Evening Star: green (day-2), small body (day-1), red (today) closing into day-2's body
    elif g2 and bp2 > STAR_OUT and rng2 > 0 \
         and rng1 > 0 and bp1 < STAR_IN \
         and r0 and bp0 > STAR_OUT \
         and closes[t0] < (opens[t2] + closes[t2]) / 2 \
         and closes[t0] > opens[t2]:
        name, lean = "Evening Star", "BEARISH"

    # Morning Star: red (day-2), small body (day-1), green (today) closing into day-2's body
    elif r2 and bp2 > STAR_OUT and rng2 > 0 \
         and rng1 > 0 and bp1 < STAR_IN \
         and g0 and bp0 > STAR_OUT \
         and closes[t0] > (opens[t2] + closes[t2]) / 2 \
         and closes[t0] < opens[t2]:
        name, lean = "Morning Star", "BULLISH"

    # ----- 2-bar patterns -----
    elif rng1 > 0:
        # Bullish Engulfing: yesterday red, today green body engulfs yesterday's body
        if r1 and g0 and bp1 > ENG_PREV and bp0 > ENG_CUR \
           and opens[t0] <= closes[t1] and closes[t0] >= opens[t1] \
           and (closes[t0] - opens[t0]) > (opens[t1] - closes[t1]):
            name, lean = "Bullish Engulfing", "BULLISH"

        # Bearish Engulfing: yesterday green, today red body engulfs yesterday's body
        elif g1 and r0 and bp1 > ENG_PREV and bp0 > ENG_CUR \
             and opens[t0] >= closes[t1] and closes[t0] <= opens[t1] \
             and (opens[t0] - closes[t0]) > (closes[t1] - opens[t1]):
            name, lean = "Bearish Engulfing", "BEARISH"

        # Dark Cloud Cover: yesterday strong green, today red opens above & closes below midpoint
        elif g1 and r0 and bp1 > PIERCE and bp0 > 0.4 \
             and opens[t0] > closes[t1] \
             and closes[t0] < (opens[t1] + closes[t1]) / 2 \
             and closes[t0] > opens[t1]:
            name, lean = "Dark Cloud Cover", "BEARISH"

        # Piercing Line: yesterday strong red, today green opens below & closes above midpoint
        elif r1 and g0 and bp1 > PIERCE and bp0 > 0.4 \
             and opens[t0] < closes[t1] \
             and closes[t0] > (opens[t1] + closes[t1]) / 2 \
             and closes[t0] < opens[t1]:
            name, lean = "Piercing Line", "BULLISH"

    # ----- 1-bar patterns -----
    if name is None:
        # Doji: tiny body, wicks on both sides
        if bp0 < DOJI_MAX:
            name, lean = "Doji", "NEUTRAL"

        # Bullish Marubozu: large green body, minimal wicks
        elif g0 and bp0 > MARU_MIN:
            name, lean = "Bullish Marubozu", "BULLISH"

        # Bearish Marubozu: large red body, minimal wicks
        elif r0 and bp0 > MARU_MIN:
            name, lean = "Bearish Marubozu", "BEARISH"

        # Hanging Man (at top of uptrend): small body at top, long lower wick, tiny upper wick
        elif bp0 < HAM_BODY and lo0 >= HAM_MULT * body0 and up0 < HAM_OPP * rng0 and body0 > 0:
            name, lean = "Hanging Man", "BEARISH"

        # Shooting Star (at top of uptrend): small body at bottom, long upper wick, tiny lower wick
        elif bp0 < HAM_BODY and up0 >= HAM_MULT * body0 and lo0 < HAM_OPP * rng0 and body0 > 0:
            name, lean = "Shooting Star", "BEARISH"

        # Spinning Top: small body, similar-sized wicks on both sides
        elif bp0 < ST_BODY and up0 > body0 and lo0 > body0 \
             and ST_LO < (up0 / lo0 if lo0 > 0 else 0) < ST_HI:
            name, lean = "Spinning Top", "NEUTRAL"

    return {"name": name, "lean": lean, "volConfirmed": bool(vol_conf and name)}


# ---------------------------------------------------------------------------
# Per-ticker scan
# ---------------------------------------------------------------------------
def scan_ticker(symbol: str) -> dict | None:
    data = fetch_yahoo(symbol)
    if data is None:
        return None
    closes, highs, lows = data["close"], data["high"], data["low"]
    volumes = data["volume"]
    conv, base, sA, sB, sA_raw, sB_raw = ichimoku(highs, lows)
    last_idx = len(closes) - 1

    # ---- Liquidity filter: 20-day average dollar volume ----
    look = min(config.LIQUIDITY_WINDOW_BARS, last_idx + 1)
    dollar_vols = [closes[i] * (volumes[i] or 0) for i in range(last_idx - look + 1, last_idx + 1)]
    avg_dollar_vol = sum(dollar_vols) / look if look else 0
    avg_dollar_vol_m = avg_dollar_vol / 1_000_000
    if avg_dollar_vol_m < config.MIN_AVG_DOLLAR_VOL_M:
        return None

    # ---- Must pass 6 base filters + (optionally) future-cloud-green ----
    if not passes_at(last_idx, closes, conv, base, sA, sB, sA_raw, sB_raw,
                     require_future_green=config.REQUIRE_FUTURE_CLOUD_GREEN):
        return None

    # ---- Pass history (with same future-cloud-green setting for streak consistency) ----
    hist = pass_history(closes, conv, base, sA, sB, sA_raw, sB_raw,
                        require_future_green=config.REQUIRE_FUTURE_CLOUD_GREEN)
    streak = streak_from_history(hist)
    setup_type, prior_passes, prior_n = classify_setup(hist)

    # ---- Candlestick pattern on the last 1-3 bars ----
    opens = data["open"]
    pattern = detect_candle_pattern(opens, highs, lows, closes, volumes)

    last_ts = data["ts"][last_idx]
    last_date = dt.datetime.utcfromtimestamp(last_ts).date().isoformat()
    return {
        "ticker": data["meta"]["symbol"],
        "name": data["meta"]["longName"],
        "exchange": data["meta"]["exchange"],
        "close": round(closes[last_idx], 4),
        "asOf": last_date,
        "daysPassing": streak,
        "setupType": setup_type,
        "priorPasses": prior_passes,
        "priorWindow": prior_n,
        "avgDollarVolM": round(avg_dollar_vol_m, 1),
        "pattern": pattern["name"],
        "patternLean": pattern["lean"],
        "volConfirmed": pattern["volConfirmed"],
        "conv": round(conv[last_idx], 4),
        "base": round(base[last_idx], 4),
        "cloudTop": round(max(sA[last_idx], sB[last_idx]), 4),
        "futureSpanA": round(sA_raw[last_idx], 4) if sA_raw[last_idx] is not None else None,
        "futureSpanB": round(sB_raw[last_idx], 4) if sB_raw[last_idx] is not None else None,
        "close26ago": round(closes[last_idx-26], 4),
        "pctAboveConv": round((closes[last_idx]/conv[last_idx]-1)*100, 2),
        "pct26d": round((closes[last_idx]/closes[last_idx-26]-1)*100, 2),
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(out_path: str, limit: int | None = None) -> None:
    universe = UNIVERSE if not limit else UNIVERSE[:limit]
    print(f"Scanning {len(universe)} tickers...", flush=True)
    start = time.time()

    results: list[dict] = []
    failed: list[str] = []
    scanned = 0

    with ThreadPoolExecutor(max_workers=config.PARALLEL_WORKERS) as ex:
        futures = {ex.submit(scan_ticker, t): t for t in universe}
        for fut in as_completed(futures):
            tk = futures[fut]
            scanned += 1
            try:
                res = fut.result()
                if res:
                    results.append(res)
            except Exception:
                failed.append(tk)
            if scanned % 50 == 0:
                print(f"  ... {scanned}/{len(universe)} scanned, {len(results)} pass", flush=True)

    # Sort: BREAKOUT first (most interesting), then RESUMPTION, MIXED, MATURE last.
    # Within each bucket, freshest streak first then biggest %-above-Conv.
    type_order = {"BREAKOUT": 0, "RESUMPTION": 1, "MIXED": 2, "MATURE": 3}
    results.sort(key=lambda r: (
        type_order.get(r["setupType"], 9),
        r["daysPassing"],                 # smaller streak first within fresh buckets
        -r.get("pctAboveConv", 0),
        r["ticker"],
    ))
    by_type = {k: sum(1 for r in results if r["setupType"] == k)
               for k in ("BREAKOUT", "RESUMPTION", "MIXED", "MATURE")}
    snapshot = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "asOfDate": results[0]["asOf"] if results else None,
        "universeSize": len(universe),
        "scanned": scanned,
        "byType": by_type,
        "passing": len(results),
        "failed": len(failed),
        "results": results,
        "filters": [
            "Daily Conversion > Daily Base",
            "Daily Base > Daily Cloud Top",
            "Daily Base > 1-day-ago Base (rising)",
            "Daily Conversion > 1-day-ago Conversion (rising)",
            "Daily Close > Daily Conversion",
            "Daily Close > 26-day-ago Close",
            "Future cloud green (today's Span A > Span B)"
              if config.REQUIRE_FUTURE_CLOUD_GREEN else
              "Future cloud green: NOT ENFORCED (REQUIRE_FUTURE_CLOUD_GREEN=False)",
            f"20-day avg dollar volume >= ${config.MIN_AVG_DOLLAR_VOL_M:.0f}M",
        ],
        "classification": {
            "BREAKOUT":   "streak<=3 AND <=4 of prior 17 days passed (fresh signal from non-trending state)",
            "RESUMPTION": "streak<=3 AND >=10 of prior 17 days passed (trend continuation after brief pullback)",
            "MIXED":      "streak<=3 AND prior 17 in gray zone (5-9 passes) — choppy/transitioning",
            "MATURE":     "streak>=4 (already in a sustained run; trend already underway)",
        },
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    elapsed = time.time() - start
    by_type_str = ", ".join(f"{k}={v}" for k, v in by_type.items())
    print(f"Done in {elapsed:.1f}s — {snapshot['passing']} stocks passing ({by_type_str})", flush=True)
    print(f"Wrote {out_path}", flush=True)
    return snapshot


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else config.LATEST_JSON
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    main(out, lim)
