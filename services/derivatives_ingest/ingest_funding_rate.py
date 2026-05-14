"""Ingest historical Funding Rate from Binance Futures (8h settlements).

Output: backtests/frozen/derivatives_1y/{SYMBOL}_funding_8h_1y.parquet
Schema: ts_ms, symbol, fundingRate, fundingTime
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .binance_client import BinanceFuturesClient

log = logging.getLogger(__name__)


def _checkpoint_path(out_path: Path) -> Path:
    return out_path.parent / (out_path.stem + "_checkpoint.json")


def _load_checkpoint(ckpt: Path) -> Optional[int]:
    if ckpt.exists():
        try:
            return json.loads(ckpt.read_text())["last_ts_ms"]
        except Exception:
            pass
    return None


def _save_checkpoint(ckpt: Path, last_ts_ms: int) -> None:
    ckpt.write_text(json.dumps({"last_ts_ms": last_ts_ms}))


def ingest_funding(
    symbol: str,
    start_ms: int,
    end_ms: int,
    out_path: Path,
    client: Optional[BinanceFuturesClient] = None,
    resume: bool = True,
) -> pd.DataFrame:
    """Fetch funding rate history and write parquet. Returns final DataFrame."""
    client = client or BinanceFuturesClient()
    ckpt = _checkpoint_path(out_path)

    cursor = start_ms
    if resume:
        saved = _load_checkpoint(ckpt)
        if saved and saved > cursor:
            log.info("Funding %s: resuming from checkpoint %d", symbol, saved)
            cursor = saved + 1

    rows: list[dict] = []
    if resume and out_path.exists():
        existing = pd.read_parquet(out_path)
        rows = existing.to_dict("records")
        log.info("Funding %s: loaded %d existing rows", symbol, len(rows))

    total_batches = 0
    for batch in client.paginate_funding_rate(symbol, cursor, end_ms):
        for row in batch:
            rows.append({
                "ts_ms": int(row["fundingTime"]),
                "symbol": symbol,
                "fundingRate": float(row.get("fundingRate", 0)),
                "fundingTime": int(row.get("fundingTime", 0)),
            })
        _save_checkpoint(ckpt, int(batch[-1]["fundingTime"]))
        total_batches += 1

    if not rows:
        log.warning("Funding %s: no rows fetched", symbol)
        return pd.DataFrame(columns=["ts_ms", "symbol", "fundingRate", "fundingTime"])

    df = pd.DataFrame(rows).drop_duplicates("ts_ms").sort_values("ts_ms").reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False, compression="zstd")
    log.info("Funding %s: wrote %d rows → %s", symbol, len(df), out_path)

    if ckpt.exists():
        ckpt.unlink()
    return df
