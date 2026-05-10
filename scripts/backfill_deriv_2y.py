"""Backfill 2y of Binance Futures derivatives data → data/historical/binance_*.parquet

Endpoints used (all public, no auth needed):
  /futures/data/openInterestHist       OI hourly
  /fapi/v1/fundingRate                  Funding rate 8h
  /futures/data/globalLongShortAccountRatio
  /futures/data/topLongShortAccountRatio
  /futures/data/takerlongshortRatio    Taker buy/sell

Per request limits (Binance docs):
  openInterestHist: max 500 rows, max 30d window
  fundingRate: max 1000 rows
  *LongShortAccountRatio: max 500 rows, max 30d window
  takerlongshortRatio: max 500 rows, max 30d window

Strategy: walk in 30-day chunks from start_date → today, paginate, dedupe,
write per-symbol parquet. Combined parquet merges all sources on ts_ms.

Idempotent: re-runs skip ranges already covered (read existing parquet,
fetch only from last_ts + 1h forward).

Run as:
    python scripts/backfill_deriv_2y.py --symbols BTCUSDT,ETHUSDT,XRPUSDT --years 2

Memory profile: streams in chunks, keeps only the current symbol's frames
in RAM. Expected peak ~150MB total even for 2y/3 symbols (60k rows × 10 cols).

Rate limit: Binance allows 1200 req/min weighted; each endpoint is weight 1.
We sleep 0.3s between requests (~200 req/min) — very conservative.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import urllib.request
import urllib.parse
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "historical"
BASE = "https://fapi.binance.com"
SLEEP_BETWEEN = 0.3
CHUNK_DAYS = 30


def _get(url: str, params: dict) -> list:
    """GET with retry. Returns parsed JSON or empty list on failure."""
    q = urllib.parse.urlencode(params)
    full = f"{url}?{q}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "bot7-backfill/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return data
                return []
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  rate-limited, sleeping 30s", file=sys.stderr)
                time.sleep(30)
            else:
                print(f"  HTTPError {e.code} on {full[:80]}", file=sys.stderr)
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  error {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    return []


def _walk_window(start_ms: int, end_ms: int, chunk_days: int = CHUNK_DAYS):
    """Yield (chunk_start, chunk_end) tuples covering [start_ms, end_ms]."""
    step = chunk_days * 86400_000
    t = start_ms
    while t < end_ms:
        yield t, min(t + step, end_ms)
        t += step


def fetch_oi_hist(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Open interest hourly history."""
    rows = []
    for chunk_start, chunk_end in _walk_window(start_ms, end_ms):
        data = _get(f"{BASE}/futures/data/openInterestHist", {
            "symbol": symbol, "period": "1h",
            "startTime": chunk_start, "endTime": chunk_end, "limit": 500,
        })
        for r in data:
            rows.append({
                "ts_ms": int(r["timestamp"]),
                "oi_native": float(r["sumOpenInterest"]),
                "oi_value_usd": float(r["sumOpenInterestValue"]),
            })
        time.sleep(SLEEP_BETWEEN)
    return pd.DataFrame(rows).drop_duplicates("ts_ms") if rows else pd.DataFrame()


def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Funding rate per 8h interval."""
    rows = []
    t = start_ms
    while t < end_ms:
        data = _get(f"{BASE}/fapi/v1/fundingRate", {
            "symbol": symbol, "startTime": t, "limit": 1000,
        })
        if not data:
            break
        for r in data:
            rows.append({
                "ts_ms": int(r["fundingTime"]),
                "funding_rate_8h": float(r["fundingRate"]),
            })
        last_ts = max(int(r["fundingTime"]) for r in data)
        if last_ts <= t:
            break
        t = last_ts + 1
        time.sleep(SLEEP_BETWEEN)
    return pd.DataFrame(rows).drop_duplicates("ts_ms") if rows else pd.DataFrame()


def fetch_globalls(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = []
    for chunk_start, chunk_end in _walk_window(start_ms, end_ms):
        data = _get(f"{BASE}/futures/data/globalLongShortAccountRatio", {
            "symbol": symbol, "period": "1h",
            "startTime": chunk_start, "endTime": chunk_end, "limit": 500,
        })
        for r in data:
            rows.append({
                "ts_ms": int(r["timestamp"]),
                "global_long_pct": float(r["longAccount"]) * 100,
                "global_short_pct": float(r["shortAccount"]) * 100,
                "global_ls_ratio": float(r["longShortRatio"]),
            })
        time.sleep(SLEEP_BETWEEN)
    return pd.DataFrame(rows).drop_duplicates("ts_ms") if rows else pd.DataFrame()


def fetch_topls(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = []
    for chunk_start, chunk_end in _walk_window(start_ms, end_ms):
        data = _get(f"{BASE}/futures/data/topLongShortAccountRatio", {
            "symbol": symbol, "period": "1h",
            "startTime": chunk_start, "endTime": chunk_end, "limit": 500,
        })
        for r in data:
            rows.append({
                "ts_ms": int(r["timestamp"]),
                "top_trader_long_pct": float(r["longAccount"]) * 100,
                "top_trader_short_pct": float(r["shortAccount"]) * 100,
                "top_trader_ls_ratio": float(r["longShortRatio"]),
            })
        time.sleep(SLEEP_BETWEEN)
    return pd.DataFrame(rows).drop_duplicates("ts_ms") if rows else pd.DataFrame()


def fetch_taker(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = []
    for chunk_start, chunk_end in _walk_window(start_ms, end_ms):
        data = _get(f"{BASE}/futures/data/takerlongshortRatio", {
            "symbol": symbol, "period": "1h",
            "startTime": chunk_start, "endTime": chunk_end, "limit": 500,
        })
        for r in data:
            rows.append({
                "ts_ms": int(r["timestamp"]),
                "taker_buy_vol": float(r["buyVol"]),
                "taker_sell_vol": float(r["sellVol"]),
                "taker_buy_sell_ratio": float(r["buySellRatio"]),
            })
        time.sleep(SLEEP_BETWEEN)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates("ts_ms")
    total = df["taker_buy_vol"] + df["taker_sell_vol"]
    df["taker_buy_pct"] = (df["taker_buy_vol"] / total * 100).round(2)
    df["taker_sell_pct"] = (df["taker_sell_vol"] / total * 100).round(2)
    return df


def _existing_last_ts(path: Path) -> int | None:
    if not path.exists(): return None
    try:
        df = pd.read_parquet(path, columns=["ts_ms"])
        if df.empty: return None
        return int(df["ts_ms"].max())
    except Exception:
        return None


def _merge_save(symbol: str, oi: pd.DataFrame, fr: pd.DataFrame,
                gls: pd.DataFrame, tls: pd.DataFrame, tk: pd.DataFrame) -> None:
    """Merge all into combined parquet, also save individual parquets."""
    # Save individual files (preserving existing data — outer merge).
    for kind, df_new in [("oi", oi), ("funding", fr), ("globalls", gls),
                          ("topls", tls), ("taker", tk)]:
        if df_new.empty: continue
        path = OUT_DIR / f"binance_{kind}_{symbol}.parquet"
        if path.exists():
            old = pd.read_parquet(path)
            df_new = pd.concat([old, df_new]).drop_duplicates("ts_ms").sort_values("ts_ms")
        df_new.to_parquet(path, index=False)
        # CSV mirror (small footprint)
        df_new.to_csv(path.with_suffix(".csv"), index=False)
        print(f"  wrote {path.name}: {len(df_new)} rows")

    # Build combined parquet: merge all five DataFrames on ts_ms (outer join).
    paths = {
        "oi": OUT_DIR / f"binance_oi_{symbol}.parquet",
        "funding": OUT_DIR / f"binance_funding_{symbol}.parquet",
        "globalls": OUT_DIR / f"binance_globalls_{symbol}.parquet",
        "topls": OUT_DIR / f"binance_topls_{symbol}.parquet",
        "taker": OUT_DIR / f"binance_taker_{symbol}.parquet",
    }
    frames = []
    for k, p in paths.items():
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return
    combined = frames[0]
    for f in frames[1:]:
        combined = combined.merge(f, on="ts_ms", how="outer")
    # Forward-fill funding to hourly grid (funding is 8h, OI is 1h).
    combined = combined.sort_values("ts_ms").reset_index(drop=True)
    if "funding_rate_8h" in combined.columns:
        combined["funding_rate_8h"] = combined["funding_rate_8h"].ffill()
    # Compute derived oi_change_1h_pct.
    if "oi_value_usd" in combined.columns:
        combined["oi_change_1h_pct"] = combined["oi_value_usd"].pct_change() * 100
    out = OUT_DIR / f"binance_combined_{symbol}.parquet"
    combined.to_parquet(out, index=False)
    print(f"  wrote {out.name}: {len(combined)} rows  "
          f"{pd.to_datetime(combined['ts_ms'].min(), unit='ms')} -> "
          f"{pd.to_datetime(combined['ts_ms'].max(), unit='ms')}")


def backfill_symbol(symbol: str, start_ms: int, end_ms: int,
                    incremental: bool = True) -> None:
    print(f"\n=== {symbol} ===")
    out_combined = OUT_DIR / f"binance_combined_{symbol}.parquet"
    effective_start = start_ms
    if incremental:
        last = _existing_last_ts(out_combined)
        if last is not None and last > start_ms:
            effective_start = last + 3600_000  # +1h
            print(f"  incremental: resuming from {pd.to_datetime(effective_start, unit='ms')}")
    if effective_start >= end_ms:
        print("  already up-to-date, skip")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  fetching OI hist...")
    oi = fetch_oi_hist(symbol, effective_start, end_ms)
    print(f"  fetching funding...")
    fr = fetch_funding(symbol, effective_start, end_ms)
    print(f"  fetching globalLS...")
    gls = fetch_globalls(symbol, effective_start, end_ms)
    print(f"  fetching topLS...")
    tls = fetch_topls(symbol, effective_start, end_ms)
    print(f"  fetching taker vol...")
    tk = fetch_taker(symbol, effective_start, end_ms)
    print(f"  rows: oi={len(oi)} fr={len(fr)} gls={len(gls)} tls={len(tls)} tk={len(tk)}")
    _merge_save(symbol, oi, fr, gls, tls, tk)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,XRPUSDT")
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--no-incremental", action="store_true",
                    help="Fetch full window even if existing data covers part of it")
    args = ap.parse_args()

    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=int(args.years * 365)))
                    .timestamp() * 1000)
    print(f"Range: {pd.to_datetime(start_ms, unit='ms')} -> {pd.to_datetime(end_ms, unit='ms')}")
    print(f"Symbols: {args.symbols}")

    for sym in args.symbols.split(","):
        sym = sym.strip()
        if not sym: continue
        try:
            backfill_symbol(sym, start_ms, end_ms,
                             incremental=not args.no_incremental)
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym} FAILED: {exc}", file=sys.stderr)

    print("\n[backfill] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
