"""Format portfolio data into Telegram message(s)."""
from __future__ import annotations

from datetime import datetime, timezone

from .alerts import liq_distance_pct
from .config import MSG_CHAR_LIMIT
from .data_source import BotData

_STATUS_EMOJI: dict[str, str] = {
    "active": "✅",
    "paused": "⏸",
    "failed": "⛔",
    "stopping": "🔴",
    "stopped": "⏹",
}
_DIVIDER = "━" * 28


def format_portfolio(
    bots: list[BotData],
    alerts: list[str],
    ts: datetime | None = None,
) -> list[str]:
    """Return list of Telegram messages (each ≤ MSG_CHAR_LIMIT chars)."""
    if ts is None:
        ts = datetime.now(timezone.utc)

    sorted_bots = sorted(bots, key=lambda b: b.trade_volume - b.trade_volume_24h_ago, reverse=True)

    lines: list[str] = []
    lines.append(f"📊 ПОРТФЕЛЬ GINAREA | {ts.strftime('%d.%m %H:%M UTC')}")
    lines.append("")
    lines.extend(_format_summary(bots))
    lines.append("")
    lines.append("ПО БОТАМ (сортировка: volume 24ч, desc)")
    lines.append(_DIVIDER)

    for bot in sorted_bots:
        lines.append("")
        lines.extend(_format_bot(bot))

    lines.append("")
    lines.append(_DIVIDER)

    if alerts:
        lines.append("⚠️ ВНИМАНИЕ")
        lines.extend(alerts)

    return _split_messages("\n".join(lines))


def _format_summary(bots: list[BotData]) -> list[str]:
    # Separate USDT-denominated (balance ≥ 1) from crypto-denominated (balance < 1 but > 0)
    usdt_now = sum(b.balance for b in bots if b.balance >= 1)
    usdt_24h = sum(b.balance_24h_ago for b in bots if b.balance_24h_ago >= 1)
    btc_balance = sum(b.balance for b in bots if 0 < b.balance < 1)

    unrealized = sum(b.current_profit for b in bots if b.position != 0)
    vol_24h = sum(b.trade_volume - b.trade_volume_24h_ago for b in bots)
    active_count = sum(1 for b in bots if b.position != 0)
    total_count = len(bots)

    lines = ["СУММАРНО"]

    if usdt_now:
        delta = usdt_now - usdt_24h
        sign = "+" if delta >= 0 else ""
        delta_pct_str = ""
        if usdt_24h:
            delta_pct = delta / usdt_24h * 100
            delta_pct_str = f" / {sign}{delta_pct:.1f}% 24ч"
        lines.append(f"  Balance:    ${usdt_now:,.0f} ({sign}${delta:,.0f}{delta_pct_str})")

    if btc_balance:
        lines.append(f"  Balance BTC: {btc_balance:.5f}")

    sign_u = "+" if unrealized >= 0 else ""
    lines.append(f"  Unrealized: {sign_u}${unrealized:,.2f}")
    lines.append(f"  Volume 24ч: ${vol_24h:,.0f}")
    lines.append(f"  Активных:   {active_count} / {total_count}")

    return lines


def _format_bot(bot: BotData) -> list[str]:
    dname = bot.alias if bot.alias else bot.name[:20].strip()
    emoji = _STATUS_EMOJI.get(bot.status.lower(), "▫️") if bot.status else "▫️"
    status_str = bot.status if bot.status else "—"

    pnl_24h = bot.profit_now - bot.profit_24h_ago
    vol_24h = bot.trade_volume - bot.trade_volume_24h_ago
    pnl_str = f"+${pnl_24h:,.2f}" if pnl_24h >= 0 else f"-${abs(pnl_24h):,.2f}"

    lines: list[str] = []
    lines.append(f"{emoji} {dname}  · {bot.side} · {status_str}")
    lines.append(f"   PnL: {pnl_str} (24ч) | Vol: ${vol_24h:,.0f}")

    if bot.position != 0:
        entry_str = f" · entry: ${bot.average_price:,.0f}" if bot.average_price else ""
        lines.append(f"   Pos: {bot.position:.4f}{entry_str}")

        dist = liq_distance_pct(bot)
        if dist is not None:
            warn = " 🚨" if dist < 25.0 else ""
            lines.append(f"   Liq: {dist:.1f}% до ликвидации{warn}")
    else:
        lines.append("   Pos: 0 · нет позиции")

    return lines


def _split_messages(text: str, limit: int = MSG_CHAR_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")

    return parts or [text]
