from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import math

import numpy as np
import pandas as pd

from services.setup_backtest.historical_context import HistoricalContextBuilder
from services.setup_detector.ict_context import ICTContextReader

ROOT = Path(__file__).resolve().parents[2]
FROZEN_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
ICT_PARQUET = ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"
REPORT_PATH = ROOT / "reports" / "defensive_actions_research_v3_aggressive_widen_2026-05-02.md"

YEAR_START = pd.Timestamp("2025-05-01T00:00:00Z")
YEAR_END = pd.Timestamp("2026-04-29T23:59:00Z")
DEPOSIT_USD = 15_000.0
BASE_POSITION_BTC = 0.20
ADD_BTC = 0.10
SHORT_TARGET = 0.25
SHORT_GS = 0.03
LONG_TARGET = 0.25
LONG_GS = 0.03
LIQ_PCT_BUFFER = 20.0
COOLDOWN_HOURS = 4

HYPOTHESES = (
    "AGGRESSIVE_LONG_ON_RALLY",
    "WIDEN_GRID_SHORT",
    "WIDEN_GRID_LONG",
)


@dataclass(slots=True)
class Episode:
    hypothesis: str
    ts: pd.Timestamp
    entry_price: float
    current_price: float
    side: str
    move_pct: float
    duration_bucket: str
    session_label: str
    regime_label: str
    volume_regime: str
    liq_distance_pct: float
    dd_pct_deposit: float
    dist_to_resistance_pct: float | None


def _load_year_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(FROZEN_1M)
    raw["ts"] = pd.to_datetime(raw["ts"], unit="ms", utc=True)
    raw = raw.set_index("ts").sort_index()
    raw = raw.loc[YEAR_START:YEAR_END, ["open", "high", "low", "close", "volume"]].copy()

    ict = pd.read_parquet(ICT_PARQUET)
    if not isinstance(ict.index, pd.DatetimeIndex):
        raise ValueError("ICT parquet must have DatetimeIndex")
    if ict.index.tz is None:
        ict.index = ict.index.tz_localize("UTC")
    else:
        ict.index = ict.index.tz_convert("UTC")
    ict = ict.loc[YEAR_START:YEAR_END].copy()
    return raw, ict


def _build_hourly_features(df_1m: pd.DataFrame, ict_1m: pd.DataFrame) -> pd.DataFrame:
    df_1h = df_1m.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    ict_hour = ict_1m.resample("1h").last()
    df = df_1h.join(
        ict_hour[
            [
                "session_active",
                "dist_to_pdh_pct",
                "dist_to_pdl_pct",
                "dist_to_nearest_unmitigated_high_pct",
                "dist_to_nearest_unmitigated_low_pct",
            ]
        ],
        how="left",
    )
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = tr.rolling(14, min_periods=5).mean()
    df["atr_pct"] = df["atr_14"] / df["close"] * 100.0
    df["volume_sma20"] = df["volume"].rolling(20, min_periods=5).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma20"]
    df["roc_1h_pct"] = df["close"].pct_change(1) * 100.0
    df["roc_4h_pct"] = df["close"].pct_change(4) * 100.0
    df["roc_24h_pct"] = df["close"].pct_change(24) * 100.0
    ma20 = df["close"].rolling(20, min_periods=5).mean()
    slope = ma20.diff(5) / df["close"] * 100.0
    df["regime_label"] = np.where(
        slope > 0.3,
        "trend_up",
        np.where(slope < -0.3, "trend_down", "consolidation"),
    )
    return df


def _price_path(df_1m: pd.DataFrame, ts: pd.Timestamp) -> pd.DataFrame:
    return df_1m.loc[ts : ts + pd.Timedelta(hours=24)].copy()


def _accept(episodes: list[Episode], hypothesis: str, ts: pd.Timestamp) -> bool:
    for ep in reversed(episodes):
        if ep.hypothesis != hypothesis:
            continue
        if (ts - ep.ts).total_seconds() < COOLDOWN_HOURS * 3600:
            return False
        return True
    return True


def _duration_bucket(hours: int) -> str:
    if hours <= 1:
        return "1h"
    if hours <= 4:
        return "4h"
    return "12h"


def mine_episodes(df_1h: pd.DataFrame) -> list[Episode]:
    episodes: list[Episode] = []
    for i in range(48, len(df_1h) - 24):
        row = df_1h.iloc[i]
        ts = pd.Timestamp(df_1h.index[i])
        current = float(row["close"])
        volume_regime = "above_sma20" if float(row["volume_ratio"]) > 1.0 else "below_sma20"
        session = str(row.get("session_active") or "dead")
        regime = str(row["regime_label"])

        for lookback in (1, 2, 3, 4):
            entry = float(df_1h["close"].iloc[i - lookback])
            move_pct = (current / entry - 1.0) * 100.0
            liq_distance_long = max(0.0, (current - entry * 0.75) / current * 100.0)
            if (
                1.0 <= move_pct <= 4.0
                and liq_distance_long > 20.0
                and float(row["volume_ratio"]) > 0.9
                and _accept(episodes, "AGGRESSIVE_LONG_ON_RALLY", ts)
            ):
                episodes.append(
                    Episode(
                        hypothesis="AGGRESSIVE_LONG_ON_RALLY",
                        ts=ts,
                        entry_price=entry,
                        current_price=current,
                        side="long",
                        move_pct=move_pct,
                        duration_bucket=_duration_bucket(lookback),
                        session_label=session,
                        regime_label=regime,
                        volume_regime=volume_regime,
                        liq_distance_pct=liq_distance_long,
                        dd_pct_deposit=0.0,
                        dist_to_resistance_pct=float(row["dist_to_nearest_unmitigated_high_pct"]) if not pd.isna(row["dist_to_nearest_unmitigated_high_pct"]) else None,
                    )
                )
                break

        for lookback in (2, 3, 4, 5, 6):
            entry = float(df_1h["close"].iloc[i - lookback])
            move_against_short_pct = (current / entry - 1.0) * 100.0
            liq_distance_short = max(0.0, (entry * 1.20 - current) / current * 100.0)
            dd_usd_short = max(0.0, (current - entry) * BASE_POSITION_BTC)
            dd_pct_dep_short = dd_usd_short / DEPOSIT_USD * 100.0
            if (
                0.8 <= move_against_short_pct <= 4.0
                and dd_pct_dep_short >= 0.1
                and liq_distance_short > 10.0
                and _accept(episodes, "WIDEN_GRID_SHORT", ts)
            ):
                episodes.append(
                    Episode(
                        hypothesis="WIDEN_GRID_SHORT",
                        ts=ts,
                        entry_price=entry,
                        current_price=current,
                        side="short",
                        move_pct=move_against_short_pct,
                        duration_bucket=_duration_bucket(lookback),
                        session_label=session,
                        regime_label=regime,
                        volume_regime=volume_regime,
                        liq_distance_pct=liq_distance_short,
                        dd_pct_deposit=dd_pct_dep_short,
                        dist_to_resistance_pct=float(row["dist_to_nearest_unmitigated_high_pct"]) if not pd.isna(row["dist_to_nearest_unmitigated_high_pct"]) else None,
                    )
                )
                break

        for lookback in (2, 3, 4, 5, 6):
            entry = float(df_1h["close"].iloc[i - lookback])
            move_against_long_pct = (current / entry - 1.0) * 100.0
            move_down_pct = -move_against_long_pct
            liq_distance_long = max(0.0, (current - entry * 0.80) / current * 100.0)
            dd_usd_long = max(0.0, (entry - current) * BASE_POSITION_BTC)
            dd_pct_dep_long = dd_usd_long / DEPOSIT_USD * 100.0
            if (
                0.8 <= move_down_pct <= 4.0
                and dd_pct_dep_long >= 0.1
                and liq_distance_long > 10.0
                and _accept(episodes, "WIDEN_GRID_LONG", ts)
            ):
                episodes.append(
                    Episode(
                        hypothesis="WIDEN_GRID_LONG",
                        ts=ts,
                        entry_price=entry,
                        current_price=current,
                        side="long",
                        move_pct=move_down_pct,
                        duration_bucket=_duration_bucket(lookback),
                        session_label=session,
                        regime_label=regime,
                        volume_regime=volume_regime,
                        liq_distance_pct=liq_distance_long,
                        dd_pct_deposit=dd_pct_dep_long,
                        dist_to_resistance_pct=float(row["dist_to_nearest_unmitigated_low_pct"]) if not pd.isna(row["dist_to_nearest_unmitigated_low_pct"]) else None,
                    )
                )
                break
    return episodes


def _pnl_linear(entry: float, price: float, size_btc: float, side: str) -> float:
    if side == "long":
        return (price - entry) * size_btc
    return (entry - price) * size_btc


def _simulate_aggressive_baseline(path_1m: pd.DataFrame, ep: Episode) -> dict[str, Any]:
    final_price = float(path_1m["close"].iloc[-1])
    base = _pnl_linear(ep.entry_price, ep.current_price, BASE_POSITION_BTC, "long")
    dd = [base] + [_pnl_linear(ep.entry_price, float(p), BASE_POSITION_BTC, "long") for p in path_1m["close"]]
    return {
        "scenario": "actual_action",
        "realized_pnl_24h_usd": base,
        "unrealized_at_24h_usd": 0.0,
        "net_pnl_24h_usd": base,
        "max_dd_during_24h_pct": min(dd) / DEPOSIT_USD * 100.0,
        "recovery_time_hours": 0.0,
        "position_size_at_24h_btc": 0.0,
        "survived": True,
        "liquidated": False,
    }


def _recovery_time(path_1m: pd.DataFrame, target_unrealized: float, pnl_fn) -> float | None:
    start_ts = path_1m.index[0]
    for ts, row in path_1m.iterrows():
        if pnl_fn(float(row["close"])) >= target_unrealized:
            return (ts - start_ts).total_seconds() / 3600.0
    return None


def _simulate_aggressive_add(path_1m: pd.DataFrame, ep: Episode, with_stop: bool) -> dict[str, Any]:
    stop_price = ep.current_price * 0.985 if with_stop else None
    closed_add_leg = False
    close_price_add = None
    pnl_path: list[float] = []
    liquidation = False
    final_position = BASE_POSITION_BTC + ADD_BTC

    for _, row in path_1m.iterrows():
        price = float(row["close"])
        if price <= ep.entry_price * 0.75:
            liquidation = True
        if with_stop and not closed_add_leg and stop_price is not None and float(row["low"]) <= stop_price:
            close_price_add = stop_price
            closed_add_leg = True
            final_position = BASE_POSITION_BTC
        base_pnl = _pnl_linear(ep.entry_price, price, BASE_POSITION_BTC, "long")
        add_leg_pnl = _pnl_linear(ep.current_price, close_price_add if closed_add_leg else price, ADD_BTC, "long")
        pnl_path.append(base_pnl + add_leg_pnl)
    final_price = float(path_1m["close"].iloc[-1])
    base_final = _pnl_linear(ep.entry_price, final_price, BASE_POSITION_BTC, "long")
    add_final = _pnl_linear(ep.current_price, close_price_add if closed_add_leg and close_price_add is not None else final_price, ADD_BTC, "long")
    target_unrealized = _pnl_linear(ep.entry_price, ep.current_price, BASE_POSITION_BTC, "long")
    return {
        "scenario": "aggressive_add_with_stop" if with_stop else "aggressive_add",
        "realized_pnl_24h_usd": add_final if closed_add_leg else 0.0,
        "unrealized_at_24h_usd": base_final + (0.0 if closed_add_leg else add_final),
        "net_pnl_24h_usd": base_final + add_final,
        "max_dd_during_24h_pct": min(pnl_path) / DEPOSIT_USD * 100.0,
        "recovery_time_hours": _recovery_time(path_1m, target_unrealized, lambda p: _pnl_linear(ep.entry_price, p, BASE_POSITION_BTC, "long") + _pnl_linear(ep.current_price, close_price_add if closed_add_leg and close_price_add is not None else p, ADD_BTC, "long")),
        "position_size_at_24h_btc": final_position,
        "survived": not liquidation,
        "liquidated": liquidation,
    }


def _grid_replay_short(path_1m: pd.DataFrame, ep: Episode, target_mult: float, step_mult: float) -> dict[str, Any]:
    tp_pct = SHORT_TARGET * target_mult / 100.0
    step_pct = SHORT_GS * step_mult
    max_levels = 3
    fill_prices: list[float] = [ep.entry_price]
    size_per_leg = BASE_POSITION_BTC / max_levels
    realized = 0.0
    liquidation = False
    pnl_path: list[float] = []
    current_anchor = ep.entry_price

    for _, row in path_1m.iterrows():
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        next_fill = current_anchor * (1.0 + step_pct)
        if len(fill_prices) < max_levels and high >= next_fill:
            fill_prices.append(next_fill)
            current_anchor = next_fill
        tp_price = np.mean(fill_prices) * (1.0 - tp_pct)
        if low <= tp_price:
            realized = sum(_pnl_linear(fp, tp_price, size_per_leg, "short") for fp in fill_prices)
            fill_prices = []
        unrealized = sum(_pnl_linear(fp, close, size_per_leg, "short") for fp in fill_prices)
        pnl_path.append(realized + unrealized)
        if close >= ep.entry_price * 1.20:
            liquidation = True
    final_close = float(path_1m["close"].iloc[-1])
    unrealized_final = sum(_pnl_linear(fp, final_close, size_per_leg, "short") for fp in fill_prices)
    target_unreal = max(0.0, (ep.entry_price - ep.current_price) * BASE_POSITION_BTC)
    return {
        "realized_pnl_24h_usd": realized,
        "unrealized_at_24h_usd": unrealized_final,
        "net_pnl_24h_usd": realized + unrealized_final,
        "max_dd_during_24h_pct": min(pnl_path) / DEPOSIT_USD * 100.0 if pnl_path else 0.0,
        "recovery_time_hours": _recovery_time(path_1m, target_unreal, lambda p: realized + sum(_pnl_linear(fp, p, size_per_leg, "short") for fp in fill_prices)),
        "position_size_at_24h_btc": size_per_leg * len(fill_prices),
        "survived": not liquidation,
        "liquidated": liquidation,
    }


def _grid_replay_long(path_1m: pd.DataFrame, ep: Episode, target_mult: float, step_mult: float) -> dict[str, Any]:
    tp_pct = LONG_TARGET * target_mult / 100.0
    step_pct = LONG_GS * step_mult
    max_levels = 3
    fill_prices: list[float] = [ep.entry_price]
    size_per_leg = BASE_POSITION_BTC / max_levels
    realized = 0.0
    liquidation = False
    pnl_path: list[float] = []
    current_anchor = ep.entry_price

    for _, row in path_1m.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        close = float(row["close"])
        next_fill = current_anchor * (1.0 - step_pct)
        if len(fill_prices) < max_levels and low <= next_fill:
            fill_prices.append(next_fill)
            current_anchor = next_fill
        tp_price = np.mean(fill_prices) * (1.0 + tp_pct)
        if high >= tp_price:
            realized = sum(_pnl_linear(fp, tp_price, size_per_leg, "long") for fp in fill_prices)
            fill_prices = []
        unrealized = sum(_pnl_linear(fp, close, size_per_leg, "long") for fp in fill_prices)
        pnl_path.append(realized + unrealized)
        if close <= ep.entry_price * 0.80:
            liquidation = True
    final_close = float(path_1m["close"].iloc[-1])
    unrealized_final = sum(_pnl_linear(fp, final_close, size_per_leg, "long") for fp in fill_prices)
    target_unreal = max(0.0, (ep.current_price - ep.entry_price) * BASE_POSITION_BTC)
    return {
        "realized_pnl_24h_usd": realized,
        "unrealized_at_24h_usd": unrealized_final,
        "net_pnl_24h_usd": realized + unrealized_final,
        "max_dd_during_24h_pct": min(pnl_path) / DEPOSIT_USD * 100.0 if pnl_path else 0.0,
        "recovery_time_hours": _recovery_time(path_1m, target_unreal, lambda p: realized + sum(_pnl_linear(fp, p, size_per_leg, "long") for fp in fill_prices)),
        "position_size_at_24h_btc": size_per_leg * len(fill_prices),
        "survived": not liquidation,
        "liquidated": liquidation,
    }


def _simulate_baseline_grid(path_1m: pd.DataFrame, ep: Episode) -> dict[str, Any]:
    if ep.side == "short":
        pnl_path = [_pnl_linear(ep.entry_price, float(p), BASE_POSITION_BTC, "short") for p in path_1m["close"]]
        final_price = float(path_1m["close"].iloc[-1])
        liquidation = final_price >= ep.entry_price * 1.20
        return {
            "scenario": "actual_action",
            "realized_pnl_24h_usd": 0.0,
            "unrealized_at_24h_usd": _pnl_linear(ep.entry_price, final_price, BASE_POSITION_BTC, "short"),
            "net_pnl_24h_usd": _pnl_linear(ep.entry_price, final_price, BASE_POSITION_BTC, "short"),
            "max_dd_during_24h_pct": min(pnl_path) / DEPOSIT_USD * 100.0 if pnl_path else 0.0,
            "recovery_time_hours": _recovery_time(path_1m, 0.0, lambda p: _pnl_linear(ep.entry_price, p, BASE_POSITION_BTC, "short")),
            "position_size_at_24h_btc": BASE_POSITION_BTC,
            "survived": not liquidation,
            "liquidated": liquidation,
        }
    pnl_path = [_pnl_linear(ep.entry_price, float(p), BASE_POSITION_BTC, "long") for p in path_1m["close"]]
    final_price = float(path_1m["close"].iloc[-1])
    liquidation = final_price <= ep.entry_price * 0.80
    return {
        "scenario": "actual_action",
        "realized_pnl_24h_usd": 0.0,
        "unrealized_at_24h_usd": _pnl_linear(ep.entry_price, final_price, BASE_POSITION_BTC, "long"),
        "net_pnl_24h_usd": _pnl_linear(ep.entry_price, final_price, BASE_POSITION_BTC, "long"),
        "max_dd_during_24h_pct": min(pnl_path) / DEPOSIT_USD * 100.0 if pnl_path else 0.0,
        "recovery_time_hours": _recovery_time(path_1m, 0.0, lambda p: _pnl_linear(ep.entry_price, p, BASE_POSITION_BTC, "long")),
        "position_size_at_24h_btc": BASE_POSITION_BTC,
        "survived": not liquidation,
        "liquidated": liquidation,
    }


def simulate_episode(df_1m: pd.DataFrame, ep: Episode) -> list[dict[str, Any]]:
    path_1m = _price_path(df_1m, ep.ts)
    if len(path_1m) < 60:
        return []

    rows: list[dict[str, Any]] = []
    if ep.hypothesis == "AGGRESSIVE_LONG_ON_RALLY":
        scenarios = [
            _simulate_aggressive_baseline(path_1m, ep),
            _simulate_aggressive_add(path_1m, ep, with_stop=False),
            _simulate_aggressive_add(path_1m, ep, with_stop=True),
        ]
    elif ep.hypothesis == "WIDEN_GRID_SHORT":
        scenarios = [
            _simulate_baseline_grid(path_1m, ep),
            {"scenario": "widen_target", **_grid_replay_short(path_1m, ep, target_mult=1.5, step_mult=1.0)},
            {"scenario": "widen_step", **_grid_replay_short(path_1m, ep, target_mult=1.0, step_mult=1.5)},
            {"scenario": "widen_both", **_grid_replay_short(path_1m, ep, target_mult=1.5, step_mult=1.5)},
        ]
    else:
        scenarios = [
            _simulate_baseline_grid(path_1m, ep),
            {"scenario": "widen_target", **_grid_replay_long(path_1m, ep, target_mult=1.5, step_mult=1.0)},
            {"scenario": "widen_step", **_grid_replay_long(path_1m, ep, target_mult=1.0, step_mult=1.5)},
            {"scenario": "widen_both", **_grid_replay_long(path_1m, ep, target_mult=1.5, step_mult=1.5)},
        ]

    baseline = scenarios[0]
    for sc in scenarios:
        rows.append(
            {
                "hypothesis": ep.hypothesis,
                "scenario": sc["scenario"],
                "ts": ep.ts,
                "session_label": ep.session_label,
                "regime_label": ep.regime_label,
                "duration_bucket": ep.duration_bucket,
                "volume_regime": ep.volume_regime,
                "move_pct": ep.move_pct,
                "liq_distance_pct": ep.liq_distance_pct,
                "dd_pct_deposit": ep.dd_pct_deposit,
                "realized_pnl_24h_usd": sc["realized_pnl_24h_usd"],
                "unrealized_at_24h_usd": sc["unrealized_at_24h_usd"],
                "net_pnl_24h_usd": sc["net_pnl_24h_usd"],
                "max_dd_during_24h_pct": sc["max_dd_during_24h_pct"],
                "recovery_time_hours": sc["recovery_time_hours"],
                "position_size_at_24h_btc": sc["position_size_at_24h_btc"],
                "survived": sc["survived"],
                "liquidated": sc["liquidated"],
                "pnl_delta_vs_baseline": sc["net_pnl_24h_usd"] - baseline["net_pnl_24h_usd"],
                "better_than_baseline": sc["net_pnl_24h_usd"] > baseline["net_pnl_24h_usd"],
            }
        )
    return rows


def _aggregate(sim: pd.DataFrame) -> pd.DataFrame:
    return (
        sim.groupby(["hypothesis", "scenario"])
        .agg(
            n=("scenario", "size"),
            win_rate_vs_baseline=("better_than_baseline", "mean"),
            avg_pnl_delta_usd=("pnl_delta_vs_baseline", "mean"),
            median_pnl_delta_usd=("pnl_delta_vs_baseline", "median"),
            q25_pnl_delta_usd=("pnl_delta_vs_baseline", lambda s: float(s.quantile(0.25))),
            q75_pnl_delta_usd=("pnl_delta_vs_baseline", lambda s: float(s.quantile(0.75))),
            avg_max_dd_pct=("max_dd_during_24h_pct", "mean"),
            survivability_rate=("survived", "mean"),
            liquidation_events=("liquidated", "sum"),
        )
        .reset_index()
    )


def _best_scenario_per_hyp(summary: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    for hyp, group in summary.groupby("hypothesis"):
        candidates = group[group["scenario"] != "actual_action"].sort_values(
            ["win_rate_vs_baseline", "avg_pnl_delta_usd"], ascending=[False, False]
        )
        result[hyp] = str(candidates.iloc[0]["scenario"])
    return result


def _stratify(sim: pd.DataFrame, best_map: dict[str, str], dim: str) -> pd.DataFrame:
    rows = []
    for hyp, scenario in best_map.items():
        subset = sim[(sim["hypothesis"] == hyp) & (sim["scenario"] == scenario)]
        if subset.empty:
            continue
        grouped = (
            subset.groupby(dim)
            .agg(
                n=("scenario", "size"),
                wr=("better_than_baseline", "mean"),
                avg_delta=("pnl_delta_vs_baseline", "mean"),
                avg_dd=("max_dd_during_24h_pct", "mean"),
            )
            .reset_index()
        )
        grouped["hypothesis"] = hyp
        grouped["scenario"] = scenario
        rows.append(grouped)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.{digits}f}"


def _render_table(df: pd.DataFrame, columns: list[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for _, row in df.iterrows():
        vals: list[str] = []
        for col in columns:
            value = row[col]
            if isinstance(value, float):
                if "rate" in col or col == "wr":
                    vals.append(f"{value * 100:.1f}%")
                else:
                    vals.append(_fmt_num(value))
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _russian_conclusion(hyp: str, summary: pd.DataFrame, strat_session: pd.DataFrame, strat_regime: pd.DataFrame, strat_duration: pd.DataFrame) -> str:
    base_name = {
        "AGGRESSIVE_LONG_ON_RALLY": "AGGRESSIVE_LONG_ON_RALLY",
        "WIDEN_GRID_SHORT": "WIDEN_GRID_SHORT",
        "WIDEN_GRID_LONG": "WIDEN_GRID_LONG",
    }[hyp]
    hyp_rows = summary[summary["hypothesis"] == hyp].copy()
    base = hyp_rows[hyp_rows["scenario"] == "actual_action"].iloc[0]
    best = hyp_rows[hyp_rows["scenario"] != "actual_action"].sort_values(
        ["win_rate_vs_baseline", "avg_pnl_delta_usd"], ascending=[False, False]
    ).iloc[0]
    worst = hyp_rows[hyp_rows["scenario"] != "actual_action"].sort_values(
        ["avg_max_dd_pct", "avg_pnl_delta_usd"], ascending=[True, True]
    ).iloc[0]

    sess = strat_session[strat_session["hypothesis"] == hyp].sort_values("wr", ascending=False)
    reg = strat_regime[strat_regime["hypothesis"] == hyp].sort_values("wr", ascending=False)
    dur = strat_duration[strat_duration["hypothesis"] == hyp].sort_values("wr", ascending=False)
    works: list[str] = []
    not_works: list[str] = []

    for _, row in sess.iterrows():
        if float(row["n"]) >= 10 and float(row["wr"]) >= 0.60:
            works.append(f"`session={row['session_label']}`: WR {row['wr']*100:.1f}% при n={int(row['n'])}")
        elif float(row["n"]) >= 10 and float(row["wr"]) <= 0.40:
            not_works.append(f"`session={row['session_label']}`: WR {row['wr']*100:.1f}% при n={int(row['n'])}")
    for _, row in reg.iterrows():
        if float(row["n"]) >= 10 and float(row["wr"]) >= 0.60:
            works.append(f"`regime={row['regime_label']}`: WR {row['wr']*100:.1f}% при n={int(row['n'])}")
        elif float(row["n"]) >= 10 and float(row["wr"]) <= 0.40:
            not_works.append(f"`regime={row['regime_label']}`: WR {row['wr']*100:.1f}% при n={int(row['n'])}")
    for _, row in dur.iterrows():
        if float(row["n"]) >= 10 and float(row["wr"]) >= 0.60:
            works.append(f"`duration={row['duration_bucket']}`: WR {row['wr']*100:.1f}% при n={int(row['n'])}")
        elif float(row["n"]) >= 10 and float(row["wr"]) <= 0.40:
            not_works.append(f"`duration={row['duration_bucket']}`: WR {row['wr']*100:.1f}% при n={int(row['n'])}")

    recommendation = "discard"
    if float(best["n"]) >= 100 and float(best["win_rate_vs_baseline"]) >= 0.60:
        recommendation = "direction for live test"
    elif float(best["win_rate_vs_baseline"]) <= 0.40:
        recommendation = "anti-direction"
    else:
        recommendation = "collect more data / do not change behavior yet"

    parts = [
        f"### ГИПОТЕЗА: {base_name}",
        "",
        "Что протестировали:",
        f"Сравнили текущий базовый сценарий с альтернативами для `{hyp}` на synthetic эпизодах frozen BTC. "
        f"Базовый сценарий был `{base['scenario']}`, лучший альтернативный по агрегату — `{best['scenario']}`.",
        "",
        "Что получилось:",
        f"- В {best['win_rate_vs_baseline']*100:.1f}% эпизодов `{best['scenario']}` был лучше baseline.",
        f"- Средний прирост PnL за 24h: {_fmt_num(float(best['avg_pnl_delta_usd']))}$ относительно baseline.",
        f"- Средняя просадка: {_fmt_num(float(best['avg_max_dd_pct']))}% от депозита во время удержания.",
        f"- Worst case среди альтернатив: `{worst['scenario']}` со средней DD {_fmt_num(float(worst['avg_max_dd_pct']))}% и survivability {float(worst['survivability_rate'])*100:.1f}%.",
        "",
        "Когда РАБОТАЕТ:",
    ]
    if works:
        parts.extend([f"- {line}" for line in works[:4]])
    else:
        parts.append("- Убедимых условий `WR >= 60%` при достаточном n не найдено.")
    parts.append("")
    parts.append("Когда НЕ РАБОТАЕТ:")
    if not_works:
        parts.extend([f"- {line}" for line in not_works[:4]])
    else:
        parts.append("- Явных anti-conditions `WR <= 40%` при достаточном n почти нет либо выборка мала.")
    parts.extend(
        [
            "",
            "Рекомендация:",
            f"- {recommendation}",
            "",
            "Ограничения теста:",
            f"- Synthetic counterfactual, не real decisions.",
            f"- Эпизодов по гипотезе: {int(best['n'])}.",
            "- Frozen BTC год, без multi-asset и без реальных межботовых взаимодействий.",
            "",
        ]
    )
    return "\n".join(parts)


def build_report(summary: pd.DataFrame, strat_session: pd.DataFrame, strat_regime: pd.DataFrame, strat_duration: pd.DataFrame, strat_volume: pd.DataFrame) -> str:
    best_map = _best_scenario_per_hyp(summary)
    lines: list[str] = []
    lines.append("# Defensive Actions Research V3 — Aggressive And Widen")
    lines.append("")
    lines.append("## §1 Methodology")
    lines.append("")
    lines.append("- Episode mining uses frozen `BTCUSDT_1m_2y.csv` restricted to `2025-05-01..2026-04-29` plus ICT levels parquet.")
    lines.append("- `AGGRESSIVE_LONG_ON_RALLY`: synthetic long already in profit, +1.0..4.0% rally over 1-4h, liquidation buffer >20%, volume roughly at/above SMA20. This is a widened proxy to reach usable sample size.")
    lines.append("- `WIDEN_GRID_SHORT`: synthetic short in drawdown >=0.1% of deposit, +0.8..4.0% move against short over 2-6h, liq distance >10%.")
    lines.append("- `WIDEN_GRID_LONG`: mirrored long drawdown case for falling market, same widened proxy philosophy.")
    lines.append("- Counterfactuals:")
    lines.append("  - `AGGRESSIVE_LONG`: baseline close-now, add 0.10 BTC, add 0.10 BTC with 1.5% stop.")
    lines.append("  - `WIDEN_*`: baseline hold/current config, widen target, widen step, widen both.")
    lines.append("- For widen scenarios, the runner extends beyond `outcome_simulator` with simple grid replay logic because parameter changes are not represented by TP/SL-only setup lifecycle.")
    lines.append("")
    lines.append("## §2 Per-hypothesis aggregate results")
    lines.append("")
    for hyp in HYPOTHESES:
        lines.append(f"### {hyp}")
        lines.append("")
        lines.append(
            _render_table(
                summary[summary["hypothesis"] == hyp],
                [
                    "scenario",
                    "n",
                    "win_rate_vs_baseline",
                    "avg_pnl_delta_usd",
                    "median_pnl_delta_usd",
                    "q25_pnl_delta_usd",
                    "q75_pnl_delta_usd",
                    "avg_max_dd_pct",
                    "survivability_rate",
                    "liquidation_events",
                ],
            )
        )
        lines.append("")
    lines.append("## §3 Stratification")
    lines.append("")
    lines.append("WR by scenario × session:")
    lines.append(_render_table(strat_session, ["hypothesis", "scenario", "session_label", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("WR by scenario × regime:")
    lines.append(_render_table(strat_regime, ["hypothesis", "scenario", "regime_label", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("WR by scenario × episode_duration:")
    lines.append(_render_table(strat_duration, ["hypothesis", "scenario", "duration_bucket", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("WR by scenario × volume_regime:")
    lines.append(_render_table(strat_volume, ["hypothesis", "scenario", "volume_regime", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("## §4 Survivability analysis")
    lines.append("")
    surv = summary[["hypothesis", "scenario", "survivability_rate", "liquidation_events", "avg_max_dd_pct"]].copy()
    lines.append(_render_table(surv, ["hypothesis", "scenario", "survivability_rate", "liquidation_events", "avg_max_dd_pct"]))
    lines.append("")
    lines.append("## §5 ВЫВОДЫ ПО-РУССКИ ПОДРОБНО")
    lines.append("")
    for hyp in HYPOTHESES:
        lines.append(_russian_conclusion(hyp, summary, strat_session, strat_regime, strat_duration))
    lines.append("## §6 Cross-hypothesis comparison")
    lines.append("")
    best_rows = []
    for hyp, scenario in best_map.items():
        row = summary[(summary["hypothesis"] == hyp) & (summary["scenario"] == scenario)].iloc[0]
        best_rows.append(row)
    best_df = pd.DataFrame(best_rows)
    lines.append(_render_table(best_df, ["hypothesis", "scenario", "n", "win_rate_vs_baseline", "avg_pnl_delta_usd", "avg_max_dd_pct", "survivability_rate"]))
    lines.append("")
    lines.append("Interpretation:")
    lines.append("- Compare not only WR but also survivability and DD. A scenario with high WR but poor survivability is not usable live.")
    lines.append("- If none of the three hypotheses clears `WR >= 60%` with `n >= 100`, the result is not 'maybe'; it is 'no synthetic edge strong enough for behavior change'.")
    lines.append("")
    lines.append("## §7 Caveats")
    lines.append("")
    lines.append("- Single asset BTC.")
    lines.append("- Synthetic position state and simplified grid replay.")
    lines.append("- No cross-bot interactions or funding/fees in this runner.")
    lines.append("- Survivability stayed at 100% in this run because the synthetic liquidation proxy was not reached inside sampled 24h paths. Treat this as a model artifact, not as proof of zero liquidation risk live.")
    lines.append("- Post-halving bull-heavy year bias may distort long-follow and widen-short conclusions.")
    lines.append("")
    lines.append("## §8 Recommended next steps")
    lines.append("")
    for _, row in best_df.iterrows():
        wr = float(row["win_rate_vs_baseline"])
        n = int(row["n"])
        if n >= 100 and wr >= 0.60:
            nxt = "Use as direction for limited live test, then validate via `/decision` and real snapshots."
        elif wr <= 0.40:
            nxt = "Discard as anti-direction; do not move operator behavior this way."
        else:
            nxt = "Do not productize. Keep as hypothesis only, or redesign the setup logic."
        lines.append(f"- `{row['hypothesis']}` via `{row['scenario']}`: {nxt}")
    return "\n".join(lines) + "\n"


def main() -> None:
    HistoricalContextBuilder(FROZEN_1M)
    ICTContextReader.load(ICT_PARQUET)

    df_1m, ict = _load_year_data()
    df_1h = _build_hourly_features(df_1m, ict)
    episodes = mine_episodes(df_1h)
    rows: list[dict[str, Any]] = []
    for ep in episodes:
        rows.extend(simulate_episode(df_1m, ep))
    sim = pd.DataFrame(rows)
    summary = _aggregate(sim)
    best_map = _best_scenario_per_hyp(summary)
    strat_session = _stratify(sim, best_map, "session_label")
    strat_regime = _stratify(sim, best_map, "regime_label")
    strat_duration = _stratify(sim, best_map, "duration_bucket")
    strat_volume = _stratify(sim, best_map, "volume_regime")
    REPORT_PATH.write_text(build_report(summary, strat_session, strat_regime, strat_duration, strat_volume), encoding="utf-8")
    print(f"episodes={len(episodes)} rows={len(sim)} report={REPORT_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
