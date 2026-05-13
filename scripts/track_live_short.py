"""Зарегистрировать SHORT-конфиги когда запустишь их в live.

Запуск:
    python scripts/track_live_short.py t1 <bot_id>     # Tier-1 (TP=12)
    python scripts/track_live_short.py t2 <bot_id>     # Tier-2 (TP=175)
    python scripts/track_live_short.py t3 <bot_id>     # Tier-3 (TP=270)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ginarea_api.live_config_tracker import LiveConfig, add_config


CONFIGS = {
    "t1": {
        "name": "SH-T1 TP=12 (пачка #22 sweet spot)",
        "gs": 0.02, "thresh": 0.7, "td": 0.21, "mult": 1.3,
        "tp": "12/12", "max_size": "0.001/0.003",
        "expected_profit_3mo_usd": 2_267.0,
        "expected_vol_3mo_musd": 13.79,
        "expected_peak_usd": 30_000.0,
        "note": "Запущен после пачки #22. backtest +2 267$ при чистом exit (1 из 2 повторов).",
    },
    "t2": {
        "name": "SH-T2 TP=175 (sweet spot перед cliff)",
        "gs": 0.03, "thresh": 1.5, "td": 0.35, "mult": 1.3,
        "tp": "175/175", "max_size": "0.002/0.004",
        "expected_profit_3mo_usd": 4_752.0,
        "expected_vol_3mo_musd": 6.00,
        "expected_peak_usd": 45_000.0,
        "note": "TP=175 — дисперсия 0.02%, на 1% хуже TP=200, но дальше от cliff (TP=220 обвал).",
    },
    "t3": {
        "name": "SH-T3 TP=270 (Tier-3 лидер)",
        "gs": 0.05, "thresh": 2.0, "td": 0.6, "mult": 1.2,
        "tp": "270/270", "max_size": "0.002/0.005",
        "expected_profit_3mo_usd": 3_248.0,
        "expected_vol_3mo_musd": 2.17,
        "expected_peak_usd": 30_000.0,
        "note": "Дисперсия 0.06% (3247/3249) — самый стабильный из всех T3-точек.",
    },
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CONFIGS:
        print("Usage: python scripts/track_live_short.py <t1|t2|t3> [bot_id]")
        sys.exit(1)
    tier = sys.argv[1]
    bot_id = sys.argv[2] if len(sys.argv) > 2 else f"SH-{tier.upper()}-pending"

    base = CONFIGS[tier]
    cfg = LiveConfig(
        bot_id=bot_id,
        name=base["name"],
        side="short",
        gs=base["gs"], thresh=base["thresh"], td=base["td"], mult=base["mult"],
        tp=base["tp"], max_size=base["max_size"],
        started_at=datetime.now(timezone.utc).isoformat(),
        expected_profit_3mo_usd=base["expected_profit_3mo_usd"],
        expected_vol_3mo_musd=base["expected_vol_3mo_musd"],
        expected_peak_usd=base["expected_peak_usd"],
        note=base["note"],
    )
    add_config(cfg)
    print(f"Registered SHORT-{tier.upper()} config bot_id={bot_id}")
    print(f"Expected: +${base['expected_profit_3mo_usd']:,.0f}/3мес, vol {base['expected_vol_3mo_musd']:.2f}M$, peak ~{base['expected_peak_usd']/1000:.0f}k$")
