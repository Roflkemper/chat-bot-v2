# services/ict_levels

Pure-Python ICT session-levels detector. Builds a per-1m-bar parquet that is
joinable to OHLCV by DatetimeIndex (UTC).

## Why this exists

The operator's main edge is **liquidity grabs at unmitigated session levels**.
Old un-touched Asia/London/NY highs and lows act as magnets for institutional
flow.  Detecting whether a setup is approaching an *unmitigated* level (vs a
fresh or already-mitigated one) is the key filter that separates low-probability
entries from high-probability ones.

`unmitigated_session_highs_history` and `unmitigated_session_lows_history`
capture **all** historical session levels in the rolling 7-day window that price
has *not* yet touched.  Setup-detector can join on timestamp and read the
nearest such level to decide whether to generate a card.

## Columns produced

| Column | Type | Description |
|---|---|---|
| `session_active` | str | asia/london/ny_am/ny_lunch/ny_pm/dead |
| `time_in_session_min` | int | minutes since session open (0 = dead zone) |
| `{sess}_open/high/low/close` | float | most recent completed session OHLC (ffilled) |
| `{sess}_midpoint` | float | (H+L)/2 of most recent session |
| `{sess}_range` | float | H-L of most recent session |
| `{sess}_range_avg5` | float | rolling 5-session mean range |
| `{sess}_high_mitigated_ts` | datetime | when most recent session's high was first touched (NaT = not yet) |
| `{sess}_low_mitigated_ts` | datetime | same for low |
| `d_open` | float | current UTC-day open |
| `pdh/pdl/pdc` | float | previous day high/low/close (UTC) |
| `pwh/pwl/pwc` | float | previous week high/low/close |
| `pmh/pml` | float | previous month high/low |
| `unmitigated_session_highs_history` | JSON str | all unmitigated highs in rolling 7d window |
| `unmitigated_session_lows_history` | JSON str | all unmitigated lows in rolling 7d window |
| `nearest_unmitigated_high_above` | float | nearest unmitigated high ABOVE close (7d) |
| `nearest_unmitigated_high_above_age_h` | float | age of that level in hours |
| `nearest_unmitigated_low_below` | float | nearest unmitigated low BELOW close (7d) |
| `nearest_unmitigated_low_below_age_h` | float | age of that level in hours |
| `unmitigated_count_7d` | int | total unmitigated highs+lows in 7d window |
| `dist_to_pdh_pct` | float | (close-pdh)/pdh*100 |
| `dist_to_pdl_pct` | float | (close-pdl)/pdl*100 |
| `dist_to_pwh/pwl/d_open_pct` | float | same pattern |
| `dist_to_asia_high/low_pct` | float | distance to current Asia session H/L |
| `dist_to_kz_mid_pct` | float | distance to active killzone midpoint (NaN = dead) |
| `dist_to_nearest_unmitigated_high/low_pct` | float | distance to nearest unmitigated level |

## CLI usage

```bash
python -m services.ict_levels.runner \
    --input backtests/frozen/BTCUSDT_1m_2y.csv \
    --output data/ict_levels/BTCUSDT_ict_levels_1m.parquet \
    --start 2025-04-25 \
    --end 2026-04-30
```

## Consuming in setup_detector

```python
import pandas as pd

# Load once at startup
ict = pd.read_parquet("data/ict_levels/BTCUSDT_ict_levels_1m.parquet")

# At detection time, join on the current bar's timestamp
row = ict.loc[current_ts]

# Check if any unmitigated high is within 0.3% above
if row["dist_to_nearest_unmitigated_high_pct"] < 0.3:
    # price approaching a liquidity magnet — high-probability setup
    ...

# Parse full 7d history
import json
highs = json.loads(row["unmitigated_session_highs_history"])
# [{"session": "asia", "session_close_ts": 1746057600000, "level": 77820.5, "age_hours": 42.5}, ...]
```
