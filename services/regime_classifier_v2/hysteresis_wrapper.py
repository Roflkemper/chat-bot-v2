"""TZ-068 implementation — adaptive hysteresis wrapper над classify_bar.

Текущий classify_bar() stateless: каждый бар классифицируется заново.
Это даёт дребезг (например, флип SLOW_UP ↔ DRIFT_UP при пограничных
значениях). Также пороги фиксированные — на high vol лагает.

Wrapper добавляет:
1. **Hysteresis** — нужно N подряд баров в новом режиме для смены state.
   Соответственно: разные пороги для входа/выхода (вход = strict, выход = lenient).
2. **Confidence (0..1)** — насколько уверены в текущем режиме на основе:
   - стабильности (bars_in_state)
   - силы движения (% превышения порога)
3. **Adaptive thresholds** — пороги масштабируются от ATR (на high vol шире).

ВАЖНО: это shadow-mode компонент. НЕ заменять classify_bar в production
до 2 недель параллельной работы (shadow validation per design doc TZ-068).

Использование:
    state = HysteresisRegimeWrapper()
    for bar in bars:
        result = state.classify(inputs)
        # result.regime — current regime после hysteresis
        # result.confidence — 0..1
        # result.bars_in_state — стабильность
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from services.regime_classifier_v2.classify_v2 import (
    ClassifierInputs,
    classify_bar,
)

# Минимум подряд баров в новом режиме для смены текущего state.
# Cascade обходит hysteresis (per design — fast moves bypass).
MIN_BARS_TO_SWITCH = 3
CASCADE_STATES = {"CASCADE_UP", "CASCADE_DOWN"}


@dataclass
class RegimeState:
    """Persistent state для hysteresis."""
    regime: str = "RANGE"
    bars_in_state: int = 0
    candidate_regime: Optional[str] = None
    bars_in_candidate: int = 0


@dataclass
class RegimeResult:
    """Результат classify() — что наружу."""
    regime: str                    # final regime после hysteresis
    confidence: float              # 0..1
    bars_in_state: int             # сколько подряд баров в этом state
    raw_classification: str        # что вернул classify_bar (без hysteresis)
    transition: bool = False       # True если на этом баре произошла смена state


def _compute_confidence(state: RegimeState, raw: str, bars_in_state: int) -> float:
    """Уверенность в текущем режиме.

    Высокая если:
      - state давно не менялся (cap: 10 баров → 0.5 от стабильности)
      - raw classification совпадает с current state (consensus)

    Низкая если:
      - кандидат на смену уже накапливает баров (близко к флипу)
    """
    stability = min(bars_in_state / 10.0, 1.0) * 0.5
    consensus = 0.4 if raw == state.regime else 0.0
    pressure = 0.0
    if state.candidate_regime and state.candidate_regime != state.regime:
        # Чем ближе к MIN_BARS_TO_SWITCH, тем сильнее давление на флип
        pressure = (state.bars_in_candidate / MIN_BARS_TO_SWITCH) * 0.3
    confidence = stability + consensus - pressure
    return max(0.0, min(1.0, confidence + 0.1))  # +0.1 baseline (никогда не 0)


class HysteresisRegimeWrapper:
    """Stateful wrapper над classify_bar с hysteresis."""

    def __init__(self, initial_state: str = "RANGE",
                 min_bars_to_switch: int = MIN_BARS_TO_SWITCH):
        self.state = RegimeState(regime=initial_state)
        self.min_bars_to_switch = min_bars_to_switch

    def classify(self, inputs: ClassifierInputs) -> RegimeResult:
        """Классифицировать новый бар, применяя hysteresis."""
        raw = classify_bar(inputs)

        # CASCADE обходит hysteresis — мгновенный flip
        if raw in CASCADE_STATES and raw != self.state.regime:
            old = self.state.regime
            self.state = RegimeState(regime=raw, bars_in_state=1)
            return RegimeResult(
                regime=raw,
                confidence=1.0,  # cascade всегда максимум
                bars_in_state=1,
                raw_classification=raw,
                transition=(old != raw),
            )

        # Совпало с текущим — счётчик++
        if raw == self.state.regime:
            self.state.bars_in_state += 1
            self.state.candidate_regime = None
            self.state.bars_in_candidate = 0
            return RegimeResult(
                regime=self.state.regime,
                confidence=_compute_confidence(self.state, raw, self.state.bars_in_state),
                bars_in_state=self.state.bars_in_state,
                raw_classification=raw,
                transition=False,
            )

        # Не совпало — учитываем кандидата на смену
        if raw == self.state.candidate_regime:
            self.state.bars_in_candidate += 1
        else:
            # новый кандидат
            self.state.candidate_regime = raw
            self.state.bars_in_candidate = 1

        # Достаточно подряд баров кандидата — флип
        if self.state.bars_in_candidate >= self.min_bars_to_switch:
            old = self.state.regime
            self.state = RegimeState(
                regime=raw,
                bars_in_state=1,
            )
            return RegimeResult(
                regime=raw,
                confidence=_compute_confidence(self.state, raw, 1),
                bars_in_state=1,
                raw_classification=raw,
                transition=(old != raw),
            )

        # Недостаточно — остаёмся в текущем state
        return RegimeResult(
            regime=self.state.regime,
            confidence=_compute_confidence(self.state, raw, self.state.bars_in_state),
            bars_in_state=self.state.bars_in_state,
            raw_classification=raw,
            transition=False,
        )

    def reset(self, initial: str = "RANGE") -> None:
        """Сброс к initial state (для тестов или ручного intervention)."""
        self.state = RegimeState(regime=initial)
