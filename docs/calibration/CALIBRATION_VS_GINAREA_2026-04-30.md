# Calibration vs GinArea — 2026-05-01 21:18 UTC

**Period:** 2025-05-01 → 2026-04-29 (frozen BTCUSDT 1m)  
**Engine:** backtest_lab engine_v2  
**Resolution gap:** 1m bars vs GinArea tick-level  

---

## Per-run calibration table

| ID | Dir | Ctr | TD | sim_trades | ga_trig | K_trades | sim_realized | ga_realized | K_realized | sim_volume | ga_volume | K_volume |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5181061252 | SHORT | LINEAR | 0.19 | 1,267 | 589 | 0.46 | -63.8624 | 31,746.8600 | -497.11 | 2,976,253 | 52,666,201 | 17.70 |
| 5658350391 | SHORT | LINEAR | 0.21 | 1,204 | 559 | 0.46 | 130.2327 | 34,791.8300 | 267.15 | 2,890,302 | 48,937,853 | 16.93 |
| 4714585329 | SHORT | LINEAR | 0.25 | 1,759 | 582 | 0.33 | -384.1267 | 38,909.9300 | -101.29 | 3,850,847 | 42,780,857 | 11.11 |
| 5360096295 | SHORT | LINEAR | 0.30 | 1,490 | 598 | 0.40 | 1,129.0636 | 42,616.7500 | 37.75 | 3,398,953 | 37,010,264 | 10.89 |
| 5380108649 | SHORT | LINEAR | 0.35 | 1,355 | 614 | 0.45 | 1,339.3181 | 46,166.4300 | 34.47 | 3,184,523 | 33,000,181 | 10.36 |
| 4929609976 | SHORT | LINEAR | 0.45 | 1,448 | 617 | 0.43 | 1,499.7065 | 49,782.5100 | 33.19 | 3,307,296 | 26,676,981 | 8.07 |
| 4373073010 | LONG | INVERSE | 0.25 | 1,797 | N/A | N/A | -0.1548 | 0.1249 | -0.81 | 3,922,800 | 14,211,200 | 3.62 |
| 5602603251 | LONG | INVERSE | 0.30 | 1,737 | N/A | N/A | -0.1551 | 0.1336 | -0.86 | 3,873,800 | 12,207,600 | 3.15 |
| 5975887092 | LONG | INVERSE | 0.45 | 1,837 | N/A | N/A | -0.1559 | 0.1542 | -0.99 | 3,956,600 | 8,344,000 | 2.11 |

---

## Per-group summary

### SHORT / USDT-M (LINEAR)

| Metric | mean K | std | CV% | min | max | Verdict |
|---|---:|---:|---:|---:|---:|---|
| K_trades | 0.423 | 0.052 | 12.2% | 0.331 | 0.465 | **STABLE** |
| K_realized | -37.641 | 254.545 | -676.2% | -497.114 | 267.151 | **FRACTURED_SIGN_FLIP** |
| K_volume | 12.509 | 3.883 | 31.0% | 8.066 | 17.695 | **TD-DEPENDENT** |

**Normalized sim_realized vs ga_realized** (sim × mean K_realized):

| ID | TD | norm_sim_realized | ga_realized | err% |
|---|---|---:|---:|---:|
| 5181061252 | 0.19 | 2,403.8532 | 31,746.8600 | -92.4% |
| 5658350391 | 0.21 | -4,902.1104 | 34,791.8300 | -114.1% |
| 4714585329 | 0.25 | 14,458.9756 | 38,909.9300 | -62.8% |
| 5360096295 | 0.30 | -42,499.2696 | 42,616.7500 | -199.7% |
| 5380108649 | 0.35 | -50,413.4910 | 46,166.4300 | -209.2% |
| 4929609976 | 0.45 | -56,450.6970 | 49,782.5100 | -213.4% |

### LONG / COIN-M (INVERSE)

| Metric | mean K | std | CV% | min | max | Verdict |
|---|---:|---:|---:|---:|---:|---|
| K_trades | N/A | N/A | N/A | N/A | N/A | UNKNOWN |
| K_realized | -0.886 | 0.094 | -10.6% | -0.989 | -0.807 | **STABLE** |
| K_volume | 2.961 | 0.775 | 26.2% | 2.109 | 3.623 | **TD-DEPENDENT** |

**Normalized sim_realized vs ga_realized** (sim × mean K_realized):

| ID | TD | norm_sim_realized | ga_realized | err% |
|---|---|---:|---:|---:|
| 4373073010 | 0.25 | 0.1371 | 0.1249 | +9.8% |
| 5602603251 | 0.30 | 0.1373 | 0.1336 | +2.8% |
| 5975887092 | 0.45 | 0.1381 | 0.1542 | -10.4% |

---

## Conclusions

**SHORT / USDT-M (LINEAR):** K_realized = -37.641 ± 254.545 (CV=-676.2%) → **FRACTURED_SIGN_FLIP**  
  → K spans positive and negative values (sign flip detected). Group is unreliable; fix engine bug before calibrating.  
**LONG / COIN-M (INVERSE):** K_realized = -0.886 ± 0.094 (CV=-10.6%) → **STABLE**  
  → Use K = -0.886 as fixed calibration multiplier.  

