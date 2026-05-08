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
REPORT_PATH = ROOT / "reports" / "defensive_actions_research_2026-05-02.md"

YEAR_START = pd.Timestamp("2025-05-01T00:00:00Z")
YEAR_END = pd.Timestamp("2026-04-29T23:59:00Z")

BASE_SHORT_BTC = 0.20
ADD_ON_BTC = 0.05
DEPOSIT_USD = 15_000.0
LIQ_MULTIPLIER = 1.20  # synthetic short liquidation at +20% from entry
COOLDOWN_HOURS = 6

ACTION_TYPES = (
    "PARTIAL_CLOSE_ON_RETRACE",
    "HOLD_THROUGH_NOISE",
    "PAUSE_BEFORE_RESISTANCE",
    "RESUME_ON_EXHAUSTION",
    "COUNTER_HEDGE_ON_DD",
    "EMERGENCY_CLOSE",
)


@dataclass
class Episode:
    action_type: str
    ts: pd.Timestamp
    entry_price: float
    current_price: float
    regime_label: str
    session_label: str
    resistance_bucket: str
    dd_hours: float
    dd_pct: float
    liq_distance_pct: float
    retrace_from_local_high_pct: float | None
    ict_distance_pct: float | None
    notes: str


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
                "time_in_session_min",
                "dist_to_pdh_pct",
                "dist_to_pwh_pct",
                "dist_to_nearest_unmitigated_high_pct",
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
    df["atr_pct_mean20"] = df["atr_pct"].rolling(20, min_periods=5).mean()
    df["volume_ratio"] = df["volume"] / df["volume"].rolling(20, min_periods=5).mean()
    df["body_pct"] = (df["close"] - df["open"]).abs() / df["open"] * 100.0
    df["range_pct"] = (df["high"] - df["low"]) / df["open"] * 100.0
    df["upper_wick_pct"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["open"] * 100.0
    df["lower_wick_pct"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["open"] * 100.0
    df["is_bear"] = df["close"] < df["open"]
    df["high_gt_prev"] = (df["high"] > df["high"].shift(1)).astype(int)
    df["low_lt_prev"] = (df["low"] < df["low"].shift(1)).astype(int)
    df["close_ret_1h_pct"] = df["close"].pct_change(1) * 100.0
    df["close_ret_4h_pct"] = df["close"].pct_change(4) * 100.0

    ma20 = df["close"].rolling(20, min_periods=5).mean()
    slope = ma20.diff(5) / df["close"] * 100.0
    df["regime_label"] = np.where(
        slope > 0.3,
        "trend_up",
        np.where(slope < -0.3, "trend_down", "consolidation"),
    )
    return df


def _hourly_short_state(df: pd.DataFrame, i: int) -> dict[str, float]:
    current = float(df["close"].iloc[i])
    entry = float(df["close"].iloc[i - 6])
    dd_pct = max(0.0, (current / entry - 1.0) * 100.0)
    liq_price = entry * LIQ_MULTIPLIER
    liq_distance = max(0.0, (liq_price - current) / current * 100.0)

    dd_hours = 0
    for j in range(i, max(0, i - 12), -1):
        if float(df["close"].iloc[j]) > entry:
            dd_hours += 1
        else:
            break

    unrealized_usd = (entry - current) * BASE_SHORT_BTC
    return {
        "entry_price": entry,
        "dd_pct": dd_pct,
        "liq_distance_pct": liq_distance,
        "dd_hours": float(dd_hours),
        "unrealized_usd": unrealized_usd,
    }


def _resistance_distance_pct(row: pd.Series) -> float | None:
    vals: list[float] = []
    for key in ("dist_to_pdh_pct", "dist_to_pwh_pct", "dist_to_nearest_unmitigated_high_pct"):
        value = row.get(key)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        vals.append(float(value))
    if not vals:
        return None
    return min(vals, key=lambda x: abs(x))


def _bucket_distance(distance_pct: float | None) -> str:
    if distance_pct is None or math.isnan(distance_pct):
        return "unknown"
    a = abs(distance_pct)
    if a <= 0.3:
        return "close_to_resistance"
    if a <= 1.0:
        return "mid"
    return "far"


def _accept_episode(
    episodes: list[Episode],
    action_type: str,
    ts: pd.Timestamp,
) -> bool:
    for e in reversed(episodes):
        if e.action_type != action_type:
            continue
        if (ts - e.ts).total_seconds() < COOLDOWN_HOURS * 3600:
            return False
        return True
    return True


def mine_episodes(df_1h: pd.DataFrame) -> list[Episode]:
    episodes: list[Episode] = []
    for i in range(48, len(df_1h) - 24):
        row = df_1h.iloc[i]
        ts = pd.Timestamp(df_1h.index[i])
        state = _hourly_short_state(df_1h, i)
        entry = state["entry_price"]
        current = float(row["close"])
        dd_pct = state["dd_pct"]
        liq_pct = state["liq_distance_pct"]
        dd_hours = state["dd_hours"]
        unrealized = state["unrealized_usd"]
        local_high = float(df_1h["high"].iloc[i - 2 : i + 1].max())
        retrace_pct = (local_high - current) / local_high * 100.0 if local_high > 0 else 0.0
        resistance_dist = _resistance_distance_pct(row)
        bucket = _bucket_distance(resistance_dist)
        accel = bool(
            row["body_pct"] > df_1h["body_pct"].iloc[i - 1] > df_1h["body_pct"].iloc[i - 2]
            and row["range_pct"] > df_1h["range_pct"].iloc[i - 1] > df_1h["range_pct"].iloc[i - 2]
        )
        atr_consistent = 0.8 <= float(row["atr_pct"] / max(row["atr_pct_mean20"], 1e-9)) <= 1.2
        no_volume_spike = float(row["volume_ratio"]) < 1.3
        upper_wick_exhaustion = float(row["upper_wick_pct"]) > max(0.35, float(row["body_pct"]) * 1.2)
        sell_volume_spike = bool(row["is_bear"] and float(row["volume_ratio"]) > 1.5)
        atr_contracting = float(row["atr_pct"]) < float(df_1h["atr_pct"].iloc[i - 2 : i + 1].mean()) * 0.9
        hh3 = bool(
            df_1h["high"].iloc[i] > df_1h["high"].iloc[i - 1] > df_1h["high"].iloc[i - 2]
        )

        candidates: list[tuple[str, str]] = []

        if dd_hours >= 4 and 0.3 <= retrace_pct <= 1.0 and 15.0 <= liq_pct <= 25.0:
            candidates.append(("PARTIAL_CLOSE_ON_RETRACE", f"retrace={retrace_pct:.2f}% liq={liq_pct:.1f}%"))

        if 2.0 <= dd_hours <= 6.0 and dd_pct <= 0.5 and atr_consistent and no_volume_spike:
            candidates.append(("HOLD_THROUGH_NOISE", f"dd={dd_pct:.2f}% atr_consistent vol={row['volume_ratio']:.2f}"))

        if resistance_dist is not None and -0.3 <= resistance_dist <= 0.0 and accel and float(row["volume_ratio"]) > 1.2:
            candidates.append(("PAUSE_BEFORE_RESISTANCE", f"dist={resistance_dist:.2f}% accel vol={row['volume_ratio']:.2f}"))

        prev1 = _resistance_distance_pct(df_1h.iloc[i - 1])
        if (
            resistance_dist is not None
            and prev1 is not None
            and -0.3 <= resistance_dist <= 0.1
            and -0.3 <= prev1 <= 0.1
            and (upper_wick_exhaustion or sell_volume_spike or atr_contracting)
        ):
            candidates.append(("RESUME_ON_EXHAUSTION", f"dist={resistance_dist:.2f}% upper_wick={upper_wick_exhaustion}"))

        if dd_hours >= 4.0 and unrealized <= -(DEPOSIT_USD * 0.005) and hh3:
            candidates.append(("COUNTER_HEDGE_ON_DD", f"upl={unrealized:.0f} hh3 liq={liq_pct:.1f}%"))

        if liq_pct < 15.0 and dd_hours >= 3.0:
            candidates.append(("EMERGENCY_CLOSE", f"liq={liq_pct:.1f}% dd={dd_pct:.2f}%"))

        for action_type, note in candidates:
            if not _accept_episode(episodes, action_type, ts):
                continue
            episodes.append(
                Episode(
                    action_type=action_type,
                    ts=ts,
                    entry_price=entry,
                    current_price=current,
                    regime_label=str(row["regime_label"]),
                    session_label=str(row.get("session_active") or "unknown"),
                    resistance_bucket=bucket,
                    dd_hours=dd_hours,
                    dd_pct=dd_pct,
                    liq_distance_pct=liq_pct,
                    retrace_from_local_high_pct=retrace_pct if action_type == "PARTIAL_CLOSE_ON_RETRACE" else None,
                    ict_distance_pct=resistance_dist,
                    notes=note,
                )
            )
    return episodes


def _short_pnl(entry: float, price: float, size_btc: float) -> float:
    return (entry - price) * size_btc


def _long_pnl(entry: float, price: float, size_btc: float) -> float:
    return (price - entry) * size_btc


def _action_and_baseline_pnl(
    action_type: str,
    entry_price: float,
    current_price: float,
    future_price: float,
) -> tuple[float, float]:
    if action_type == "PARTIAL_CLOSE_ON_RETRACE":
        action = _short_pnl(entry_price, current_price, BASE_SHORT_BTC * 0.25) + _short_pnl(
            entry_price, future_price, BASE_SHORT_BTC * 0.75
        )
        baseline = _short_pnl(entry_price, future_price, BASE_SHORT_BTC)
        return action, baseline
    if action_type == "HOLD_THROUGH_NOISE":
        action = _short_pnl(entry_price, future_price, BASE_SHORT_BTC)
        baseline = _short_pnl(entry_price, current_price, BASE_SHORT_BTC * 0.25) + _short_pnl(
            entry_price, future_price, BASE_SHORT_BTC * 0.75
        )
        return action, baseline
    if action_type == "PAUSE_BEFORE_RESISTANCE":
        action = _short_pnl(entry_price, future_price, BASE_SHORT_BTC)
        baseline = action + _short_pnl(current_price, future_price, ADD_ON_BTC)
        return action, baseline
    if action_type == "RESUME_ON_EXHAUSTION":
        baseline = _short_pnl(entry_price, future_price, BASE_SHORT_BTC)
        action = baseline + _short_pnl(current_price, future_price, ADD_ON_BTC)
        return action, baseline
    if action_type == "COUNTER_HEDGE_ON_DD":
        baseline = _short_pnl(entry_price, future_price, BASE_SHORT_BTC)
        action = baseline + _long_pnl(current_price, future_price, ADD_ON_BTC)
        return action, baseline
    if action_type == "EMERGENCY_CLOSE":
        action = _short_pnl(entry_price, current_price, BASE_SHORT_BTC)
        baseline = _short_pnl(entry_price, future_price, BASE_SHORT_BTC)
        return action, baseline
    raise ValueError(action_type)


def _action_pnl_only(action_type: str, entry_price: float, current_price: float, future_price: float) -> float:
    action, _ = _action_and_baseline_pnl(action_type, entry_price, current_price, future_price)
    return action


def _recovery_time_min(action_type: str, entry_price: float, current_price: float, future_window: pd.DataFrame) -> float | None:
    for offset, (_, row) in enumerate(future_window.iterrows(), start=1):
        price = float(row["close"])
        pnl = _action_pnl_only(action_type, entry_price, current_price, price)
        if pnl >= 0.0:
            return float(offset)
    return None


def simulate_episodes(df_1m: pd.DataFrame, episodes: list[Episode]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ep in episodes:
        future = df_1m.loc[ep.ts : ep.ts + pd.Timedelta(hours=24)]
        if len(future) < 60:
            continue

        result: dict[str, Any] = {
            "action_type": ep.action_type,
            "ts": ep.ts,
            "regime_label": ep.regime_label,
            "session_label": ep.session_label,
            "resistance_bucket": ep.resistance_bucket,
            "ict_distance_pct": ep.ict_distance_pct,
            "dd_hours": ep.dd_hours,
            "dd_pct": ep.dd_pct,
            "liq_distance_pct": ep.liq_distance_pct,
            "notes": ep.notes,
        }

        for hours in (1, 4, 24):
            target_ts = ep.ts + pd.Timedelta(hours=hours)
            horizon = future.loc[:target_ts]
            if horizon.empty:
                result[f"delta_pnl_{hours}h"] = np.nan
                result[f"action_pnl_{hours}h"] = np.nan
                result[f"baseline_pnl_{hours}h"] = np.nan
                result[f"action_max_dd_{hours}h"] = np.nan
                result[f"baseline_max_dd_{hours}h"] = np.nan
                continue
            future_price = float(horizon["close"].iloc[-1])
            action_pnl, baseline_pnl = _action_and_baseline_pnl(
                ep.action_type, ep.entry_price, ep.current_price, future_price
            )
            action_path = [
                _action_pnl_only(ep.action_type, ep.entry_price, ep.current_price, float(p))
                for p in horizon["close"]
            ]
            baseline_path = [
                _action_and_baseline_pnl(ep.action_type, ep.entry_price, ep.current_price, float(p))[1]
                for p in horizon["close"]
            ]
            result[f"delta_pnl_{hours}h"] = action_pnl - baseline_pnl
            result[f"action_pnl_{hours}h"] = action_pnl
            result[f"baseline_pnl_{hours}h"] = baseline_pnl
            result[f"action_max_dd_{hours}h"] = float(min(action_path))
            result[f"baseline_max_dd_{hours}h"] = float(min(baseline_path))

        result["recovery_time_min"] = _recovery_time_min(ep.action_type, ep.entry_price, ep.current_price, future)
        result["win_24h"] = bool(result.get("delta_pnl_24h", np.nan) > 0.0)
        rows.append(result)
    return pd.DataFrame(rows)


def _fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.{digits}f}"


def _aggregate(sim: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        sim.groupby("action_type")
        .agg(
            n=("action_type", "size"),
            win_rate_24h=("win_24h", "mean"),
            avg_delta_1h=("delta_pnl_1h", "mean"),
            avg_delta_4h=("delta_pnl_4h", "mean"),
            avg_delta_24h=("delta_pnl_24h", "mean"),
            avg_recovery_h=(
                "recovery_time_min",
                lambda s: float(np.nanmean(s.dropna())) / 60.0 if len(s.dropna()) else np.nan,
            ),
        )
        .reset_index()
    )
    grouped = grouped.set_index("action_type")
    grouped = grouped.reindex(ACTION_TYPES)
    grouped.index.name = "action_type"
    grouped = grouped.reset_index()
    grouped["n"] = grouped["n"].fillna(0).astype(int)
    return grouped.sort_values("win_rate_24h", ascending=False)


def _recommendation_rows(sim: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for action_type in ACTION_TYPES:
        subset = sim[sim["action_type"] == action_type].copy()
        n = len(subset)
        wr = float(subset["win_24h"].mean()) if n else float("nan")
        if n == 0:
            rows.append(
                {
                    "action_type": action_type,
                    "trigger": "n/a — episodes not found",
                    "assessment": "inconclusive",
                    "n": 0,
                    "wr": float("nan"),
                    "recovery_h": float("nan"),
                }
            )
            continue
        if action_type == "PARTIAL_CLOSE_ON_RETRACE":
            trigger = "position_dd_hours >= 4 AND retrace_from_local_high_pct in [0.3, 1.0] AND liq_distance_pct in [15, 25]"
        elif action_type == "HOLD_THROUGH_NOISE":
            trigger = "position_dd_hours in [2, 6] AND dd_pct <= 0.5 AND atr_regime stable AND volume_ratio < 1.3"
        elif action_type == "PAUSE_BEFORE_RESISTANCE":
            trigger = "dist_to_resistance_pct in [-0.3, 0.0] AND last_3_1h_bars accelerating AND volume_ratio > 1.2"
        elif action_type == "RESUME_ON_EXHAUSTION":
            trigger = "dist_to_resistance_pct in [-0.3, 0.1] for >=1h AND (upper_wick OR bearish_volume_spike OR atr_contraction)"
        elif action_type == "COUNTER_HEDGE_ON_DD":
            trigger = "position_dd_hours >= 4 AND unrealized_pnl <= -0.5% deposit AND 3 higher-high 1h candles"
        else:
            trigger = "liq_distance_pct < 15 AND position_dd_hours >= 3"
        if n < 30:
            assessment = "needs more data"
        elif wr >= 0.55:
            assessment = "production-ready candidate"
        else:
            assessment = "do not productionize"
        rows.append(
            {
                "action_type": action_type,
                "trigger": trigger,
                "assessment": assessment,
                "n": n,
                "wr": wr,
                "recovery_h": float(np.nanmean(subset["recovery_time_min"].dropna())) / 60.0
                if len(subset["recovery_time_min"].dropna())
                else float("nan"),
            }
        )
    return rows


def _top2_breakdowns(sim: pd.DataFrame, summary: pd.DataFrame) -> dict[str, dict[str, pd.DataFrame]]:
    eligible = summary[summary["n"] >= 30]
    source = eligible if len(eligible) >= 2 else summary
    top2 = list(source["action_type"].head(2))
    result: dict[str, dict[str, pd.DataFrame]] = {}
    for action_type in top2:
        subset = sim[sim["action_type"] == action_type].copy()
        result[action_type] = {
            "session": subset.groupby("session_label").agg(n=("action_type", "size"), wr=("win_24h", "mean"), avg_delta_24h=("delta_pnl_24h", "mean")).reset_index().sort_values("wr", ascending=False),
            "regime": subset.groupby("regime_label").agg(n=("action_type", "size"), wr=("win_24h", "mean"), avg_delta_24h=("delta_pnl_24h", "mean")).reset_index().sort_values("wr", ascending=False),
            "distance": subset.groupby("resistance_bucket").agg(n=("action_type", "size"), wr=("win_24h", "mean"), avg_delta_24h=("delta_pnl_24h", "mean")).reset_index().sort_values("wr", ascending=False),
        }
    return result


def _render_table(df: pd.DataFrame, columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "|---" * len(columns) + "|"
    lines = [header, sep]
    for _, row in df.iterrows():
        vals: list[str] = []
        for col in columns:
            value = row[col]
            if isinstance(value, float):
                if "wr" in col:
                    vals.append(f"{value * 100:.1f}%")
                else:
                    vals.append(_fmt_num(value))
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def build_report(summary: pd.DataFrame, top2: dict[str, dict[str, pd.DataFrame]], recs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# Defensive Actions Research — 2026-05-02")
    lines.append("")
    lines.append("## §1 Methodology")
    lines.append("")
    lines.append("- Data: frozen `BTCUSDT_1m_2y.csv`, sliced to `2025-05-01..2026-04-29`, plus `data/ict_levels/BTCUSDT_ict_levels_1m.parquet`.")
    lines.append("- Mining cadence: hourly candidate scan with 6h cooldown per action type to reduce cluster-duplicates.")
    lines.append("- Position model: synthetic counter-trend SHORT basket, base size `0.20 BTC`, add-on / hedge leg `0.05 BTC`, synthetic liquidation at `entry * 1.20`.")
    lines.append("- Outcome engine: replay-style future look-ahead on frozen 1m bars from the existing `services/setup_backtest` stack. Action accounting is custom because the built-in simulator is TP/SL-oriented, while this study compares action-vs-baseline state changes.")
    lines.append("- Win definition: `delta_pnl_24h > 0` versus baseline. Recovery time = hours until action PnL returns to non-negative within 24h.")
    lines.append("- Important proxy: `HOLD_THROUGH_NOISE` is compared against premature `25%` partial close, because literal `do nothing` would be identical to hold and not measurable.")
    lines.append("")
    lines.append("## §2 Per-type results")
    lines.append("")
    lines.append(
        _render_table(
            summary.rename(
                columns={
                    "action_type": "type",
                    "win_rate_24h": "wr_24h",
                    "avg_delta_1h": "avg_delta_1h_usd",
                    "avg_delta_4h": "avg_delta_4h_usd",
                    "avg_delta_24h": "avg_delta_24h_usd",
                    "avg_recovery_h": "avg_recovery_h",
                }
            ),
            ["type", "n", "wr_24h", "avg_delta_1h_usd", "avg_delta_4h_usd", "avg_delta_24h_usd", "avg_recovery_h"],
        )
    )
    lines.append("")
    lines.append("## §3 Top performers stratification")
    lines.append("")
    for action_type, blocks in top2.items():
        lines.append(f"### {action_type}")
        lines.append("")
        lines.append("By session:")
        lines.append(_render_table(blocks["session"], ["session_label", "n", "wr", "avg_delta_24h"]))
        lines.append("")
        lines.append("By regime:")
        lines.append(_render_table(blocks["regime"], ["regime_label", "n", "wr", "avg_delta_24h"]))
        lines.append("")
        lines.append("By ICT distance bucket:")
        lines.append(_render_table(blocks["distance"], ["resistance_bucket", "n", "wr", "avg_delta_24h"]))
        lines.append("")
    lines.append("## §4 Recommended trigger conditions per type")
    lines.append("")
    for row in recs:
        wr = "n/a" if math.isnan(row["wr"]) else f"{row['wr'] * 100:.1f}%"
        recovery = "n/a" if math.isnan(row["recovery_h"]) else f"{row['recovery_h']:.1f}h"
        lines.append(f"### {row['action_type']}")
        lines.append("")
        lines.append(f"- Trigger: `{row['trigger']}`")
        lines.append(f"- Expected outcome: WR {wr}, avg recovery {recovery}, n={row['n']}")
        lines.append(f"- Assessment: {row['assessment']}")
        lines.append("")
    lines.append("## §5 Confidence assessment per type")
    lines.append("")
    lines.append("| type | confidence | rationale |")
    lines.append("|---|---|---|")
    for row in recs:
        if row["n"] < 30:
            rationale = f"n={row['n']} < 30"
        elif math.isnan(row["wr"]):
            rationale = "no measurable episodes"
        elif row["wr"] >= 0.60:
            rationale = f"WR {row['wr'] * 100:.1f}% with adequate sample"
        elif row["wr"] >= 0.55:
            rationale = f"borderline but usable candidate, WR {row['wr'] * 100:.1f}%"
        else:
            rationale = f"WR {row['wr'] * 100:.1f}% below production threshold"
        lines.append(f"| {row['action_type']} | {row['assessment']} | {rationale} |")
    lines.append("")
    lines.append("## §6 Caveats")
    lines.append("")
    lines.append("- Synthetic position state: entry, DD duration, and liq distance are reconstructed proxies, not real bot snapshots.")
    lines.append("- No cross-bot interactions: pausing/resuming/hedging is modeled as a single basket state change, not a full GinArea multi-bot portfolio.")
    lines.append("- Single asset / single historical regime sample: BTC only, one frozen year.")
    lines.append("- `PAUSE` and `RESUME` are evaluated as add-on leg suppression / activation, which is the cleanest measurable proxy but not a full order-routing replay.")
    lines.append("- `HOLD_THROUGH_NOISE` required a non-literal baseline proxy because hold versus literal do-nothing is observationally identical.")
    return "\n".join(lines) + "\n"


def main() -> None:
    # Touch existing infrastructure explicitly so report generation fails fast if dependencies drift.
    HistoricalContextBuilder(FROZEN_1M)
    ICTContextReader.load(ICT_PARQUET)

    df_1m, ict = _load_year_data()
    df_1h = _build_hourly_features(df_1m, ict)
    episodes = mine_episodes(df_1h)
    sim = simulate_episodes(df_1m, episodes)
    summary = _aggregate(sim)
    recs = _recommendation_rows(sim)
    top2 = _top2_breakdowns(sim, summary)
    REPORT_PATH.write_text(build_report(summary, top2, recs), encoding="utf-8")
    print(f"episodes={len(episodes)} simulated={len(sim)} report={REPORT_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
