# Grid_coordinator night research — 2026-05-10

**Lookback:** 90 days | **Operator extrema tested:** 12 | **Score thresholds:** 3 / 4 | **Horizons:** 60/120/240 min

**PnL setup:** TP +1%, SL -0.5%, max hold 240m, fee 0.165% round-trip

## 1. 15m TF

- Signals score>=3: **417**
- Signals score>=4: **62**

**9/12 extrema caught (score>=3, ±4h)**

| Date UTC | Type | Caught | Best score | N near |
|---|---|---|---|---|
| 2026-03-17 01:35 | high | [OK] | 4 | 2 |
| 2026-03-26 00:49 | high | [MISS] | - | 0 |
| 2026-04-12 22:30 | low | [MISS] | - | 0 |
| 2026-04-14 14:32 | high | [OK] | 3 | 3 |
| 2026-04-17 16:23 | high | [OK] | 4 | 8 |
| 2026-04-20 00:00 | low | [OK] | 5 | 14 |
| 2026-04-21 19:46 | low | [OK] | 3 | 1 |
| 2026-04-22 16:05 | high | [OK] | 5 | 11 |
| 2026-04-27 01:01 | high | [OK] | 4 | 2 |
| 2026-04-28 14:41 | low | [OK] | 4 | 8 |
| 2026-04-29 10:30 | high | [MISS] | - | 0 |
| 2026-04-29 18:10 | low | [OK] | 3 | 1 |

**Verdict matrix:**

| direction   |   horizon |   score>= |   TRUE |   FALSE |   NEUTRAL |   precision_% |   avg_move_% |
|:------------|----------:|----------:|-------:|--------:|----------:|--------------:|-------------:|
| upside      |        60 |         3 |     45 |      82 |       116 |          35.4 |        0.108 |
| upside      |        60 |         4 |      3 |       9 |        16 |          25   |        0.135 |
| upside      |       120 |         3 |     61 |      71 |       111 |          46.2 |        0.115 |
| upside      |       120 |         4 |      5 |      14 |         9 |          26.3 |        0.301 |
| upside      |       240 |         3 |     88 |      86 |        69 |          50.6 |        0.137 |
| upside      |       240 |         4 |      7 |      10 |        11 |          41.2 |        0.395 |
| downside    |        60 |         3 |     55 |      21 |        98 |          72.4 |        0.116 |
| downside    |        60 |         4 |     13 |       5 |        16 |          72.2 |        0.045 |
| downside    |       120 |         3 |     54 |      37 |        82 |          59.3 |        0.095 |
| downside    |       120 |         4 |     13 |       7 |        13 |          65   |        0.061 |
| downside    |       240 |         3 |     70 |      52 |        51 |          57.4 |        0.082 |
| downside    |       240 |         4 |     16 |       8 |         9 |          66.7 |        0.185 |

**PnL (score>=3):**

- Trades: 417 (TP=93, SL=223, timeout=101)
- Win rate: 37.9%, avg net -0.143%, median -0.665%
- Total net: **-59.83%** (best 0.835%, worst -0.665%)

**PnL (score>=4):**

- Trades: 62 (TP=15, SL=34, timeout=13)
- Win rate: 40.3%, avg net -0.107%, median -0.665%
- Total net: **-6.64%** (best 0.835%, worst -0.665%)

## 2. 1h TF (baseline)

- Signals score>=3: **258**
- Signals score>=4: **70**

**9/12 extrema caught (score>=3, ±4h)**

| Date UTC | Type | Caught | Best score | N near |
|---|---|---|---|---|
| 2026-03-17 01:35 | high | [OK] | 4 | 4 |
| 2026-03-26 00:49 | high | [MISS] | - | 0 |
| 2026-04-12 22:30 | low | [OK] | 3 | 1 |
| 2026-04-14 14:32 | high | [OK] | 3 | 2 |
| 2026-04-17 16:23 | high | [OK] | 4 | 5 |
| 2026-04-20 00:00 | low | [OK] | 4 | 4 |
| 2026-04-21 19:46 | low | [MISS] | - | 0 |
| 2026-04-22 16:05 | high | [OK] | 4 | 3 |
| 2026-04-27 01:01 | high | [OK] | 4 | 4 |
| 2026-04-28 14:41 | low | [OK] | 4 | 4 |
| 2026-04-29 10:30 | high | [MISS] | - | 0 |
| 2026-04-29 18:10 | low | [OK] | 4 | 3 |

**Verdict matrix:**

| direction   |   horizon |   score>= |   TRUE |   FALSE |   NEUTRAL |   precision_% |   avg_move_% |
|:------------|----------:|----------:|-------:|--------:|----------:|--------------:|-------------:|
| upside      |        60 |         3 |      1 |       1 |       138 |          50   |        0.006 |
| upside      |        60 |         4 |      0 |       1 |        39 |           0   |        0.025 |
| upside      |       120 |         3 |     31 |      27 |        82 |          53.4 |       -0.001 |
| upside      |       120 |         4 |      8 |      12 |        20 |          40   |        0.107 |
| upside      |       240 |         3 |     55 |      34 |        51 |          61.8 |       -0.067 |
| upside      |       240 |         4 |     17 |      12 |        11 |          58.6 |        0.079 |
| downside    |        60 |         3 |      2 |       3 |       113 |          40   |        0.013 |
| downside    |        60 |         4 |      0 |       2 |        28 |           0   |       -0.025 |
| downside    |       120 |         3 |     35 |      21 |        62 |          62.5 |        0.077 |
| downside    |       120 |         4 |      9 |       4 |        17 |          69.2 |        0.033 |
| downside    |       240 |         3 |     49 |      27 |        42 |          64.5 |        0.161 |
| downside    |       240 |         4 |     13 |       8 |         9 |          61.9 |        0.171 |

**PnL (score>=3):**

- Trades: 258 (TP=78, SL=119, timeout=61)
- Win rate: 43.4%, avg net -0.047%, median -0.198%
- Total net: **-12.1%** (best 0.835%, worst -0.665%)

**PnL (score>=4):**

- Trades: 70 (TP=31, SL=32, timeout=7)
- Win rate: 54.3%, avg net 0.091%, median 0.21%
- Total net: **6.37%** (best 0.835%, worst -0.665%)

## 3. 4h TF

- Signals score>=3: **0**
- Signals score>=4: **0**

**0/12 extrema caught (score>=3, ±4h)**

| Date UTC | Type | Caught | Best score | N near |
|---|---|---|---|---|
| 2026-03-17 01:35 | high | [MISS] | - | 0 |
| 2026-03-26 00:49 | high | [MISS] | - | 0 |
| 2026-04-12 22:30 | low | [MISS] | - | 0 |
| 2026-04-14 14:32 | high | [MISS] | - | 0 |
| 2026-04-17 16:23 | high | [MISS] | - | 0 |
| 2026-04-20 00:00 | low | [MISS] | - | 0 |
| 2026-04-21 19:46 | low | [MISS] | - | 0 |
| 2026-04-22 16:05 | high | [MISS] | - | 0 |
| 2026-04-27 01:01 | high | [MISS] | - | 0 |
| 2026-04-28 14:41 | low | [MISS] | - | 0 |
| 2026-04-29 10:30 | high | [MISS] | - | 0 |
| 2026-04-29 18:10 | low | [MISS] | - | 0 |

**Verdict matrix:**

_no signals_

**PnL (score>=3):**

_no trades_

**PnL (score>=4):**

_no trades_

## 4. Multi-TF confluence (15m + 1h)

- Confluent signals: **255**

**8/12 extrema caught (score>=3, ±4h)**

| Date UTC | Type | Caught | Best score | N near |
|---|---|---|---|---|
| 2026-03-17 01:35 | high | [OK] | 4 | 2 |
| 2026-03-26 00:49 | high | [MISS] | - | 0 |
| 2026-04-12 22:30 | low | [MISS] | - | 0 |
| 2026-04-14 14:32 | high | [OK] | 3 | 3 |
| 2026-04-17 16:23 | high | [OK] | 4 | 8 |
| 2026-04-20 00:00 | low | [OK] | 4 | 14 |
| 2026-04-21 19:46 | low | [MISS] | - | 0 |
| 2026-04-22 16:05 | high | [OK] | 4 | 11 |
| 2026-04-27 01:01 | high | [OK] | 4 | 2 |
| 2026-04-28 14:41 | low | [OK] | 4 | 5 |
| 2026-04-29 10:30 | high | [MISS] | - | 0 |
| 2026-04-29 18:10 | low | [OK] | 3 | 1 |

**Verdict matrix:**

| direction   |   horizon |   score>= |   TRUE |   FALSE |   NEUTRAL |   precision_% |   avg_move_% |
|:------------|----------:|----------:|-------:|--------:|----------:|--------------:|-------------:|
| upside      |        60 |         3 |     29 |      72 |        61 |          28.7 |        0.234 |
| upside      |        60 |         4 |      3 |       9 |        11 |          25   |        0.169 |
| upside      |       120 |         3 |     38 |      60 |        64 |          38.8 |        0.27  |
| upside      |       120 |         4 |      4 |      13 |         6 |          23.5 |        0.381 |
| upside      |       240 |         3 |     63 |      61 |        38 |          50.8 |        0.203 |
| upside      |       240 |         4 |      5 |      10 |         8 |          33.3 |        0.549 |
| downside    |        60 |         3 |     33 |      15 |        45 |          68.8 |        0.065 |
| downside    |        60 |         4 |      4 |       3 |        10 |          57.1 |       -0.077 |
| downside    |       120 |         3 |     34 |      21 |        38 |          61.8 |        0.057 |
| downside    |       120 |         4 |      7 |       2 |         8 |          77.8 |        0.099 |
| downside    |       240 |         3 |     45 |      28 |        20 |          61.6 |        0.094 |
| downside    |       240 |         4 |     10 |       2 |         5 |          83.3 |        0.336 |

**PnL (score>=3):**

- Trades: 255 (TP=64, SL=150, timeout=41)
- Win rate: 37.6%, avg net -0.149%, median -0.665%
- Total net: **-37.94%** (best 0.835%, worst -0.665%)

## 5. 1h with extra signal `low_vol_rally_top`

- Signals score>=3: **259**
- Signals score>=4: **71**

**9/12 extrema caught (score>=3, ±4h)**

| Date UTC | Type | Caught | Best score | N near |
|---|---|---|---|---|
| 2026-03-17 01:35 | high | [OK] | 4 | 4 |
| 2026-03-26 00:49 | high | [MISS] | - | 0 |
| 2026-04-12 22:30 | low | [OK] | 3 | 1 |
| 2026-04-14 14:32 | high | [OK] | 3 | 2 |
| 2026-04-17 16:23 | high | [OK] | 4 | 5 |
| 2026-04-20 00:00 | low | [OK] | 4 | 4 |
| 2026-04-21 19:46 | low | [MISS] | - | 0 |
| 2026-04-22 16:05 | high | [OK] | 4 | 3 |
| 2026-04-27 01:01 | high | [OK] | 4 | 4 |
| 2026-04-28 14:41 | low | [OK] | 4 | 4 |
| 2026-04-29 10:30 | high | [MISS] | - | 0 |
| 2026-04-29 18:10 | low | [OK] | 4 | 3 |

**Verdict matrix:**

| direction   |   horizon |   score>= |   TRUE |   FALSE |   NEUTRAL |   precision_% |   avg_move_% |
|:------------|----------:|----------:|-------:|--------:|----------:|--------------:|-------------:|
| upside      |        60 |         3 |      1 |       1 |       139 |          50   |        0.006 |
| upside      |        60 |         4 |      1 |       1 |        39 |          50   |        0.017 |
| upside      |       120 |         3 |     32 |      27 |        82 |          54.2 |       -0.004 |
| upside      |       120 |         4 |      8 |      13 |        20 |          38.1 |        0.12  |
| upside      |       240 |         3 |     56 |      34 |        51 |          62.2 |       -0.076 |
| upside      |       240 |         4 |     17 |      13 |        11 |          56.7 |        0.088 |
| downside    |        60 |         3 |      2 |       3 |       113 |          40   |        0.013 |
| downside    |        60 |         4 |      0 |       2 |        28 |           0   |       -0.025 |
| downside    |       120 |         3 |     35 |      21 |        62 |          62.5 |        0.077 |
| downside    |       120 |         4 |      9 |       4 |        17 |          69.2 |        0.033 |
| downside    |       240 |         3 |     49 |      27 |        42 |          64.5 |        0.161 |
| downside    |       240 |         4 |     13 |       8 |         9 |          61.9 |        0.171 |

**PnL (score>=4):**

- Trades: 71 (TP=31, SL=33, timeout=7)
- Win rate: 53.5%, avg net 0.08%, median 0.137%
- Total net: **5.71%** (best 0.835%, worst -0.665%)

## 6. Walk-forward 1h (60d train / 30d test)

- Train days: 60
- Test days: 30
- Test signals (score>=3): 78

**Out-of-sample verdict matrix:**

| direction   |   horizon |   score>= |   TRUE |   FALSE |   NEUTRAL |   precision_% |   avg_move_% |
|:------------|----------:|----------:|-------:|--------:|----------:|--------------:|-------------:|
| upside      |        60 |         3 |      0 |       0 |        55 |         nan   |       -0.005 |
| upside      |        60 |         4 |      0 |       0 |        19 |         nan   |        0.009 |
| upside      |       120 |         3 |     11 |       7 |        37 |          61.1 |       -0.039 |
| upside      |       120 |         4 |      3 |       3 |        13 |          50   |       -0.009 |
| upside      |       240 |         3 |     21 |      13 |        21 |          61.8 |       -0.105 |
| upside      |       240 |         4 |      8 |       5 |         6 |          61.5 |       -0.051 |
| downside    |        60 |         3 |      0 |       1 |        22 |           0   |       -0.009 |
| downside    |        60 |         4 |      0 |       0 |         8 |         nan   |       -0.003 |
| downside    |       120 |         3 |      4 |       4 |        15 |          50   |       -0.003 |
| downside    |       120 |         4 |      0 |       0 |         8 |         nan   |       -0.014 |
| downside    |       240 |         3 |     10 |       3 |        10 |          76.9 |        0.126 |
| downside    |       240 |         4 |      4 |       0 |         4 |         100   |        0.297 |
