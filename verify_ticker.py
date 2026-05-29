"""
verify_ticker.py — debug & verify any single ticker against the scanner's logic.

Usage:
  python verify_ticker.py <TICKER> [N_BARS]

Prints a day-by-day pass/fail table for the last N bars (default 12), showing
every one of the 7 daily Ichimoku conditions and whether each held. Useful for
sanity-checking the streak/classification a stock receives in the snapshot.

Examples:
  python verify_ticker.py AAPL          # last 12 bars for AAPL
  python verify_ticker.py CRWD 20       # last 20 bars for CRWD
  python verify_ticker.py TXN 10        # debug a near-miss
"""
from __future__ import annotations
import os, sys, datetime as dt
# Make sure this script can import config/scanner regardless of the directory
# it's launched from (cross-platform — no backslash assumptions).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from scanner import fetch_yahoo, ichimoku


def verify(ticker: str, n_bars: int = 12) -> None:
    d = fetch_yahoo(ticker)
    if d is None:
        print(f"Could not fetch {ticker}")
        sys.exit(1)

    closes, highs, lows, ts = d["close"], d["high"], d["low"], d["ts"]
    conv, base, sA, sB, sA_raw, sB_raw = ichimoku(highs, lows)
    n = len(closes)
    C = config.CLOUD_SHIFT

    print(f"{ticker} — verifying last {n_bars} closed daily bars (all 7 daily filters):\n")
    print("  C1: Conv > Base")
    print("  C2: Base > Cloud Top (visible cloud, plotted from 26 bars ago)")
    print("  C3: Base > Base[t-1]  (Kijun rising)")
    print("  C4: Conv > Conv[t-1]  (Tenkan rising)")
    print("  C5: Close > Conv")
    print("  C6: Close > Close[t-26]")
    print("  C7: Span A_raw > Span B_raw  (FUTURE cloud green — today's leading-span calc)")
    print()
    print(f"{'Date':<12} {'Close':>8} {'Conv':>8} {'Base':>8} {'Cloud':>8} {'SpA_r':>8} {'SpB_r':>8}  "
          f"{'C1':>3} {'C2':>3} {'C3':>3} {'C4':>3} {'C5':>3} {'C6':>3} {'C7':>3}  ALL")

    Y = lambda b: ' Y' if b else ' n'
    passing = []
    for i in range(max(C, n - n_bars), n):
        if conv[i] is None or base[i] is None or sA[i] is None or sB[i] is None:
            continue
        date = dt.datetime.fromtimestamp(ts[i], dt.timezone.utc).date().isoformat()
        ct = max(sA[i], sB[i])
        c1 = conv[i] > base[i]
        c2 = base[i] > ct
        c3 = base[i] > base[i-1] if base[i-1] is not None else False
        c4 = conv[i] > conv[i-1] if conv[i-1] is not None else False
        c5 = closes[i] > conv[i]
        c6 = closes[i] > closes[i-C]
        c7 = (sA_raw[i] is not None and sB_raw[i] is not None
              and sA_raw[i] > sB_raw[i])
        all_pass = c1 and c2 and c3 and c4 and c5 and c6 and c7
        passing.append(all_pass)
        print(f"{date:<12} {closes[i]:>8.2f} {conv[i]:>8.2f} {base[i]:>8.2f} {ct:>8.2f} "
              f"{(sA_raw[i] or 0):>8.2f} {(sB_raw[i] or 0):>8.2f}  "
              f"{Y(c1):>3}{Y(c2):>3}{Y(c3):>3}{Y(c4):>3}{Y(c5):>3}{Y(c6):>3}{Y(c7):>3}   "
              f"{'YES' if all_pass else 'no '}")

    # Streak (consecutive YES from latest)
    streak = 0
    for v in reversed(passing):
        if v: streak += 1
        else: break
    print(f"\nStreak (consecutive YES from latest, all 7 conditions): {streak}")

    # Also report under the OLD 6-filter rule for comparison
    passing_old = []
    for i in range(max(C, n - n_bars), n):
        if conv[i] is None or base[i] is None or sA[i] is None or sB[i] is None:
            continue
        ct = max(sA[i], sB[i])
        c1 = conv[i] > base[i]
        c2 = base[i] > ct
        c3 = base[i] > base[i-1] if base[i-1] is not None else False
        c4 = conv[i] > conv[i-1] if conv[i-1] is not None else False
        c5 = closes[i] > conv[i]
        c6 = closes[i] > closes[i-C]
        passing_old.append(c1 and c2 and c3 and c4 and c5 and c6)
    streak_old = 0
    for v in reversed(passing_old):
        if v: streak_old += 1
        else: break
    print(f"Streak under OLD 6-filter rule (no future-cloud-green): {streak_old}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ticker = sys.argv[1].upper()
    n_bars = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    verify(ticker, n_bars)
