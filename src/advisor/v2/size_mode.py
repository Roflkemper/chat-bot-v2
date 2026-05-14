"""Size mode picker for advisor v2."""
from __future__ import annotations

from .portfolio import PortfolioState

MODE_TO_SIZE: dict[str, float] = {
    "conservative": 0.05,
    "normal": 0.10,
    "aggressive": 0.18,
}


def pick_size_mode(portfolio: PortfolioState) -> tuple[str, str]:
    """Return (mode, reason). Mode: 'conservative' | 'normal' | 'aggressive'."""
    dd = portfolio.dd_pct
    free_margin = portfolio.free_margin_pct
    has_dd = portfolio.has_open_dd

    if dd > 5.0 or free_margin < 30.0 or has_dd:
        reasons: list[str] = []
        if dd > 5.0:
            reasons.append(f"DD {dd:.1f}%>5%")
        if free_margin < 30.0:
            reasons.append(f"margin {free_margin:.0f}%<30%")
        if has_dd:
            dd_bots = [b for b in portfolio.bots if b.current_profit < 0 and b.position not in ("", "NONE")]
            dd_total = sum(b.current_profit for b in dd_bots)
            reasons.append(f"просадка {len(dd_bots)} бот(ов) (${dd_total:+.0f})")
        return "conservative", "; ".join(reasons) or "условия conservative"

    if free_margin > 60.0 and not has_dd:
        return "aggressive", f"margin {free_margin:.0f}%>60%, нет DD"

    return "normal", f"margin {free_margin:.0f}%, стандарт"
