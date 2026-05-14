# Setup filter research

**Period:** last 14,400 1m bars (~10d)
**Setups analyzed:** 1

## detect_short_pdh_rejection

- Total emits: 377
- Classes: {'FALSE': 168, 'NEUTRAL': 121, 'TRUE': 88}
- **Baseline:** {'n': 377, 'wr': 29.2, 'pf': 0.576, 'total_pnl_pct': -45.47, 'avg_pnl_pct': -0.1206}

### Top discriminating features (KS, T-mean vs F-mean)

| feature            |   true_mean |   false_mean |   true_median |   false_median |   delta_mean |    ks |
|:-------------------|------------:|-------------:|--------------:|---------------:|-------------:|------:|
| trend_slope_6h_pct |       1.329 |        1.013 |         1.012 |          0.776 |        0.316 | 0.189 |
| rsi_1h             |      72.35  |       68.759 |        72.431 |         68.131 |        3.591 | 0.18  |
| mfi_1h             |      71.29  |       68.593 |        71.804 |         68.122 |        2.697 | 0.16  |
| rsi_15m            |      68.979 |       66.497 |        68.406 |         66.075 |        2.482 | 0.152 |
| adx_1h             |      52.95  |       47.651 |        54.114 |         45.15  |        5.299 | 0.134 |
| vol_z_1h           |       0.929 |        0.687 |         0.456 |          0.428 |        0.243 | 0.124 |
| atr_1h_pct         |       0.593 |        0.529 |         0.553 |          0.506 |        0.064 | 0.108 |
| bb_width_pct       |       2.979 |        2.511 |         2.383 |          2.198 |        0.468 | 0.1   |

### Filter built

```json
{
  "rules": [
    {
      "feature": "trend_slope_6h_pct",
      "op": ">=",
      "threshold": 1.012
    },
    {
      "feature": "rsi_1h",
      "op": ">=",
      "threshold": 72.431
    },
    {
      "feature": "mfi_1h",
      "op": ">=",
      "threshold": 71.804
    }
  ],
  "ks_total": 0.529
}
```

**Filtered metrics:** {'n': 67, 'wr': 34.3, 'pf': 1.11, 'total_pnl_pct': 1.84, 'avg_pnl_pct': 0.0275}

**Confirmed-only (10m lag, +0.1% drift):** {'n': 329, 'wr': 28.0, 'pf': 0.571, 'total_pnl_pct': -38.88, 'avg_pnl_pct': -0.1182}

**Filter + Confirmation:** {'n': 54, 'wr': 35.2, 'pf': 1.35, 'total_pnl_pct': 3.95, 'avg_pnl_pct': 0.0732}

### Walk-forward (4 folds)

|   fold |   baseline_n |   baseline_pf |   baseline_pnl% |   filt_n |   filt_pf |   filt_pnl% |
|-------:|-------------:|--------------:|----------------:|---------:|----------:|------------:|
|      1 |           94 |         0.516 |          -14.9  |       21 |     1.268 |        1.34 |
|      2 |           94 |         0.821 |           -3.61 |       18 |     0.758 |       -0.92 |
|      3 |           94 |         0.6   |           -8.49 |        8 |     1.601 |        0.71 |
|      4 |           95 |         0.472 |          -18.47 |       20 |     1.105 |        0.71 |

---
