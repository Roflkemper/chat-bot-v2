# REGIME CLASSIFIER v2 — CALIBRATION 2026-05-06

**Источник:** `data\forecast_features\full_features_1y.parquet`
**Период:** 2025-05-01 → 2026-05-01
**Всего часов:** 8761

---

## §1 Распределение 10 состояний за 1y

| State | Count | % of year |
|---|---:|---:|
| **RANGE** | 3482 | 39.74% |
| **SLOW_DOWN** | 2130 | 24.31% |
| **SLOW_UP** | 1921 | 21.93% |
| **COMPRESSION** | 706 | 8.06% |
| **DRIFT_DOWN** | 201 | 2.29% |
| **DRIFT_UP** | 144 | 1.64% |
| **STRONG_UP** | 117 | 1.34% |
| **STRONG_DOWN** | 60 | 0.68% |

## §2 3-state projection (для Decision Layer compat)

| 3-state | Count | % |
|---|---:|---:|
| RANGE | 4188 | 47.8% |
| MARKDOWN | 2391 | 27.29% |
| MARKUP | 2182 | 24.91% |

## §3 Episode statistics — длительности

| State | Episodes | Median (h) | p75 (h) | p90 (h) | Max (h) |
|---|---:|---:|---:|---:|---:|
| COMPRESSION | 87 | 3.0 | 10.5 | 22.200000000000017 | 41 |
| DRIFT_DOWN | 64 | 2.0 | 5.0 | 7.700000000000003 | 10 |
| DRIFT_UP | 55 | 1.0 | 2.5 | 6.0 | 24 |
| RANGE | 351 | 6.0 | 15.0 | 24.0 | 53 |
| SLOW_DOWN | 123 | 5.0 | 21.5 | 48.0 | 160 |
| SLOW_UP | 137 | 5.0 | 18.0 | 37.400000000000006 | 87 |
| STRONG_DOWN | 13 | 2.0 | 4.0 | 11.000000000000004 | 20 |
| STRONG_UP | 25 | 3.0 | 7.0 | 13.0 | 16 |

## §4 Confusion matrix — старый vs новый projected 3-state

Строки = старый `regime_int` (RANGE/MARKUP/MARKDOWN); столбцы = v2 projected.

| old \\ v2 | MARKDOWN | MARKUP | RANGE |
|---|---:|---:|---:|
| MARKDOWN | 1038 | 22 | 249 |
| MARKUP | 44 | 771 | 320 |
| RANGE | 1309 | 1389 | 3619 |

## §5 Operator window 30.04 → 06.05 (бычий drift из скриншота)

Период когда классификатор v1 говорил RANGE на trend up.

| State | % of window |
|---|---:|
| STRONG_DOWN | 80.0% |
| RANGE | 20.0% |

## §6 Recent week distribution (last 168h)

| State | % |
|---|---:|
| RANGE | 43.5% |
| SLOW_UP | 22.6% |
| COMPRESSION | 19.6% |
| STRONG_DOWN | 11.9% |
| DRIFT_DOWN | 2.4% |

---

**Конец calibration.** Если в operator window появились SLOW_UP/DRIFT_UP — v2 решает META-issue.