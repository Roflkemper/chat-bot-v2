"""Range Hunter — TG-emitter для полу-ручной mean-revert стратегии.

Стратегия (бэктест 2y BTC 1m, см. scripts/range_hunter_backtest.py + walkforward):
- Раз в минуту проверяем условия 'ренжа': низкая волатильность, узкий диапазон, нет тренда
- При срабатывании — TG-карточка с готовыми BUY/SELL уровнями
- Оператор руками ставит 2 лимитки post-only на BitMEX
- Inline-кнопки [✅ Placed both] / [⏭ Skip] для журналирования

Walk-forward 4 фолда: WR 66-70%, PnL все 4 в плюсе, DD ≤ $222.
Fill-rate sensitivity: edge живой при p ≥ 0.65 (typical BitMEX maker = 0.75-0.85).
"""
from services.range_hunter.signal import (
    DEFAULT_PARAMS,
    RangeHunterParams,
    RangeHunterSignal,
    compute_signal,
)

__all__ = [
    "DEFAULT_PARAMS",
    "RangeHunterParams",
    "RangeHunterSignal",
    "compute_signal",
]
