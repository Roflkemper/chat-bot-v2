"""Range Hunter live loop — генерирует TG-сигналы + следит за outcome.

Два независимых цикла:
1. signal_loop — раз в минуту читает market_live/market_1m.csv, считает фильтры,
   при срабатывании шлёт TG-карточку + пишет в журнал.
2. outcome_loop — раз в минуту проходит по pending signals (user_action="placed"),
   симулирует fill BUY/SELL/SL/timeout на свежих 1m данных, пишет результат.

Cooldown: 2h после signal (any direction) — не шлём повторных пока не пройдёт.
"""
from __future__ import annotations

import asyncio
import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from services.range_hunter.signal import (
    DEFAULT_PARAMS,
    RangeHunterParams,
    RangeHunterSignal,
    compute_signal,
    format_tg_card,
)
from services.range_hunter.journal import (
    JOURNAL_PATH,
    append_signal,
    pending_signals,
    read_all,
    signal_id_from_ts,
    update_record,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
MARKET_1M_CSV = ROOT / "market_live" / "market_1m.csv"
STATE_PATH = ROOT / "state" / "range_hunter_state.json"

POLL_INTERVAL_SEC = 60


# ──────────────────────────────────────────────────────────────────────
# Signal loop
# ──────────────────────────────────────────────────────────────────────

def _load_recent_1m(*, needed_bars: int, csv_path: Path = MARKET_1M_CSV) -> Optional[pd.DataFrame]:
    """Load tail of market_1m.csv, parse ts as DatetimeIndex."""
    if not csv_path.exists():
        return None
    try:
        # Эффективно: читаем весь файл, берём tail. Файл небольшой (~1 KB на бар).
        df = pd.read_csv(csv_path)
    except (OSError, pd.errors.ParserError):
        logger.exception("range_hunter.read_1m_failed")
        return None
    if df.empty or "ts_utc" not in df.columns:
        return None
    df["ts"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df.tail(needed_bars + 10)  # +10 запасных на dedup


def _last_signal_ts(*, journal_path: Path = JOURNAL_PATH) -> Optional[datetime]:
    """Время последнего сигнала (для cooldown)."""
    rows = read_all(path=journal_path)
    if not rows:
        return None
    try:
        last_iso = rows[-1].get("ts_signal", "")
        return datetime.fromisoformat(last_iso) if last_iso else None
    except (ValueError, TypeError):
        return None


def _build_signal_record(sig: RangeHunterSignal) -> dict:
    """Compose journal record from signal."""
    return {
        "signal_id": signal_id_from_ts(datetime.fromisoformat(sig.ts)),
        "ts_signal": sig.ts,
        "mid_signal": sig.mid,
        "buy_level": sig.buy_level,
        "sell_level": sig.sell_level,
        "stop_loss_pct": sig.stop_loss_pct,
        "size_usd": sig.size_usd,
        "size_btc": sig.size_btc,
        "contract": sig.contract,
        "hold_h": sig.hold_h,
        "range_4h_pct": sig.range_4h_pct,
        "atr_pct": sig.atr_pct,
        "trend_pct_per_h": sig.trend_pct_per_h,
        "placed_at": None,
        "user_action": None,
        "decision_latency_sec": None,
        "buy_fill_ts": None,
        "sell_fill_ts": None,
        "exit_ts": None,
        "exit_reason": None,
        "legs_filled": None,
        "pnl_usd": None,
    }


def check_and_emit(*, send_fn: Optional[Callable] = None,
                   params: RangeHunterParams = DEFAULT_PARAMS,
                   csv_path: Path = MARKET_1M_CSV,
                   journal_path: Path = JOURNAL_PATH,
                   now: Optional[datetime] = None,
                   ) -> Optional[dict]:
    """One tick of signal-detection. Returns fired signal record or None.

    send_fn: callable(text, reply_markup=None) — для TG. Если None — только в журнал.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Cooldown
    last_ts = _last_signal_ts(journal_path=journal_path)
    if last_ts is not None:
        elapsed = (now - last_ts).total_seconds() / 3600.0
        if elapsed < params.cooldown_h:
            return None  # too soon

    needed = params.lookback_h * 60
    df = _load_recent_1m(needed_bars=needed, csv_path=csv_path)
    if df is None or len(df) < needed:
        return None

    sig = compute_signal(df, params)
    if sig is None:
        return None

    # Record + send
    record = _build_signal_record(sig)
    append_signal(record, path=journal_path)

    if send_fn is not None:
        expiry = now + timedelta(hours=sig.hold_h)
        try:
            text = format_tg_card(sig, expiry_ts=expiry)
            # Inline keyboard передаётся caller'у через build_keyboard если нужен.
            send_fn(text, reply_markup=_build_keyboard(record["signal_id"]))
        except Exception:
            logger.exception("range_hunter.send_failed")

    logger.info("range_hunter.signal mid=%.0f range=%.2f%% atr=%.2f%% trend=%+.2f%%/h",
                sig.mid, sig.range_4h_pct, sig.atr_pct, sig.trend_pct_per_h)
    return record


def _build_keyboard(signal_id: str):
    """Build inline keyboard for TG. Returns None if telebot не доступен."""
    try:
        from telebot import types  # noqa
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ Placed both", callback_data=f"rh:placed:{signal_id}"),
            types.InlineKeyboardButton("⏭ Skip", callback_data=f"rh:skip:{signal_id}"),
        )
        return kb
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# Outcome tracker
# ──────────────────────────────────────────────────────────────────────

# BitMEX fees (Tier 1, linear XBTUSDT)
MAKER_REBATE_PCT = 0.02   # +0.02% rebate
TAKER_FEE_PCT = 0.075


def evaluate_outcome(record: dict, df: pd.DataFrame, *,
                     now: Optional[datetime] = None) -> Optional[dict]:
    """Simulate fills of BUY/SELL legs and decide outcome.

    Returns dict of updates (buy_fill_ts/sell_fill_ts/exit_ts/exit_reason/legs_filled/pnl_usd)
    or None if outcome ещё не определён (timeout не наступил).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        ts_signal = datetime.fromisoformat(record["ts_signal"])
        placed_at = datetime.fromisoformat(record.get("placed_at") or record["ts_signal"])
    except (ValueError, TypeError):
        return None

    hold_h = int(record["hold_h"])
    deadline = placed_at + timedelta(hours=hold_h)
    deadline_reached = now >= deadline

    buy_level = float(record["buy_level"])
    sell_level = float(record["sell_level"])
    sl_pct = float(record["stop_loss_pct"])
    size_usd = float(record["size_usd"])
    mid_signal = float(record["mid_signal"])

    # Scan bars from placed_at to min(now, deadline)
    end_t = min(now, deadline)
    window = df[(df.index >= placed_at) & (df.index <= end_t)]
    if window.empty:
        if not deadline_reached:
            return None  # ждём данных
        # Бары пропали (нет 1m данных) — закроем как timeout без fill
        return _resolve_no_fill(end_t)

    buy_fill_ts = None
    sell_fill_ts = None
    for ts, bar in window.iterrows():
        if buy_fill_ts is None and float(bar["low"]) <= buy_level:
            buy_fill_ts = ts
        if sell_fill_ts is None and float(bar["high"]) >= sell_level:
            sell_fill_ts = ts
        if buy_fill_ts is not None and sell_fill_ts is not None:
            break

    # Если ничего не fill'нулось и до deadline ещё есть время — ждём
    if buy_fill_ts is None and sell_fill_ts is None and not deadline_reached:
        return None

    size_btc = size_usd / mid_signal

    # Case A: обе fill — pair_win
    if buy_fill_ts is not None and sell_fill_ts is not None:
        # spread = sell - buy. PnL = size_btc * spread. Plus 2x maker rebate.
        spread = sell_level - buy_level
        pnl_spread = size_btc * spread
        rebate = 2 * size_usd * (MAKER_REBATE_PCT / 100.0)
        pnl = pnl_spread + rebate
        exit_ts = max(buy_fill_ts, sell_fill_ts)
        return {
            "buy_fill_ts": buy_fill_ts.isoformat(),
            "sell_fill_ts": sell_fill_ts.isoformat(),
            "exit_ts": exit_ts.isoformat(),
            "exit_reason": "pair_win",
            "legs_filled": 2,
            "pnl_usd": round(pnl, 2),
        }

    # Case B: только BUY fill — стоп при движении против на sl_pct, иначе timeout
    if buy_fill_ts is not None and sell_fill_ts is None:
        sl_price = buy_level * (1 - sl_pct / 100.0)
        # ищем SL hit после buy_fill
        after_buy = window[window.index > buy_fill_ts]
        sl_idx = None
        for ts, bar in after_buy.iterrows():
            if float(bar["low"]) <= sl_price:
                sl_idx = ts
                break
        if sl_idx is not None:
            # taker exit at sl_price
            pnl_move = size_btc * (sl_price - buy_level)
            maker_in = size_usd * (MAKER_REBATE_PCT / 100.0)
            taker_out = size_usd * (TAKER_FEE_PCT / 100.0)
            pnl = pnl_move + maker_in - taker_out
            return {
                "buy_fill_ts": buy_fill_ts.isoformat(),
                "exit_ts": sl_idx.isoformat(),
                "exit_reason": "buy_stopped",
                "legs_filled": 1,
                "pnl_usd": round(pnl, 2),
            }
        if deadline_reached:
            # timeout exit at last close
            last_close = float(window["close"].iloc[-1])
            pnl_move = size_btc * (last_close - buy_level)
            maker_in = size_usd * (MAKER_REBATE_PCT / 100.0)
            taker_out = size_usd * (TAKER_FEE_PCT / 100.0)
            pnl = pnl_move + maker_in - taker_out
            return {
                "buy_fill_ts": buy_fill_ts.isoformat(),
                "exit_ts": end_t.isoformat(),
                "exit_reason": "buy_timeout",
                "legs_filled": 1,
                "pnl_usd": round(pnl, 2),
            }
        return None  # ждём

    # Case C: только SELL fill
    if sell_fill_ts is not None and buy_fill_ts is None:
        sl_price = sell_level * (1 + sl_pct / 100.0)
        after_sell = window[window.index > sell_fill_ts]
        sl_idx = None
        for ts, bar in after_sell.iterrows():
            if float(bar["high"]) >= sl_price:
                sl_idx = ts
                break
        if sl_idx is not None:
            pnl_move = size_btc * (sell_level - sl_price)
            maker_in = size_usd * (MAKER_REBATE_PCT / 100.0)
            taker_out = size_usd * (TAKER_FEE_PCT / 100.0)
            pnl = pnl_move + maker_in - taker_out
            return {
                "sell_fill_ts": sell_fill_ts.isoformat(),
                "exit_ts": sl_idx.isoformat(),
                "exit_reason": "sell_stopped",
                "legs_filled": 1,
                "pnl_usd": round(pnl, 2),
            }
        if deadline_reached:
            last_close = float(window["close"].iloc[-1])
            pnl_move = size_btc * (sell_level - last_close)
            maker_in = size_usd * (MAKER_REBATE_PCT / 100.0)
            taker_out = size_usd * (TAKER_FEE_PCT / 100.0)
            pnl = pnl_move + maker_in - taker_out
            return {
                "sell_fill_ts": sell_fill_ts.isoformat(),
                "exit_ts": end_t.isoformat(),
                "exit_reason": "sell_timeout",
                "legs_filled": 1,
                "pnl_usd": round(pnl, 2),
            }
        return None

    # Deadline reached, no fills
    if deadline_reached:
        return _resolve_no_fill(end_t)
    return None


def _resolve_no_fill(end_t: datetime) -> dict:
    return {
        "exit_ts": end_t.isoformat(),
        "exit_reason": "no_fill",
        "legs_filled": 0,
        "pnl_usd": 0.0,
    }


def check_outcomes(*, csv_path: Path = MARKET_1M_CSV,
                   journal_path: Path = JOURNAL_PATH,
                   now: Optional[datetime] = None) -> int:
    """One pass — try to resolve all pending signals. Returns count resolved."""
    if now is None:
        now = datetime.now(timezone.utc)
    pendings = pending_signals(path=journal_path)
    if not pendings:
        return 0
    # Загружаем достаточно данных — самое старое pending placement + hold_h
    df = _load_recent_1m(needed_bars=24 * 60, csv_path=csv_path)  # 24h tail
    if df is None or df.empty:
        return 0
    n_resolved = 0
    for rec in pendings:
        upd = evaluate_outcome(rec, df, now=now)
        if upd is not None:
            update_record(rec["signal_id"], upd, path=journal_path)
            n_resolved += 1
            logger.info("range_hunter.outcome id=%s reason=%s pnl=%s",
                        rec["signal_id"], upd.get("exit_reason"), upd.get("pnl_usd"))
    return n_resolved


# ──────────────────────────────────────────────────────────────────────
# Async loops
# ──────────────────────────────────────────────────────────────────────

async def range_hunter_signal_loop(stop_event: asyncio.Event, *,
                                   send_fn: Optional[Callable] = None,
                                   params: RangeHunterParams = DEFAULT_PARAMS,
                                   interval_sec: int = POLL_INTERVAL_SEC) -> None:
    logger.info("range_hunter.signal_loop.start interval=%ds width=%.2f%% hold=%dh",
                interval_sec, params.width_pct, params.hold_h)
    while not stop_event.is_set():
        try:
            check_and_emit(send_fn=send_fn, params=params)
        except Exception:
            logger.exception("range_hunter.signal_loop.tick_failed")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
    logger.info("range_hunter.signal_loop.stopped")


async def range_hunter_outcome_loop(stop_event: asyncio.Event, *,
                                    interval_sec: int = POLL_INTERVAL_SEC) -> None:
    logger.info("range_hunter.outcome_loop.start interval=%ds", interval_sec)
    while not stop_event.is_set():
        try:
            n = check_outcomes()
            if n > 0:
                logger.info("range_hunter.outcome_loop.resolved n=%d", n)
        except Exception:
            logger.exception("range_hunter.outcome_loop.tick_failed")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
    logger.info("range_hunter.outcome_loop.stopped")
