# Liq-cluster pre-cascade alert — retro hit-rate validation

**Дата:** 2026-05-13
**Data window:** 2026-05-07 18:32 — 2026-05-13 16:50 (5d 22h)
**События:** 4 513 liq, 27 cascades
**Скрипт:** [scripts/validate_liq_cluster_hitrate.py](../../scripts/validate_liq_cluster_hitrate.py)

## Метод

Stream-симуляция production-логики `liq_clustering.check_and_alert` по минутам.
Для каждого hypothetical fire — проверяем случился ли каскад same-side в +0..30 мин.
Для каждого каскада — был ли alert same-side в -30..0 мин (recall).

## Результаты (threshold=0.3 BTC, production default)

| Metric | Value | Interpretation |
|---|---:|---|
| Fires | 87 | За 6 дней (≈14.5/день) |
| Hits | 21 | Каскад в +0..30 мин same side |
| **Hit rate** | **24.1%** | 1 из 4 alert'ов — точное предсказание |
| False positives | 66 | Каскад не случился |
| Cascades total | 27 | LONG: 10, SHORT: 17 |
| **Recall** | **77.8%** | 21 из 27 каскадов имели pre-alert |
| Missed cascades | 6 | "блицы" без предупреждения |

## Per-side breakdown

| Side | Hit rate | Recall |
|---|---:|---:|
| **LONG** | 16% (8/51) | 80% (8/10) |
| **SHORT** | 36% (13/36) | 76% (13/17) |

**Вывод:** SHORT-сторона ловится лучше. На LONG слишком много мелкошумных liq, которые **не** заканчиваются каскадом.

## R&D vs реальность

| | R&D z-score | Hit rate |
|---|---:|---:|
| LONG | z=20 (88× baseline) | 16% |
| SHORT | z=4.2 (22× baseline) | 36% |

R&D z для LONG был **inflated** одним outlier (29 BTC за 5 мин в bucket -30..-25). Реальный hit-rate показывает обратную картину: SHORT лучше LONG.

## Threshold sensitivity

| Threshold | Fires | Hit% | Recall% | FP |
|---:|---:|---:|---:|---:|
| 0.15 | 109 | 20 | 81 | 87 |
| 0.20 | 100 | 22 | 81 | 78 |
| 0.30 (current) | 87 | 24 | 78 | 66 |
| 0.40 | 78 | 26 | 74 | 58 |
| **0.50** | **75** | **25** | **70** | **56** |
| 0.70 | 59 | 31 | 67 | 41 |
| 1.00 | 48 | 31 | 56 | 33 |

## Рекомендации

### Option A: оставить 0.30 (текущий)
- Pro: лучший recall (78%) — почти все каскады ловятся.
- Con: 66 FP за неделю = 9.4 ложных alert/день. Шумно.

### Option B: поднять до 0.50 ⭐
- Pro: -15% алертов (87→75), почти тот же hit-rate (24→25%), recall просел только на 8pp (78→70%).
- Con: пропускаем 8 каскадов вместо 6.

### Option C: повысить до 0.70 для high-confidence info-channel, оставить 0.30 в ROUTINE
- Pro: иметь два уровня сигнала.
- Con: ещё один канал = усложнение.

## Решение

**Поднимаю в production threshold с 0.30 до 0.50 BTC** — лучший trade-off:
- 15% меньше шума.
- Recall 70% всё ещё хороший.
- Hit rate +1pp (24→25%).
- Phase-2 score продолжит работать — он fixed с LIQ_NORM_BTC=0.3 ⇒ score-баллы не меняются, просто меньше сообщений.

## Дальнейшие действия

- [ ] Через 7 дней повторить validation с production journal (`state/liq_pre_cascade_fires.jsonl`) — оценить hit-rate уже на новом threshold.
- [ ] Подумать про per-side threshold: LONG=0.7 (hit 31%, дёшево пропустить блиц-LONG), SHORT=0.4 (hit 36%, не терять recall).
- [ ] Score auto-tune (см. отдельный todo) — анализ journal раз в неделю.
