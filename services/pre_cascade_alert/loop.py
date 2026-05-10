"""Pre-cascade alert — predicts long/short cascade ~10-30 min ahead.

Reads state/deriv_live.json each minute. Fires when all 3 conditions hold:
  - oi_change_1h_pct  ≥ OI_RISING_PCT  (default +1.5%)
  - |funding_rate_8h| ≥ FUNDING_EXTREME (default 0.0006, i.e. 0.06%/8h)
  - global_ls_ratio   crowded one way (≥ LS_LONG_CROWDED or ≤ LS_SHORT_CROWDED)

Direction:
  - long-crowded (LS≥1.3, funding>0)  → expects SHORT cascade (longs flushed)
  - short-crowded (LS≤0.77, funding<0) → expects LONG cascade (shorts squeezed)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DERIV_LIVE_PATH = ROOT / "state" / "deriv_live.json"
DEDUP_PATH = ROOT / "state" / "pre_cascade_dedup.json"
JOURNAL_PATH = ROOT / "state" / "pre_cascade_fires.jsonl"

POLL_INTERVAL_SEC = 60
SYMBOLS = ("BTCUSDT", "ETHUSDT", "XRPUSDT")

# 2026-05-10: relaxed from 1.5%/0.06%/1.30/0.77 (those gave 0 signals/28d in
# backtest — current 2025-2026 BTC funding mostly negative, LS rarely >1.05).
# New thresholds tuned to actual data range (see PRE_CASCADE_BACKTEST.md).
OI_RISING_PCT = 0.5            # was 1.5
FUNDING_EXTREME = 0.0001       # was 0.0006 (current funding median -0.003%)
LS_LONG_CROWDED = 1.05         # was 1.30 (current LS max 1.08)
LS_SHORT_CROWDED = 0.60        # was 0.77 (current LS min 0.48)

COOLDOWN_SEC = 3600            # 1h between alerts per (symbol, direction)


def _load_dedup() -> dict:
    if not DEDUP_PATH.exists():
        return {}
    try:
        return json.loads(DEDUP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_dedup(d: dict) -> None:
    try:
        DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEDUP_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("pre_cascade.dedup_save_failed")


def _read_deriv_live() -> dict:
    if not DERIV_LIVE_PATH.exists():
        return {}
    try:
        return json.loads(DERIV_LIVE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _journal_append(event: dict) -> None:
    try:
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("pre_cascade.journal_write_failed")


def _evaluate(symbol: str, sym_data: dict) -> tuple[str, dict] | None:
    """Returns (direction, payload) if pre-cascade signature matches, else None.

    direction='short' means: longs are over-crowded → SHORT cascade likely.
    direction='long'  means: shorts are over-crowded → LONG cascade likely.
    """
    oi_change = sym_data.get("oi_change_1h_pct")
    funding = sym_data.get("funding_rate_8h")
    ls = sym_data.get("global_ls_ratio")
    if oi_change is None or funding is None or ls is None:
        return None

    if abs(funding) < FUNDING_EXTREME:
        return None
    if oi_change < OI_RISING_PCT:
        return None

    # long-crowded: LS≥1.3 + positive funding (longs paying shorts)
    if ls >= LS_LONG_CROWDED and funding > 0:
        direction = "short"  # short cascade = longs flushed
    elif ls <= LS_SHORT_CROWDED and funding < 0:
        direction = "long"   # long cascade = shorts squeezed
    else:
        return None

    payload = {
        "symbol": symbol,
        "expected_cascade_direction": direction,
        "oi_change_1h_pct": round(float(oi_change), 2),
        "funding_rate_8h": round(float(funding), 6),
        "global_ls_ratio": round(float(ls), 3),
        "taker_buy_sell_ratio": sym_data.get("taker_buy_sell_ratio"),
        "top_trader_ls_ratio": sym_data.get("top_trader_ls_ratio"),
        "mark_price": sym_data.get("mark_price"),
    }
    return direction, payload


def _format_card(payload: dict) -> str:
    sym = payload["symbol"]
    direction = payload["expected_cascade_direction"]
    arrow = "📉" if direction == "short" else "📈"
    crowded_side = "LONGs" if direction == "short" else "SHORTs"
    bag_warn = "SHORT-bags" if direction == "long" else "LONG-bags"
    return (
        f"{arrow} PRE-CASCADE WARNING {sym} ({direction.upper()} cascade likely)\n"
        f"\n"
        f"Crowding: {crowded_side} переполнены (LS={payload['global_ls_ratio']})\n"
        f"OI 1h: {payload['oi_change_1h_pct']:+.2f}% (быстрый набор позиций)\n"
        f"Funding 8h: {payload['funding_rate_8h']*100:+.4f}% (extreme)\n"
        f"Mark: ${payload['mark_price']:,.2f}\n"
        f"\n"
        f"Прогноз: cascade {direction.upper()} в ближайшие 10-30 мин.\n"
        f"Это раннее предупреждение — закрой {bag_warn} если есть.\n"
        f"Бот не торгует. Историческая precision этого паттерна — собирается."
    )


def _check_one(symbol: str, deriv: dict, now: datetime, dedup: dict, send_fn) -> None:
    sym_data = deriv.get(symbol)
    if not isinstance(sym_data, dict):
        return
    res = _evaluate(symbol, sym_data)
    if res is None:
        return
    direction, payload = res

    key = f"{symbol}_{direction}"
    last = dedup.get(key)
    if last:
        try:
            last_ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if (now - last_ts).total_seconds() < COOLDOWN_SEC:
                return
        except ValueError:
            pass

    text = _format_card(payload)
    logger.warning("pre_cascade.fire symbol=%s dir=%s oi=%.2f%% funding=%.4f%% ls=%.2f",
                   symbol, direction, payload["oi_change_1h_pct"],
                   payload["funding_rate_8h"] * 100, payload["global_ls_ratio"])
    if send_fn is not None:
        try:
            send_fn(text)
        except Exception:
            logger.exception("pre_cascade.send_failed symbol=%s", symbol)
    dedup[key] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    _journal_append({
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "pre_cascade_fire",
        **payload,
    })


async def pre_cascade_alert_loop(stop_event: asyncio.Event, *, send_fn=None,
                                  interval_sec: int = POLL_INTERVAL_SEC) -> None:
    """Async loop. Every 60s checks each symbol for pre-cascade signature."""
    if send_fn is None:
        logger.warning("pre_cascade.no_send_fn — alerts будут только в логе")
    logger.info(
        "pre_cascade.start interval=%ds OI>=%.1f%% funding>=%.4f LS>=%.2f or<=%.2f",
        interval_sec, OI_RISING_PCT, FUNDING_EXTREME, LS_LONG_CROWDED, LS_SHORT_CROWDED,
    )

    while not stop_event.is_set():
        try:
            now = datetime.now(timezone.utc)
            deriv = _read_deriv_live()
            dedup = _load_dedup()
            for symbol in SYMBOLS:
                _check_one(symbol, deriv, now, dedup, send_fn)
            _save_dedup(dedup)
        except Exception:
            logger.exception("pre_cascade.tick_failed")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
