"""Shadow-loop для GA-найденных кандидатов.

Запускается отдельным процессом (через launchd com.bot7.ga-shadow), каждые
5 минут читает свежие 1h-свечи для BTCUSDT/ETHUSDT/XRPUSDT и проверяет
3 GA-кандидата. Срабатывания пишутся в state/ga_shadow_emissions.jsonl.

В TG ничего не отправляет — это shadow-mode для сбора forward-данных.

После 2-4 недель данных запустить scripts/audit_ga_shadow_results.py чтобы
сравнить forward-PnL с walk-forward predicted PF.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Если запущено напрямую (не как часть app_runner) — добавить ROOT в sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.setup_detector.ga_shadow_detectors import EVALUATORS_BY_PAIR, write_emission  # noqa: E402

logger = logging.getLogger(__name__)

LOOP_INTERVAL_SEC = 300  # 5 мин — частота проверки (1h-свечи обновляются 1 раз в час)
PAIRS = ("BTCUSDT", "ETHUSDT", "XRPUSDT")


def _load_latest_1h_bars(pair: str, n_bars: int = 300) -> pd.DataFrame | None:
    """Подгружает последние n_bars свечей через core.data_loader."""
    try:
        from core.data_loader import load_klines
    except Exception:
        logger.exception("ga_shadow.load_klines_unavailable")
        return None
    try:
        df = load_klines(symbol=pair, timeframe="1h", limit=n_bars)
        if df is None or df.empty:
            return None
        return df
    except Exception:
        logger.exception("ga_shadow.load_klines_failed pair=%s", pair)
        return None


async def shadow_evaluation_loop(stop_event: asyncio.Event | None = None) -> None:
    """Одна итерация = по очереди вычислить детекторы для каждой пары."""
    logger.info("ga_shadow_loop.start interval=%ds pairs=%s", LOOP_INTERVAL_SEC, PAIRS)
    iteration = 0
    while True:
        iteration += 1
        started = datetime.now(timezone.utc)
        n_fired = 0
        for pair in PAIRS:
            evaluators = EVALUATORS_BY_PAIR.get(pair, [])
            if not evaluators:
                continue
            df = _load_latest_1h_bars(pair)
            if df is None:
                logger.warning("ga_shadow.no_data pair=%s", pair)
                continue
            for fn in evaluators:
                try:
                    em = fn(df)
                except Exception:
                    logger.exception("ga_shadow.evaluator_crash pair=%s fn=%s", pair, fn.__name__)
                    continue
                if em is not None:
                    write_emission(em)
                    n_fired += 1
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        logger.info("ga_shadow_loop.iter iter=%d fired=%d elapsed=%.1fs", iteration, n_fired, elapsed)

        if stop_event and stop_event.is_set():
            logger.info("ga_shadow_loop.stop")
            return
        try:
            if stop_event:
                await asyncio.wait_for(stop_event.wait(), timeout=LOOP_INTERVAL_SEC)
                return  # был set
            else:
                await asyncio.sleep(LOOP_INTERVAL_SEC)
        except asyncio.TimeoutError:
            continue


def main_standalone() -> int:
    """CLI-режим: запустить loop как отдельный процесс."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(shadow_evaluation_loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main_standalone())
