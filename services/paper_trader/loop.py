"""Paper trader async loop — pulls new setups + tracks open trades.

Runs every 60 seconds:
  1. Read setups.jsonl → find any new OPEN-eligible setups (conf>=60, not yet papered)
  2. Open paper trade if any
  3. Get current BTC price
  4. Update open trades (close TP/SL hits)
  5. Telegram alerts for opens/closes
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from services.paper_trader import journal, trader
from services.setup_detector.models import (
    Setup,
    SetupBasis,
    SetupStatus,
    SetupType,
    make_setup,
)

logger = logging.getLogger(__name__)

LOOP_INTERVAL_SEC = 60
SETUPS_PATH = Path("state/setups.jsonl")
DEDUP_PATH = Path("state/paper_trader_dedup.json")  # tracks setup_ids already opened


def _load_dedup() -> set[str]:
    if not DEDUP_PATH.exists():
        return set()
    try:
        return set(json.loads(DEDUP_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def _save_dedup(seen: set[str]) -> None:
    DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        DEDUP_PATH.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except OSError:
        pass


def _read_recent_setups() -> list[dict]:
    """Read raw setup JSON dicts from setups.jsonl."""
    if not SETUPS_PATH.exists():
        return []
    out: list[dict] = []
    try:
        for line in SETUPS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as exc:
        logger.warning("paper_trader.loop.read_setups_failed: %s", exc)
    return out


def _setup_from_dict(d: dict) -> Setup | None:
    """Reconstruct minimal Setup from journal dict.

    setups.jsonl writes a flat dict; we reconstruct just enough fields for
    paper_trader.open_paper_trade().
    """
    try:
        setup_type = SetupType(d["setup_type"])
    except (KeyError, ValueError):
        return None
    try:
        detected_at = datetime.fromisoformat(d.get("detected_at", "").replace("Z", "+00:00"))
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        detected_at = datetime.now(timezone.utc)

    basis_raw = d.get("basis") or []
    basis = []
    for b in basis_raw:
        try:
            basis.append(SetupBasis(label=b["label"], value=b["value"], weight=float(b.get("weight", 0))))
        except (KeyError, TypeError):
            continue

    return make_setup(
        setup_type=setup_type,
        pair=d.get("pair", "BTCUSDT"),
        current_price=float(d.get("current_price", 0)),
        regime_label=d.get("regime_label", "unknown"),
        session_label=d.get("session_label", "unknown"),
        entry_price=d.get("entry_price"),
        stop_price=d.get("stop_price"),
        tp1_price=d.get("tp1_price"),
        tp2_price=d.get("tp2_price"),
        risk_reward=d.get("risk_reward"),
        strength=int(d.get("strength", 0)),
        confidence_pct=float(d.get("confidence_pct", 0)),
        basis=tuple(basis),
        cancel_conditions=tuple(d.get("cancel_conditions") or ()),
        window_minutes=int(d.get("window_minutes", 120)),
        portfolio_impact_note=d.get("portfolio_impact_note", ""),
        detected_at=detected_at,
    )


def _get_current_price() -> float | None:
    """Read latest BTC price from market_live/market_1m.csv."""
    p = Path("market_live/market_1m.csv")
    if not p.exists():
        return None
    try:
        # Read last line efficiently
        with p.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            block = min(2048, size)
            fh.seek(-block, 2)
            data = fh.read().decode("utf-8", errors="replace")
        last_line = None
        for line in data.splitlines():
            if line.strip() and not line.startswith("ts_utc"):
                last_line = line
        if last_line:
            parts = last_line.strip().split(",")
            if len(parts) >= 5:
                return float(parts[4])
    except (OSError, ValueError):
        pass
    return None


def _format_open_alert(record: dict) -> str:
    side = "📈 PAPER LONG" if record["side"] == "long" else "📉 PAPER SHORT"
    entry = record["entry"]
    sl = record["sl"]
    tp1 = record.get("tp1") or "n/a"
    tp2 = record.get("tp2") or "n/a"
    rr = record.get("rr_planned") or "n/a"
    setup = record["setup_type"]
    conf = record["confidence_pct"]
    reason = record.get("reason", "")
    return (
        f"{side} @ {entry:.0f} | SL {sl:.0f} | TP1 {tp1 if isinstance(tp1, str) else f'{tp1:.0f}'} "
        f"| TP2 {tp2 if isinstance(tp2, str) else f'{tp2:.0f}'} | RR {rr}\n"
        f"setup: {setup} | conf {conf:.0f}% | {reason}"
    )


def _format_close_alert(event: dict) -> str:
    action = event["action"]
    pnl = event["realized_pnl_usd"]
    rr = event["rr_realized"]
    hours = event["hours_in_trade"]
    side = event["side"]
    setup = event["setup_type"]
    icon = {"TP1": "✅", "TP2": "🎯", "SL": "🛑", "EXPIRE": "⏱️"}.get(action, "•")
    sign = "+" if pnl > 0 else ""
    return (
        f"{icon} PAPER {action} | {setup} ({side}) | "
        f"{sign}${pnl:.0f} | RR {rr:+.2f} | {hours:.1f}h"
    )


async def paper_trader_loop(
    stop_event: asyncio.Event,
    *,
    send_fn: Callable[[str], None] | None = None,
    interval_sec: int = LOOP_INTERVAL_SEC,
) -> None:
    """Main async loop. Runs until stop_event is set."""
    logger.info("paper_trader.loop.start interval=%ds", interval_sec)
    seen_setup_ids = _load_dedup()
    while not stop_event.is_set():
        try:
            # 1. New setups → open paper trades
            setups_raw = _read_recent_setups()
            new_setups = [s for s in setups_raw if s.get("setup_id") not in seen_setup_ids]
            for raw in new_setups:
                seen_setup_ids.add(raw.get("setup_id", ""))
                setup = _setup_from_dict(raw)
                if setup is None:
                    continue
                opened = trader.open_paper_trade(setup)
                if opened and send_fn:
                    try:
                        send_fn(_format_open_alert(opened))
                    except Exception:
                        logger.exception("paper_trader.loop.send_open_failed")
            if new_setups:
                _save_dedup(seen_setup_ids)

            # 2. Update open trades with current price
            price = _get_current_price()
            if price is not None and price > 0:
                closes = trader.update_open_trades(price)
                for ev in closes:
                    if send_fn:
                        try:
                            send_fn(_format_close_alert(ev))
                        except Exception:
                            logger.exception("paper_trader.loop.send_close_failed")
        except Exception:
            logger.exception("paper_trader.loop.iteration_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
    logger.info("paper_trader.loop.stopped")
