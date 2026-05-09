"""Скачивание истории derivative-метрик с Binance Futures API.

Endpoints (free, no auth):
  /futures/data/openInterestHist           (1h period, max 30d back)
  /fapi/v1/fundingRate                     (per-funding-event = 8h, max 1000 entries)
  /futures/data/takerlongshortRatio        (1h period, max 30d back)
  /futures/data/globalLongShortAccountRatio (1h period, max 30d back)
  /futures/data/topLongShortPositionRatio  (1h period, max 30d back)

Для retro-валидации grid_coordinator: нужны OI / funding / taker_buy/sell / LS-ratio
на исторических 1h барах.

Output: data/historical/binance_deriv_<symbol>_<endpoint>.parquet
"""
from __future__ import annotations

import io
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "historical"
OUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

SYMBOLS = ("BTCUSDT", "ETHUSDT", "XRPUSDT")
DAYS_BACK = 28  # Binance rejects startTime > ~29d for OI/ratio endpoints (tested 2026-05-10)


def _fetch(path: str, params: dict, max_retries: int = 3) -> list:
    url = f"https://fapi.binance.com{path}"
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
            print(f"  HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException as exc:
            print(f"  attempt {attempt+1} failed: {exc}")
        time.sleep(2)
    return []


def fetch_oi_history(symbol: str, days_back: int = DAYS_BACK) -> pd.DataFrame:
    """OI history 1h."""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days_back * 86400 * 1000
    all_data = []
    cursor = start_ms
    while cursor < end_ms:
        batch = _fetch("/futures/data/openInterestHist", {
            "symbol": symbol, "period": "1h", "limit": 500,
            "startTime": cursor,
        })
        if not batch:
            break
        all_data.extend(batch)
        last_ts = int(batch[-1]["timestamp"])
        if last_ts <= cursor:
            break
        cursor = last_ts + 3600_000
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    df = pd.DataFrame(all_data)
    df["ts_ms"] = df["timestamp"].astype("int64")
    df["oi_native"] = pd.to_numeric(df["sumOpenInterest"], errors="coerce")
    df["oi_value_usd"] = pd.to_numeric(df["sumOpenInterestValue"], errors="coerce")
    df = df.drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms").reset_index(drop=True)
    return df[["ts_ms", "oi_native", "oi_value_usd"]]


def fetch_funding_history(symbol: str, days_back: int = DAYS_BACK) -> pd.DataFrame:
    """Funding rate history (8h period — fundingRate endpoint)."""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days_back * 86400 * 1000
    all_data = []
    cursor = start_ms
    while cursor < end_ms:
        batch = _fetch("/fapi/v1/fundingRate", {
            "symbol": symbol, "limit": 1000,
            "startTime": cursor,
        })
        if not batch:
            break
        all_data.extend(batch)
        last_ts = int(batch[-1]["fundingTime"])
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    df = pd.DataFrame(all_data)
    df["ts_ms"] = df["fundingTime"].astype("int64")
    df["funding_rate_8h"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    df = df.drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms").reset_index(drop=True)
    return df[["ts_ms", "funding_rate_8h"]]


def fetch_taker_ratio(symbol: str, days_back: int = DAYS_BACK) -> pd.DataFrame:
    """Taker long/short ratio 1h."""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days_back * 86400 * 1000
    all_data = []
    cursor = start_ms
    while cursor < end_ms:
        batch = _fetch("/futures/data/takerlongshortRatio", {
            "symbol": symbol, "period": "1h", "limit": 500,
            "startTime": cursor,
        })
        if not batch:
            break
        all_data.extend(batch)
        last_ts = int(batch[-1]["timestamp"])
        if last_ts <= cursor:
            break
        cursor = last_ts + 3600_000
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    df = pd.DataFrame(all_data)
    df["ts_ms"] = df["timestamp"].astype("int64")
    df["taker_buy_vol"] = pd.to_numeric(df["buyVol"], errors="coerce")
    df["taker_sell_vol"] = pd.to_numeric(df["sellVol"], errors="coerce")
    df["taker_buy_sell_ratio"] = pd.to_numeric(df["buySellRatio"], errors="coerce")
    total_vol = df["taker_buy_vol"] + df["taker_sell_vol"]
    df["taker_buy_pct"] = (df["taker_buy_vol"] / total_vol * 100).round(2)
    df["taker_sell_pct"] = (df["taker_sell_vol"] / total_vol * 100).round(2)
    df = df.drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms").reset_index(drop=True)
    return df[["ts_ms", "taker_buy_vol", "taker_sell_vol",
               "taker_buy_sell_ratio", "taker_buy_pct", "taker_sell_pct"]]


def fetch_global_ls(symbol: str, days_back: int = DAYS_BACK) -> pd.DataFrame:
    """Global account long/short ratio 1h."""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days_back * 86400 * 1000
    all_data = []
    cursor = start_ms
    while cursor < end_ms:
        batch = _fetch("/futures/data/globalLongShortAccountRatio", {
            "symbol": symbol, "period": "1h", "limit": 500,
            "startTime": cursor,
        })
        if not batch:
            break
        all_data.extend(batch)
        last_ts = int(batch[-1]["timestamp"])
        if last_ts <= cursor:
            break
        cursor = last_ts + 3600_000
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    df = pd.DataFrame(all_data)
    df["ts_ms"] = df["timestamp"].astype("int64")
    df["global_long_pct"] = pd.to_numeric(df["longAccount"], errors="coerce") * 100
    df["global_short_pct"] = pd.to_numeric(df["shortAccount"], errors="coerce") * 100
    df["global_ls_ratio"] = pd.to_numeric(df["longShortRatio"], errors="coerce")
    df = df.drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms").reset_index(drop=True)
    return df[["ts_ms", "global_long_pct", "global_short_pct", "global_ls_ratio"]]


def fetch_top_trader_ls(symbol: str, days_back: int = DAYS_BACK) -> pd.DataFrame:
    """Top trader position long/short ratio 1h."""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days_back * 86400 * 1000
    all_data = []
    cursor = start_ms
    while cursor < end_ms:
        batch = _fetch("/futures/data/topLongShortPositionRatio", {
            "symbol": symbol, "period": "1h", "limit": 500,
            "startTime": cursor,
        })
        if not batch:
            break
        all_data.extend(batch)
        last_ts = int(batch[-1]["timestamp"])
        if last_ts <= cursor:
            break
        cursor = last_ts + 3600_000
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    df = pd.DataFrame(all_data)
    df["ts_ms"] = df["timestamp"].astype("int64")
    df["top_trader_long_pct"] = pd.to_numeric(df["longAccount"], errors="coerce") * 100
    df["top_trader_short_pct"] = pd.to_numeric(df["shortAccount"], errors="coerce") * 100
    df["top_trader_ls_ratio"] = pd.to_numeric(df["longShortRatio"], errors="coerce")
    df = df.drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms").reset_index(drop=True)
    return df[["ts_ms", "top_trader_long_pct", "top_trader_short_pct",
               "top_trader_ls_ratio"]]


def main() -> int:
    print(f"[binance-hist] downloading {DAYS_BACK}d for symbols: {SYMBOLS}")
    print(f"[binance-hist] OUT_DIR: {OUT_DIR}")
    print()

    for symbol in SYMBOLS:
        print(f"=== {symbol} ===")
        # OI history
        print(f"  /futures/data/openInterestHist...")
        df_oi = fetch_oi_history(symbol)
        print(f"    {len(df_oi)} rows, {df_oi.iloc[0]['ts_ms'] if not df_oi.empty else 'n/a'} → {df_oi.iloc[-1]['ts_ms'] if not df_oi.empty else 'n/a'}")
        if not df_oi.empty:
            df_oi.to_parquet(OUT_DIR / f"binance_oi_{symbol}.parquet", index=False)
            df_oi.to_csv(OUT_DIR / f"binance_oi_{symbol}.csv", index=False)

        # Funding
        print(f"  /fapi/v1/fundingRate...")
        df_f = fetch_funding_history(symbol)
        print(f"    {len(df_f)} rows")
        if not df_f.empty:
            df_f.to_parquet(OUT_DIR / f"binance_funding_{symbol}.parquet", index=False)
            df_f.to_csv(OUT_DIR / f"binance_funding_{symbol}.csv", index=False)

        # Taker ratio
        print(f"  /futures/data/takerlongshortRatio...")
        df_t = fetch_taker_ratio(symbol)
        print(f"    {len(df_t)} rows")
        if not df_t.empty:
            df_t.to_parquet(OUT_DIR / f"binance_taker_{symbol}.parquet", index=False)
            df_t.to_csv(OUT_DIR / f"binance_taker_{symbol}.csv", index=False)

        # Global LS
        print(f"  /futures/data/globalLongShortAccountRatio...")
        df_g = fetch_global_ls(symbol)
        print(f"    {len(df_g)} rows")
        if not df_g.empty:
            df_g.to_parquet(OUT_DIR / f"binance_globalls_{symbol}.parquet", index=False)
            df_g.to_csv(OUT_DIR / f"binance_globalls_{symbol}.csv", index=False)

        # Top trader LS
        print(f"  /futures/data/topLongShortPositionRatio...")
        df_top = fetch_top_trader_ls(symbol)
        print(f"    {len(df_top)} rows")
        if not df_top.empty:
            df_top.to_parquet(OUT_DIR / f"binance_topls_{symbol}.parquet", index=False)
            df_top.to_csv(OUT_DIR / f"binance_topls_{symbol}.csv", index=False)
        print()

    # Build combined: all metrics aligned on 1h timeline per symbol
    print("[binance-hist] building combined per-symbol files...")
    for symbol in SYMBOLS:
        files = {
            "oi": OUT_DIR / f"binance_oi_{symbol}.parquet",
            "taker": OUT_DIR / f"binance_taker_{symbol}.parquet",
            "globalls": OUT_DIR / f"binance_globalls_{symbol}.parquet",
            "topls": OUT_DIR / f"binance_topls_{symbol}.parquet",
        }
        if not all(f.exists() for f in files.values()):
            print(f"  {symbol}: missing some files, skip combine")
            continue
        df_combined = pd.read_parquet(files["oi"])
        for key in ("taker", "globalls", "topls"):
            df_combined = df_combined.merge(pd.read_parquet(files[key]),
                                              on="ts_ms", how="outer")
        # Add OI change pct (1h)
        df_combined = df_combined.sort_values("ts_ms").reset_index(drop=True)
        df_combined["oi_change_1h_pct"] = df_combined["oi_native"].pct_change() * 100

        # Add funding (interpolated since 8h period)
        df_funding = pd.read_parquet(OUT_DIR / f"binance_funding_{symbol}.parquet")
        df_combined = pd.merge_asof(
            df_combined.sort_values("ts_ms"),
            df_funding.sort_values("ts_ms"),
            on="ts_ms", direction="backward",
        )
        df_combined.to_parquet(OUT_DIR / f"binance_combined_{symbol}.parquet", index=False)
        print(f"  {symbol}: combined {len(df_combined)} rows → "
              f"binance_combined_{symbol}.parquet")
        # Show first row sample
        if not df_combined.empty:
            print(f"    cols: {df_combined.columns.tolist()[:8]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
