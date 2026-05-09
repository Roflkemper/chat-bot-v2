"""TEST_3 TP-flat B variant — TP=$5 immediate dd=3% paper simulator.

Re-uses the core state machine from services.test3_tpflat_simulator by
overriding a couple of constants in a thin wrapper. Writes to its own
journal/state paths so the primary A variant (TP=$10) is unaffected.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "state" / "test3_tpflat_b_state.json"
JOURNAL_PATH = ROOT / "state" / "test3_tpflat_b_paper.jsonl"

# B variant parameters
TP_USD_B = 5.0
DD_CAP_PCT_B = 3.0


async def test3_tpflat_b_simulator_loop(stop_event: asyncio.Event,
                                         interval_sec: int = 60) -> None:
    """Async loop. Reuses A's _check_and_act / _load_state / _save_state /
    _journal_append by patching A's module-level constants for the duration
    of this loop. Cleaner alternative would be parameterized class — but a
    simple monkey-patch keeps changes minimal and the A variant entirely
    untouched."""
    from services.test3_tpflat_simulator import loop as a_loop
    logger.info("test3_tpflat_b.start interval=%ds tp=$%.0f dd=%.1f%% size=$%.0f reentry=immediate",
                interval_sec, TP_USD_B, DD_CAP_PCT_B, a_loop.BASE_SIZE_USD)

    while not stop_event.is_set():
        try:
            from core.data_loader import load_klines
            df_1m = load_klines(symbol=a_loop.SYMBOL, timeframe="1m", limit=2)
            df_1h = load_klines(symbol=a_loop.SYMBOL, timeframe="1h", limit=250)
            if df_1m is None or len(df_1m) < 1 or df_1h is None or len(df_1h) < 200:
                logger.warning("test3_tpflat_b.data_thin")
            else:
                closes_1h = df_1h["close"].astype(float).tolist()
                current = float(df_1m["close"].iloc[-1])
                high_now = float(df_1m["high"].iloc[-1])
                low_now = float(df_1m["low"].iloc[-1])
                # Patch module-level params + paths for this tick
                orig_tp = a_loop.TP_USD
                orig_dd = a_loop.DD_CAP_PCT
                orig_state = a_loop.STATE_PATH
                orig_journal = a_loop.JOURNAL_PATH
                try:
                    a_loop.TP_USD = TP_USD_B
                    a_loop.DD_CAP_PCT = DD_CAP_PCT_B
                    a_loop.STATE_PATH = STATE_PATH
                    a_loop.JOURNAL_PATH = JOURNAL_PATH
                    state = a_loop._load_state()
                    a_loop._check_and_act(closes_1h, current, high_now, low_now, state)
                    a_loop._save_state(state)
                finally:
                    a_loop.TP_USD = orig_tp
                    a_loop.DD_CAP_PCT = orig_dd
                    a_loop.STATE_PATH = orig_state
                    a_loop.JOURNAL_PATH = orig_journal
        except Exception:
            logger.exception("test3_tpflat_b.tick_failed")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
