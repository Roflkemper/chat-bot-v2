"""Open paper trade в ответ на live cascade event.

Использует backtest-validated edge:
- long-cascade ≥5 BTC за 5 мин → BUY с TP +1.14% / SL -0.5% / hold 12h (73% accuracy)

Этот модуль вызывается из cascade_alert loop. Открывает paper trade напрямую
через journal.append_event (минуя обычный setup_detector pipeline, потому что
наш сигнал — каскадный, не setup-based).

Через 1-2 месяца forward данных можно будет валидировать что edge живой.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import journal

logger = logging.getLogger(__name__)

PAPER_NOTIONAL_USD = 10_000.0
HOLD_HOURS = 12  # из backtest — оптимальное окно для cascade edge

# Backtest-калиброванные параметры из POST_LIQUIDATION_CASCADE_2026-05-07
CASCADE_PARAMS = {
    ("long", 5.0): {
        "side": "long",  # buy после long-cascade (mean-reversion bounce)
        "tp_pct": 1.14,
        "sl_pct": 0.50,
        "hold_h": 12,
        "expected_pct_up": 73,
    },
    ("long", 2.0): {
        "side": "long",
        "tp_pct": 0.68,
        "sl_pct": 0.40,
        "hold_h": 12,
        "expected_pct_up": 63,
    },
    ("short", 5.0): {
        # short-cascade продолжение тренда вверх (61% pct_up за 24h)
        # Но edge маленький, NOT to take aggressive trades — skip
        "side": None,
        "tp_pct": 0,
        "sl_pct": 0,
        "hold_h": 0,
        "expected_pct_up": 61,
    },
    ("short", 2.0): {"side": None, "tp_pct": 0, "sl_pct": 0, "hold_h": 0, "expected_pct_up": 61},
}


def open_cascade_trade(side: str, threshold: float, qty_btc: float, current_price: float) -> dict | None:
    """Открыть paper trade на cascade event. Returns OPEN record or None.

    Если для (side, threshold) edge не определён или цена 0 — возвращаем None.
    """
    params = CASCADE_PARAMS.get((side, threshold))
    if params is None:
        return None
    if params["side"] is None:
        return None  # short cascade пропускаем (edge маленький)
    if current_price <= 0:
        return None

    trade_side = params["side"]
    tp_pct = params["tp_pct"]
    sl_pct = params["sl_pct"]
    hold_h = params["hold_h"]

    entry = current_price
    if trade_side == "long":
        tp_price = entry * (1 + tp_pct / 100)
        sl_price = entry * (1 - sl_pct / 100)
    else:
        tp_price = entry * (1 - tp_pct / 100)
        sl_price = entry * (1 + sl_pct / 100)

    size_btc = round(PAPER_NOTIONAL_USD / entry, 6)
    now = datetime.now(timezone.utc)
    trade_id = f"pt-cascade-{now.strftime('%Y-%m-%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    record = {
        "ts": now.isoformat(),
        "trade_id": trade_id,
        "action": "OPEN",
        "side": trade_side,
        "setup_type": f"cascade_{side}_{threshold:.0f}btc",
        "setup_id": trade_id,
        "entry": round(entry, 2),
        "size_usd": PAPER_NOTIONAL_USD,
        "size_btc": size_btc,
        "sl": round(sl_price, 2),
        "tp1": round(tp_price, 2),
        "tp2": None,
        "rr_planned": round(tp_pct / sl_pct, 2),
        "regime_at_entry": "cascade",
        "session_at_entry": "n/a",
        "confidence_pct": float(params["expected_pct_up"]),
        "strength": 8,
        "expires_at": (now + timedelta(hours=hold_h)).isoformat(),
        "time_stop_at": (now + timedelta(hours=hold_h)).isoformat(),
        "reason": (
            f"Live cascade {side}-side {qty_btc:.2f} BTC за 5 мин. "
            f"Backtest n=103/297 → +{tp_pct}% target в {hold_h}h ({params['expected_pct_up']}% accuracy)"
        ),
        "_source": "cascade_alert",
    }
    journal.append_event(record)
    logger.info(
        "paper_trader.cascade_opened trade_id=%s side=%s threshold=%.1f entry=%.2f tp=%.2f sl=%.2f",
        trade_id, side, threshold, entry, tp_price, sl_price,
    )
    return record
