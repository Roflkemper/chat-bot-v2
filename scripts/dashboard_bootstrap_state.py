"""One-shot bootstrap: produce regime/forecast state files for dashboard.

Picks the most recent bar across all 3 regime parquets (by timestamp),
runs RegimeForecastSwitcher.forecast(), and writes:

  data/regime/switcher_state.json
  data/forecast_features/latest_forecast.json

These files are then read by services/dashboard/state_builder.py.

Live wiring (per-bar emission inside an orchestrator loop) is a Day 2+ task;
this script keeps the dashboard meaningful in the meantime.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from services.market_forward_analysis.regime_switcher import (
    RegimeForecastSwitcher, _CV_BRIER, _DELIVERY_MATRIX, _STABILITY_THRESHOLD,
)


REGIME_PARQUETS = {
    "MARKUP":   "data/forecast_features/regime_splits/regime_markup.parquet",
    "MARKDOWN": "data/forecast_features/regime_splits/regime_markdown.parquet",
    "RANGE":    "data/forecast_features/regime_splits/regime_range.parquet",
}


def _pick_latest_bar() -> tuple[str, pd.DataFrame, pd.Timestamp]:
    """Return (regime_label, single-row DF, bar_timestamp) for the most recent bar."""
    candidates = []
    for regime, path in REGIME_PARQUETS.items():
        p = Path(path)
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if df.empty:
            continue
        last_ts = df.index[-1]
        candidates.append((last_ts, regime, df.iloc[[-1]]))
    if not candidates:
        raise RuntimeError("No regime parquets found.")
    candidates.sort(key=lambda x: x[0], reverse=True)
    last_ts, regime, bar = candidates[0]
    return regime, bar, last_ts


def main() -> int:
    regime, bar, bar_ts = _pick_latest_bar()
    bar_iso = bar_ts.isoformat()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    confidence = 0.85
    stability = 0.80

    switcher = RegimeForecastSwitcher()
    forecasts = switcher.forecast(
        bar, current_regime=regime,
        regime_confidence=confidence, regime_stability=stability,
    )

    # ── switcher_state.json ──
    regime_path = Path("data/regime/switcher_state.json")
    regime_path.parent.mkdir(parents=True, exist_ok=True)
    regime_payload = {
        "regime": switcher.state.last_regime,
        "regime_confidence": confidence,
        "regime_stability": stability,
        "bars_in_current_regime": switcher.state.bars_in_current_regime,
        "candidate_regime": switcher.state.candidate_regime,
        "candidate_bars": switcher.state.candidate_bars,
        "bar_time": bar_iso,
        "updated_at": now_iso,
        "source": "scripts/dashboard_bootstrap_state.py",
    }
    regime_path.write_text(json.dumps(regime_payload, indent=2), encoding="utf-8")
    print(f"wrote {regime_path}: regime={switcher.state.last_regime}")

    # ── latest_forecast.json ──
    forecast_path = Path("data/forecast_features/latest_forecast.json")
    forecast_path.parent.mkdir(parents=True, exist_ok=True)
    horizons_payload: dict[str, dict] = {}
    for hz in ("1h", "4h", "1d"):
        fr = forecasts[hz]
        cv_brier = _CV_BRIER.get(switcher.state.last_regime, {}).get(hz)
        horizons_payload[hz] = {
            "mode": fr.mode,
            "value": fr.value if fr.mode == "numeric" else fr.value,
            "confidence": fr.confidence,
            "brier": cv_brier,
            "caveat": fr.caveat,
        }
    forecast_payload = {
        "regime": switcher.state.last_regime,
        "regime_confidence": confidence,
        "regime_stability": stability,
        "bar_time": bar_iso,
        "updated_at": now_iso,
        "horizons": horizons_payload,
        "source": "scripts/dashboard_bootstrap_state.py",
    }
    forecast_path.write_text(json.dumps(forecast_payload, indent=2, default=str), encoding="utf-8")
    print(f"wrote {forecast_path}: 3 horizons, regime={switcher.state.last_regime}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
