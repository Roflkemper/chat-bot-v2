# Setup filter research

**Period:** last 14,400 1m bars (~10d)
**Setups analyzed:** 3

## detect_long_multi_divergence

- Total emits: 1291
- Classes: {'NEUTRAL': 826, 'TRUE': 241, 'FALSE': 224}
- **Baseline:** {'n': 1291, 'wr': 42.0, 'pf': 0.83, 'total_pnl_pct': -67.54, 'avg_pnl_pct': -0.0523}

### Top discriminating features (KS, T-mean vs F-mean)

| feature              |   true_mean |   false_mean |   true_median |   false_median |   delta_mean |    ks |
|:---------------------|------------:|-------------:|--------------:|---------------:|-------------:|------:|
| atr_1h_pct           |       0.738 |        0.701 |         0.729 |          0.627 |        0.037 | 0.17  |
| bb_width_pct         |       3.21  |        2.996 |         2.999 |          2.553 |        0.213 | 0.136 |
| adx_1h               |      42.771 |       37.821 |        43.749 |         36.097 |        4.95  | 0.122 |
| mfi_1h               |      50.04  |       47.124 |        48.32  |         45.948 |        2.915 | 0.112 |
| vol_z_1m             |       0.141 |       -0.055 |        -0.232 |         -0.361 |        0.195 | 0.096 |
| rsi_15m              |      52.333 |       49.958 |        53.937 |         50.958 |        2.375 | 0.091 |
| vol_z_15m            |       0.138 |       -0.019 |        -0.281 |         -0.412 |        0.157 | 0.088 |
| ema50_200_spread_pct |      -0.895 |       -0.816 |        -0.731 |         -0.572 |       -0.079 | 0.087 |

### Filter built

```json
{
  "rules": [
    {
      "feature": "atr_1h_pct",
      "op": ">=",
      "threshold": 0.729
    },
    {
      "feature": "bb_width_pct",
      "op": ">=",
      "threshold": 2.999
    },
    {
      "feature": "adx_1h",
      "op": ">=",
      "threshold": 43.749
    }
  ],
  "ks_total": 0.42800000000000005
}
```

**Filtered metrics:** {'n': 167, 'wr': 46.1, 'pf': 1.156, 'total_pnl_pct': 9.31, 'avg_pnl_pct': 0.0557}

**Confirmed-only (10m lag, +0.1% drift):** {'n': 100, 'wr': 53.0, 'pf': 1.53, 'total_pnl_pct': 17.79, 'avg_pnl_pct': 0.1779}

**Filter + Confirmation:** {'n': 25, 'wr': 60.0, 'pf': 4.531, 'total_pnl_pct': 16.03, 'avg_pnl_pct': 0.6411}

### Walk-forward (4 folds)

|   fold |   baseline_n |   baseline_pf |   baseline_pnl% |   filt_n |   filt_pf |   filt_pnl% |
|-------:|-------------:|--------------:|----------------:|---------:|----------:|------------:|
|      1 |          322 |         0.59  |          -38.73 |       21 |     1.475 |        2.38 |
|      2 |          322 |         0.705 |          -31.52 |       61 |     0.769 |       -5.93 |
|      3 |          322 |         0.665 |          -29.75 |       25 |     0.542 |       -4.4  |
|      4 |          325 |         1.305 |           32.46 |       60 |     1.898 |       17.26 |

---

## detect_short_rally_fade

- Total emits: 940
- Classes: {'NEUTRAL': 635, 'FALSE': 237, 'TRUE': 68}
- **Baseline:** {'n': 940, 'wr': 31.5, 'pf': 0.54, 'total_pnl_pct': -114.2, 'avg_pnl_pct': -0.1215}

### Top discriminating features (KS, T-mean vs F-mean)

| feature              |   true_mean |   false_mean |   true_median |   false_median |   delta_mean |    ks |
|:---------------------|------------:|-------------:|--------------:|---------------:|-------------:|------:|
| trend_slope_6h_pct   |       2.021 |        1.252 |         1.611 |          0.965 |        0.769 | 0.338 |
| rsi_15m              |      73.398 |       66.68  |        75.627 |         68.317 |        6.718 | 0.331 |
| atr_1h_pct           |       0.757 |        0.611 |         0.649 |          0.546 |        0.146 | 0.266 |
| last5_close_lean     |       0.554 |        0.518 |         0.536 |          0.512 |        0.035 | 0.207 |
| bb_width_pct         |       4.065 |        3.337 |         3.203 |          2.862 |        0.728 | 0.192 |
| ema50_200_spread_pct |      -0.707 |        0.125 |         0.008 |          0.308 |       -0.832 | 0.191 |
| mfi_1h               |      72.757 |       69.892 |        76.725 |         73.104 |        2.865 | 0.158 |
| vol_z_1h             |       0.961 |        0.732 |         0.605 |          0.336 |        0.229 | 0.14  |

### Filter built

```json
{
  "rules": [
    {
      "feature": "trend_slope_6h_pct",
      "op": ">=",
      "threshold": 1.611
    },
    {
      "feature": "rsi_15m",
      "op": ">=",
      "threshold": 75.627
    },
    {
      "feature": "atr_1h_pct",
      "op": ">=",
      "threshold": 0.649
    }
  ],
  "ks_total": 0.935
}
```

**Filtered metrics:** {'n': 74, 'wr': 40.5, 'pf': 1.108, 'total_pnl_pct': 2.38, 'avg_pnl_pct': 0.0322}

**Confirmed-only (10m lag, +0.1% drift):** {'n': 842, 'wr': 30.2, 'pf': 0.519, 'total_pnl_pct': -104.29, 'avg_pnl_pct': -0.1239}

**Filter + Confirmation:** {'n': 56, 'wr': 41.1, 'pf': 1.392, 'total_pnl_pct': 5.57, 'avg_pnl_pct': 0.0994}

### Walk-forward (4 folds)

|   fold |   baseline_n |   baseline_pf |   baseline_pnl% |   filt_n |   filt_pf |   filt_pnl% |
|-------:|-------------:|--------------:|----------------:|---------:|----------:|------------:|
|      1 |          235 |         0.565 |          -23.06 |        7 |     2.09  |        1.14 |
|      2 |          235 |         0.429 |          -29.65 |        3 |     0     |       -1.02 |
|      3 |          235 |         0.59  |          -28.74 |       24 |     0.985 |       -0.1  |
|      4 |          235 |         0.554 |          -32.75 |       40 |     1.176 |        2.36 |

---

## detect_double_bottom_setup

- Total emits: 769
- Classes: {'NEUTRAL': 667, 'TRUE': 95, 'FALSE': 7}
- **Baseline:** {'n': 769, 'wr': 41.1, 'pf': 0.607, 'total_pnl_pct': -96.88, 'avg_pnl_pct': -0.126}

### Top discriminating features (KS, T-mean vs F-mean)



### Filter built

```json
{}
```

**Filtered metrics:** {'n': 769, 'wr': 41.1, 'pf': 0.607, 'total_pnl_pct': -96.88, 'avg_pnl_pct': -0.126}

**Confirmed-only (10m lag, +0.1% drift):** {'n': 43, 'wr': 46.5, 'pf': 1.053, 'total_pnl_pct': 0.61, 'avg_pnl_pct': 0.0141}

**Filter + Confirmation:** {'n': 43, 'wr': 46.5, 'pf': 1.053, 'total_pnl_pct': 0.61, 'avg_pnl_pct': 0.0141}

### Walk-forward (4 folds)

|   fold |   baseline_n |   baseline_pf |   baseline_pnl% |   filt_n |   filt_pf |   filt_pnl% |
|-------:|-------------:|--------------:|----------------:|---------:|----------:|------------:|
|      1 |          192 |         0.501 |          -31.63 |      192 |     0.501 |      -31.63 |
|      2 |          192 |         0.553 |          -27.64 |      192 |     0.553 |      -27.64 |
|      3 |          192 |         0.589 |          -23.22 |      192 |     0.589 |      -23.22 |
|      4 |          193 |         0.777 |          -14.4  |      193 |     0.777 |      -14.4  |

---
