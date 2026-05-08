from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.ginarea_api.models import BotStatus, Side
from src.features.technical import _atr, _rsi

SCHEMA_VERSION = 1
PARAM_CHANGE_FIELDS = (
    "target",
    "grid_step",
    "order_size",
    "border_top",
    "border_bottom",
    "dsblin",
)
STATUS_MAP: dict[int, str] = {
    int(BotStatus.CREATED): "created",
    int(BotStatus.STARTING): "starting",
    int(BotStatus.ACTIVE): "running",
    int(BotStatus.PAUSED): "paused",
    int(BotStatus.DISABLE_IN): "paused",
    int(BotStatus.FAILED): "failed",
    int(BotStatus.STOPPING): "stopping",
    int(BotStatus.STOPPED): "stopped",
    int(BotStatus.CLOSING): "stopping",
    int(BotStatus.FINISHED): "stopped",
    int(BotStatus.TP_STOPPED): "stopped",
    int(BotStatus.SL_STOPPED): "stopped",
}
SIDE_SYMBOL_MAP: dict[int, str] = {
    int(Side.LONG): "BTCUSDT",
    int(Side.SHORT): "BTCUSDT",
}


@dataclass(slots=True)
class ExtractionPaths:
    params_csv: Path = Path("ginarea_live/params.csv")
    snapshots_csv: Path = Path("ginarea_live/snapshots.csv")
    ict_parquet: Path = Path("data/ict_levels/BTCUSDT_ict_levels_1m.parquet")
    frozen_ohlcv_csv: Path = Path("backtests/frozen/BTCUSDT_1m_2y.csv")
    output_parquet: Path = Path("data/operator_journal/decisions.parquet")


def _coerce_ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _normalize_bool(value: Any) -> bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _safe_json_loads(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else {}
    except json.JSONDecodeError:
        return {}


def _serialize_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _extract_order_size(raw: dict[str, Any]) -> float | None:
    q = raw.get("q")
    if not isinstance(q, dict):
        return None
    value = q.get("minQ")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load_params_history(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = _coerce_ts(df["ts_utc"])
    df = df.dropna(subset=["ts"]).sort_values(["bot_id", "ts"]).copy()
    df["bot_id"] = df["bot_id"].astype(str)
    df["side_num"] = pd.to_numeric(df["side"], errors="coerce")
    df["raw_params"] = df["raw_params_json"].apply(_safe_json_loads)
    df["order_size"] = df["raw_params"].apply(_extract_order_size)
    for col in ("target", "grid_step", "border_top", "border_bottom"):
        df[col] = _to_float(df[col])
    df["dsblin"] = df["dsblin"].apply(_normalize_bool)
    return df


def _load_snapshots(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = _coerce_ts(df["ts_utc"])
    df = df.dropna(subset=["ts"]).sort_values(["bot_id", "ts"]).copy()
    df["bot_id"] = df["bot_id"].astype(str)
    for col in ("position", "profit", "current_profit", "average_price", "liquidation_price"):
        df[col] = _to_float(df[col])
    status_num = pd.to_numeric(df["status"], errors="coerce")
    df["state"] = status_num.apply(lambda x: STATUS_MAP.get(int(x)) if pd.notna(x) and int(x) == x else None)
    return df


def _compute_market_features(ohlcv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(ohlcv_path)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).set_index("ts").sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df_1h = df.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    atr_1h = _atr(df_1h)
    rsi_1h = _rsi(df_1h["close"])
    df["price"] = df["close"]
    df["atr_1h"] = atr_1h.shift(1).reindex(df.index, method="ffill")
    df["rsi_1h"] = rsi_1h.shift(1).reindex(df.index, method="ffill")
    df["roc_1h_pct"] = df["close"].pct_change(60) * 100.0
    df["roc_4h_pct"] = df["close"].pct_change(240) * 100.0
    return df[["price", "atr_1h", "rsi_1h", "roc_1h_pct", "roc_4h_pct"]]


def _load_ict_context(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if "ts" in df.columns:
        df["ts"] = _coerce_ts(df["ts"])
        df = df.set_index("ts")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("ICT parquet must have a DatetimeIndex or ts column")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    cols = [
        "session_active",
        "dist_to_pdh_pct",
        "dist_to_nearest_unmitigated_high_pct",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
    return df[cols].sort_index()


def _build_param_events(params_df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for bot_id, group in params_df.groupby("bot_id", sort=False):
        prev: pd.Series | None = None
        for _, row in group.iterrows():
            if prev is None:
                prev = row
                continue
            for field in PARAM_CHANGE_FIELDS:
                old_value = prev.get(field)
                new_value = row.get(field)
                if pd.isna(old_value) and pd.isna(new_value):
                    continue
                if old_value == new_value:
                    continue
                records.append(
                    {
                        "ts": row["ts"],
                        "bot_id": bot_id,
                        "alias": row.get("alias"),
                        "symbol": SIDE_SYMBOL_MAP.get(int(row["side_num"])) if pd.notna(row["side_num"]) else "BTCUSDT",
                        "change_type": "param_change",
                        "field": field,
                        "old_value": old_value,
                        "new_value": new_value,
                    }
                )
            prev = row
    return pd.DataFrame.from_records(records)


def _build_state_events(snapshots_df: pd.DataFrame, params_df: pd.DataFrame) -> pd.DataFrame:
    aliases = (
        params_df.sort_values("ts")
        .groupby("bot_id", as_index=False)
        .last()[["bot_id", "alias", "side_num"]]
    )
    records: list[dict[str, Any]] = []
    for bot_id, group in snapshots_df.groupby("bot_id", sort=False):
        prev: pd.Series | None = None
        for _, row in group.iterrows():
            current_state = row.get("state")
            if prev is not None:
                old_state = prev.get("state")
                if current_state and old_state and current_state != old_state:
                    records.append(
                        {
                            "ts": row["ts"],
                            "bot_id": bot_id,
                            "change_type": "state_change",
                            "field": "state",
                            "old_value": old_state,
                            "new_value": current_state,
                        }
                    )
            prev = row
    if not records:
        return pd.DataFrame(columns=["ts", "bot_id", "alias", "symbol", "change_type", "field", "old_value", "new_value"])
    df = pd.DataFrame.from_records(records)
    df = df.merge(aliases, on="bot_id", how="left")
    df["symbol"] = df["side_num"].apply(lambda x: SIDE_SYMBOL_MAP.get(int(x)) if pd.notna(x) else "BTCUSDT")
    return df.drop(columns=["side_num"])


def _attach_context(events_df: pd.DataFrame, market_df: pd.DataFrame, ict_df: pd.DataFrame, snapshots_df: pd.DataFrame) -> pd.DataFrame:
    if events_df.empty:
        return events_df.copy()
    out = events_df.sort_values(["ts", "bot_id", "field"]).reset_index(drop=True).copy()

    market_reset = market_df.sort_index().rename_axis("market_ts").reset_index()
    ict_reset = ict_df.sort_index().rename_axis("ict_ts").reset_index()
    snap_reset = snapshots_df.sort_values(["bot_id", "ts"]).reset_index(drop=True)

    out = pd.merge_asof(out, market_reset, left_on="ts", right_on="market_ts", direction="backward")
    out = pd.merge_asof(out, ict_reset, left_on="ts", right_on="ict_ts", direction="backward")
    snapshot_cols = ["profit", "current_profit", "position", "average_price", "liquidation_price"]
    snapshot_map = {
        bot_id: group.set_index("ts")[snapshot_cols].sort_index()
        for bot_id, group in snap_reset.groupby("bot_id", sort=False)
    }
    for col in snapshot_cols:
        out[col] = np.nan
    for idx, row in out.iterrows():
        group = snapshot_map.get(str(row["bot_id"]))
        if group is None or group.empty:
            continue
        subset = group[group.index <= row["ts"]]
        if subset.empty:
            continue
        latest = subset.iloc[-1]
        for col in snapshot_cols:
            out.at[idx, col] = latest[col]

    out["unrealized_pnl"] = out["current_profit"]
    out["realized_pnl_24h"] = out.apply(
        lambda row: _realized_delta_last_24h(snapshots_df, str(row["bot_id"]), row["ts"]),
        axis=1,
    )
    out["position_size_btc"] = out["position"].abs()
    out["distance_to_liq_pct"] = ((out["liquidation_price"] - out["average_price"]) / out["average_price"].replace(0, np.nan)) * 100.0
    return out


def _realized_delta_last_24h(snapshots_df: pd.DataFrame, bot_id: str, ts: pd.Timestamp) -> float | None:
    group = snapshots_df[snapshots_df["bot_id"] == bot_id]
    if group.empty:
        return None
    current = group[group["ts"] <= ts].tail(1)
    past = group[group["ts"] <= ts - pd.Timedelta(hours=24)].tail(1)
    if current.empty or past.empty:
        return None
    return float(current["profit"].iloc[0] - past["profit"].iloc[0])


def _snapshot_value_at_or_after(snapshots_df: pd.DataFrame, bot_id: str, ts: pd.Timestamp) -> pd.Series | None:
    group = snapshots_df[snapshots_df["bot_id"] == bot_id]
    future = group[group["ts"] >= ts].head(1)
    if future.empty:
        return None
    return future.iloc[0]


def _price_at_or_after(market_df: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    future = market_df[market_df.index >= ts]
    if future.empty:
        return None
    return float(future["price"].iloc[0])


def _apply_outcomes(events_df: pd.DataFrame, snapshots_df: pd.DataFrame, market_df: pd.DataFrame) -> pd.DataFrame:
    if events_df.empty:
        return events_df.copy()
    out = events_df.copy()
    horizons = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "24h": pd.Timedelta(hours=24)}
    helpful_scores: list[float | None] = []
    helpful_bases: list[float | None] = []

    for idx, row in out.iterrows():
        base_price = row.get("price")
        base_realized = row.get("profit")
        bot_id = str(row["bot_id"])
        ts = row["ts"]
        delta_1h_realized: float | None = None
        for label, delta in horizons.items():
            target_ts = ts + delta
            future_snapshot = _snapshot_value_at_or_after(snapshots_df, bot_id, target_ts)
            future_price = _price_at_or_after(market_df, target_ts)
            out.at[idx, f"price_change_pct_{label}"] = (
                ((future_price - base_price) / base_price * 100.0) if future_price is not None and pd.notna(base_price) and base_price else np.nan
            )
            if future_snapshot is None or pd.isna(base_realized):
                out.at[idx, f"bot_realized_pnl_{label}"] = np.nan
                out.at[idx, f"bot_unrealized_pnl_{label}"] = np.nan
            else:
                realized_delta = float(future_snapshot["profit"] - base_realized)
                out.at[idx, f"bot_realized_pnl_{label}"] = realized_delta
                out.at[idx, f"bot_unrealized_pnl_{label}"] = float(future_snapshot["current_profit"])
                if label == "1h":
                    delta_1h_realized = realized_delta
        helpful_scores.append(delta_1h_realized)
        helpful_bases.append(_rolling_mean_before(out.iloc[: idx + 1], bot_id, ts))

    helpful: list[Any] = []
    for score, base in zip(helpful_scores, helpful_bases):
        if score is None or pd.isna(score) or base is None or pd.isna(base):
            helpful.append(np.nan)
        else:
            helpful.append(bool(score > base))
    out["decision_was_helpful"] = helpful
    return out


def _rolling_mean_before(events_df: pd.DataFrame, bot_id: str, ts: pd.Timestamp) -> float | None:
    prior = events_df[(events_df["bot_id"].astype(str) == bot_id) & (events_df["ts"] < ts) & (events_df["ts"] >= ts - pd.Timedelta(hours=24))]
    if prior.empty or "bot_realized_pnl_1h" not in prior.columns:
        return None
    values = pd.to_numeric(prior["bot_realized_pnl_1h"], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def build_decision_records(
    *,
    params_csv: str | Path,
    snapshots_csv: str | Path,
    ict_parquet: str | Path,
    frozen_ohlcv_csv: str | Path,
    existing_output: str | Path | None = None,
    incremental: bool = False,
) -> pd.DataFrame:
    params_df = _load_params_history(Path(params_csv))
    snapshots_df = _load_snapshots(Path(snapshots_csv))
    market_df = _compute_market_features(Path(frozen_ohlcv_csv))
    ict_df = _load_ict_context(Path(ict_parquet))

    param_events = _build_param_events(params_df)
    state_events = _build_state_events(snapshots_df, params_df)
    events_df = pd.concat([param_events, state_events], ignore_index=True, sort=False)
    if events_df.empty:
        return pd.DataFrame()

    if incremental and existing_output and Path(existing_output).exists():
        existing = pd.read_parquet(existing_output)
        if not existing.empty and "ts" in existing.columns:
            last_ts = pd.to_datetime(existing["ts"], utc=True, errors="coerce").max()
            if pd.notna(last_ts):
                events_df = events_df[events_df["ts"] > last_ts]

    events_df = _attach_context(events_df, market_df, ict_df, snapshots_df)
    events_df = _apply_outcomes(events_df, snapshots_df, market_df)
    events_df["bot_id"] = events_df["bot_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    if "alias" in events_df.columns:
        events_df["alias"] = events_df["alias"].astype("string")
    if "symbol" in events_df.columns:
        events_df["symbol"] = events_df["symbol"].astype("string")
    if "change_type" in events_df.columns:
        events_df["change_type"] = events_df["change_type"].astype("string")
    if "field" in events_df.columns:
        events_df["field"] = events_df["field"].astype("string")
    if "session_active" in events_df.columns:
        events_df["session_active"] = events_df["session_active"].astype("string")
    events_df["old_value"] = events_df["old_value"].apply(_serialize_value).astype("string")
    events_df["new_value"] = events_df["new_value"].apply(_serialize_value).astype("string")
    events_df["version"] = SCHEMA_VERSION
    events_df = events_df.drop_duplicates(subset=["ts", "bot_id", "field", "new_value", "change_type"]).sort_values(["ts", "bot_id", "field"])
    return events_df.reset_index(drop=True)


def run_extraction(
    *,
    paths: ExtractionPaths | None = None,
    rebuild: bool = False,
    incremental: bool = False,
    output: str | Path | None = None,
) -> pd.DataFrame:
    paths = paths or ExtractionPaths()
    output_path = Path(output) if output is not None else paths.output_parquet
    batch = build_decision_records(
        params_csv=paths.params_csv,
        snapshots_csv=paths.snapshots_csv,
        ict_parquet=paths.ict_parquet,
        frozen_ohlcv_csv=paths.frozen_ohlcv_csv,
        existing_output=output_path,
        incremental=incremental and not rebuild,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if rebuild or not output_path.exists():
        batch.to_parquet(output_path, index=False)
        return batch
    existing = pd.read_parquet(output_path)
    combined = pd.concat([existing, batch], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(subset=["ts", "bot_id", "field", "new_value", "change_type"]).sort_values(["ts", "bot_id", "field"])
    combined.to_parquet(output_path, index=False)
    return combined
