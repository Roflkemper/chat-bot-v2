"""Backfill BTC 1m OHLCV with 2024-02-12 to 2024-04-24 (~73 days).

Существующий backtests/frozen/BTCUSDT_1m_2y.csv начинается с 2024-04-25.
ohlcv_ingest.py не догружает раньше file start (только append-forward).
Обходной путь: скачиваем ранний период напрямую с Binance, prepend'им к файлу.

После выполнения BTCUSDT_1m_2y.csv будет покрывать с 2024-02-12 до сейчас,
что даст overlap с liquidations history для post-cascade backtest n=100+.

Time estimate: ~5-10 минут (73 days × 1440 min = 105k bars, batches по 1000).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
TARGET_CSV = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
TARGET_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"

START_TS = int(datetime(2024, 2, 12, tzinfo=timezone.utc).timestamp() * 1000)
END_TS = int(datetime(2024, 4, 25, tzinfo=timezone.utc).timestamp() * 1000)


def fetch_batch(start_ms: int) -> list[list]:
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "startTime": start_ms,
        "endTime": END_TS,
        "limit": 1000,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    print(f"Backfill window: {datetime.fromtimestamp(START_TS/1000, tz=timezone.utc)} to {datetime.fromtimestamp(END_TS/1000, tz=timezone.utc)}")

    rows = []
    cursor = START_TS
    batch_n = 0
    while cursor < END_TS:
        try:
            batch = fetch_batch(cursor)
        except requests.RequestException as e:
            print(f"  retry batch_n={batch_n} err={e}")
            time.sleep(3)
            continue
        if not batch:
            print(f"  empty batch at cursor={cursor}, stop")
            break
        for k in batch:
            # k = [open_time, open, high, low, close, volume, close_time, ...]
            rows.append({
                "ts": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        batch_n += 1
        last_ts = int(batch[-1][0])
        cursor = last_ts + 60_000  # next minute
        if batch_n % 20 == 0:
            print(f"  progress batch={batch_n}, cursor={datetime.fromtimestamp(cursor/1000, tz=timezone.utc)}, rows={len(rows):,}")
        # respectful
        time.sleep(0.05)

    if not rows:
        print("No data downloaded.")
        return

    print(f"\nDownloaded {len(rows):,} 1m bars")

    df_new = pd.DataFrame(rows).drop_duplicates(subset="ts").sort_values("ts")
    print(f"Unique: {len(df_new):,} rows from {pd.to_datetime(df_new['ts'].min(), unit='ms', utc=True)} to {pd.to_datetime(df_new['ts'].max(), unit='ms', utc=True)}")

    # Load existing
    if TARGET_CSV.exists():
        df_old = pd.read_csv(TARGET_CSV)
        print(f"Existing: {len(df_old):,} rows from {pd.to_datetime(df_old['ts'].min(), unit='ms', utc=True)} to {pd.to_datetime(df_old['ts'].max(), unit='ms', utc=True)}")
        # Merge: keep both (новые до start of old, old без изменений)
        df_combined = pd.concat([df_new, df_old], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
        print(f"Combined: {len(df_combined):,} rows from {pd.to_datetime(df_combined['ts'].min(), unit='ms', utc=True)} to {pd.to_datetime(df_combined['ts'].max(), unit='ms', utc=True)}")
    else:
        df_combined = df_new

    # Backup before write
    if TARGET_CSV.exists():
        backup = TARGET_CSV.with_suffix(".csv.bak_pre_backfill")
        backup.write_bytes(TARGET_CSV.read_bytes())
        print(f"Backup: {backup}")

    df_combined.to_csv(TARGET_CSV, index=False)
    print(f"Wrote: {TARGET_CSV} ({TARGET_CSV.stat().st_size / 1024 / 1024:.1f} MB)")

    # Resample 1h from combined
    df_1m = df_combined.copy()
    df_1m["ts_dt"] = pd.to_datetime(df_1m["ts"], unit="ms", utc=True)
    df_1m = df_1m.set_index("ts_dt").sort_index()
    df_1h = df_1m.resample("1h").agg({
        "ts": "first",  # placeholder, override below
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    df_1h["ts"] = (df_1h.index.astype("int64") // 1_000_000).astype(int)
    df_1h = df_1h.reset_index(drop=True)[["ts", "open", "high", "low", "close", "volume"]]
    if TARGET_1H.exists():
        backup_1h = TARGET_1H.with_suffix(".csv.bak_pre_backfill")
        backup_1h.write_bytes(TARGET_1H.read_bytes())
        print(f"Backup 1h: {backup_1h}")
    df_1h.to_csv(TARGET_1H, index=False)
    print(f"Wrote 1h: {TARGET_1H} ({len(df_1h):,} rows)")


if __name__ == "__main__":
    main()
