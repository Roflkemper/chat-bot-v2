# Setup Detector + Tracker + Backtest — Architecture

**TZ:** TZ-SETUP-DETECTOR-LIVE, TZ-SETUP-TRACKER-OUTCOMES, TZ-SETUP-HISTORICAL-BACKTEST  
**Generated:** 2026-04-30

---

## Inventory findings

| Item | Finding |
|---|---|
| `services/setup_detector/` | Did NOT exist — created from scratch |
| `services/setup_backtest/` | Did NOT exist — created from scratch |
| Duplicate check | No `SetupDetector`, `SetupBacktest`, `class Setup` anywhere in project |
| MarketContext, RSI | Already defined in `services/advise_v2/{schemas,paper_journal}.py` — reused |
| Session intelligence | `services/advise_v2/session_intelligence.py:compute_session_context()` — reused |
| Regime adapter | `services/advise_v2/regime_adapter.py` — used as-is |
| Frozen data | `frozen/ETHUSDT_1m.parquet`, `frozen/XRPUSDT_1m.parquet` (~527k bars, 1 year) |
| BTCUSDT frozen | `backtests/frozen/BTCUSDT_1m_2y.csv` (CSV, ~521k bars) — supported via auto-detect |
| app_runner baseline | 9 real tasks + stop_event; adding tasks 10 (detector) + 11 (tracker) |
| Baseline failures | 5 pre-existing in `test_protection_alerts.py` — not touched |

---

## Architecture layers

```
 ┌────────────────────────────────────────────────────────────────┐
 │  services/setup_detector/                                      │
 │                                                                │
 │  models.py          Setup, SetupType, SetupStatus, SetupBasis │
 │  indicators.py      RSI, volume_ratio, swing highs/lows, PDH/L│
 │  scorer.py          compute_strength, compute_confidence       │
 │  setup_types.py     DetectionContext + detector functions      │
 │  telegram_card.py   format_telegram_card (trade/grid/def)     │
 │  storage.py         SetupStorage (JSONL + active JSON)         │
 │  loop.py            setup_detector_loop (5 min async)          │
 │  tracker.py  (TZ-2) setup_tracker_loop (60s), status checks   │
 │  outcomes.py (TZ-2) SetupOutcome, OutcomesWriter               │
 │  stats_aggregator.py(TZ-2) compute_setup_stats                 │
 └────────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────────┐
 │  services/setup_backtest/                          (TZ-3)     │
 │                                                                │
 │  historical_context.py  HistoricalContextBuilder              │
 │  replay_engine.py       SetupBacktestReplay                    │
 │  outcome_simulator.py   HistoricalOutcomeSimulator             │
 └────────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────────┐
 │  tools/run_setup_backtest.py   CLI                             │
 └────────────────────────────────────────────────────────────────┘
```

---

## State files

| File | Purpose |
|---|---|
| `state/setups.jsonl` | Append-only — all detected setups ever |
| `state/setups_active.json` | Current active (DETECTED/ENTRY_HIT) setups |
| `state/setup_outcomes.jsonl` | All status transitions with outcome data |
| `data/historical_setups_*.parquet` | Output of backtest CLI runs |

---

## Detector registry (active v1)

| SetupType | Conditions | Regime alignment |
|---|---|---|
| LONG_DUMP_REVERSAL | -2% 4h + RSI<35 + reversal wicks + volume + PDL | Anti: trend_down |
| SHORT_RALLY_FADE | +2% 4h + RSI>65 + rejection wicks + volume + PDH | Anti: trend_up |
| DEFENSIVE_MARGIN_LOW | free_margin_pct < 25% | Always |
| GRID_BOOSTER_ACTIVATE | RSI<35 on 1h in range regime + liq below | Best: range |

Min strength threshold: 6 (no weak signals).

---

## Frozen data compatibility

| Symbol | File | Format |
|---|---|---|
| ETHUSDT | `frozen/ETHUSDT_1m.parquet` | Parquet, index=ts |
| XRPUSDT | `frozen/XRPUSDT_1m.parquet` | Parquet, index=ts |
| BTCUSDT | `backtests/frozen/BTCUSDT_1m_2y.csv` | CSV, col=ts |

`HistoricalContextBuilder` auto-detects format by extension.

---

## Operator action post-deploy

```bash
# Restart app_runner to activate tasks 10 (detector) + 11 (tracker)
python -m bot7 restart app_runner

# Check detection after 5-15 min
cat state/setups.jsonl | python -c "import sys,json;[print(json.dumps(json.loads(l),indent=2)) for l in sys.stdin]"

# Full year BTC backtest (run on operator machine, ~30-60 min)
python tools/run_setup_backtest.py \
  --start 2025-05-01 --end 2026-04-30 \
  --frozen-path backtests/frozen/BTCUSDT_1m_2y.csv \
  --output data/historical_setups_y1_2026-04-30.parquet

# Check /advise stats after 1 week of live data
# /advise stats in Telegram
```
