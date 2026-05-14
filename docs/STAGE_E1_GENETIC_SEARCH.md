# Stage E1 — Genetic detector search

## Что это

GA (Genetic Algorithm) для **автоматического поиска** новых детекторов по
скользящему окну параметров. Вместо ручного перебора (как делал в B2/B5)
эволюция сама находит комбинацию `(индикаторы + thresholds + gate + horizon)`,
которая даёт лучший walk-forward PF на исторических данных.

## Что это даст тебе

1. **Новые edge candidates без ручного дизайна.** Сейчас все 17 detector'ов
   написаны человеком. GA может найти неочевидную комбинацию (например
   `RSI<32 + OBV-div + PDL_proximity<0.5%` на 4h hold), которую никто
   не подумал бы тестировать.

2. **Quantitative edge confirmation.** Каждый кандидат сразу проходит
   walk-forward на 4 fold'ах. Если PF≥2.0 + STABLE на ≥3/4 — wire в
   production как новый detector. Если нет — отбрасывается без затрат
   ручного времени.

3. **Систематическая защита от overfitting.** Fitness функция = walk-forward
   metric, а не in-sample PF. Это то, чего не хватает ручному дизайну —
   человек видит хороший backtest и заканчивает на нём, не делая walk-fwd.

4. **Ожидаемый результат:** 1-3 новых STABLE detector'а из ~5000 evaluated
   genomes. Каждый добавляет независимый edge к портфелю signals.

## Цена и время

- **Compute:** ~24 часа на твоём ПК. GA evaluation 5000 genomes × 4 folds
  каждый × 2y BTC 1h backtest. Один genome ≈ 15-20 секунд simulation.
- **Disk:** ~50 MB для results + history (cache).
- **Память:** до 2 GB (BTC 1h 2y + indicators). Уровень app_runner.
- **Risk:** 0 — purely backtest, не трогает live.

Не забивает live-бот: GA скрипт запускается отдельно, можно ночью.
Можно прервать (Ctrl+C) и продолжить — checkpoint каждые 100 evals.

## Как устроен GA

**Genome (15 параметров):**
```python
{
  # Indicator selection (which to use as primary signal)
  "primary_ind": "RSI" | "MFI" | "OBV" | "CMF" | "MACD",
  "primary_threshold": float[20, 80],   # e.g. RSI<35 = oversold
  "primary_direction": "below" | "above",

  # Pivot detection
  "pivot_lookback": int[3, 15],
  "div_window_bars": int[10, 50],

  # Confluence requirement
  "confluence_min": int[1, 5],

  # Trend gate
  "use_ema_gate": bool,
  "ema_fast": int[20, 100],
  "ema_slow": int[100, 300],

  # Volume filter
  "use_volume_filter": bool,
  "vol_z_min": float[0.5, 3.0],

  # Entry / SL / TP
  "sl_pct": float[0.3, 1.5],
  "tp1_rr": float[1.2, 4.0],
  "hold_horizon_h": int[1, 48],
  "direction": "long" | "short",
}
```

**Fitness (одно число для ranking):**
```python
fitness = walk_forward_pf_avg × log(1 + walk_forward_n_avg) × stability_penalty
```
где
- `walk_forward_pf_avg` = среднее PF по 4 fold'ам
- `walk_forward_n_avg` = среднее N сигналов на fold (>=10 для надежности)
- `stability_penalty` = 1.0 если 3+/4 fold positive, 0.5 если 2/4, 0.0 иначе

**GA operations:**
- Population: 50 genomes
- Generations: 100
- Selection: tournament (k=3)
- Crossover: uniform (50% genes from each parent)
- Mutation: Gaussian noise on numeric, flip on bool/enum (rate 10%)
- Elitism: top-5 carries over

Итого 50 × 100 = 5000 evaluations, минус cache hits ≈ ~3500-4000 unique.

## Запуск

```bash
# Полный прогон (~24h)
python tools/_genetic_detector_search.py \
  --population 50 --generations 100 \
  --output state/ga_results.jsonl

# Smoke test (~30 min) — для проверки что работает
python tools/_genetic_detector_search.py \
  --population 10 --generations 5 \
  --output state/ga_smoke.jsonl

# Resume from checkpoint
python tools/_genetic_detector_search.py --resume state/ga_results.jsonl
```

## Output

Каждый genome пишется в `state/ga_results.jsonl`:
```json
{"gen": 42, "rank": 1, "fitness": 8.34, "genome": {...}, "metrics": {
   "all_period_pf": 2.45, "all_period_n": 312, "all_period_wr": 58.4,
   "fold_metrics": [{"pf": 2.1, "n": 78}, ...],
   "verdict": "STABLE"
}}
```

После прогона: `python tools/_ga_report.py` → `docs/GA_RESULTS.md` с
top-10 genomes + recommendations.

## Решение wire-or-not

Genome автоматически **не идёт** в production. Я смотрю top-10 и:

- Если **PF≥2.0** AND **STABLE** AND **N≥50/year** → готовлю wire skeleton:
  - Новый файл `services/setup_detector/ga_<name>.py`
  - SetupType enum entry
  - Регистрация в DETECTOR_REGISTRY
  - 5-7 unit tests
  - Тебе на ревью

- Иначе — записываю в `docs/GA_REJECTED.md` с причиной (low N, OVERFIT,
  PF marginal). Можно вернуться через год когда данных больше.

## Скелет уже есть в файлах

Я создал заготовку: [tools/_genetic_detector_search.py](tools/_genetic_detector_search.py)

Там есть:
- Genome dataclass + sampling
- Tournament selection, crossover, mutation
- Walk-forward fitness eval (импортирует существующий `tools/backtest_signals.py`)
- Checkpoint/resume
- Простейший CLI

Не запускал в этой сессии (24h compute). Готов к запуску оператором.

## Что **не** делает

- Не оптимизирует **существующие** detector'ы (это D3 P-15 auto-tuner).
- Не делает multi-asset (только BTC 1h). Расширение на ETH/XRP — следующая
  версия.
- Не учитывает funding fee (только entry/exit fees). Если выиграет detector
  с N>2000 trade в year — нужно reproject с funding.
