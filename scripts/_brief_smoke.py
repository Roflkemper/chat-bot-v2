"""End-to-end brief generation smoke test."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone
import pandas as pd

from services.market_forward_analysis.regime_switcher import RegimeForecastSwitcher
from services.market_forward_analysis.brief_generator import (
    generate_brief, Level, DayPotential, VirtualTraderSnapshot,
)

df = pd.read_parquet("data/forecast_features/regime_splits/regime_markdown.parquet")
bar = df.iloc[[-1]]
last_close = float(bar["close"].iloc[0])
last_24h_close = float(df["close"].iloc[-min(288, len(df))])
pct_24h = (last_close - last_24h_close) / last_24h_close * 100

sw = RegimeForecastSwitcher()
forecasts = sw.forecast(bar, "MARKDOWN", regime_confidence=0.85, regime_stability=0.80)

supply_label = "зона предложения (хай NY-сессии)"
demand_label = "зона спроса (свеча капитуляции)"
mb_action_long  = "рассмотри частичный TP 30-40% на " + f"{last_close*1.025:.0f}"
mb_action_short = "сдвинь стоп выше " + f"{last_close*1.025:.0f}"
mb_action_flat  = "false breakout в MARKDOWN частый - шорт со стопом " + f"{last_close*1.027:.0f}"

levels = [
    Level(price=round(last_close * 1.02, 0), label=supply_label, kind="supply",
          scenarios=[
              {"name": "А", "trigger": "пробой полным телом NY-сессии",
               "target": f"{last_close*1.04:.0f}-{last_close*1.045:.0f} (следующая supply)",
               "rr": "2.3",
               "action_long":  mb_action_long,
               "action_short": mb_action_short,
               "action_flat":  mb_action_flat},
              {"name": "B", "trigger": "ретест без удержания (фейк)",
               "target": f"откат к {last_close*0.98:.0f}",
               "action_long": f"трейл-стоп под {last_close*1.005:.0f} или выход",
               "action_flat": f"шорт со стопом {last_close*1.022:.0f}"},
          ]),
    Level(price=round(last_close * 0.96, 0), label=demand_label, kind="demand",
          scenarios=[
              {"name": "А", "trigger": "волатильный обвал к зоне",
               "action_short": f"TP 30-40% на {last_close*0.962:.0f}, готовиться к сквизу",
               "action_flat":  f"лонг на бычьей реакции 4ч, стоп {last_close*0.955:.0f}"},
          ]),
]

dp = DayPotential(
    base_pct=60, base_range=(last_close * 0.962, last_close * 1.022),
    bear_pct=25, bear_path=f"{last_close*0.96:.0f} -> {last_close*0.93:.0f} при сломе уровня",
    bull_pct=15, bull_path=f"{last_close*1.02:.0f} пробит -> {last_close*1.04:.0f}+",
)

vt_snap = VirtualTraderSnapshot(
    today_setup={
        "direction": "short", "entry": last_close * 1.02,
        "sl": last_close * 1.027, "tp1": last_close * 0.98, "tp2": last_close * 0.96,
        "rr1": 2.9, "rr2": 5.0, "ttl": "до 18:00 UTC", "reason": supply_label,
    },
    open_positions=[],
    stats_7d={"signals": 4, "wins": 2, "losses": 1, "open": 1, "avg_rr": 1.6},
)

watches = [
    {"key": "funding_flip"},
    {"key": "volume_spike"},
    {"key": "regime_change", "args": {"from_r": "MARKDOWN", "to_r": "RANGE"}},
]

brief = generate_brief(
    timestamp=datetime.now(timezone.utc),
    price=last_close, pct_24h=pct_24h,
    regime="MARKDOWN", regime_confidence=0.85, stable_bars=14, switch_pending=False,
    forecasts=forecasts, levels=levels,
    day_potential=dp, virtual_trader=vt_snap, watches=watches,
)

sys.stdout.buffer.write(brief.encode("utf-8", "replace"))
sys.stdout.buffer.write(b"\n")
