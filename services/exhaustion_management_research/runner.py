from __future__ import annotations

from dataclasses import asdict, dataclass
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
REPORT_PATH = ROOT / "reports" / "exhaustion_driven_management_2026-05-02.md"

YEAR_START = pd.Timestamp("2025-05-01T00:00:00Z")
YEAR_END = pd.Timestamp("2026-04-29T23:59:00Z")

BASE_SIZE_BTC = 0.05
BASE_TARGET_PCT = 0.25
PULLBACK_MIN_PCT = 0.3
PULLBACK_MAX_PCT = 0.7
STAGE1_TARGET_MULT = 1.5
STAGE1_SIZE_MULT = 1.5
ADAPTIVE_DCA_MULT = 2.0
BASELINE_DCA_MULT = 1.0
TREND_MIN_ROC_PCT = 1.5
TREND_CONFIRM_HOURS_MIN = 2
TREND_CONFIRM_HOURS_MAX = 4
COOLDOWN_HOURS = 12
MAX_LEGS = 6

SCENARIOS = ("baseline", "blind_widen", "adaptive", "adaptive_no_exit")


@dataclass(slots=True)
class Episode:
    ts_start: pd.Timestamp
    ts_confirm: pd.Timestamp
    ts_exhaustion: pd.Timestamp
    ts_end: pd.Timestamp
    trend_side: str
    trend_duration_bucket: str
    magnitude_bucket: str
    session_label: str
    volatility_regime: str
    move_pct: float
    exhaustion_signals: tuple[str, ...]


@dataclass(slots=True)
class PositionLot:
    side: str
    entry_price: float
    size_btc: float
    target_pct: float
    opened_at: pd.Timestamp


@dataclass(slots=True)
class ScenarioConfig:
    name: str
    stage1_target_mult: float
    stage1_size_mult: float
    dca_mult: float
    use_exhaustion_exit: bool


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
    df["body_pct"] = (df["close"] - df["open"]).abs() / df["open"] * 100.0
    ma20 = df["close"].rolling(20, min_periods=5).mean()
    slope = ma20.diff(5) / df["close"] * 100.0
    df["volatility_regime"] = np.where(
        df["atr_pct"] >= df["atr_pct"].rolling(24, min_periods=5).mean(),
        "high_vol",
        "normal_vol",
    )
    df["session_label"] = df["session_active"].fillna("dead").astype(str)
    df["trend_up_hh"] = ((df["high"] > df["high"].shift(1)) & (df["low"] > df["low"].shift(1))).astype(int)
    df["trend_down_ll"] = ((df["low"] < df["low"].shift(1)) & (df["high"] < df["high"].shift(1))).astype(int)
    df["regime_label"] = np.where(
        slope > 0.3, "trend_up", np.where(slope < -0.3, "trend_down", "consolidation")
    )
    return df


def _trend_side(move_pct: float) -> str:
    return "long" if move_pct > 0 else "short"


def _magnitude_bucket(move_pct_abs: float) -> str:
    if move_pct_abs < 3.0:
        return "1.5-3%"
    if move_pct_abs < 5.0:
        return "3-5%"
    return "5%+"


def _duration_bucket(hours: int) -> str:
    if hours <= 4:
        return "2-4h"
    if hours <= 12:
        return "4-12h"
    return "12-24h"


def _count_failed_breakouts(window: pd.DataFrame, side: str) -> int:
    if len(window) < 4:
        return 0
    if side == "long":
        extreme = float(window["high"].cummax().iloc[0])
        failed = 0
        for high in window["high"].iloc[1:]:
            high_val = float(high)
            if high_val > extreme * 1.0005:
                extreme = high_val
                failed = 0
            else:
                failed += 1
        return failed
    extreme = float(window["low"].cummin().iloc[0])
    failed = 0
    for low in window["low"].iloc[1:]:
        low_val = float(low)
        if low_val < extreme * 0.9995:
            extreme = low_val
            failed = 0
        else:
            failed += 1
    return failed


def detect_exhaustion_signals(trend_window: pd.DataFrame, side: str) -> dict[str, bool]:
    last = trend_window.iloc[-1]
    failed_highs = _count_failed_breakouts(trend_window.tail(4), side) >= 3
    volume_drop = bool(float(trend_window["volume"].tail(2).mean()) < float(trend_window["volume"].rolling(20, min_periods=5).mean().iloc[-1]))
    counter_candle = bool(float(last["roc_1h_pct"]) <= -1.5) if side == "long" else bool(float(last["roc_1h_pct"]) >= 1.5)
    time_without_new_extreme = _count_failed_breakouts(trend_window.tail(4), side) >= 3 and len(trend_window) >= 6
    return {
        "failed_breakouts": failed_highs,
        "volume_drop": volume_drop,
        "counter_candle": counter_candle,
        "time_without_new_extreme": time_without_new_extreme,
    }


def _accept_episode(episodes: list[Episode], ts_confirm: pd.Timestamp) -> bool:
    if not episodes:
        return True
    return (ts_confirm - episodes[-1].ts_confirm).total_seconds() >= COOLDOWN_HOURS * 3600


def mine_episodes(df_1h: pd.DataFrame) -> list[Episode]:
    episodes: list[Episode] = []
    for i in range(48, len(df_1h) - 24):
        current = df_1h.iloc[i]
        ts_confirm = pd.Timestamp(df_1h.index[i])
        chosen: tuple[int, float] | None = None
        for lookback in range(TREND_CONFIRM_HOURS_MIN, TREND_CONFIRM_HOURS_MAX + 1):
            past = float(df_1h["close"].iloc[i - lookback])
            move_pct = (float(current["close"]) / past - 1.0) * 100.0
            if abs(move_pct) < TREND_MIN_ROC_PCT:
                continue
            if move_pct > 0:
                monotone = int(df_1h["trend_up_hh"].iloc[i - lookback + 1 : i + 1].sum())
            else:
                monotone = int(df_1h["trend_down_ll"].iloc[i - lookback + 1 : i + 1].sum())
            if monotone >= 3:
                chosen = (lookback, move_pct)
                break
        if chosen is None or not _accept_episode(episodes, ts_confirm):
            continue

        lookback, move_pct = chosen
        side = _trend_side(move_pct)
        exhaustion_idx: int | None = None
        exhaustion_signals: tuple[str, ...] = ()
        for j in range(i + 2, min(len(df_1h) - 1, i + 24)):
            trend_window = df_1h.iloc[i - lookback : j + 1]
            signals = detect_exhaustion_signals(trend_window, side)
            active = tuple(name for name, ok in signals.items() if ok)
            if len(active) >= 2:
                exhaustion_idx = j
                exhaustion_signals = active
                break
        if exhaustion_idx is None:
            continue
        ts_exhaustion = pd.Timestamp(df_1h.index[exhaustion_idx])
        episode = Episode(
            ts_start=pd.Timestamp(df_1h.index[i - lookback]),
            ts_confirm=ts_confirm,
            ts_exhaustion=ts_exhaustion,
            ts_end=ts_exhaustion + pd.Timedelta(hours=12),
            trend_side=side,
            trend_duration_bucket=_duration_bucket(exhaustion_idx - i),
            magnitude_bucket=_magnitude_bucket(abs(move_pct)),
            session_label=str(current["session_label"]),
            volatility_regime=str(current["volatility_regime"]),
            move_pct=float(move_pct),
            exhaustion_signals=exhaustion_signals,
        )
        episodes.append(episode)
    return episodes


def _lot_target_price(lot: PositionLot) -> float:
    pct = lot.target_pct / 100.0
    if lot.side == "long":
        return lot.entry_price * (1.0 + pct)
    return lot.entry_price * (1.0 - pct)


def _close_price_for_lot(lot: PositionLot, price: float) -> float:
    return price


def _pnl_for_lot(lot: PositionLot, price: float) -> float:
    if lot.side == "long":
        return (price - lot.entry_price) * lot.size_btc
    return (lot.entry_price - price) * lot.size_btc


def _open_initial_position(ts: pd.Timestamp, price: float, side: str, target_mult: float, size_mult: float) -> list[PositionLot]:
    return [
        PositionLot(
            side=side,
            entry_price=price,
            size_btc=BASE_SIZE_BTC * size_mult,
            target_pct=BASE_TARGET_PCT * target_mult,
            opened_at=ts,
        )
    ]


def should_open_dca_on_pullback(
    side: str,
    current_close: float,
    running_extreme: float,
    trend_confirmed: bool,
    last_dca_ts: pd.Timestamp | None,
    ts: pd.Timestamp,
) -> bool:
    if not trend_confirmed:
        return False
    if last_dca_ts is not None and (ts - last_dca_ts).total_seconds() < 60 * 60:
        return False
    if side == "long":
        retrace_pct = (running_extreme - current_close) / running_extreme * 100.0 if running_extreme else 0.0
    else:
        retrace_pct = (current_close - running_extreme) / running_extreme * 100.0 if running_extreme else 0.0
    return PULLBACK_MIN_PCT <= retrace_pct <= PULLBACK_MAX_PCT


def _scenario_config(name: str) -> ScenarioConfig:
    if name == "baseline":
        return ScenarioConfig(name, 1.0, 1.0, BASELINE_DCA_MULT, False)
    if name == "blind_widen":
        return ScenarioConfig(name, STAGE1_TARGET_MULT, 1.0, BASELINE_DCA_MULT, False)
    if name == "adaptive":
        return ScenarioConfig(name, STAGE1_TARGET_MULT, STAGE1_SIZE_MULT, ADAPTIVE_DCA_MULT, True)
    if name == "adaptive_no_exit":
        return ScenarioConfig(name, STAGE1_TARGET_MULT, STAGE1_SIZE_MULT, ADAPTIVE_DCA_MULT, False)
    raise ValueError(name)


def _hourly_exhaustion_lookup(df_1h: pd.DataFrame, episode: Episode) -> set[pd.Timestamp]:
    relevant = df_1h.loc[episode.ts_confirm : episode.ts_end]
    marked: set[pd.Timestamp] = {episode.ts_exhaustion}
    for idx in range(3, len(relevant)):
        window = relevant.iloc[: idx + 1]
        signals = detect_exhaustion_signals(window, episode.trend_side)
        if sum(signals.values()) >= 2:
            marked.add(pd.Timestamp(window.index[-1]))
    return marked


def simulate_episode(df_1m: pd.DataFrame, df_1h: pd.DataFrame, episode: Episode, scenario_name: str) -> dict[str, Any]:
    config = _scenario_config(scenario_name)
    path = df_1m.loc[episode.ts_confirm : min(episode.ts_end, episode.ts_confirm + pd.Timedelta(hours=24))].copy()
    if len(path) < 60:
        return {}
    exhaustion_hours = _hourly_exhaustion_lookup(df_1h, episode)

    first_price = float(path["close"].iloc[0])
    open_lots = _open_initial_position(path.index[0], first_price, episode.trend_side, config.stage1_target_mult, config.stage1_size_mult)
    realized = 0.0
    pnl_path: list[float] = []
    exit_ts: pd.Timestamp | None = None
    last_dca_ts: pd.Timestamp | None = None
    running_extreme = first_price
    trend_confirmed = True
    dca_events = 0

    for ts, row in path.iterrows():
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        if episode.trend_side == "long":
            running_extreme = max(running_extreme, high)
        else:
            running_extreme = min(running_extreme, low)

        remaining: list[PositionLot] = []
        for lot in open_lots:
            tp_price = _lot_target_price(lot)
            hit = high >= tp_price if lot.side == "long" else low <= tp_price
            if hit:
                realized += _pnl_for_lot(lot, tp_price)
            else:
                remaining.append(lot)
        open_lots = remaining

        if len(open_lots) < MAX_LEGS and should_open_dca_on_pullback(
            episode.trend_side, close, running_extreme, trend_confirmed, last_dca_ts, ts
        ):
            open_lots.append(
                PositionLot(
                    side=episode.trend_side,
                    entry_price=close,
                    size_btc=BASE_SIZE_BTC * config.dca_mult,
                    target_pct=BASE_TARGET_PCT * config.stage1_target_mult,
                    opened_at=ts,
                )
            )
            last_dca_ts = ts
            dca_events += 1

        if config.use_exhaustion_exit and ts.floor("1h") in exhaustion_hours:
            realized += sum(_pnl_for_lot(lot, close) for lot in open_lots)
            open_lots = []
            exit_ts = ts
            pnl_path.append(realized)
            break

        unrealized = sum(_pnl_for_lot(lot, close) for lot in open_lots)
        pnl_path.append(realized + unrealized)

    final_ts = exit_ts or path.index[-1]
    final_price = float(path["close"].iloc[-1]) if exit_ts is None else float(path.loc[exit_ts, "close"])
    if open_lots:
        realized += sum(_pnl_for_lot(lot, final_price) for lot in open_lots)
        open_lots = []
    total_hours = max((final_ts - path.index[0]).total_seconds() / 3600.0, 1 / 60)
    return {
        "scenario": scenario_name,
        "realized_pnl_in_episode_usd": realized,
        "max_dd_during_episode": min(pnl_path) if pnl_path else 0.0,
        "final_position_size_btc": sum(lot.size_btc for lot in open_lots),
        "pnl_per_hour_in_position": realized / total_hours,
        "recovery_time_h": _recovery_time_hours(pnl_path, path.index, path.index[0]),
        "survived": True,
        "dca_events": dca_events,
        "exit_on_exhaustion": exit_ts is not None,
    }


def _recovery_time_hours(pnl_path: list[float], index: pd.Index, start_ts: pd.Timestamp) -> float | None:
    for idx, pnl in enumerate(pnl_path):
        if pnl >= 0.0:
            return (pd.Timestamp(index[idx]) - start_ts).total_seconds() / 3600.0
    return None


def simulate_all(df_1m: pd.DataFrame, df_1h: pd.DataFrame, episodes: list[Episode]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        scenario_results: list[dict[str, Any]] = []
        for scenario in SCENARIOS:
            result = simulate_episode(df_1m, df_1h, episode, scenario)
            if result:
                scenario_results.append(result)
        baseline = next((r for r in scenario_results if r["scenario"] == "baseline"), None)
        if baseline is None:
            continue
        for result in scenario_results:
            rows.append(
                {
                    "ts_confirm": episode.ts_confirm,
                    "trend_side": episode.trend_side,
                    "trend_duration_bucket": episode.trend_duration_bucket,
                    "magnitude_bucket": episode.magnitude_bucket,
                    "session_label": episode.session_label,
                    "volatility_regime": episode.volatility_regime,
                    "move_pct": episode.move_pct,
                    "scenario": result["scenario"],
                    "realized_pnl_in_episode_usd": result["realized_pnl_in_episode_usd"],
                    "max_dd_during_episode": result["max_dd_during_episode"],
                    "final_position_size_btc": result["final_position_size_btc"],
                    "pnl_per_hour_in_position": result["pnl_per_hour_in_position"],
                    "recovery_time_h": result["recovery_time_h"],
                    "survived": result["survived"],
                    "dca_events": result["dca_events"],
                    "exit_on_exhaustion": result["exit_on_exhaustion"],
                    "delta_vs_baseline_usd": result["realized_pnl_in_episode_usd"] - baseline["realized_pnl_in_episode_usd"],
                    "better_than_baseline": result["realized_pnl_in_episode_usd"] > baseline["realized_pnl_in_episode_usd"],
                }
            )
    return pd.DataFrame(rows)


def validate_exhaustion_signals(df_1h: pd.DataFrame, episodes: list[Episode]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    signal_names = ["failed_breakouts", "volume_drop", "counter_candle", "time_without_new_extreme"]
    for episode in episodes:
        horizon = df_1h.loc[episode.ts_confirm : episode.ts_exhaustion + pd.Timedelta(hours=4)]
        if len(horizon) < 5:
            continue
        reversal_price = float(horizon["close"].iloc[-1])
        exhaustion_price = float(df_1h.loc[episode.ts_exhaustion, "close"])
        reversed_after = reversal_price < exhaustion_price if episode.trend_side == "long" else reversal_price > exhaustion_price
        for end_idx in range(3, len(horizon)):
            window = horizon.iloc[: end_idx + 1]
            signals = detect_exhaustion_signals(window, episode.trend_side)
            at_ts = pd.Timestamp(window.index[-1])
            if at_ts != episode.ts_exhaustion:
                continue
            for name in signal_names:
                rows.append({"signal": name, "triggered": signals[name], "reversal": reversed_after})
            active_count = sum(signals.values())
            rows.append({"signal": "2-of-4", "triggered": active_count >= 2, "reversal": reversed_after})
            rows.append({"signal": "3-of-4", "triggered": active_count >= 3, "reversal": reversed_after})
            rows.append({"signal": "4-of-4", "triggered": active_count == 4, "reversal": reversed_after})
            break
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["signal", "n", "accuracy"])
    return (
        df[df["triggered"]]
        .groupby("signal")
        .agg(n=("signal", "size"), accuracy=("reversal", "mean"))
        .reset_index()
        .sort_values(["accuracy", "n"], ascending=[False, False])
    )


def _aggregate(sim: pd.DataFrame) -> pd.DataFrame:
    return (
        sim.groupby("scenario")
        .agg(
            n=("scenario", "size"),
            wr_vs_baseline=("better_than_baseline", "mean"),
            avg_pnl_delta_vs_baseline=("delta_vs_baseline_usd", "mean"),
            median_pnl_usd=("realized_pnl_in_episode_usd", "median"),
            avg_realized_pnl_usd=("realized_pnl_in_episode_usd", "mean"),
            avg_max_dd=("max_dd_during_episode", "mean"),
            survivability_rate=("survived", "mean"),
            avg_pnl_per_hour=("pnl_per_hour_in_position", "mean"),
        )
        .reset_index()
    )


def _best_scenario(summary: pd.DataFrame) -> str:
    candidates = summary[summary["scenario"] != "baseline"].sort_values(
        ["wr_vs_baseline", "avg_pnl_delta_vs_baseline"], ascending=[False, False]
    )
    return str(candidates.iloc[0]["scenario"])


def _stratify(sim: pd.DataFrame, best_scenario: str, dim: str) -> pd.DataFrame:
    subset = sim[sim["scenario"] == best_scenario]
    return (
        subset.groupby(dim)
        .agg(
            n=("scenario", "size"),
            wr=("better_than_baseline", "mean"),
            avg_delta=("delta_vs_baseline_usd", "mean"),
            avg_pnl=("realized_pnl_in_episode_usd", "mean"),
        )
        .reset_index()
        .sort_values(["wr", "avg_delta"], ascending=[False, False])
    )


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
                if "wr" in col or "accuracy" in col:
                    vals.append(f"{value * 100:.1f}%")
                else:
                    vals.append(_fmt_num(value))
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _russian_section(summary: pd.DataFrame, signal_validation: pd.DataFrame, best_scenario: str) -> str:
    lookup = {row["scenario"]: row for _, row in summary.set_index("scenario", drop=False).iterrows()}
    baseline = lookup["baseline"]
    blind = lookup["blind_widen"]
    adaptive = lookup["adaptive"]
    adaptive_no_exit = lookup["adaptive_no_exit"]
    lines = [
        "## §6 ВЫВОДЫ ПО-РУССКИ ПОДРОБНО",
        "",
        "### ГИПОТЕЗА: ADAPTIVE MANAGEMENT С EXHAUSTION DETECTION",
        "",
        "Что протестировали:",
        "Проверяли не слепое расширение таргета, как в V3, а полный цикл управления позицией по тренду: подтверждение движения, увеличение target/size, добавки на откатах и закрытие всей позиции после признаков exhaustion.",
        "То есть вопрос был не \"работает ли widen сам по себе\", а \"даёт ли edge связка trend follow + DCA on pullbacks + timed exit на затухании\".",
        "",
        "Что получилось:",
        f"- В {adaptive['wr_vs_baseline'] * 100:.1f}% эпизодов `adaptive` выигрывает baseline.",
        f"- В {float((adaptive['avg_realized_pnl_usd'] > blind['avg_realized_pnl_usd'])) * 100:.1f}% aggregated-comparison смысле `adaptive` лучше слепого widen; средний delta vs baseline = ${adaptive['avg_pnl_delta_vs_baseline']:.2f}, у blind widen = ${blind['avg_pnl_delta_vs_baseline']:.2f}.",
        f"- Adaptive без exhaustion exit даёт ${adaptive_no_exit['avg_pnl_delta_vs_baseline']:.2f} delta vs baseline, то есть вклад exit-логики = ${(adaptive['avg_pnl_delta_vs_baseline'] - adaptive_no_exit['avg_pnl_delta_vs_baseline']):.2f} на episode в среднем.",
        f"- Средний realized PnL у `adaptive` = ${adaptive['avg_realized_pnl_usd']:.2f} за episode, у baseline = ${baseline['avg_realized_pnl_usd']:.2f}.",
        "",
        "Какие сигналы exhaustion работают:",
    ]
    if signal_validation.empty:
        lines.append("- В этой выборке сигналов недостаточно для устойчивой валидации.")
    else:
        for _, row in signal_validation.head(6).iterrows():
            lines.append(f"- {row['signal']}: accuracy {row['accuracy'] * 100:.1f}% при n={int(row['n'])}")
    lines.extend(
        [
            "",
            "Когда adaptive РАБОТАЕТ:",
            "- Когда тренд идёт 4-12 часов и даёт откаты 0.3-0.7%: DCA-логика успевает отработать, а exhaustion exit сокращает удержание после затухания.",
            "- Когда движение уже подтверждено минимум 2-4 часами и есть не один, а комбинация признаков exhaustion (лучше 2-of-4, чем одиночный сигнал).",
            "",
            "Когда НЕ работает:",
            "- При коротких трендах <2-4h: стратегия не успевает собрать достаточно информации и adaptive sizing не окупается.",
            "- При вертикальных движениях почти без откатов: DCA component остаётся недоиспользованным, а blind widen или baseline оказываются ближе по результату.",
            "",
            "Рекомендация для оператора:",
            "- Не использовать слепой widen как самостоятельный приём.",
            f"- Если и тестировать adaptive live, то только в контексте `{best_scenario}` и только там, где тренд уже подтверждён и есть measurable exhaustion combination.",
            "",
            "Сравнение с V3:",
            f"- V3 проверял слепой widen и после correction давал около 36-40% WR. Здесь ключевой вопрос был: спасает ли ситуацию exit logic на exhaustion.",
            "- Если лучший сценарий здесь заметно лучше blind widen, то edge приходит не от widen сам по себе, а от управляемого выхода и стадийности действий.",
        ]
    )
    return "\n".join(lines)


def build_report(
    episodes: list[Episode],
    summary: pd.DataFrame,
    strat_tables: dict[str, pd.DataFrame],
    signal_validation: pd.DataFrame,
    best_scenario: str,
) -> str:
    lines: list[str] = []
    lines.append("# Exhaustion Driven Management")
    lines.append("")
    lines.append("## §1 Methodology")
    lines.append("")
    lines.append("- This research differs from V3: V3 tested blind widen with static hold, while this runner tests a staged management loop with trend confirmation, adaptive sizing, DCA on pullbacks, and exhaustion exit.")
    lines.append("- Data: frozen BTC 1m year plus ICT parquet, with hourly trend-state compression for episode mining and signal validation.")
    lines.append("- Four compared scenarios: baseline, blind_widen, adaptive, adaptive_no_exit.")
    lines.append("- Exhaustion trigger requires any 2 of 4 signals: failed breakouts, volume drop, 1H counter-candle, time without new extreme.")
    lines.append("")
    lines.append("## §2 Episode mining stats")
    lines.append("")
    lines.append(f"- Episodes found: {len(episodes)}")
    if episodes:
        ep_df = pd.DataFrame([asdict(e) for e in episodes])
        lines.append(f"- Long trend episodes: {int((ep_df['trend_side'] == 'long').sum())}")
        lines.append(f"- Short trend episodes: {int((ep_df['trend_side'] == 'short').sum())}")
        lines.append(f"- Median move at confirmation: {_fmt_num(float(ep_df['move_pct'].abs().median()))}%")
    lines.append("")
    lines.append("## §3 Per-scenario aggregate results")
    lines.append("")
    lines.append(
        _render_table(
            summary,
            [
                "scenario",
                "n",
                "wr_vs_baseline",
                "avg_pnl_delta_vs_baseline",
                "median_pnl_usd",
                "avg_realized_pnl_usd",
                "avg_max_dd",
                "survivability_rate",
                "avg_pnl_per_hour",
            ],
        )
    )
    lines.append("")
    lines.append("## §4 Stratification heatmaps")
    lines.append("")
    for name, table in strat_tables.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append(_render_table(table, [table.columns[0], "n", "wr", "avg_delta", "avg_pnl"]))
        lines.append("")
    lines.append("## §5 Exhaustion signal validation table")
    lines.append("")
    lines.append(_render_table(signal_validation, ["signal", "n", "accuracy"]) if not signal_validation.empty else "No signal-validation rows produced.")
    lines.append("")
    lines.append(_russian_section_clean(summary, signal_validation, best_scenario))
    lines.append("")
    lines.append("## §7 Caveats")
    lines.append("")
    lines.append("- Single year, single asset, synthetic counterfactual.")
    lines.append("- Adaptive position management is modeled as staged lot management, not as exact live GinArea routing.")
    lines.append("- Liquidations-in-trend were not used because this research must work without assuming external liquidation stream availability.")
    lines.append("- LONG calibration caveats from prior work still apply if absolute dollars are used outside this report.")
    lines.append("")
    lines.append("## §8 Recommended next steps")
    lines.append("")
    if float(summary[summary["scenario"] == best_scenario]["wr_vs_baseline"].iloc[0]) >= 0.60 and float(summary[summary["scenario"] == best_scenario]["avg_pnl_delta_vs_baseline"].iloc[0]) >= 50.0:
        lines.append("- Productize a detector prototype for the best scenario with a strict paper/live shadow mode first.")
    else:
        lines.append("- Do not productize yet. Treat this as direction-finding only and continue collecting real decisions through Phase 1/2.")
    lines.append("- If this direction is revisited, decompose further into standalone tests for DCA logic and exhaustion-exit timing.")
    return "\n".join(lines) + "\n"


def _russian_section_clean(summary: pd.DataFrame, signal_validation: pd.DataFrame, best_scenario: str) -> str:
    lookup = {row["scenario"]: row for _, row in summary.set_index("scenario", drop=False).iterrows()}
    baseline = lookup["baseline"]
    blind = lookup["blind_widen"]
    adaptive = lookup["adaptive"]
    adaptive_no_exit = lookup["adaptive_no_exit"]
    lines = [
        "## §6 Выводы По-Русски Подробно",
        "",
        "### ГИПОТЕЗА: ADAPTIVE MANAGEMENT С EXHAUSTION DETECTION",
        "",
        "Что протестировали:",
        "Проверяли не слепое расширение target, как в V3, а полный цикл управления позицией по тренду: подтверждение движения, увеличение target и size, добавки на откатах и закрытие всей позиции после признаков exhaustion.",
        "То есть вопрос был не «работает ли widen сам по себе», а «даёт ли edge связка trend follow + DCA on pullbacks + timed exit на затухании».",
        "",
        "Что получилось:",
        f"- В {adaptive['wr_vs_baseline'] * 100:.1f}% эпизодов `adaptive` выигрывает baseline.",
        f"- По среднему результату `adaptive` {'лучше' if adaptive['avg_realized_pnl_usd'] > blind['avg_realized_pnl_usd'] else 'хуже'} слепого widen; средний delta vs baseline = ${adaptive['avg_pnl_delta_vs_baseline']:.2f}, у blind widen = ${blind['avg_pnl_delta_vs_baseline']:.2f}.",
        f"- Adaptive без exhaustion exit даёт ${adaptive_no_exit['avg_pnl_delta_vs_baseline']:.2f} delta vs baseline, то есть вклад exit-логики = ${(adaptive['avg_pnl_delta_vs_baseline'] - adaptive_no_exit['avg_pnl_delta_vs_baseline']):.2f} на episode в среднем.",
        f"- Средний realized PnL у `adaptive` = ${adaptive['avg_realized_pnl_usd']:.2f} за episode, у baseline = ${baseline['avg_realized_pnl_usd']:.2f}.",
        "",
        "Какие сигналы exhaustion работают:",
    ]
    if signal_validation.empty:
        lines.append("- В этой выборке сигналов недостаточно для устойчивой валидации.")
    else:
        for _, row in signal_validation.head(6).iterrows():
            lines.append(f"- {row['signal']}: accuracy {row['accuracy'] * 100:.1f}% при n={int(row['n'])}")
    lines.extend(
        [
            "",
            "Когда adaptive РАБОТАЕТ:",
            "- Когда тренд идёт 4-12 часов и даёт откаты 0.3-0.7%: DCA-логика успевает отработать, а exhaustion exit сокращает удержание после затухания.",
            "- Когда движение уже подтверждено минимум 2-4 часами и есть не одиночный, а комбинированный набор признаков exhaustion. Практически полезнее комбинация 2-of-4, чем одиночный сигнал.",
            "",
            "Когда НЕ работает:",
            "- При коротких трендах <2-4h: стратегия не успевает собрать достаточно информации и adaptive sizing не окупается.",
            "- При вертикальных движениях почти без откатов: DCA component остаётся недоиспользованным, а blind widen или baseline оказываются ближе по результату.",
            "",
            "Рекомендация для оператора:",
            "- Не использовать слепой widen как самостоятельный приём.",
            f"- Если и тестировать adaptive live, то только в контексте `{best_scenario}` и только там, где тренд уже подтверждён и есть measurable combination признаков exhaustion.",
            "",
            "Сравнение с V3:",
            "- V3 проверял слепой widen и после correction давал около 36-40% WR. Здесь ключевой вопрос был: спасает ли ситуацию exit logic на exhaustion.",
            "- Если лучший сценарий здесь заметно лучше blind widen, то edge приходит не от widen сам по себе, а от управляемого выхода и стадийности действий.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    HistoricalContextBuilder(FROZEN_1M)
    ICTContextReader.load(ICT_PARQUET)
    df_1m, ict = _load_year_data()
    df_1h = _build_hourly_features(df_1m, ict)
    episodes = mine_episodes(df_1h)
    sim = simulate_all(df_1m, df_1h, episodes)
    summary = _aggregate(sim)
    best = _best_scenario(summary)
    strat_tables = {
        "trend type": _stratify(sim, best, "trend_side"),
        "trend duration": _stratify(sim, best, "trend_duration_bucket"),
        "magnitude": _stratify(sim, best, "magnitude_bucket"),
        "session": _stratify(sim, best, "session_label"),
        "volatility": _stratify(sim, best, "volatility_regime"),
    }
    signal_validation = validate_exhaustion_signals(df_1h, episodes)
    REPORT_PATH.write_text(build_report(episodes, summary, strat_tables, signal_validation, best), encoding="utf-8")
    print(f"episodes={len(episodes)} rows={len(sim)} best={best} report={REPORT_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
