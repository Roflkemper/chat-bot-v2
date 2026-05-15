"""Named "play" templates that enrich watchlist alerts with concrete entry plans.

When a Rule.label matches a key here, watchlist_loop appends a "ПЛАН ВХОДА" section
with absolute entry/stop/TP levels computed from current BTC mark price.

Thresholds based on combined 2024+2026 backtest (scripts/cascade_backtest_combined.py)
and funding-edge study (2 years of 8h BTCUSDT funding vs forward 4h/24h price moves).
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
MARKET_1M_CSV = ROOT / "market_live" / "market_1m.csv"


def _last_btc_price() -> Optional[float]:
    """Read last close from market_live/market_1m.csv (small file tailed inline)."""
    if not MARKET_1M_CSV.exists():
        return None
    last_close: Optional[float] = None
    try:
        with MARKET_1M_CSV.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    last_close = float(row["close"])
                except (ValueError, KeyError):
                    continue
    except OSError:
        logger.exception("play_templates.market_read_failed")
    return last_close


PLAYS: dict[str, dict] = {
    "funding_squeeze_long": {
        "title": "📈 FUNDING SQUEEZE → LONG",
        "edge": "n=10 (за 2 года) при funding < -0.010%/8h\n"
                "  +4ч: 70% pct_up, mean +0.68%\n"
                "  +24ч: 70% pct_up, mean +0.60%",
        "dir": "LONG",
        "tp1_pct": +0.46,
        "tp2_pct": +0.68,
        "stop_pct": -0.40,
        "exit_after_h": 4,
        "note": "Редкий сетап (~5 раз/год). Размер обычный.",
    },
    "cascade_short_continuation_long": {
        "title": "📈 SHORT-каскад → LONG (продолжение тренда вверх)",
        "edge": "n=139 (2024+2026 combined, обновлено): 70% pct_up 4h, mean +0.41%\n"
                "  Сетап работал стабильно в обоих периодах.",
        "dir": "LONG",
        "tp1_pct": +0.41,
        "tp2_pct": +0.74,
        "stop_pct": -0.40,
        "exit_after_h": 4,
        "note": None,
    },
    "cascade_long_reversal_short": {
        "title": "📉 LONG-каскад → SHORT (новый сетап для 2026 режима)",
        "edge": "n=20 (2026): 65% pct_down 4h, mean -0.17%, 12h -0.58%\n"
                "  ⚠ ИНВЕРСИЯ от 2024 (там был bounce). Малая выборка.",
        "dir": "SHORT",
        "tp1_pct": -0.40,
        "tp2_pct": -0.78,
        "stop_pct": +0.40,
        "exit_after_h": 4,
        "note": "Свежий edge на 2026 регим. Половинный размер до n>=40.",
    },
}


def format_play(label: str, current_value: float) -> Optional[str]:
    """Return enriched alert lines for known play label, or None."""
    play = PLAYS.get(label)
    if not play:
        return None
    price = _last_btc_price()
    if not price or price <= 0:
        return None

    tp1 = price * (1 + play["tp1_pct"] / 100)
    tp2 = price * (1 + play["tp2_pct"] / 100)
    stop = price * (1 + play["stop_pct"] / 100)
    risk = abs(play["stop_pct"])
    rr1 = abs(play["tp1_pct"]) / risk if risk else 0
    rr2 = abs(play["tp2_pct"]) / risk if risk else 0

    exit_at = datetime.now(timezone.utc) + timedelta(hours=play["exit_after_h"])

    lines = [
        "",
        play["title"],
        "",
        "ЭДЖ:",
        play["edge"],
        "",
        "💰 ПЛАН ВХОДА",
        f"  Направление: {play['dir']}",
        f"  Entry:  ~${price:,.0f}",
        f"  Stop:   ${stop:,.0f}   ({play['stop_pct']:+.2f}%)",
        f"  TP1:    ${tp1:,.0f}   ({play['tp1_pct']:+.2f}%, R:R 1:{rr1:.1f})",
        f"  TP2:    ${tp2:,.0f}   ({play['tp2_pct']:+.2f}%, R:R 1:{rr2:.1f})",
        f"  Exit by time: {exit_at.strftime('%Y-%m-%d %H:%M UTC')} ({play['exit_after_h']}ч)",
    ]
    if play.get("note"):
        lines.append(f"  ⚠ {play['note']}")
    return "\n".join(lines)
