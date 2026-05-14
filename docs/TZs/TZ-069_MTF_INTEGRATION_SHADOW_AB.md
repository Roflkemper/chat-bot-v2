# TZ-069 — MTF интеграция в shadow A/B

**Статус:** DESIGN  
**Дата:** 2026-05-14  
**Триггер:** `BACKLOG_TRIGGERS.md → TZ-MTF-INTEGRATION` (после TZ-MTF-FEASIBILITY-CHECK)  
**Owner:** TBD  
**Effort:** 1 неделя дизайн + 2 недели impl + 2-4 недели shadow-валидация

## Проблема

Сейчас `services/setup_detector/mtf_check.py` работает как **бинарный gate**:
- Проверяет согласие 4h × 1h × 15m направлений
- Если конфликт (например 4h=trend_up, 15m=trend_down) → `mtf_conflict` → setup убивается
- Если все нейтральны → `mtf_neutral` → тоже отказ

Из логов: **20-27 mtf_conflict + 12-21 mtf_neutral за день** = 30-50 потенциальных сигналов в день режутся бинарно. Часть из них могла быть валидными (например, trend на 4h, краткосрочный pullback на 15m — классический buy-the-dip).

## Цель

Превратить MTF-чек из **gate** в **scoring layer**:

| Сценарий | Сейчас | Должно быть |
|----------|--------|-------------|
| Все TF согласны | ✅ pass | confluence_boost = +30% |
| 4h+1h согласны, 15m против | ❌ block | confluence_neutral = 0 (не блок) |
| 4h противоположен 15m | ❌ block | confluence_penalty = -20% |
| Все нейтральны | ❌ block | confluence_neutral = 0 (но и не boost) |

## Спецификация

### MTF score

```python
@dataclass
class MTFScore:
    score_pct: float    # -30..+30, добавка к confluence_score
    label: str          # "ALIGNED" | "MIXED" | "PARTIAL_CONFLICT" | "FULL_CONFLICT"
    detail: dict        # {"4h": "trend_up", "1h": "range", "15m": "trend_down"}

def compute_mtf_score(setup_side: str, regimes: dict) -> MTFScore:
    """setup_side='long' or 'short'.
    regimes={'4h': Regime, '1h': Regime, '15m': Regime}.
    """
    weights = {"4h": 0.5, "1h": 0.3, "15m": 0.2}  # старший TF важнее
    
    score = 0.0
    for tf, regime in regimes.items():
        w = weights[tf]
        if _aligned(setup_side, regime):
            score += w * 30  # max +30 если all aligned
        elif _opposite(setup_side, regime):
            score -= w * 20  # max -20 если all opposed
        # neutral → 0
    
    return MTFScore(
        score_pct=score,
        label=_classify(score),
        detail={tf: r.primary.name for tf, r in regimes.items()},
    )
```

### Изменения в pipeline

| Файл | Изменение |
|------|-----------|
| `services/setup_detector/mtf_check.py` | `check_mtf()` → `compute_mtf_score()` |
| `services/setup_detector/confluence_score.py` | Прибавить `mtf_score.score_pct` к `confluence_pct` |
| `services/setup_detector/loop.py` | Убрать early-exit на `mtf_conflict`, добавить `mtf_score` в setup payload |
| `services/setup_detector/telegram_card.py` | Показывать MTF в карточке: `MTF: ALIGNED 4h↑ 1h↑ 15m↑ (+30%)` |
| `state/pipeline_metrics.jsonl` | `stage_outcome=emitted` теперь содержит `mtf_score` |

### Совместимость со старой логикой

Через конфиг-флаг:
```python
# .env.local
MTF_MODE=score   # 'gate' (legacy) | 'score' (new)
```

Default `gate` — не ломаем поведение. Включаем `score` только в shadow phase.

## Shadow A/B протокол

**Phase 1 — neighbor logging (1 неделя):**
- `mtf_check` остаётся gate'ом (как сейчас)
- ПАРАЛЛЕЛЬНО считается `compute_mtf_score()` и пишется в `state/mtf_shadow.jsonl`
- Не влияет на эмиссию сигналов
- Цель: накопить 200+ сэмплов разных MTF-конфигураций

**Phase 2 — score-mode shadow (2 недели):**
- `MTF_MODE=score` включён
- ВСЕ сигналы которые выходят с MTF-score-modifier помечаются `mtf_origin=score`
- Сравниваем post-hoc PnL: если `mtf_origin=score && score>0` сигналы **выгоднее** старых блокированных — мигрируем в prod

**Phase 3 — production switch (1 неделя shake-out):**
- Default `MTF_MODE=score`
- Старый `gate` остаётся как fallback на `MTF_MODE=gate`

## Метрики успеха

После Phase 2 за 2 недели:
- **N эмиссий**: должно вырасти с ~50/день до ~70-80/день (часть `mtf_conflict` теперь проходят)
- **PnL новых эмиссий** (score-modified): PF ≥ 1.0 на post-hoc анализе
- **PnL старых эмиссий** (без MTF-modifier): не упал

Если PnL новых < 0 и PnL старых стабилен — mtf_score не работает, откатываем на `gate`.

## Open questions

- Какой weight для каждого TF? Сейчас предложено 0.5/0.3/0.2, но это эвристика. Нужно walk-forward optimization.
- Зависит ли вес от типа сетапа? `long_pdl_bounce` (15m-events) может больше доверять 15m, чем 4h. Возможно нужны setup-specific weights.
- Как быть со старым `combo_blocked: regime=consolidation`? Это отдельный gate, не MTF — но философия похожая. Стоит ли его тоже в score?
