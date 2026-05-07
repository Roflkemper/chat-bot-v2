"""Ingest historical OI + Long-Short ratios via data.binance.vision daily metrics files.

Uses data portal (not live API) — covers full 1y history at 5m granularity.

Output files:
  backtests/frozen/derivatives_1y/{SYMBOL}_OI_5m_1y.parquet
    Schema: ts_ms, symbol, sum_open_interest, sum_open_interest_value

  backtests/frozen/derivatives_1y/{SYMBOL}_LS_5m_1y.parquet
    Schema: ts_ms, symbol, top_trader_ls_ratio, global_ls_ratio, taker_vol_ratio
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .data_portal_client import DataPortalClient

log = logging.getLogger(__name__)


def _checkpoint_path(out_path: Path) -> Path:
    return out_path.parent / (out_path.stem + "_checkpoint.json")


def _load_checkpoint(ckpt: Path) -> Optional[date]:
    if ckpt.exists():
        try:
            d = json.loads(ckpt.read_text())["last_date"]
            return datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            pass
    return None


def _save_checkpoint(ckpt: Path, last_date: date) -> None:
    ckpt.write_text(json.dumps({"last_date": str(last_date)}))


def ingest_metrics(
    symbol: str,
    start_date: date,
    end_date: date,
    out_oi: Path,
    out_ls: Path,
    client: Optional[DataPortalClient] = None,
    resume: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch daily metrics from data portal and write OI + LS parquets.

    Returns (oi_df, ls_df).
    """
    client = client or DataPortalClient()
    ckpt = _checkpoint_path(out_oi)

    resume_after: Optional[date] = None
    oi_rows: list[dict] = []
    ls_rows: list[dict] = []

    if resume:
        # Always load existing parquet rows if present (covers both checkpoint and partial-run)
        if out_oi.exists():
            df_existing = pd.read_parquet(out_oi)
            oi_rows = df_existing.to_dict("records")
        if out_ls.exists():
            df_existing_ls = pd.read_parquet(out_ls)
            ls_rows = df_existing_ls.to_dict("records")
        saved = _load_checkpoint(ckpt)
        if saved:
            log.info("Metrics %s: resuming after checkpoint %s", symbol, saved)
            resume_after = saved

    days_fetched = 0
    for day, df in client.iter_metrics_range(symbol, start_date, end_date, resume_after):
        for _, row in df.iterrows():
            oi_rows.append({
                "ts_ms": int(row["ts_ms"]),
                "symbol": symbol,
                "sum_open_interest": float(row["sum_open_interest"]),
                "sum_open_interest_value": float(row["sum_open_interest_value"]),
            })
            ls_rows.append({
                "ts_ms": int(row["ts_ms"]),
                "symbol": symbol,
                "top_trader_ls_ratio": float(row["top_trader_ls_ratio"]),
                "global_ls_ratio": float(row["global_ls_ratio"]),
                "taker_vol_ratio": float(row["taker_vol_ratio"]),
            })
        _save_checkpoint(ckpt, day)
        days_fetched += 1
        if days_fetched % 30 == 0:
            log.info("Metrics %s: %d days fetched, %d OI rows", symbol, days_fetched, len(oi_rows))

    # OI parquet
    if not oi_rows:
        log.warning("Metrics %s: no OI rows", symbol)
        oi_df = pd.DataFrame(columns=["ts_ms", "symbol", "sum_open_interest", "sum_open_interest_value"])
    else:
        oi_df = (
            pd.DataFrame(oi_rows)
            .drop_duplicates("ts_ms")
            .sort_values("ts_ms")
            .reset_index(drop=True)
        )
        out_oi.parent.mkdir(parents=True, exist_ok=True)
        oi_df.to_parquet(out_oi, index=False, compression="zstd")
        log.info("OI %s: wrote %d rows → %s", symbol, len(oi_df), out_oi)

    # LS parquet
    if not ls_rows:
        log.warning("Metrics %s: no LS rows", symbol)
        ls_df = pd.DataFrame(columns=["ts_ms", "symbol", "top_trader_ls_ratio", "global_ls_ratio", "taker_vol_ratio"])
    else:
        ls_df = (
            pd.DataFrame(ls_rows)
            .drop_duplicates("ts_ms")
            .sort_values("ts_ms")
            .reset_index(drop=True)
        )
        out_ls.parent.mkdir(parents=True, exist_ok=True)
        ls_df.to_parquet(out_ls, index=False, compression="zstd")
        log.info("LS %s: wrote %d rows → %s", symbol, len(ls_df), out_ls)

    if ckpt.exists():
        ckpt.unlink()
    return oi_df, ls_df
