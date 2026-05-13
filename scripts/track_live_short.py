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
        "name": "SH-T1 TP=12 stops=0.012/0.035 (пачка #23 — wide)",
        "gs": 0.02, "thresh": 0.7, "td": 0.21, "mult": 1.3,
        "tp": "12/12", "max_size": "0.001/0.003",
        "expected_profit_3mo_usd": 2_315.0,
        "expected_vol_3mo_musd": 13.52,
        "expected_peak_usd": 120_000.0,
        "note": (
            "Пачка #23: T1 чувствителен к стопам. min=0.012 / max=0.035 — "
            "+10.6% vs узкого 0.005/0.015. Backtest +2 314.89$ (id 4839809357)."
        ),
    },
    "t2": {
        "name": "SH-T2 TP=175 stops=0.006/0.020 (пачка #23 — tight)",
        "gs": 0.03, "thresh": 1.5, "td": 0.35, "mult": 1.3,
        "tp": "175/175", "max_size": "0.002/0.004",
        "expected_profit_3mo_usd": 4_699.0,
        "expected_vol_3mo_musd": 6.00,
        "expected_peak_usd": 80_000.0,
        "note": (
            "Пачка #23: T2 нечувствителен к профиту, узкий min=0.006/max=0.020 "
            "режет пик USD на 9% без потерь. Backtest +4 698.85$ (id 4794987162)."
        ),
    },
    "t3": {
        "name": "SH-T3 TP=270 stops=0.012/0.045 (пачка #23 — tight)",
        "gs": 0.05, "thresh": 2.0, "td": 0.6, "mult": 1.2,
        "tp": "270/270", "max_size": "0.002/0.005",
        "expected_profit_3mo_usd": 3_247.0,
        "expected_vol_3mo_musd": 2.18,
        "expected_peak_usd": 48_000.0,
        "note": (
            "Пачка #23: T3 нечувствителен, узкий min=0.012/max=0.045 даёт тот же "
            "профит при пике −15% (48k vs 56k). Backtest +3 247.35$ (id 6064034130)."
        ),
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
