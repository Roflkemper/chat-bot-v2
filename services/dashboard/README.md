# services/dashboard

Dashboard state builder + localhost HTTP server for Grid Orchestrator Dashboard.

## Components

| File | Purpose |
|------|---------|
| `state_builder.py` | Builds `docs/STATE/dashboard_state.json` from live data sources (snapshots, signals, events…). Sections: market, portfolio, queue, positions, competition, phase_1, alerts |
| `loop.py` | asyncio loop — calls `build_and_save_state()` every 60 seconds (TZ-DASHBOARD-LIVE-FRESHNESS) |
| `http_server.py` | asyncio HTTP server on `http://127.0.0.1:8765/` — serves dashboard HTML + `/state.json` |

## Auto-start

Both `dashboard_state_loop` and `dashboard_http_server` are launched as asyncio tasks inside `app_runner.py`. No manual start needed.

## Open dashboard

```
python tools/dashboard_open.py
```

Or navigate directly to `http://127.0.0.1:8765/`

## HTTP endpoints

| Path | Response |
|------|---------|
| `GET /` | `docs/dashboard.html` |
| `GET /state.json` | `docs/STATE/dashboard_state.json` (refreshed every 60 sec) |
| `GET /dashboard.js` | `docs/dashboard.js` |
| `GET /dashboard.css` | `docs/dashboard.css` |
| `GET /state_inline.js` | `docs/state_inline.js` |

Port fallback: 8765 → 8766 → 8767. Bound host is always `127.0.0.1` (localhost only).

## State sections

| Key | Source |
|-----|--------|
| `market` | Last signal `market_context` + clock-based ICT session |
| `portfolio` | `ginarea_live/snapshots.csv` filtered by `ginarea_tracker/bot_aliases.json`. **Bot IDs are normalized** (legacy `.0` suffix stripped) before dedup — see TZ-DASHBOARD-POSITION-DEDUP, `_normalize_bot_id` in `state_builder.py` |
| `queue` | `docs/STATE/QUEUE.md` — rows with `⬜ OPEN` status |
| `positions` | Aggregated longs/shorts from snapshots |
| `competition` | `state/competition_state.json` |
| `phase_1_paper_journal` | `state/advise_signals.jsonl` |
| `engine_status` | `state/engine_status.json` |
| `alerts_24h` | `state/decision_log/events.jsonl` (WARNING/CRITICAL last 24h) |
| `regime` | `data/regime/switcher_state.json` (RegimeForecastSwitcher hysteresis state) |
| `forecast` | `data/forecast_features/latest_forecast.json` (live) OR CV-matrix fallback |
| `virtual_trader` | `data/virtual_trader/positions_log.jsonl` (7d aggregation) |
| `freshness` | File-mtime ages for snapshots / forecast / regime; 3-tier level (ok/yellow/red) |

## Data flow (TZ-DASHBOARD-LIVE-FRESHNESS — D77 closure)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ EXCHANGE                                                                │
│   GinArea platform (which talks to Binance USDT-M / Coin-M)             │
└─────────────────────────────────────────────────────────────────────────┘
                              │ GinArea API (services/ginarea_api/)
                              │ credentials via env vars (GINAREA_EMAIL etc)
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ TRACKER                                                                 │
│   ginarea_tracker/tracker.py — long-running process                     │
│   Polls every 1 min → appends to ginarea_live/snapshots.csv             │
│   Bot lifecycle events → ginarea_live/events.csv                        │
└─────────────────────────────────────────────────────────────────────────┘
                              │ append-only files
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ DASHBOARD STATE BUILDER                                                 │
│   services/dashboard/state_builder.py                                   │
│   loop.py runs build_and_save_state() every 60 sec                      │
│   Reads snapshots.csv (latest per bot_id) + 9 other sources             │
│   Writes docs/STATE/dashboard_state.json                                │
└─────────────────────────────────────────────────────────────────────────┘
                              │ JSON refresh
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ HTTP SERVER + BROWSER                                                   │
│   http_server.py serves /state.json on localhost:8765                   │
│   dashboard.js polls every 60 sec, re-renders                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why no direct exchange API?

The dashboard does NOT call Binance / BitMEX / GinArea API directly — it reads
from `ginarea_live/snapshots.csv` which the tracker keeps fresh (~1 min lag).
This is a deliberate **v1** design choice (D77 decision, 2026-05-05):

- **Pros:** zero auth surface in the dashboard process; tracker failure is
  visible as snapshot staleness; downstream readers (dashboard, briefs,
  decision log) all see the same data; no duplicate API rate-limit budget.
- **Cons:** ~1 min lag vs hypothetical live API; can't show order-book depth
  or futures-specific fields not in the snapshot schema.

The freshness layer (`freshness` key in state.json) surfaces the lag explicitly
so the operator can spot tracker downtime: `level: red` when snapshots are
>120 min old, indicating the tracker process died.

A direct exchange API integration (separate TZ if scoped) is **not necessary
for v1** — the snapshots.csv pipeline meets dashboard freshness requirements.
