# TZ-068 — Adaptive regime hysteresis

**Статус:** DESIGN  
**Дата:** 2026-05-14  
**Триггер:** `BACKLOG_TRIGGERS.md → TZ-PERSISTENCE-ADAPTIVE-DESIGN`  
**Owner:** TBD  
**Effort:** 1-2 дня дизайн + 3-5 дней impl + 1 неделя shadow-валидация

## Проблема

Текущий regime detector (`services/regime_v2/`) использует **фиксированные пороги** для определения режима (TREND_UP / TREND_DOWN / RANGE / CONSOLIDATION).

Из BACKLOG_TRIGGERS.md:
> При high vol regime detection лагает >15% — пока он переключается на TREND, рынок уже флипнулся обратно в RANGE.

Симптомы:
- `state_snapshot` пишет `4h=RANGE 1h=RANGE 15m=RANGE` сутками подряд, хотя на 15m видны trend-импульсы
- `mtf_conflict` срабатывает 20-27 раз/сутки — режимы разных таймфреймов конфликтуют
- Сетапы блокируются из-за `combo_blocked: regime=consolidation` хотя по факту уже trend

## Цель

1. **Hysteresis** — разные пороги для **входа** и **выхода** из режима. Войти в TREND_UP — нужны 5 баров +0.5%/бар, чтобы выйти — 3 бара -0.3%/бар. Это убирает дребезг.

2. **Adaptive по volatility** — пороги масштабируются от текущего ATR. На high vol пороги шире (нужна сильнее динамика чтобы признать тренд), на low vol — уже.

3. **Confidence layer** — не только `primary` режим, но и `confidence` (0..1). Сетапы тогда могут весить confluence по силе режима.

## Спецификация

### Текущая модель (упрощённо)

```python
def detect_regime(df_1h: DataFrame) -> Regime:
    slope = (df_1h.close.iloc[-1] - df_1h.close.iloc[-N]) / df_1h.close.iloc[-N]
    if slope > THRESHOLD_TREND:
        return Regime.TREND_UP
    elif slope < -THRESHOLD_TREND:
        return Regime.TREND_DOWN
    else:
        return Regime.RANGE
```

`THRESHOLD_TREND` фиксирован (~0.02 = 2%).

### Новая модель

```python
@dataclass
class RegimeState:
    primary: Regime           # текущий режим
    confidence: float         # 0..1, насколько уверены
    bars_in_state: int        # сколько подряд баров в этом режиме
    exit_pressure: float      # 0..1, насколько близко к выходу

def detect_regime_adaptive(
    df_1h: DataFrame,
    prev_state: RegimeState,
) -> RegimeState:
    atr_pct = atr(df_1h, 14) / df_1h.close.iloc[-1]
    
    # Адаптивные пороги: при vol 0.5% порог входа 1.5%, при vol 2% порог 4%
    enter_threshold = max(0.015, atr_pct * 1.8)
    exit_threshold = enter_threshold * 0.55  # hysteresis: выход легче входа
    
    slope = (df_1h.close.iloc[-1] - df_1h.close.iloc[-5]) / df_1h.close.iloc[-5]
    
    # Уже в TREND_UP — проверяем не пора ли выходить
    if prev_state.primary == Regime.TREND_UP:
        if slope > exit_threshold:
            return _continue(prev_state, slope, atr_pct)
        else:
            return RegimeState(primary=Regime.RANGE, confidence=0.4, ...)
    
    # В RANGE — проверяем не пора ли входить в trend
    elif prev_state.primary == Regime.RANGE:
        if slope > enter_threshold and prev_state.bars_in_state > 2:
            return RegimeState(primary=Regime.TREND_UP, confidence=...)
        ...
```

### Confidence формула

```python
confidence = clamp(
    (abs(slope) / enter_threshold) * 0.5    # 0..0.5 от силы движения
    + (bars_in_state / 10) * 0.3            # 0..0.3 от стабильности (cap 10 баров)
    + (1.0 - exit_pressure) * 0.2,          # 0..0.2 если далеко от выхода
    min=0.0, max=1.0,
)
```

## Изменения в коде

| Файл | Изменение |
|------|-----------|
| `services/regime_v2/detector.py` | Заменить `detect_regime` на `detect_regime_adaptive` |
| `services/regime_v2/state.py` | Добавить `RegimeState` dataclass, persist в `state/regime_state.json` |
| `services/setup_detector/confluence_score.py` | Учитывать `regime.confidence` в score (умножать на confidence) |
| `services/setup_detector/combo_filter.py` | `combo_blocked` теперь soft: low confidence → boost penalty, не hard block |

## Валидация (обязательная перед prod)

1. **Shadow A/B на 14 дней:** новый детектор работает параллельно старому, оба пишут в `state/regime_shadow.jsonl`. Сравниваем:
   - Частоту смены режима (новый должен реже флипать)
   - Совпадение с post-hoc разметкой эпизодов
   - Влияние на `combo_blocked` rate

2. **Backtest на 2y BTC 1h:** какой PF был бы у активных стратегий с новым regime detector. Должен быть **≥** текущему.

3. **Replay на инциденте 2026-04-25** (flash dump): новый detector должен поймать TREND_DOWN раньше старого (target: -3 бара).

## Риски

- **Hysteresis может маскировать настоящий разворот** — exit_threshold слишком низкий → застрянем в TREND_UP когда уже dump. Mitigation: hard reset при движении >3% за 1 бар.
- **Confidence layer breaks downstream** — `regime.confidence` нет в текущих сигнатурах функций. Migration phase: writeable только в shadow file, читать только новой версией score.

## Open questions

- Поддерживать `MIXED` regime (когда 4h trend, 1h range)? Сейчас MTF гасит такое. Может стоит явный код.
- Persistence: regime_state.json при рестарте — стартуем с `RANGE confidence=0` или восстанавливаем последнее?
- Timeframes: hysteresis на каждом TF (4h, 1h, 15m) независимо, или один master state?
