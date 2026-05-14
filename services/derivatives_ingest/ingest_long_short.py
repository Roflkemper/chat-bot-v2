"""Ingest historical Long-Short / Taker ratios from Binance Futures.

Endpoints (all public, 5-minute granularity):
  /futures/data/topLongShortAccountRatio   → top-trader account ratio
  /futures/data/topLongShortPositionRatio  → top-trader position ratio
  /futures/data/globalLongShortAccountRatio → global account ratio
  /futures/data/takerlongshortRatio        → taker buy/sell volume ratio

Output: backtests/frozen/derivatives_1y/{SYMBOL}_LS_5m_1y.parquet
Schema: ts_ms, symbol, ratio_type, longAccount, shortAccount, longShortRatio
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .binance_client import BinanceFuturesClient

log = logging.getLogger(__name__)

PERIOD = "5m"

# endpoint path → ratio_type label
_LS_ENDPOINTS: dict[str, str] = {
    "/futures/data/topLongShortAccountRatio": "top_account",
    "/futures/data/topLongShortPositionRatio": "top_position",
    "/futures/data/globalLongShortAccountRatio": "global_account",
    "/futures/data/takerlongshortRatio": "taker_volume",
}


def _checkpoint_path(out_path: Path) -> Path:
    return out_path.parent / (out_path.stem + "_checkpoint.json")


def _load_checkpoint(ckpt: Path) -> dict[str, int]:
    if ckpt.exists():
        try:
            return json.loads(ckpt.read_text())
        except Exception:
            pass
    return {}


def _save_checkpoint(ckpt: Path, state: dict[str, int]) -> None:
    ckpt.write_text(json.dumps(state))


def _parse_row(row: dict, symbol: str, ratio_type: str) -> dict:
    """Normalise a single API row across all 4 endpoint shapes."""
    ts = int(row.get("timestamp", 0))
    # taker endpoint uses "buySellRatio" instead of "longShortRatio"
    ls_ratio = float(row.get("longShortRatio") or row.get("buySellRatio") or 0)
    long_acc = float(row.get("longAccount") or row.get("buyVol") or 0)
    short_acc = float(row.get("shortAccount") or row.get("sellVol") or 0)
    return {
        "ts_ms": ts,
        "symbol": symbol,
        "ratio_type": ratio_type,
        "longAccount": long_acc,
        "shortAccount": short_acc,
        "longShortRatio": ls_ratio,
    }


def ingest_long_short(
    symbol: str,
    start_ms: int,
    end_ms: int,
    out_path: Path,
    client: Optional[BinanceFuturesClient] = None,
    resume: bool = True,
) -> pd.DataFrame:
    """Fetch all 4 LS ratio series and write a single parquet. Returns DataFrame."""
    client = client or BinanceFuturesClient()
    ckpt = _checkpoint_path(out_path)
    ckpt_state = _load_checkpoint(ckpt) if resume else {}

    rows: list[dict] = []
    if resume and out_path.exists():
        existing = pd.read_parquet(out_path)
        rows = existing.to_dict("records")
        log.info("LS %s: loaded %d existing rows", symbol, len(rows))

    for endpoint, ratio_type in _LS_ENDPOINTS.items():
        cursor = start_ms
        if resume:
            saved = ckpt_state.get(ratio_type)
            if saved and saved > cursor:
                log.info("LS %s/%s: resuming from %d", symbol, ratio_type, saved)
                cursor = saved + 1

        ep_batches = 0
        for batch in client.paginate_ls_ratio(endpoint, symbol, PERIOD, cursor, end_ms):
            for row in batch:
                rows.append(_parse_row(row, symbol, ratio_type))
            ckpt_state[ratio_type] = int(batch[-1]["timestamp"])
            _save_checkpoint(ckpt, ckpt_state)
            ep_batches += 1

        log.info("LS %s/%s: fetched %d batches", symbol, ratio_type, ep_batches)

    if not rows:
        log.warning("LS %s: no rows fetched", symbol)
        return pd.DataFrame(columns=["ts_ms", "symbol", "ratio_type", "longAccount", "shortAccount", "longShortRatio"])

    df = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["ts_ms", "ratio_type"])
        .sort_values(["ratio_type", "ts_ms"])
        .reset_index(drop=True)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False, compression="zstd")
    log.info("LS %s: wrote %d rows → %s", symbol, len(df), out_path)

    if ckpt.exists():
        ckpt.unlink()
    return df
