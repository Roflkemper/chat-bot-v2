# market_forward_analysis — Regime-conditional Forecast Pipeline

Per-regime calibration models, OOS-validated delivery matrix, runtime auto-switching, virtual paper trading and brief generation.

## Pipeline overview

```
bar (5m features)
   │
   ▼
RegimeForecastSwitcher.forecast(bar, regime, conf, stability)
   │   ├─ hysteresis (12-bar/0.65-conf gate)
   │   ├─ MARKUP-1d gating (regime_stability > 0.70)
   │   └─ route to {markup, markdown, range}.load_best_weights()
   ▼
{1h: ForecastResult, 4h: ForecastResult, 1d: ForecastResult}
   │
   ├─► VirtualTrader.evaluate_and_open() → positions_log.jsonl
   │
   ├─► live_monitor.record_prediction() → live_brier_log.jsonl
   │
   └─► brief_generator.generate_brief(...)
          ▼
       delivery.send_brief() → Telegram (existing infra)
```

## Validated CV delivery matrix (5 windows × 3 regimes × 3 horizons)

|          | 1h          | 4h          | 1d                    |
|----------|-------------|-------------|-----------------------|
| MARKUP   | qualitative | numeric     | numeric (gated)       |
| MARKDOWN | numeric ✓   | numeric     | qualitative           |
| RANGE    | numeric     | numeric     | numeric               |

`numeric (gated)` falls back to qualitative when `regime_stability ≤ 0.70` (matches the 2026-01-05 → 02-25 contamination zone).

## Modules

| Module | Purpose |
|--------|---------|
| `calibration.py` | `_compute_signals_batch(features, horizon)` — 5-signal ensemble (A/B/C/D/E) with Tier-1 wired + Tier-2 features |
| `regime_models/{markup,markdown,range}.py` | Per-regime weight optimization (seed=42, 400 trials) |
| `regime_switcher.py` | Hysteresis routing per validated matrix |
| `virtual_trader.py` | Deterministic paper trading: 1h-signal entry, 1.2×ATR stop, 1.5R/3R TPs, 4h time exit |
| `brief_generator.py` | Russian markdown brief renderer (8 sections) |
| `live_monitor.py` | Rolling Brier per (regime, horizon), alerts when live > 0.28 |
| `delivery.py` | Send triggers: morning 08:00 UTC, regime change, prob shift > 0.15 |

## Storage

- `data/forecast_features/full_features_1y.parquet` — 105k rows × 84 cols, 5m bars
- `data/forecast_features/regime_splits/regime_{markup,markdown,range}.parquet`
- `data/calibration/regime_{markup,markdown,range}_*.json` — calibration reports
- `data/calibration/oos_validation_*.json` — full CV matrix
- `data/calibration/live_brier_log.jsonl` — append-only live predictions + resolutions
- `data/virtual_trader/positions_log.jsonl` — append-only paper trade log

## Tests

`core/tests/test_regime_models.py` — 20 tests (per-regime models, base weights, calibration)
`core/tests/test_regime_switcher.py` — 14 tests (routing, hysteresis, gating)
`core/tests/test_brief_pipeline.py` — 21 tests (brief render, virtual trader lifecycle, live monitor, delivery)

**55 tests total. All green.**
