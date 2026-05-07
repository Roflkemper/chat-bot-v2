"""Download Bybit BTC liquidations from sferez/BybitMarketData GitHub repo.

Fetches all available daily zip files, extracts JSONL, normalizes to single
parquet at data/historical/bybit_liquidations_2024.parquet.

Repo: https://github.com/sferez/BybitMarketData
Coverage: BTC 2024-02-12..2024-06-02 (68 days, ~4 months).

JSONL format (per liquidation): {"t": ts_ms, "d": {"updateTime", "symbol", "side", "size", "price"}}
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Iterator

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "historical"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REPO_RAW = "https://raw.githubusercontent.com/sferez/BybitMarketData/main"
REPO_API = "https://api.github.com/repos/sferez/BybitMarketData/contents/data/BTC"


def _list_dates() -> list[str]:
    r = requests.get(REPO_API, timeout=20)
    r.raise_for_status()
    items = r.json()
    return [it["name"] for it in items if it.get("type") == "dir"]


def _download_day(date: str) -> list[dict] | None:
    url = f"{REPO_RAW}/data/BTC/{date}/liquidations_BTC_{date}.zip"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            print(f"  {date}: HTTP {r.status_code}")
            return None
        # Unzip in-memory
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        events = []
        for fname in zf.namelist():
            with zf.open(fname) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events
    except Exception as e:
        print(f"  {date}: error {e}")
        return None


def main():
    print("Fetching date list...")
    dates = _list_dates()
    print(f"Found {len(dates)} days: {dates[0]} to {dates[-1]}")

    all_events = []
    for i, date in enumerate(dates, 1):
        events = _download_day(date)
        if events is None:
            continue
        all_events.extend(events)
        if i % 10 == 0:
            print(f"  progress {i}/{len(dates)}, total events so far: {len(all_events):,}")

    print(f"\nTotal events: {len(all_events):,}")
    if not all_events:
        print("No data — abort.")
        return

    # Normalize to dataframe
    import pandas as pd
    rows = []
    for ev in all_events:
        t_ms = ev.get("t")
        d = ev.get("d", {})
        if not d:
            continue
        # Bybit allLiquidation иногда отдаёт data как список объектов, иногда как dict
        records = d if isinstance(d, list) else [d]
        for rec in records:
            if not isinstance(rec, dict):
                continue
            try:
                # Bybit V5 short keys: v=size, p=price, S=side, s=symbol, T=ts
                qty = float(rec.get("v") or rec.get("size") or 0)
                price = float(rec.get("p") or rec.get("price") or 0)
            except (ValueError, TypeError):
                continue
            if qty <= 0 or price <= 0:
                continue
            symbol = rec.get("s") or rec.get("symbol") or ""
            side = rec.get("S") or rec.get("side") or ""
            ts_v = rec.get("T") or rec.get("updateTime") or t_ms or 0
            try:
                ts_ms = int(ts_v)
            except (ValueError, TypeError):
                continue
            rows.append({
                "ts_ms": ts_ms,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
            })

    df = pd.DataFrame(rows)
    df = df[df["symbol"] == "BTCUSDT"]  # filter just in case
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    print(f"BTCUSDT events: {len(df):,}")
    print(f"Date range: {df['ts'].min()} to {df['ts'].max()}")
    print(f"Total BTC liquidated: {df['qty'].sum():.2f}")
    print(f"Long-side: {df[df['side'].str.lower() == 'buy']['qty'].sum():.2f} BTC")
    print(f"Short-side: {df[df['side'].str.lower() == 'sell']['qty'].sum():.2f} BTC")

    out_path = OUT_DIR / "bybit_liquidations_2024.parquet"
    df.to_parquet(out_path, compression="snappy")
    print(f"\nSaved: {out_path}")
    print(f"Size: {out_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
