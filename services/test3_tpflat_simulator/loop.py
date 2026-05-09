"""TEST_3 TP-flat paper simulator.

State machine (per tick, 60s):
  IDLE  → if SHORT gate (EMA50>EMA200 & close>EMA50 on 1h) fires → OPEN
  OPEN  → emit OPEN event, set entry=close, extreme=close
  TRACK → on each tick:
            extreme = max(extreme, current_high)
            if low_now <= entry*(1 - tp_usd/base_size) → CLOSE (tp_hit), record PnL, IDLE+immediate
            elif (extreme-entry)/entry >= dd_cap_pct → CLOSE (forced), record PnL, IDLE
  IDLE (post-close, immediate reentry):
            if SHORT gate still True next tick → OPEN at close[i+1]
            else wait for fresh gate
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "state" / "test3_tpflat_state.json"
JOURNAL_PATH = ROOT / "state" / "test3_tpflat_paper.jsonl"

POLL_INTERVAL_SEC = 60
SYMBOL = "BTCUSDT"
TP_USD = 10.0
DD_CAP_PCT = 3.0
BASE_SIZE_USD = 1000.0
FEE_BPS = 5.0  # 0.05% per side, taker
DIRECTION = "short"  # TEST_3 is SHORT linear BTCUSDT


@dataclass
class _State:
    in_pos: bool = False
    entry: float = 0.0
    entry_ts: str = ""
    extreme: float = 0.0  # running high (SHORT) — adverse tracker
    last_close_price: float = 0.0  # for immediate reentry
    n_tp: int = 0
    n_forced: int = 0
    realized_pnl_usd: float = 0.0
    volume_usd: float = 0.0


def _load_state() -> _State:
    if not STATE_PATH.exists():
        return _State()
    try:
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return _State(**d)
    except (OSError, ValueError, TypeError):
        logger.exception("test3_tpflat.state_load_failed; resetting")
        return _State()


def _save_state(s: _State) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")
    except OSError:
        logger.exception("test3_tpflat.state_save_failed")


def _journal_append(event: dict) -> None:
    try:
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("test3_tpflat.journal_write_failed")


def _ema(values: list[float], n: int) -> float:
    if len(values) < n:
        return values[-1] if values else 0.0
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def _short_gate(closes_1h: list[float]) -> bool:
    if len(closes_1h) < 200:
        return False
    e50 = _ema(closes_1h[-220:], 50)
    e200 = _ema(closes_1h[-220:], 200)
    last = closes_1h[-1]
    # SHORT direction: e50>e200 AND close>e50 (uptrend → bot opens SHORT to fade)
    return e50 > e200 and last > e50


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fee_dollar(notional: float) -> float:
    return notional * (FEE_BPS / 10000.0)


def _check_and_act(closes_1h: list[float], current_price: float,
                   high_now: float, low_now: float, state: _State) -> None:
    """One tick of the TP-flat state machine. Mutates `state` in place,
    appends events to journal."""
    gate = _short_gate(closes_1h)

    if not state.in_pos:
        if not gate:
            return
        # OPEN
        state.in_pos = True
        state.entry = current_price
        state.entry_ts = _now_iso()
        state.extreme = current_price
        state.volume_usd += BASE_SIZE_USD
        _journal_append({
            "ts": state.entry_ts, "event": "OPEN", "side": DIRECTION,
            "entry": round(current_price, 2), "size_usd": BASE_SIZE_USD,
            "tp_usd": TP_USD, "dd_cap_pct": DD_CAP_PCT,
            "trigger": "EMA50>EMA200 & close>EMA50 (1h)",
        })
        logger.info("test3_tpflat.OPEN entry=%.2f", current_price)
        return

    # In position — update extreme
    state.extreme = max(state.extreme, high_now)
    adverse_pct = (state.extreme - state.entry) / state.entry * 100.0

    # TP target price (SHORT closes by buying back at lower price)
    tp_price = state.entry * (1 - TP_USD / BASE_SIZE_USD)
    tp_hit = low_now <= tp_price

    if tp_hit:
        # Close at exact TP price
        gross = (state.entry - tp_price) / state.entry * BASE_SIZE_USD
        fees = 2 * _fee_dollar(BASE_SIZE_USD)
        pnl = gross - fees
        state.realized_pnl_usd += pnl
        state.volume_usd += BASE_SIZE_USD
        state.n_tp += 1
        state.last_close_price = tp_price
        _journal_append({
            "ts": _now_iso(), "event": "CLOSE_TP", "side": DIRECTION,
            "entry": round(state.entry, 2), "exit": round(tp_price, 2),
            "size_usd": BASE_SIZE_USD, "pnl_usd": round(pnl, 2),
            "fees_usd": round(fees, 2),
            "cum_realized_usd": round(state.realized_pnl_usd, 2),
            "n_tp": state.n_tp, "n_forced": state.n_forced,
        })
        logger.info("test3_tpflat.CLOSE_TP pnl=%.2f cum=%.2f", pnl, state.realized_pnl_usd)
        state.in_pos = False
        state.entry = 0.0
        state.entry_ts = ""
        state.extreme = 0.0
        # IMMEDIATE reentry: if gate still True next tick, OPEN happens then
        return

    if adverse_pct >= DD_CAP_PCT:
        # Forced close at current price
        gross = (state.entry - current_price) / state.entry * BASE_SIZE_USD
        fees = 2 * _fee_dollar(BASE_SIZE_USD)
        pnl = gross - fees
        state.realized_pnl_usd += pnl
        state.volume_usd += BASE_SIZE_USD
        state.n_forced += 1
        _journal_append({
            "ts": _now_iso(), "event": "CLOSE_FORCED", "side": DIRECTION,
            "entry": round(state.entry, 2), "exit": round(current_price, 2),
            "size_usd": BASE_SIZE_USD, "pnl_usd": round(pnl, 2),
            "fees_usd": round(fees, 2),
            "adverse_pct": round(adverse_pct, 2),
            "cum_realized_usd": round(state.realized_pnl_usd, 2),
            "n_tp": state.n_tp, "n_forced": state.n_forced,
        })
        logger.warning("test3_tpflat.CLOSE_FORCED pnl=%.2f adverse=%.2f%% cum=%.2f",
                       pnl, adverse_pct, state.realized_pnl_usd)
        state.in_pos = False
        state.entry = 0.0
        state.entry_ts = ""
        state.extreme = 0.0


async def test3_tpflat_simulator_loop(stop_event: asyncio.Event,
                                       interval_sec: int = POLL_INTERVAL_SEC) -> None:
    """Async loop. Polls BTC 1m+1h, ticks TP-flat state machine, journals events."""
    logger.info("test3_tpflat.start interval=%ds tp=$%.0f dd=%.1f%% size=$%.0f reentry=immediate",
                interval_sec, TP_USD, DD_CAP_PCT, BASE_SIZE_USD)

    while not stop_event.is_set():
        try:
            from core.data_loader import load_klines
            df_1m = load_klines(symbol=SYMBOL, timeframe="1m", limit=2)
            df_1h = load_klines(symbol=SYMBOL, timeframe="1h", limit=250)
            if df_1m is None or len(df_1m) < 1 or df_1h is None or len(df_1h) < 200:
                logger.warning("test3_tpflat.data_thin")
            else:
                closes_1h = df_1h["close"].astype(float).tolist()
                current = float(df_1m["close"].iloc[-1])
                high_now = float(df_1m["high"].iloc[-1])
                low_now = float(df_1m["low"].iloc[-1])
                state = _load_state()
                _check_and_act(closes_1h, current, high_now, low_now, state)
                _save_state(state)
        except Exception:
            logger.exception("test3_tpflat.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
