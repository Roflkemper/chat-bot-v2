"""Rule-based alert detection for /portfolio command."""
from __future__ import annotations

from .config import DD_ALERT_PCT, LIQ_ALERT_PCT
from .data_source import BotData


def compute_alerts(bots: list[BotData]) -> list[str]:
    """Return list of alert lines. Empty list if nothing to report."""
    idle_bots: list[str] = []
    dd_bots: list[str] = []
    liq_bots: list[str] = []
    failed_bots: list[str] = []

    for bot in bots:
        dname = _display_name(bot)

        # Idle > 6h: inFilledCount unchanged between 6h-ago snapshot and now
        if bot.source == "csv" and bot.in_filled_count == bot.in_filled_count_6h_ago:
            idle_bots.append(dname)

        # DD > threshold: unrealized loss relative to balance
        if bot.balance > 0 and bot.current_profit < 0:
            dd_pct = abs(bot.current_profit) / bot.balance * 100
            if dd_pct > DD_ALERT_PCT:
                dd_bots.append(f"{dname} ({dd_pct:.1f}%)")

        # Distance to liquidation < threshold
        liq_dist = liq_distance_pct(bot)
        if liq_dist is not None and 0 < liq_dist < LIQ_ALERT_PCT:
            liq_bots.append(f"{dname} ({liq_dist:.1f}%)")

        # Failed / error bots
        if bot.status.lower() in ("failed", "error"):
            failed_bots.append(dname)

    alerts: list[str] = []
    if idle_bots:
        alerts.append("  • Без сработок >6ч: " + ", ".join(idle_bots))
    if dd_bots:
        alerts.append(f"  • DD >{DD_ALERT_PCT:.0f}%: " + ", ".join(dd_bots))
    if liq_bots:
        alerts.append(f"  • Близко к ликвидации (<{LIQ_ALERT_PCT:.0f}%): " + ", ".join(liq_bots))
    if failed_bots:
        alerts.append("  • Статус Failed: " + ", ".join(failed_bots))

    return alerts


def liq_distance_pct(bot: BotData) -> float | None:
    """Distance from entry price to liquidation price, in percent. None if not applicable."""
    if bot.position == 0 or bot.average_price == 0 or bot.liquidation_price == 0:
        return None
    return abs(bot.liquidation_price - bot.average_price) / bot.average_price * 100


def _display_name(bot: BotData) -> str:
    return bot.alias if bot.alias else bot.name[:20].strip()
