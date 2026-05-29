"""
update_history.py — append today's scan summary to the daily history archive.

Reads snapshots/latest.json (produced by scanner.py) and upserts a compact
record into history/history.json. The record holds only aggregate counts — not
the full per-stock results — so the file stays small enough to commit to the
repo every day. The dashboard reads this archive to chart how the
BREAKOUT/RESUMPTION/MIXED/MATURE mix shifts over time.

Behaviour:
  - Keyed by asOfDate, so re-running for the same trading day REPLACES that
    day's record rather than duplicating it (idempotent).
  - Sorted ascending by date; trimmed to the most recent HISTORY_MAX_DAYS.
  - Skips gracefully if the latest snapshot has no asOfDate (e.g. 0 passing and
    no data) — nothing to record.

Stdlib only. Run after scanner.py and before build_dashboard.py.
"""

from __future__ import annotations
import json
import os
import sys

import config


def _load_history(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def update_history(snap_path: str = config.LATEST_JSON,
                   hist_path: str = config.HISTORY_JSON) -> dict | None:
    with open(snap_path, "r", encoding="utf-8") as f:
        snap = json.load(f)

    as_of = snap.get("asOfDate")
    if not as_of:
        print("No asOfDate in snapshot — nothing to archive.")
        return None

    by_type = snap.get("byType", {}) or {}
    record = {
        "asOfDate": as_of,
        "generatedAt": snap.get("generatedAt"),
        "passing": snap.get("passing", 0),
        "fetched": snap.get("fetched"),
        "coverage": snap.get("coverage"),
        "byType": {
            "BREAKOUT":   by_type.get("BREAKOUT", 0),
            "RESUMPTION": by_type.get("RESUMPTION", 0),
            "MIXED":      by_type.get("MIXED", 0),
            "MATURE":     by_type.get("MATURE", 0),
        },
    }

    history = _load_history(hist_path)
    # Upsert by date (idempotent): drop any existing record for this date.
    history = [h for h in history if h.get("asOfDate") != as_of]
    history.append(record)
    history.sort(key=lambda h: h.get("asOfDate", ""))
    if len(history) > config.HISTORY_MAX_DAYS:
        history = history[-config.HISTORY_MAX_DAYS:]

    os.makedirs(os.path.dirname(hist_path), exist_ok=True)
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print(f"History updated: {len(history)} day(s) on record "
          f"(latest {as_of} — {record['passing']} passing).")
    return record


if __name__ == "__main__":
    snap = sys.argv[1] if len(sys.argv) > 1 else config.LATEST_JSON
    hist = sys.argv[2] if len(sys.argv) > 2 else config.HISTORY_JSON
    update_history(snap, hist)
