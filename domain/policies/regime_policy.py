from __future__ import annotations


class RegimePolicy:
    def allow(self, market_regime: str, strategy_id: str) -> bool:
        return True
