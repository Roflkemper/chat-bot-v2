from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import math

import numpy as np
import pandas as pd

from services.defensive_actions_research.v3_aggressive_widen import (
    BASE_POSITION_BTC,
    COOLDOWN_HOURS,
    DEPOSIT_USD,
    FROZEN_1M,
    ICT_PARQUET,
    LONG_GS,
    LONG_TARGET,
    SHORT_GS,
    SHORT_TARGET,
    YEAR_END,
    YEAR_START,
    _build_hourly_features,
    _duration_bucket,
    _load_year_data,
)
from services.setup_backtest.historical_context import HistoricalContextBuilder
from services.setup_detector.ict_context import ICTContextReader

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "reports" / "defensive_v3_corrected_2026-05-02.md"

MAX_LEVELS = 3
SIZE_PER_LEG_BTC = BASE_POSITION_BTC / MAX_LEVELS
LONG_LIQ_MULT = 0.80
SHORT_LIQ_MULT = 1.20

ORIGINAL_METRICS = {
    "WIDEN_GRID_LONG": {"best_scenario": "widen_target", "n": 694, "wr": 0.759, "avg_delta": 162.96},
    "WIDEN_GRID_SHORT": {"best_scenario": "widen_both", "n": 724, "wr": 0.700, "avg_delta": 114.68},
}


@dataclass(slots=True)
class Episode:
    hypothesis: str
    ts: pd.Timestamp
    entry_ts: pd.Timestamp
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


@dataclass(slots=True)
class FillLot:
    entry_price: float
    target_pct: float
    size_btc: float
    cohort: str


@dataclass(slots=True)
class GridState:
    active_lots: list[FillLot]
    anchor_price: float


def _accept(episodes: list[Episode], hypothesis: str, ts: pd.Timestamp) -> bool:
    for ep in reversed(episodes):
        if ep.hypothesis != hypothesis:
            continue
        if (ts - ep.ts).total_seconds() < COOLDOWN_HOURS * 3600:
            return False
        return True
    return True


def mine_widen_episodes(df_1h: pd.DataFrame) -> list[Episode]:
    episodes: list[Episode] = []
    for i in range(48, len(df_1h) - 24):
        row = df_1h.iloc[i]
        ts = pd.Timestamp(df_1h.index[i])
        current = float(row["close"])
        volume_regime = "above_sma20" if float(row["volume_ratio"]) > 1.0 else "below_sma20"
        session = str(row.get("session_active") or "dead")
        regime = str(row["regime_label"])

        for lookback in (2, 3, 4, 5, 6):
            entry_ts = pd.Timestamp(df_1h.index[i - lookback])
            entry = float(df_1h["close"].iloc[i - lookback])
            move_against_short_pct = (current / entry - 1.0) * 100.0
            liq_distance_short = max(0.0, (entry * SHORT_LIQ_MULT - current) / current * 100.0)
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
                        entry_ts=entry_ts,
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
                        dist_to_resistance_pct=float(row["dist_to_nearest_unmitigated_high_pct"])
                        if not pd.isna(row["dist_to_nearest_unmitigated_high_pct"])
                        else None,
                    )
                )
                break

        for lookback in (2, 3, 4, 5, 6):
            entry_ts = pd.Timestamp(df_1h.index[i - lookback])
            entry = float(df_1h["close"].iloc[i - lookback])
            move_against_long_pct = (current / entry - 1.0) * 100.0
            move_down_pct = -move_against_long_pct
            liq_distance_long = max(0.0, (current - entry * LONG_LIQ_MULT) / current * 100.0)
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
                        entry_ts=entry_ts,
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
                        dist_to_resistance_pct=float(row["dist_to_nearest_unmitigated_low_pct"])
                        if not pd.isna(row["dist_to_nearest_unmitigated_low_pct"])
                        else None,
                    )
                )
                break
    return episodes


def _pnl_linear(entry: float, price: float, size_btc: float, side: str) -> float:
    if side == "long":
        return (price - entry) * size_btc
    return (entry - price) * size_btc


def _target_price(lot: FillLot, side: str) -> float:
    target = lot.target_pct / 100.0
    if side == "long":
        return lot.entry_price * (1.0 + target)
    return lot.entry_price * (1.0 - target)


def _next_fill_price(anchor_price: float, side: str, step_pct: float) -> float:
    if side == "long":
        return anchor_price * (1.0 - step_pct)
    return anchor_price * (1.0 + step_pct)


def _liquidation_price(entry_price: float, side: str) -> float:
    if side == "long":
        return entry_price * LONG_LIQ_MULT
    return entry_price * SHORT_LIQ_MULT


def _close_triggered_lots(active_lots: list[FillLot], side: str, high: float, low: float) -> tuple[list[FillLot], list[FillLot]]:
    closed: list[FillLot] = []
    remaining: list[FillLot] = []
    for lot in active_lots:
        tp_price = _target_price(lot, side)
        hit = high >= tp_price if side == "long" else low <= tp_price
        if hit:
            closed.append(lot)
        else:
            remaining.append(lot)
    return remaining, closed


def _open_new_lots(
    active_lots: list[FillLot],
    anchor_price: float,
    side: str,
    bar_low: float,
    bar_high: float,
    step_pct: float,
    target_pct: float,
    cohort: str,
) -> tuple[list[FillLot], float]:
    lots = [replace(lot) for lot in active_lots]
    anchor = anchor_price
    while len(lots) < MAX_LEVELS:
        next_fill = _next_fill_price(anchor, side, step_pct)
        hit = bar_low <= next_fill if side == "long" else bar_high >= next_fill
        if not hit:
            break
        lots.append(FillLot(entry_price=next_fill, target_pct=target_pct, size_btc=SIZE_PER_LEG_BTC, cohort=cohort))
        anchor = next_fill
    return lots, anchor


def _mark_to_market(active_lots: list[FillLot], close_price: float, side: str) -> float:
    return sum(_pnl_linear(lot.entry_price, close_price, lot.size_btc, side) for lot in active_lots)


def bootstrap_grid_state(
    pre_action_path_1m: pd.DataFrame,
    entry_price: float,
    side: str,
    target_pct: float,
    step_pct: float,
) -> GridState:
    active_lots = [FillLot(entry_price=entry_price, target_pct=target_pct, size_btc=SIZE_PER_LEG_BTC, cohort="existing")]
    anchor_price = entry_price
    for _, row in pre_action_path_1m.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        close = float(row["close"])
        active_lots, anchor_price = _open_new_lots(
            active_lots, anchor_price, side, low, high, step_pct, target_pct, "existing"
        )
        active_lots, closed = _close_triggered_lots(active_lots, side, high, low)
        if closed and not active_lots:
            anchor_price = close
    return GridState(active_lots=active_lots, anchor_price=anchor_price)


def replay_grid_correct(
    future_path_1m: pd.DataFrame,
    side: str,
    state: GridState,
    original_target_pct: float,
    original_step_pct: float,
    new_target_pct: float,
    new_step_pct: float,
    scenario_name: str,
) -> dict[str, Any]:
    active_lots = [replace(lot) for lot in state.active_lots]
    anchor_price = state.anchor_price
    realized = 0.0
    pnl_path: list[float] = []
    liquidation = False
    closed_lots: list[FillLot] = []
    target_unrealized = _mark_to_market(active_lots, float(future_path_1m["close"].iloc[0]), side) if not future_path_1m.empty else 0.0
    recovery_time_hours: float | None = None
    start_ts = future_path_1m.index[0] if not future_path_1m.empty else None

    for ts, row in future_path_1m.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        close = float(row["close"])
        liq_price = _liquidation_price(active_lots[0].entry_price if active_lots else anchor_price, side)
        if (close <= liq_price and side == "long") or (close >= liq_price and side == "short"):
            liquidation = True
            if active_lots:
                realized += sum(_pnl_linear(lot.entry_price, liq_price, lot.size_btc, side) for lot in active_lots)
                closed_lots.extend(active_lots)
                active_lots = []
            pnl_path.append(realized)
            break

        active_lots, anchor_price = _open_new_lots(
            active_lots, anchor_price, side, low, high, new_step_pct, new_target_pct, "new"
        )
        active_lots, closed = _close_triggered_lots(active_lots, side, high, low)
        if closed:
            for lot in closed:
                realized += _pnl_linear(lot.entry_price, _target_price(lot, side), lot.size_btc, side)
            closed_lots.extend(closed)
            if not active_lots:
                anchor_price = close

        unrealized = _mark_to_market(active_lots, close, side)
        total_pnl = realized + unrealized
        pnl_path.append(total_pnl)
        if recovery_time_hours is None and total_pnl >= target_unrealized and start_ts is not None:
            recovery_time_hours = (ts - start_ts).total_seconds() / 3600.0

    final_close = float(future_path_1m["close"].iloc[-1])
    unrealized_final = _mark_to_market(active_lots, final_close, side)
    return {
        "scenario": scenario_name,
        "realized_pnl_24h_usd": realized,
        "unrealized_at_24h_usd": unrealized_final,
        "net_pnl_24h_usd": realized + unrealized_final,
        "max_dd_during_24h_pct": min(pnl_path) / DEPOSIT_USD * 100.0 if pnl_path else 0.0,
        "recovery_time_hours": recovery_time_hours,
        "position_size_at_24h_btc": sum(lot.size_btc for lot in active_lots),
        "survived": not liquidation,
        "liquidated": liquidation,
        "closed_lots": closed_lots,
        "active_lots": active_lots,
        "original_target_pct": original_target_pct,
        "original_step_pct": original_step_pct,
        "new_target_pct": new_target_pct,
        "new_step_pct": new_step_pct,
    }


def _baseline_and_variants(df_1m: pd.DataFrame, ep: Episode) -> list[dict[str, Any]]:
    pre_action_path = df_1m.loc[ep.entry_ts : ep.ts].iloc[:-1].copy()
    future_path = df_1m.loc[ep.ts : ep.ts + pd.Timedelta(hours=24)].copy()
    if len(future_path) < 60:
        return []

    original_target = SHORT_TARGET if ep.side == "short" else LONG_TARGET
    original_step = SHORT_GS if ep.side == "short" else LONG_GS
    state = bootstrap_grid_state(pre_action_path, ep.entry_price, ep.side, original_target, original_step)
    scenarios = [
        replay_grid_correct(
            future_path,
            ep.side,
            state,
            original_target,
            original_step,
            original_target,
            original_step,
            "actual_action",
        ),
        replay_grid_correct(
            future_path,
            ep.side,
            state,
            original_target,
            original_step,
            original_target * 1.5,
            original_step,
            "widen_target",
        ),
        replay_grid_correct(
            future_path,
            ep.side,
            state,
            original_target,
            original_step,
            original_target,
            original_step * 1.5,
            "widen_step",
        ),
        replay_grid_correct(
            future_path,
            ep.side,
            state,
            original_target,
            original_step,
            original_target * 1.5,
            original_step * 1.5,
            "widen_both",
        ),
    ]
    baseline = scenarios[0]
    rows: list[dict[str, Any]] = []
    for sc in scenarios:
        rows.append(
            {
                "hypothesis": ep.hypothesis,
                "scenario": sc["scenario"],
                "ts": ep.ts,
                "entry_ts": ep.entry_ts,
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


def _best_scenario(summary: pd.DataFrame, hypothesis: str) -> pd.Series:
    hyp = summary[summary["hypothesis"] == hypothesis]
    candidates = hyp[hyp["scenario"] != "actual_action"].sort_values(
        ["win_rate_vs_baseline", "avg_pnl_delta_usd"], ascending=[False, False]
    )
    return candidates.iloc[0]


def _stratify(sim: pd.DataFrame, summary: pd.DataFrame, dim: str) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for hyp in ("WIDEN_GRID_LONG", "WIDEN_GRID_SHORT"):
        best_scenario = str(_best_scenario(summary, hyp)["scenario"])
        subset = sim[(sim["hypothesis"] == hyp) & (sim["scenario"] == best_scenario)]
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
        grouped["scenario"] = best_scenario
        rows.append(grouped)
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


def _cross_validate_long(best_long: pd.Series) -> dict[str, float]:
    calibration_path = ROOT / "reports" / "calibration_long_extended_2026-05-02.md"
    calibration_text = calibration_path.read_text(encoding="utf-8")
    realized_min = 0.116400
    realized_max = 0.154230
    realized_spread_btc = realized_max - realized_min
    midpoint_price = 100_000.0
    realized_spread_usd = realized_spread_btc * midpoint_price
    corrected_annualized_usd = float(best_long["avg_pnl_delta_usd"]) * int(best_long["n"])
    ratio = corrected_annualized_usd / realized_spread_usd if realized_spread_usd else float("nan")
    return {
        "annualized_episode_delta_usd": corrected_annualized_usd,
        "realized_spread_usd_proxy": realized_spread_usd,
        "ratio_vs_realized_spread": ratio,
        "source_mentions_direction_only": 1.0 if "directionally valid" in calibration_text else 0.0,
    }


def build_report(summary: pd.DataFrame, strat_session: pd.DataFrame, strat_regime: pd.DataFrame, strat_duration: pd.DataFrame, strat_volume: pd.DataFrame) -> str:
    best_long = _best_scenario(summary, "WIDEN_GRID_LONG")
    best_short = _best_scenario(summary, "WIDEN_GRID_SHORT")
    cross_val = _cross_validate_long(best_long)
    lines: list[str] = []
    lines.append("# Defensive V3 Corrected")
    lines.append("")
    lines.append("## §1 Methodology")
    lines.append("")
    lines.append("- Original V3 used a basket-level `tp_price` derived from mean fill and one widened target for the whole basket.")
    lines.append("- Corrected V3 keeps existing OUT logic unchanged at decision time: every pre-action fill retains its original `target_pct`.")
    lines.append("- Only fills opened after the widen action get the widened `target_pct` and/or widened `grid_step`.")
    lines.append("- Replay is now per-fill: each lot closes against its own TP instead of one basket TP.")
    lines.append("- Episode mining is intentionally kept aligned with V3 for `WIDEN_GRID_LONG` and `WIDEN_GRID_SHORT`.")
    lines.append("")
    lines.append("## §2 Per-hypothesis results table")
    lines.append("")
    comparison_rows = pd.DataFrame(
        [
            {
                "hypothesis": "WIDEN_GRID_LONG",
                "metric": "N",
                "v3_original": ORIGINAL_METRICS["WIDEN_GRID_LONG"]["n"],
                "v3_corrected": int(best_long["n"]),
                "delta": int(best_long["n"]) - int(ORIGINAL_METRICS["WIDEN_GRID_LONG"]["n"]),
            },
            {
                "hypothesis": "WIDEN_GRID_LONG",
                "metric": "WR",
                "v3_original": ORIGINAL_METRICS["WIDEN_GRID_LONG"]["wr"],
                "v3_corrected": float(best_long["win_rate_vs_baseline"]),
                "delta": float(best_long["win_rate_vs_baseline"]) - float(ORIGINAL_METRICS["WIDEN_GRID_LONG"]["wr"]),
            },
            {
                "hypothesis": "WIDEN_GRID_LONG",
                "metric": "Avg PnL delta",
                "v3_original": ORIGINAL_METRICS["WIDEN_GRID_LONG"]["avg_delta"],
                "v3_corrected": float(best_long["avg_pnl_delta_usd"]),
                "delta": float(best_long["avg_pnl_delta_usd"]) - float(ORIGINAL_METRICS["WIDEN_GRID_LONG"]["avg_delta"]),
            },
            {
                "hypothesis": "WIDEN_GRID_SHORT",
                "metric": "N",
                "v3_original": ORIGINAL_METRICS["WIDEN_GRID_SHORT"]["n"],
                "v3_corrected": int(best_short["n"]),
                "delta": int(best_short["n"]) - int(ORIGINAL_METRICS["WIDEN_GRID_SHORT"]["n"]),
            },
            {
                "hypothesis": "WIDEN_GRID_SHORT",
                "metric": "WR",
                "v3_original": ORIGINAL_METRICS["WIDEN_GRID_SHORT"]["wr"],
                "v3_corrected": float(best_short["win_rate_vs_baseline"]),
                "delta": float(best_short["win_rate_vs_baseline"]) - float(ORIGINAL_METRICS["WIDEN_GRID_SHORT"]["wr"]),
            },
            {
                "hypothesis": "WIDEN_GRID_SHORT",
                "metric": "Avg PnL delta",
                "v3_original": ORIGINAL_METRICS["WIDEN_GRID_SHORT"]["avg_delta"],
                "v3_corrected": float(best_short["avg_pnl_delta_usd"]),
                "delta": float(best_short["avg_pnl_delta_usd"]) - float(ORIGINAL_METRICS["WIDEN_GRID_SHORT"]["avg_delta"]),
            },
        ]
    )
    lines.append(_render_table(comparison_rows, ["hypothesis", "metric", "v3_original", "v3_corrected", "delta"]))
    lines.append("")
    lines.append("Corrected aggregate tables:")
    lines.append("")
    for hypothesis in ("WIDEN_GRID_LONG", "WIDEN_GRID_SHORT"):
        lines.append(f"### {hypothesis}")
        lines.append("")
        lines.append(
            _render_table(
                summary[summary["hypothesis"] == hypothesis],
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
    lines.append("## §3 Stratification corrected")
    lines.append("")
    lines.append("By session:")
    lines.append(_render_table(strat_session, ["hypothesis", "scenario", "session_label", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("By regime:")
    lines.append(_render_table(strat_regime, ["hypothesis", "scenario", "regime_label", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("By duration:")
    lines.append(_render_table(strat_duration, ["hypothesis", "scenario", "duration_bucket", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("By volume:")
    lines.append(_render_table(strat_volume, ["hypothesis", "scenario", "volume_regime", "n", "wr", "avg_delta", "avg_dd"]))
    lines.append("")
    lines.append("## §4 Direction validity")
    lines.append("")
    for hypothesis, best in (("WIDEN_GRID_LONG", best_long), ("WIDEN_GRID_SHORT", best_short)):
        original = ORIGINAL_METRICS[hypothesis]
        wr_drop_pp = (float(best["win_rate_vs_baseline"]) - float(original["wr"])) * 100.0
        magnitude_ratio = float(best["avg_pnl_delta_usd"]) / float(original["avg_delta"]) if float(original["avg_delta"]) else float("nan")
        lines.append(
            f"- `{hypothesis}` best corrected scenario is `{best['scenario']}`. "
            f"WR moved from {float(original['wr']) * 100:.1f}% to {float(best['win_rate_vs_baseline']) * 100:.1f}% "
            f"({wr_drop_pp:+.1f}pp). Avg delta moved from ${float(original['avg_delta']):.2f} "
            f"to ${float(best['avg_pnl_delta_usd']):.2f} ({magnitude_ratio:.2f}x of original magnitude)."
        )
    lines.append("")
    lines.append("## §5 Recommendation for adaptive params switch")
    lines.append("")
    for hypothesis, best in (("WIDEN_GRID_LONG", best_long), ("WIDEN_GRID_SHORT", best_short)):
        wr = float(best["win_rate_vs_baseline"])
        magnitude = float(best["avg_pnl_delta_usd"])
        if wr >= 0.60 and magnitude >= 30.0:
            verdict = "switch logic foundation valid"
        elif 0.50 <= wr < 0.60:
            verdict = "marginal; switch arguable but weak"
        else:
            verdict = "not enough edge for switch overhead"
        lines.append(
            f"- `{hypothesis}` via `{best['scenario']}`: WR {wr * 100:.1f}%, avg delta ${magnitude:.2f} -> {verdict}."
        )
    lines.append("")
    lines.append("## §6 Real GinArea cross-validation")
    lines.append("")
    lines.append("- Source used: `reports/calibration_long_extended_2026-05-02.md` available in repo.")
    lines.append(
        f"- That artifact reports LONG realized spread across TD sweep 0.21..0.50 of roughly "
        f"${cross_val['realized_spread_usd_proxy']:.0f} proxy USD at 100k BTC and explicitly says confidence is directional, not absolute."
    )
    lines.append(
        f"- Corrected `WIDEN_GRID_LONG` annualized episode delta proxy: ${cross_val['annualized_episode_delta_usd']:.0f} "
        f"({cross_val['ratio_vs_realized_spread']:.2f}x the realized-spread proxy)."
    )
    if cross_val["ratio_vs_realized_spread"] > 2.0:
        lines.append("- Cross-validation result: corrected episode-local edge still looks too large to map directly into full-year total outcome. Use it as direction, not sizing of expected annual uplift.")
    else:
        lines.append("- Cross-validation result: corrected episode-local edge is in the same order of magnitude as the available LONG sweep proxy, so direction and scale are at least not obviously fractured.")
    lines.append("")
    return "\n".join(lines) + "\n"


def run_research() -> tuple[pd.DataFrame, pd.DataFrame]:
    HistoricalContextBuilder(FROZEN_1M)
    ICTContextReader.load(ICT_PARQUET)
    df_1m, ict = _load_year_data()
    df_1h = _build_hourly_features(df_1m, ict)
    episodes = mine_widen_episodes(df_1h)
    rows: list[dict[str, Any]] = []
    for ep in episodes:
        rows.extend(_baseline_and_variants(df_1m, ep))
    sim = pd.DataFrame(rows)
    summary = _aggregate(sim)
    return sim, summary


def main() -> None:
    sim, summary = run_research()
    strat_session = _stratify(sim, summary, "session_label")
    strat_regime = _stratify(sim, summary, "regime_label")
    strat_duration = _stratify(sim, summary, "duration_bucket")
    strat_volume = _stratify(sim, summary, "volume_regime")
    REPORT_PATH.write_text(
        build_report(summary, strat_session, strat_regime, strat_duration, strat_volume),
        encoding="utf-8",
    )
    print(f"rows={len(sim)} report={REPORT_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
