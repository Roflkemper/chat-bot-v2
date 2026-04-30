# Dashboard Inventory — 2026-04-30

## Existing dashboard file
- `docs/dashboard.html` — 323 lines, dark theme, reads `state_inline.js` OR `docs/STATE/state_latest.json`
  - Sections: Aggregate Exposure, Bots table, AGM 24h, DD Recovery, Anomalies, Roadmap, Queue
  - Will be replaced with new layout per TZ (reads `dashboard_state.json`)

## State file sources (available)

| File | Lines/Size | Content |
|---|---|---|
| `ginarea_live/snapshots.csv` | live | Per-bot position, profit, status |
| `docs/STATE/state_latest.json` | json | Exposure, bots, AGM, DD, anomalies, roadmap |
| `state/advise_signals.jsonl` | 6 | Phase 1 paper journal signals |
| `state/advise_null_signals.jsonl` | 79 | Null signal reasons |
| `state/decision_log/events.jsonl` | 147 | Decision log events (WARNING/CRITICAL for alerts) |
| `state/regime_state.json` | json | Current regime (RANGE, bars=8) |
| `state/grid_portfolio.json` | json | Orchestrator categories (btc_short, btc_long, etc.) |
| `state/bot_manager_state.json` | json | ct_long/ct_short phase/action |

## Missing sources (graceful fallback)

| File | Status | Notes |
|---|---|---|
| `state/liq_clusters/active.json` | MISSING | After TZ-LIQ-SET-MANUAL |
| `state/portfolio/cached_exposure.json` | MISSING | After TZ-PORTFOLIO-SYNC |
| `state/competition_state.json` | MISSING | Tracker DEAD, no live source |
| `state/engine_status.json` | MISSING | Hardcode from TZ-ENGINE-BUG-INVESTIGATION |

## competition_state.json: not available
- ginarea_tracker is DEAD (missing credentials)
- `state_builder.py` reads `state/competition_state.json` if present, else returns null fields
- Operator can create `state/competition_state.json` manually to populate competition section

## Phase 1 paper journal
- First signal ts: `2026-04-30T08:45:05Z` → day_n = 1 of 14
- 6 advise signals total, dominant setup: P-3 (4/6)
- Regimes: trend_down (4), consolidation (2)
- Null signals: 79 (mostly pre-Phase-1 from 2026-04-29)

## Engine status (hardcoded defaults)
- calibration_done_at: 2026-04-30T10:36:00Z
- bugs_detected: 3 (from TZ-ENGINE-BUG-INVESTIGATION)
- bugs_fixed: 0

## Boli (4 pain points, hardcoded)
1. Стресс-мониторинг — manual
2. Detection ложных выносов — manual
3. Manual sizing rebalance — manual
4. Drift к катастрофе — in_progress

## GAPS
- G-1: No live competition data source (tracker DEAD)
- G-2: liq_clusters/active.json not populated yet
- G-3: engine_status.json not auto-updated by any process
