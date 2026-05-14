# Managed Grid Sim Architecture

`services/managed_grid_sim/` — отдельный framework поверх `engine_v2`.

## Core decisions

- `engine_v2` не модифицируется
- `GinareaBot` используется как black box через `BotConfig/GinareaBot/OHLCBar`
- interventions применяются management-layer поверх bar-by-bar run
- sweep CLI вынесен в `tools/sweep_runner.py`

## Pre-engine-fix disclaimer

Framework results pre-engine-fix нужно трактовать как **relative**:

- сравнение конфигураций между собой полезно
- абсолютный PnL / realized до закрытия `TZ-ENGINE-BUG-FIX-PHASE-1` может быть искажён
- после engine fix sweeps нужно прогнать заново для absolute correctness
