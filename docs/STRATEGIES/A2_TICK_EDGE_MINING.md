# A2 — tick-data edge mining (BTCUSDT 1s, 90 days)

**Engine:** 1s OHLCV → per-minute features → forward-return analysis
**Period:** last 90 days, 129,600 1m windows
**Folds:** 4 walk-forward
**Edge criteria:** |mean| >= 0.05%, PF >= 1.3, consistent across folds

## Features mined
- **wick_imbalance** — upper-wick volume / lower-wick volume in 1m
- **micro_velocity** — count of close-to-close direction flips in 60s
- **vol_burst** — max 5s rolling volume / median 5s volume
- **close_lean** — close position in [low, high] range, 1s-resolution

## Edge candidates summary

**No edges found** — all features fail at least one of (|mean| >= 0.05%, PF >= 1.3, walk-forward consistency).

Best candidates (sorted by |mean|):

| feature        | bucket   |   horizon_min |   in_sample_mean_% |   in_sample_pf | wf_consistent_folds   | edge_found   |
|:---------------|:---------|--------------:|-------------------:|---------------:|:----------------------|:-------------|
| wick_imbalance | mid      |            30 |            -0.0064 |          0.941 | 0/4                   | False        |
| wick_imbalance | low      |            30 |             0.0051 |          1.033 | 0/4                   | False        |
| vol_burst      | mid      |            30 |            -0.0048 |          0.953 | 0/4                   | False        |
| vol_burst      | low      |            30 |             0.0042 |          1.024 | 0/4                   | False        |
| wick_imbalance | low      |            15 |             0.0041 |          1.035 | 0/4                   | False        |
| wick_imbalance | high     |            15 |            -0.0037 |          0.957 | 0/4                   | False        |
| vol_burst      | high     |            30 |            -0.0036 |          0.955 | 0/4                   | False        |
| close_lean     | mid      |            30 |            -0.0035 |          0.974 | 0/4                   | False        |
| micro_velocity | low      |            30 |            -0.0029 |          0.967 | 0/4                   | False        |
| wick_imbalance | high     |            30 |            -0.0028 |          0.979 | 0/4                   | False        |

## All in-sample buckets

| feature        | bucket   |   horizon_min |   in_sample_mean_% |   in_sample_pf | wf_consistent_folds   | edge_found   |
|:---------------|:---------|--------------:|-------------------:|---------------:|:----------------------|:-------------|
| wick_imbalance | low      |             5 |             0.0023 |          1.014 | 0/4                   | False        |
| wick_imbalance | low      |            15 |             0.0041 |          1.035 | 0/4                   | False        |
| wick_imbalance | low      |            30 |             0.0051 |          1.033 | 0/4                   | False        |
| wick_imbalance | mid      |             5 |            -0.0008 |          0.96  | 0/4                   | False        |
| wick_imbalance | mid      |            15 |            -0.0025 |          0.968 | 0/4                   | False        |
| wick_imbalance | mid      |            30 |            -0.0064 |          0.941 | 0/4                   | False        |
| wick_imbalance | high     |             5 |            -0.0022 |          0.961 | 0/4                   | False        |
| wick_imbalance | high     |            15 |            -0.0037 |          0.957 | 0/4                   | False        |
| wick_imbalance | high     |            30 |            -0.0028 |          0.979 | 0/4                   | False        |
| micro_velocity | low      |             5 |            -0.0007 |          0.945 | 0/4                   | False        |
| micro_velocity | low      |            15 |            -0.0012 |          0.968 | 0/4                   | False        |
| micro_velocity | low      |            30 |            -0.0029 |          0.967 | 0/4                   | False        |
| micro_velocity | mid      |             5 |            -0      |          0.991 | 0/4                   | False        |
| micro_velocity | mid      |            15 |             0.0003 |          1.003 | 0/4                   | False        |
| micro_velocity | mid      |            30 |            -0.0008 |          0.993 | 0/4                   | False        |
| micro_velocity | high     |             5 |             0      |          0.987 | 0/4                   | False        |
| micro_velocity | high     |            15 |            -0.0009 |          0.99  | 0/4                   | False        |
| micro_velocity | high     |            30 |            -0.0005 |          0.992 | 0/4                   | False        |
| vol_burst      | low      |             5 |             0.0008 |          0.999 | 0/4                   | False        |
| vol_burst      | low      |            15 |             0.0016 |          1.011 | 0/4                   | False        |
| vol_burst      | low      |            30 |             0.0042 |          1.024 | 0/4                   | False        |
| vol_burst      | mid      |             5 |            -0.0018 |          0.934 | 0/4                   | False        |
| vol_burst      | mid      |            15 |            -0.0027 |          0.957 | 0/4                   | False        |
| vol_burst      | mid      |            30 |            -0.0048 |          0.953 | 0/4                   | False        |
| vol_burst      | high     |             5 |             0.0004 |          0.994 | 0/4                   | False        |
| vol_burst      | high     |            15 |            -0.0009 |          0.978 | 0/4                   | False        |
| vol_burst      | high     |            30 |            -0.0036 |          0.955 | 0/4                   | False        |
| close_lean     | low      |             5 |             0.0001 |          0.945 | 0/4                   | False        |
| close_lean     | low      |            15 |            -0.0011 |          0.976 | 0/4                   | False        |
| close_lean     | low      |            30 |            -0.0005 |          0.992 | 0/4                   | False        |
| close_lean     | mid      |             5 |             0.0008 |          1.006 | 0/4                   | False        |
| close_lean     | mid      |            15 |            -0.0007 |          0.988 | 0/4                   | False        |
| close_lean     | mid      |            30 |            -0.0035 |          0.974 | 0/4                   | False        |
| close_lean     | high     |             5 |            -0.0016 |          0.978 | 0/4                   | False        |
| close_lean     | high     |            15 |            -0.0003 |          0.999 | 0/4                   | False        |
| close_lean     | high     |            30 |            -0.0003 |          0.995 | 0/4                   | False        |