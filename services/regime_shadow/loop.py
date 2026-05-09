"""Shadow regime classifier — observation-only ML alongside production.

Every 5 min:
  1. Load BTCUSDT 1h klines (≥250 bars for warmup)
  2. Compute features via services.regime_red_green.features.compute_features
  3. Take last bar's feature row → classify with services.regime_red_green.rules.classify
  4. Read production regime via core.orchestrator.regime_classifier (Classifier A)
  5. Append both to state/regime_shadow.jsonl

Comparison happens offline (e.g. tools/_regime_shadow_report.py — to be written
after 30d of data). No alerts are emitted; this is purely observational.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
JOURNAL_PATH = ROOT / "state" / "regime_shadow.jsonl"
PROD_REGIME_PATH = ROOT / "state" / "regime_state.json"

POLL_INTERVAL_SEC = 300  # 5 min — match Classifier A cadence
SYMBOL = "BTCUSDT"


def _journal_append(event: dict) -> None:
    try:
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("regime_shadow.journal_write_failed")


def _read_prod_regime() -> dict | None:
    """Read Classifier A's latest verdict for SYMBOL from state/regime_state.json.

    File layout (Classifier A): {"symbols": {"BTCUSDT": {"current_primary": ...,
    "active_modifiers": {...}, ...}}}.
    """
    if not PROD_REGIME_PATH.exists():
        return None
    try:
        raw = json.loads(PROD_REGIME_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sym = raw.get("symbols", {}).get(SYMBOL) if isinstance(raw, dict) else None
    if not isinstance(sym, dict):
        return None
    return {
        "primary": sym.get("current_primary"),
        "regime_label": sym.get("current_primary"),
        "modifiers": list((sym.get("active_modifiers") or {}).keys()),
        "regime_age_bars": sym.get("regime_age_bars"),
    }


def _classify_b(df: pd.DataFrame) -> tuple[str, dict]:
    """Compute B-classifier verdict on the given 1h dataframe.

    Returns (verdict, last_row_features). On any failure returns ("ERROR", {}).
    """
    try:
        from services.regime_red_green.features import compute_features
        from services.regime_red_green.rules import classify, FEATURE_NAMES
        feats = compute_features(df)
        if feats.empty:
            return "ERROR", {}
        last = feats.iloc[-1]
        feat_dict = {name: float(last.get(name, 0.0) or 0.0) for name in FEATURE_NAMES}
        verdict = classify(feat_dict)
        return str(verdict), feat_dict
    except Exception:
        logger.exception("regime_shadow.classify_b_failed")
        return "ERROR", {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def regime_shadow_loop(stop_event: asyncio.Event,
                              interval_sec: int = POLL_INTERVAL_SEC) -> None:
    """Async loop. Every 5 min: poll BTC 1h klines, run B-classifier,
    log alongside Classifier A's current verdict."""
    logger.info("regime_shadow.start interval=%ds symbol=%s", interval_sec, SYMBOL)

    while not stop_event.is_set():
        try:
            from core.data_loader import load_klines
            df = load_klines(symbol=SYMBOL, timeframe="1h", limit=250)
            if df is None or len(df) < 50:
                logger.warning("regime_shadow.data_thin")
            else:
                # Need DatetimeIndex for compute_features
                if "open_time" in df.columns:
                    df = df.copy().set_index(pd.to_datetime(df["open_time"], utc=True))
                elif "ts" in df.columns:
                    df = df.copy().set_index(pd.to_datetime(df["ts"], unit="ms", utc=True))
                verdict_b, feats_b = _classify_b(df)
                prod = _read_prod_regime() or {}
                event = {
                    "ts": _now_iso(),
                    "verdict_b": verdict_b,
                    "verdict_a_label": prod.get("regime_label") or prod.get("primary"),
                    "verdict_a_modifiers": prod.get("modifiers", []),
                    "verdict_a_confidence": prod.get("confidence"),
                    "btc_close": float(df["close"].iloc[-1]) if "close" in df.columns else None,
                    "agree": _verdicts_agree(verdict_b, prod),
                }
                _journal_append(event)
                if verdict_b != "ERROR":
                    logger.info("regime_shadow.tick b=%s a=%s agree=%s",
                                verdict_b, event["verdict_a_label"], event["agree"])
        except Exception:
            logger.exception("regime_shadow.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass


def _verdicts_agree(verdict_b: str, prod: dict) -> bool | None:
    """Coarse agreement: B says RANGE → A's primary should be RANGE/COMPRESSION.
    B says TREND → A's primary should be TREND_UP/TREND_DOWN/CASCADE_*.
    B says AMBIGUOUS → no opinion, returns None."""
    if verdict_b in ("AMBIGUOUS", "ERROR"):
        return None
    a_label = str(prod.get("regime_label") or prod.get("primary") or "").upper()
    if not a_label:
        return None
    if verdict_b == "RANGE":
        return a_label in ("RANGE", "COMPRESSION")
    if verdict_b == "TREND":
        return any(t in a_label for t in ("TREND", "CASCADE"))
    return None
