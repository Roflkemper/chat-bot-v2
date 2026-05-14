"""Зарегистрировать запущенный сегодня LONG-конфиг T2-mild.

Запуск (один раз): python scripts/track_live_long.py [bot_id]
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ginarea_api.live_config_tracker import LiveConfig, add_config


if __name__ == "__main__":
    bot_id = sys.argv[1] if len(sys.argv) > 1 else "T2-mild-pending-id"
    cfg = LiveConfig(
        bot_id=bot_id,
        name="T2-mild (LONG лидер пачки #22)",
        side="long",
        gs=0.04, thresh=1.5, td=0.85, mult=1.2,
        tp="off", max_size="100/300",
        started_at=datetime.now(timezone.utc).isoformat(),
        expected_profit_3mo_usd=22_387.0,
        expected_vol_3mo_musd=4.50,
        expected_peak_usd=70_000.0,
        note="Запущен 2026-05-13 после sub-grid пачки #22. backtest gs=0.04 t=1.5 TD=0.85 mult=1.2 TP=off max=300 → +22 387$ / 3мес.",
    )
    add_config(cfg)
    print(f"Registered live LONG config bot_id={bot_id}")
    print(f"Expected: +$22 387 / 3 мес, vol 4.5M$, peak ~70k$")
