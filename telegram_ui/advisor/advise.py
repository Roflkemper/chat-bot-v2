"""/advise command — on-demand market + portfolio snapshot."""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_MARKET_LIVE = _ROOT / "market_live"
_GINAREA_LIVE = _ROOT / "ginarea_tracker" / "ginarea_live"

SIGNALS_CSV = _MARKET_LIVE / "signals.csv"
OHLCV_1M = _MARKET_LIVE / "market_1m.csv"
OHLCV_15M = _MARKET_LIVE / "market_15m.csv"
OHLCV_1H = _MARKET_LIVE / "market_1h.csv"
PARAMS_CSV = _GINAREA_LIVE / "params.csv"
SNAPSHOTS_CSV = _GINAREA_LIVE / "snapshots.csv"

SIGNALS_WINDOW_SEC = 1800  # 30 min


def _read_last_close(path: Path) -> float | None:
    if not path.exists():
        return None
    last: float | None = None
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                last = float(row["close"])
            except (KeyError, ValueError):
                pass
    return last


def _get_active_signals(window_sec: int) -> list[dict]:
    if not SIGNALS_CSV.exists():
        return []
    cutoff = time.time() - window_sec
    result: list[dict] = []
    with SIGNALS_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row.get("ts_utc", "")).timestamp()
                if ts >= cutoff:
                    result.append({
                        "ts": row.get("ts_utc", ""),
                        "signal": row.get("signal_type", ""),
                        "details": json.loads(row.get("details_json", "{}") or "{}"),
                    })
            except Exception:
                continue
    return result


def _get_portfolio_summary() -> dict:
    if not SNAPSHOTS_CSV.exists():
        return {}
    latest: dict[str, dict] = {}
    with SNAPSHOTS_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            bot_id = row.get("bot_id", "")
            if not bot_id:
                continue
            ts = row.get("ts_utc", "")
            existing = latest.get(bot_id)
            if existing is None or ts > existing.get("ts_utc", ""):
                latest[bot_id] = dict(row)

    total_unrealized = 0.0
    total_position = 0.0
    liq_distances: list[float] = []
    danger_bots: list[str] = []
    active_count = 0

    for row in latest.values():
        status = row.get("status", "")
        if status in ("failed", "error", "stopped"):
            continue
        active_count += 1
        try:
            total_position += abs(float(row.get("position", 0) or 0))
        except ValueError:
            pass
        try:
            total_unrealized += float(row.get("current_profit", 0) or 0)
        except ValueError:
            pass
        try:
            liq = float(row.get("liquidation_price", 0) or 0)
            avg = float(row.get("average_price", 0) or 0)
            pos = float(row.get("position", 0) or 0)
            if liq > 0 and avg > 0 and pos != 0:
                dist = abs(liq - avg) / avg * 100.0
                liq_distances.append(dist)
                if dist < 25.0:
                    name = row.get("bot_name", row.get("bot_id", "?"))
                    danger_bots.append(f"{name} ({dist:.1f}%)")
        except (ValueError, ZeroDivisionError):
            pass

    result: dict = {
        "active_count": active_count,
        "total_bots": len(latest),
        "total_unrealized": round(total_unrealized, 2),
        "total_position": round(total_position, 4),
        "danger_bots": danger_bots,
    }
    if liq_distances:
        sorted_dists = sorted(liq_distances)
        result["liq_dist_min"] = round(sorted_dists[0], 1)
        result["liq_dist_median"] = round(sorted_dists[len(sorted_dists) // 2], 1)
    return result


def handle_advise_command() -> str:
    try:
        from market_collector.indicators import (
            compute_atr_from_csv, compute_move_pct_from_csv, compute_rsi_from_csv,
        )
        from market_collector.levels import get_levels
        has_market = True
    except ImportError:
        has_market = False

    lines: list[str] = []

    # Price
    price = _read_last_close(OHLCV_1M)
    price_str = f"{price:,.0f}" if price else "н/д"
    lines.append(f"BTC: {price_str} USDT")

    if has_market:
        # RSI
        rsi_1h = compute_rsi_from_csv(OHLCV_1H)
        rsi_15m = compute_rsi_from_csv(OHLCV_15M)
        rsi_1h_s = f"{rsi_1h}" if rsi_1h is not None else "н/д"
        rsi_15m_s = f"{rsi_15m}" if rsi_15m is not None else "н/д"
        lines.append(f"RSI 1h: {rsi_1h_s}  RSI 15m: {rsi_15m_s}")

        # ATR
        atr_1h = compute_atr_from_csv(OHLCV_1H)
        lines.append(f"ATR 1h: {atr_1h if atr_1h is not None else 'н/д'}")

        # Move %
        def _fmt_move(v: float | None) -> str:
            if v is None:
                return "н/д"
            sign = "+" if v >= 0 else ""
            return f"{sign}{v:.2f}%"
        m1h = compute_move_pct_from_csv(OHLCV_1H, 1)
        m4h = compute_move_pct_from_csv(OHLCV_1H, 4)
        m24h = compute_move_pct_from_csv(OHLCV_1H, 24)
        lines.append(f"Движение: 1ч {_fmt_move(m1h)}  4ч {_fmt_move(m4h)}  24ч {_fmt_move(m24h)}")
        lines.append("")

        # Levels
        if price:
            lvls = get_levels(price, PARAMS_CSV if PARAMS_CSV.exists() else None, count=3)
            above_s = " | ".join(f"{l:,.0f}" for l in lvls.above[:3]) or "н/д"
            below_s = " | ".join(f"{l:,.0f}" for l in lvls.below[:3]) or "н/д"
            lines.append(f"Уровни выше: {above_s}")
            lines.append(f"Уровни ниже: {below_s}")
        else:
            lines.append("Уровни: нет данных о цене")
    else:
        lines.append("(market_collector не установлен — рыночные данные недоступны)")
    lines.append("")

    # Signals
    signals = _get_active_signals(SIGNALS_WINDOW_SEC)
    if signals:
        lines.append(f"Сигналы за 30 мин ({len(signals)} шт):")
        for s in signals:
            ts_s = s["ts"][11:19] if len(s["ts"]) >= 19 else s["ts"]
            details = s.get("details", {})
            detail_s = "  ".join(f"{k}={v}" for k, v in details.items())
            lines.append(f"  [{ts_s}] {s['signal']}  {detail_s}")
    else:
        lines.append("Сигналы за 30 мин: нет")
    lines.append("")

    # Portfolio
    pf = _get_portfolio_summary()
    if pf:
        lines.append(f"Портфель: {pf.get('active_count', 0)}/{pf.get('total_bots', 0)} ботов активны")
        lines.append(f"Позиция: {pf.get('total_position', 0):.4f} BTC")
        lines.append(f"Unrealized P&L: {pf.get('total_unrealized', 0):+.2f} USDT")
        if "liq_dist_min" in pf:
            lines.append(
                f"До ликвидации: мин {pf['liq_dist_min']}%  медиана {pf.get('liq_dist_median', '?')}%"
            )
        if pf.get("danger_bots"):
            lines.append(f"Опасная зона (<25%): {', '.join(pf['danger_bots'])}")
    else:
        lines.append("Портфель: нет данных")

    return "\n".join(lines)
