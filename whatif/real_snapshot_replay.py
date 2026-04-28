from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.whatif.action_simulator import ACTIONS
from src.whatif.grid_search import Episode
from src.whatif.horizon_runner import StateAtMinute, run_horizon
from src.whatif.outcome import compute_outcome
from src.whatif.runner import PLAY_CONFIGS, load_episodes
from src.whatif.snapshot import Snapshot, build_snapshot

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIR = ROOT / "features_out"
EPISODES_PATH = ROOT / "frozen" / "labels" / "episodes.parquet"
TRACKER_PARQUET_DIR = ROOT / "data" / "tracker" / "snapshots"
TRACKER_SNAPSHOTS_CSV = ROOT / "ginarea_tracker" / "ginarea_live" / "snapshots_v2.csv"
TRACKER_PARAMS_CSV = ROOT / "ginarea_tracker" / "ginarea_live" / "params_v2.csv"
ALIASES_PATH = ROOT / "ginarea_tracker" / "bot_aliases.json"


@dataclass
class ReplayResult:
    play_id: str
    bot_selector: str
    episode_id: str
    ts_start: pd.Timestamp
    horizon_min: int
    params: dict[str, Any]
    baseline_real_pnl_usd: float
    baseline_real_dd_pct: float
    action_pnl_usd: float
    pnl_vs_baseline_usd: float
    action_dd_pct: float
    dd_vs_baseline_pct: float
    n_points: int


def _load_aliases() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


def _safe_read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def _resolve_bot_selector(frame: pd.DataFrame, selector: str) -> pd.DataFrame:
    selector_str = str(selector).strip()
    aliases = frame["alias"].fillna("").astype(str).str.strip()
    bot_names = frame["bot_name"].fillna("").astype(str).str.strip()
    bot_ids = frame["bot_id"].astype(str).str.strip()
    mask = (aliases == selector_str) | (bot_names == selector_str) | (bot_ids == selector_str)

    if not mask.any():
        alias_map = _load_aliases()
        inv_alias = {alias: bot_id for bot_id, alias in alias_map.items()}
        mapped = inv_alias.get(selector_str)
        if mapped is not None:
            mask = bot_ids == str(mapped)

    return frame.loc[mask].copy()


def _load_price_series(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    current = start.normalize()
    stop = end.normalize()
    parts: list[pd.DataFrame] = []
    while current <= stop:
        path = FEATURES_DIR / symbol / f"{current.date()}.parquet"
        if path.exists():
            part = pd.read_parquet(path, columns=["close"]).reset_index()
            part = part.rename(columns={part.columns[0]: "ts_utc", "close": "price"})
            parts.append(part)
        current += pd.Timedelta(days=1)
    if not parts:
        return pd.DataFrame(columns=["ts_utc", "price"])
    prices = pd.concat(parts, ignore_index=True)
    prices["ts_utc"] = pd.to_datetime(prices["ts_utc"], utc=True)
    return prices[(prices["ts_utc"] >= start) & (prices["ts_utc"] <= end)].copy()


def _load_tracker_csv(bot_selector: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    snaps = _safe_read_csv(TRACKER_SNAPSHOTS_CSV)
    params = _safe_read_csv(TRACKER_PARAMS_CSV)

    snaps["ts_utc"] = pd.to_datetime(snaps["ts_utc"], utc=True, errors="coerce")
    params["ts_utc"] = pd.to_datetime(params["ts_utc"], utc=True, errors="coerce")
    snaps = _resolve_bot_selector(snaps, bot_selector)
    params = _resolve_bot_selector(params, bot_selector)
    snaps = snaps[(snaps["ts_utc"] >= start) & (snaps["ts_utc"] <= end)].copy()
    params = params[(params["ts_utc"] >= start - pd.Timedelta(hours=6)) & (params["ts_utc"] <= end)].copy()
    if snaps.empty:
        return snaps

    snaps = snaps.sort_values("ts_utc")
    params = params.sort_values("ts_utc")
    merged = pd.merge_asof(
        snaps,
        params[
            [
                "ts_utc",
                "bot_id",
                "grid_step",
                "border_top",
                "border_bottom",
                "target",
                "side",
            ]
        ],
        on="ts_utc",
        by="bot_id",
        direction="backward",
    )
    prices = _load_price_series("BTCUSDT", start, end)
    merged = pd.merge_asof(
        merged.sort_values("ts_utc"),
        prices.sort_values("ts_utc"),
        on="ts_utc",
        direction="nearest",
        tolerance=pd.Timedelta(minutes=2),
    )
    merged["symbol"] = "BTCUSDT"
    merged["position_btc"] = pd.to_numeric(merged["position"], errors="coerce").fillna(0.0)
    merged["unrealized_pnl"] = pd.to_numeric(merged["current_profit"], errors="coerce").fillna(0.0)
    merged["realized_pnl_session"] = pd.to_numeric(merged["profit"], errors="coerce").fillna(0.0)
    merged["grid_top"] = pd.to_numeric(merged["border_top"], errors="coerce")
    merged["grid_bottom"] = pd.to_numeric(merged["border_bottom"], errors="coerce")
    merged["grid_step"] = pd.to_numeric(merged["grid_step"], errors="coerce")
    merged["n_filled_orders"] = (
        pd.to_numeric(merged["in_filled_count"], errors="coerce").fillna(0.0)
        + pd.to_numeric(merged["out_filled_count"], errors="coerce").fillna(0.0)
    )
    return merged[
        [
            "ts_utc",
            "bot_id",
            "bot_name",
            "alias",
            "symbol",
            "price",
            "position_btc",
            "unrealized_pnl",
            "grid_top",
            "grid_bottom",
            "grid_step",
            "n_filled_orders",
            "realized_pnl_session",
            "average_price",
            "target",
            "side",
        ]
    ].dropna(subset=["price"]).reset_index(drop=True)


def _bot_coverage(bot_selectors: list[str]) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if not TRACKER_SNAPSHOTS_CSV.exists():
        return None, None
    snaps = _safe_read_csv(TRACKER_SNAPSHOTS_CSV)
    snaps["ts_utc"] = pd.to_datetime(snaps["ts_utc"], utc=True, errors="coerce")
    parts = []
    for selector in bot_selectors:
        part = _resolve_bot_selector(snaps, selector)
        if not part.empty:
            parts.append(part[["ts_utc"]])
    if not parts:
        return None, None
    all_rows = pd.concat(parts, ignore_index=True)
    return all_rows["ts_utc"].min(), all_rows["ts_utc"].max()


def load_bot_episode(bot_id: str, ts_start: pd.Timestamp | str, horizon_min: int) -> pd.DataFrame:
    ts = pd.Timestamp(ts_start, tz="UTC") if not isinstance(ts_start, pd.Timestamp) else ts_start
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    ts_end = ts + pd.Timedelta(minutes=horizon_min)

    parquet_day = TRACKER_PARQUET_DIR / str(bot_id) / f"{ts.date()}.parquet"
    if parquet_day.exists():
        frame = pd.read_parquet(parquet_day)
        frame["ts_utc"] = pd.to_datetime(frame["ts_utc"], utc=True)
        return frame[(frame["ts_utc"] >= ts) & (frame["ts_utc"] <= ts_end)].reset_index(drop=True)

    return _load_tracker_csv(bot_id, ts, ts_end)


def _real_baseline_metrics(episode: pd.DataFrame) -> tuple[float, float]:
    if episode.empty:
        return 0.0, 0.0
    first = episode.iloc[0]
    last = episode.iloc[-1]
    pnl = (
        float(last["realized_pnl_session"]) - float(first["realized_pnl_session"])
        + float(last["unrealized_pnl"]) - float(first["unrealized_pnl"])
    )
    equity = float(first["realized_pnl_session"]) + episode["unrealized_pnl"].astype(float)
    peak = equity.cummax()
    drawdown = peak - equity
    denom = max(1.0, abs(float(first["realized_pnl_session"])) + abs(float(first["unrealized_pnl"])))
    dd_pct = float(drawdown.max() / denom * 100.0)
    return pnl, dd_pct


def _build_real_snapshot(row: pd.Series) -> Snapshot:
    ts = pd.Timestamp(row["ts_utc"], tz="UTC") if not isinstance(row["ts_utc"], pd.Timestamp) else row["ts_utc"]
    target = float(row.get("target", 0.25) or 0.25)
    step = float(row.get("grid_step", 0.03) or 0.03)
    return build_snapshot(
        timestamp=ts,
        symbol=str(row.get("symbol", "BTCUSDT")),
        features_dir=FEATURES_DIR,
        position_size_btc=float(row.get("position_btc", 0.0) or 0.0),
        avg_entry=float(row.get("average_price", 0.0) or 0.0),
        unrealized_pnl_usd=float(row.get("unrealized_pnl", 0.0) or 0.0),
        realized_pnl_session=float(row.get("realized_pnl_session", 0.0) or 0.0),
        grid_target_pct=target,
        grid_step_pct=step,
        boundary_top=float(row.get("grid_top", 0.0) or 0.0),
        boundary_bottom=float(row.get("grid_bottom", 0.0) or 0.0),
    )


def apply_play_to_real(episode: pd.DataFrame, play: str, params: dict[str, Any]) -> ReplayResult:
    if play not in PLAY_CONFIGS:
        raise ValueError(f"Unknown play: {play}")
    if episode.empty:
        raise ValueError("Empty episode trajectory")

    config = PLAY_CONFIGS[play]
    first = episode.iloc[0]
    snap = _build_real_snapshot(first)
    action_snap = ACTIONS[config.action_name](snap, params)
    states = run_horizon(action_snap, horizon_min=max(1, len(episode) - 1), features_dir=FEATURES_DIR)
    outcome = compute_outcome(states, snap.capital_usd)
    baseline_pnl, baseline_dd = _real_baseline_metrics(episode)
    return ReplayResult(
        play_id=play,
        bot_selector=str(first.get("alias") or first.get("bot_name") or first.get("bot_id")),
        episode_id=str(first.get("episode_id", "")),
        ts_start=pd.Timestamp(first["ts_utc"]),
        horizon_min=max(1, len(episode) - 1),
        params=dict(params),
        baseline_real_pnl_usd=baseline_pnl,
        baseline_real_dd_pct=baseline_dd,
        action_pnl_usd=outcome.pnl_usd,
        pnl_vs_baseline_usd=outcome.pnl_usd - baseline_pnl,
        action_dd_pct=outcome.max_drawdown_pct,
        dd_vs_baseline_pct=outcome.max_drawdown_pct - baseline_dd,
        n_points=len(episode),
    )


def _ci95(values: pd.Series) -> tuple[float, float]:
    if values.empty:
        return 0.0, 0.0
    mean = float(values.mean())
    if len(values) < 2:
        return mean, mean
    std = float(values.std(ddof=1))
    half = 1.96 * std / math.sqrt(len(values))
    return mean - half, mean + half


def run_real_play(
    play: str,
    bot_selectors: list[str],
    horizon_min: int = 240,
    episodes_path: Path = EPISODES_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = PLAY_CONFIGS[play]
    episodes_df = load_episodes(config, episodes_path, FEATURES_DIR, ["BTCUSDT"])
    if episodes_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    episodes_df = episodes_df.copy()
    episodes_df["ts_start"] = pd.to_datetime(episodes_df["ts_start"], utc=True)
    cov_start, cov_end = _bot_coverage(bot_selectors)
    if cov_start is not None and cov_end is not None:
        latest_start = cov_end - pd.Timedelta(minutes=horizon_min)
        episodes_df = episodes_df[
            (episodes_df["ts_start"] >= cov_start) & (episodes_df["ts_start"] <= latest_start)
        ].reset_index(drop=True)
    if episodes_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    records: list[dict[str, Any]] = []
    for _, episode_row in episodes_df.iterrows():
        for bot_selector in bot_selectors:
            trajectory = load_bot_episode(bot_selector, episode_row["ts_start"], horizon_min)
            if trajectory.empty:
                continue
            trajectory = trajectory.copy()
            trajectory["episode_id"] = episode_row.get("episode_id", "")
            for params in config.param_grids:
                result = apply_play_to_real(trajectory, play, params)
                records.append(result.__dict__)

    raw = pd.DataFrame.from_records(records)
    if raw.empty:
        return raw, raw

    grouped = []
    for param_values, grp in raw.groupby(raw["params"].apply(lambda x: json.dumps(x, sort_keys=True)), sort=False):
        ci_low, ci_high = _ci95(grp["pnl_vs_baseline_usd"])
        grouped.append(
            {
                "play_id": play,
                "param_values": param_values,
                "n_episodes": int(len(grp)),
                "n_bots": int(grp["bot_selector"].nunique()),
                "mean_pnl_vs_baseline_usd": float(grp["pnl_vs_baseline_usd"].mean()),
                "ci95_low_usd": ci_low,
                "ci95_high_usd": ci_high,
                "mean_action_pnl_usd": float(grp["action_pnl_usd"].mean()),
                "mean_baseline_real_pnl_usd": float(grp["baseline_real_pnl_usd"].mean()),
                "mean_action_dd_pct": float(grp["action_dd_pct"].mean()),
                "mean_baseline_real_dd_pct": float(grp["baseline_real_dd_pct"].mean()),
            }
        )
    summary = pd.DataFrame(grouped).sort_values("mean_pnl_vs_baseline_usd", ascending=False).reset_index(drop=True)
    return summary, raw
