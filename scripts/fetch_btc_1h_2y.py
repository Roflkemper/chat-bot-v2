"""Скачать SYMBOL 1h kline за 2 года с Binance API.

Готовит данные для GA-поиска (Stage E1). На Mac после миграции
файла backtests/frozen/<SYMBOL>_1h_2y.csv не было — этот скрипт
его восстанавливает.

Binance API: один запрос отдаёт max 1000 свечей. 2 года × 8760ч = 17520
свечей → ~18 запросов. Время: ~30 секунд + сеть.

Запуск:
    python scripts/fetch_btc_1h_2y.py              # default BTCUSDT
    python scripts/fetch_btc_1h_2y.py ETHUSDT
    python scripts/fetch_btc_1h_2y.py XRPUSDT
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
INTERVAL = "1h"
DAYS = 730
LIMIT = 1000  # Binance max per request

OUT = ROOT / "backtests" / "frozen" / f"{SYMBOL}_1h_2y.csv"


def fetch_chunk(start_ms: int, end_ms: int) -> list[list]:
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": LIMIT,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=DAYS)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    print(f"Качаю {SYMBOL} {INTERVAL} с {start_dt:%Y-%m-%d} по {end_dt:%Y-%m-%d}")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[list] = []
    cursor = start_ms
    chunks = 0
    while cursor < end_ms:
        chunk_end = min(cursor + LIMIT * 3600 * 1000, end_ms)
        try:
            data = fetch_chunk(cursor, chunk_end)
        except Exception as exc:
            print(f"  ошибка на {cursor}: {exc}, ретрай через 3с")
            time.sleep(3)
            continue
        if not data:
            print(f"  пустой ответ на {cursor}, продвигаюсь")
            cursor = chunk_end + 1
            continue
        all_rows.extend(data)
        chunks += 1
        last_ts = data[-1][0]
        last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
        print(f"  chunk {chunks}: {len(data)} свечей, до {last_dt:%Y-%m-%d %H:%M}")
        cursor = last_ts + 1
        time.sleep(0.3)  # rate limit friendly

    # Дедуп по timestamp (на стыках чанков может быть наложение)
    seen = set()
    unique = []
    for row in all_rows:
        ts = row[0]
        if ts in seen:
            continue
        seen.add(ts)
        unique.append(row)
    unique.sort(key=lambda r: r[0])

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts_ms", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "n_trades",
                    "taker_buy_base", "taker_buy_quote", "ignore"])
        for row in unique:
            w.writerow(row)

    print(f"\nЗаписано {len(unique)} свечей в {OUT}")
    print(f"Размер: {OUT.stat().st_size // 1024 // 1024} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
