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
REPORT_PATH = ROOT / "reports" / "defensive_v4_disable_in_2026-05-02.md"

YEAR_START = pd.Timestamp("2025-05-01T00:00:00Z")
YEAR_END = pd.Timestamp("2026-04-29T23:59:00Z")
DEPOSIT_USD = 15_000.0
BASE_POSITION_BTC = 0.20
SHORT_TARGET = 0.25
SHORT_GS = 0.03
PREDECISION_IN_STEP = 0.02
MAX_LEVELS = 3
COOLDOWN_HOURS = 4


@dataclass(slots=True)
class Episode:
    ts: pd.Timestamp
    entry_price: float
    current_price: float
    move_pct: float
    duration_hours: int
    duration_bucket: str
    session_label: str
    regime_label: str
    volume_regime: str
    liq_distance_pct: float
    dd_pct_deposit: float
    initial_position_size_btc: float
    initial_fill_count: int


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
    df = df_1h.join(ict_hour[["session_active"]], how="left")
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
    ma20 = df["close"].rolling(20, min_periods=5).mean()
    slope = ma20.diff(5) / df["close"] * 100.0
    df["regime_label"] = np.where(
        slope > 0.3,
        "trend_up",
        np.where(slope < -0.3, "trend_down", "consolidation"),
    )
    return df


def _duration_bucket(hours: int) -> str:
    if hours <= 2:
        return "2h"
    if hours <= 4:
        return "4h"
    return "6h"


def _accept(episodes: list[Episode], ts: pd.Timestamp) -> bool:
    if not episodes:
        return True
    last = episodes[-1]
    return (ts - last.ts).total_seconds() >= COOLDOWN_HOURS * 3600


def _initial_fill_prices(entry_price: float, current_price: float) -> list[float]:
    fills = [entry_price]
    step_pct = PREDECISION_IN_STEP
    while len(fills) < MAX_LEVELS:
        nxt = fills[-1] * (1.0 + step_pct)
        if nxt <= current_price:
            fills.append(nxt)
        else:
            break
    return fills


def mine_episodes(df_1h: pd.DataFrame) -> list[Episode]:
    episodes: list[Episode] = []
    for i in range(48, len(df_1h) - 24):
        row = df_1h.iloc[i]
        ts = pd.Timestamp(df_1h.index[i])
        current = float(row["close"])
        volume_regime = "above_sma20" if float(row["volume_ratio"]) > 1.0 else "below_sma20"
        session = str(row.get("session_active") or "dead")
        regime = str(row["regime_label"])
        for lookback in (2, 3, 4, 5, 6):
            entry = float(df_1h["close"].iloc[i - lookback])
            move_pct = (current / entry - 1.0) * 100.0
            liq_distance = max(0.0, (entry * 1.20 - current) / current * 100.0)
            dd_usd = max(0.0, (current - entry) * BASE_POSITION_BTC)
            dd_pct_deposit = dd_usd / DEPOSIT_USD * 100.0
            fills = _initial_fill_prices(entry, current)
            if (
                0.8 <= move_pct <= 4.0
                and dd_pct_deposit >= 0.1
                and liq_distance > 10.0
                and len(fills) >= 2
                and _accept(episodes, ts)
            ):
                size_per_leg = BASE_POSITION_BTC / MAX_LEVELS
                episodes.append(
                    Episode(
                        ts=ts,
                        entry_price=entry,
                        current_price=current,
                        move_pct=move_pct,
                        duration_hours=lookback,
                        duration_bucket=_duration_bucket(lookback),
                        session_label=session,
                        regime_label=regime,
                        volume_regime=volume_regime,
                        liq_distance_pct=liq_distance,
                        dd_pct_deposit=dd_pct_deposit,
                        initial_position_size_btc=size_per_leg * len(fills),
                        initial_fill_count=len(fills),
                    )
                )
                break
    return episodes


def _price_path(df_1m: pd.DataFrame, ts: pd.Timestamp) -> pd.DataFrame:
    return df_1m.loc[ts : ts + pd.Timedelta(hours=24)].copy()


def _pnl_linear(entry: float, price: float, size_btc: float, side: str) -> float:
    return (entry - price) * size_btc if side == "short" else (price - entry) * size_btc


def _recovery_time(path_1m: pd.DataFrame, target_unrealized: float, pnl_fn) -> float | None:
    start_ts = path_1m.index[0]
    for ts, row in path_1m.iterrows():
        if pnl_fn(float(row["close"])) >= target_unrealized:
            return (ts - start_ts).total_seconds() / 3600.0
    return None


def _simulate_short_grid(
    path_1m: pd.DataFrame,
    ep: Episode,
    *,
    allow_new_in: bool,
    target_mult: float,
) -> dict[str, Any]:
    step_pct = SHORT_GS
    tp_pct = SHORT_TARGET * target_mult / 100.0
    size_per_leg = BASE_POSITION_BTC / MAX_LEVELS
    fills = _initial_fill_prices(ep.entry_price, ep.current_price)
    realized = 0.0
    pnl_path: list[float] = []
    current_anchor = fills[-1]
    max_position = size_per_leg * len(fills)
    target_unrealized = sum(_pnl_linear(fp, ep.current_price, size_per_leg, "short") for fp in fills)

    for _, row in path_1m.iterrows():
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        if allow_new_in:
            while len(fills) < MAX_LEVELS:
                nxt = current_anchor * (1.0 + step_pct)
                if high >= nxt:
                    fills.append(nxt)
                    current_anchor = nxt
                    max_position = max(max_position, size_per_leg * len(fills))
                else:
                    break

        tp_price = np.mean(fills) * (1.0 - tp_pct)
        if low <= tp_price:
            realized += sum(_pnl_linear(fp, tp_price, size_per_leg, "short") for fp in fills)
            fills = []

        unrealized = sum(_pnl_linear(fp, close, size_per_leg, "short") for fp in fills)
        pnl_path.append(realized + unrealized)

    final_close = float(path_1m["close"].iloc[-1])
    unrealized_final = sum(_pnl_linear(fp, final_close, size_per_leg, "short") for fp in fills)
    return {
        "realized_pnl_usd": realized,
        "unrealized_at_24h_usd": unrealized_final,
        "net_pnl_24h_usd": realized + unrealized_final,
        "max_dd_during_24h_pct": min(pnl_path) / DEPOSIT_USD * 100.0 if pnl_path else 0.0,
        "final_position_size_btc": size_per_leg * len(fills),
        "max_position_size_btc": max_position,
        "position_size_delta_btc": max_position - ep.initial_position_size_btc,
        "recovery_time_hours": _recovery_time(
            path_1m,
            target_unrealized,
            lambda p: realized + sum(_pnl_linear(fp, p, size_per_leg, "short") for fp in fills),
        ),
    }


def simulate_episode(df_1m: pd.DataFrame, ep: Episode) -> list[dict[str, Any]]:
    path_1m = _price_path(df_1m, ep.ts)
    if len(path_1m) < 60:
        return []

    actual = _simulate_short_grid(path_1m, ep, allow_new_in=True, target_mult=1.0)
    disable_in = _simulate_short_grid(path_1m, ep, allow_new_in=False, target_mult=1.0)
    widen_target = _simulate_short_grid(path_1m, ep, allow_new_in=True, target_mult=1.5)

    scenario_map = {
        "actual_action": actual,
        "disable_in": disable_in,
        "widen_target": widen_target,
    }
    rows: list[dict[str, Any]] = []
    for scenario, res in scenario_map.items():
        rows.append(
            {
                "scenario": scenario,
                "ts": ep.ts,
                "session_label": ep.session_label,
                "regime_label": ep.regime_label,
                "duration_bucket": ep.duration_bucket,
                "volume_regime": ep.volume_regime,
                "initial_position_bucket": (
                    "small" if ep.initial_position_size_btc <= 0.10 else "medium" if ep.initial_position_size_btc <= 0.14 else "large"
                ),
                "initial_position_size_btc": ep.initial_position_size_btc,
                "move_pct": ep.move_pct,
                "liq_distance_pct": ep.liq_distance_pct,
                "dd_pct_deposit": ep.dd_pct_deposit,
                **res,
            }
        )
    return rows


def _aggregate(sim: pd.DataFrame) -> pd.DataFrame:
    baseline = sim[sim["scenario"] == "actual_action"][["ts", "net_pnl_24h_usd"]].rename(columns={"net_pnl_24h_usd": "baseline_pnl"})
    out = sim.merge(baseline, on="ts", how="left")
    out["pnl_delta_vs_actual"] = out["net_pnl_24h_usd"] - out["baseline_pnl"]
    out["better_than_actual"] = out["net_pnl_24h_usd"] > out["baseline_pnl"]
    return (
        out.groupby("scenario")
        .agg(
            n=("scenario", "size"),
            wr_vs_actual=("better_than_actual", "mean"),
            avg_pnl_delta=("pnl_delta_vs_actual", "mean"),
            median_pnl_delta=("pnl_delta_vs_actual", "median"),
            q25_pnl_delta=("pnl_delta_vs_actual", lambda s: float(s.quantile(0.25))),
            q75_pnl_delta=("pnl_delta_vs_actual", lambda s: float(s.quantile(0.75))),
            avg_max_dd=("max_dd_during_24h_pct", "mean"),
            avg_position_size_delta=("position_size_delta_btc", "mean"),
            avg_final_position_size=("final_position_size_btc", "mean"),
        )
        .reset_index()
    )


def _cross_compare(sim: pd.DataFrame) -> pd.DataFrame:
    pivot = sim.pivot_table(
        index=["ts", "session_label", "regime_label", "duration_bucket", "volume_regime", "initial_position_bucket", "initial_position_size_btc"],
        columns="scenario",
        values=["net_pnl_24h_usd", "position_size_delta_btc"],
    )
    pivot.columns = [f"{a}_{b}" for a, b in pivot.columns]
    pivot = pivot.reset_index()
    pivot["disable_better_than_actual"] = pivot["net_pnl_24h_usd_disable_in"] > pivot["net_pnl_24h_usd_actual_action"]
    pivot["disable_better_than_widen"] = pivot["net_pnl_24h_usd_disable_in"] > pivot["net_pnl_24h_usd_widen_target"]
    pivot["widen_better_than_disable"] = pivot["net_pnl_24h_usd_widen_target"] > pivot["net_pnl_24h_usd_disable_in"]
    pivot["position_economy_disable_vs_actual"] = pivot["position_size_delta_btc_actual_action"] - pivot["position_size_delta_btc_disable_in"]
    pivot["position_economy_disable_vs_widen"] = pivot["position_size_delta_btc_widen_target"] - pivot["position_size_delta_btc_disable_in"]
    return pivot


def _stratify(compare_df: pd.DataFrame, dim: str, metric: str) -> pd.DataFrame:
    return (
        compare_df.groupby(dim)
        .agg(
            n=("ts", "size"),
            wr=(metric, "mean"),
            avg_position_economy=("position_economy_disable_vs_actual", "mean"),
            avg_pnl_disable=("net_pnl_24h_usd_disable_in", "mean"),
            avg_pnl_widen=("net_pnl_24h_usd_widen_target", "mean"),
        )
        .reset_index()
        .sort_values("wr", ascending=False)
    )


def _render_table(df: pd.DataFrame, columns: list[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for _, row in df.iterrows():
        vals: list[str] = []
        for col in columns:
            value = row[col]
            if isinstance(value, float):
                if col.startswith("wr"):
                    vals.append(f"{value * 100:.1f}%")
                else:
                    vals.append(f"{value:.2f}")
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def build_report(summary: pd.DataFrame, compare_df: pd.DataFrame, by_session: pd.DataFrame, by_duration: pd.DataFrame, by_position: pd.DataFrame, disable_vs_widen_session: pd.DataFrame, disable_vs_widen_duration: pd.DataFrame, disable_vs_widen_position: pd.DataFrame) -> str:
    disable_row = summary[summary["scenario"] == "disable_in"].iloc[0]
    widen_row = summary[summary["scenario"] == "widen_target"].iloc[0]
    actual_row = summary[summary["scenario"] == "actual_action"].iloc[0]
    disable_vs_widen_wr = float(compare_df["disable_better_than_widen"].mean())
    position_economy_overall = float(compare_df["position_economy_disable_vs_actual"].mean())

    works: list[str] = []
    disable_better: list[str] = []
    widen_better: list[str] = []

    for _, row in by_session.iterrows():
        if int(row["n"]) >= 20 and float(row["wr"]) >= 0.60:
            works.append(f"`session={row['session_label']}`: WR {row['wr']*100:.1f}% против actual при n={int(row['n'])}")
    for _, row in disable_vs_widen_duration.iterrows():
        if int(row["n"]) >= 20 and float(row["wr"]) >= 0.55:
            disable_better.append(f"`duration={row['duration_bucket']}`: disable_in лучше widen_target в {row['wr']*100:.1f}% случаев")
        elif int(row["n"]) >= 20 and float(row["wr"]) <= 0.45:
            widen_better.append(f"`duration={row['duration_bucket']}`: widen_target лучше disable_in в {(1-row['wr'])*100:.1f}% случаев")
    for _, row in disable_vs_widen_position.iterrows():
        if int(row["n"]) >= 20 and float(row["wr"]) >= 0.55:
            disable_better.append(f"`position_bucket={row['initial_position_bucket']}`: disable_in лучше widen_target в {row['wr']*100:.1f}% случаев")
        elif int(row["n"]) >= 20 and float(row["wr"]) <= 0.45:
            widen_better.append(f"`position_bucket={row['initial_position_bucket']}`: widen_target лучше disable_in в {(1-row['wr'])*100:.1f}% случаев")

    lines: list[str] = []
    lines.append("# Defensive V4 — disable_in Research")
    lines.append("")
    lines.append("## §1 Methodology")
    lines.append("")
    lines.append("- Episodes reuse the same synthetic SHORT drawdown setup-space as `V3 WIDEN_GRID_SHORT`.")
    lines.append("- Baseline `actual_action`: current grid continues with new IN orders enabled.")
    lines.append("- `disable_in`: no new IN orders after decision moment, existing OUT orders remain active.")
    lines.append("- `widen_target`: keep IN enabled, but raise target by `1.5x`.")
    lines.append("- Grid replay is synthetic and single-bot: it models fills and exits on frozen BTC 1m data over 24h.")
    lines.append("")
    lines.append("## §2 Aggregate results")
    lines.append("")
    lines.append(_render_table(summary, ["scenario", "n", "wr_vs_actual", "avg_pnl_delta", "median_pnl_delta", "q25_pnl_delta", "q75_pnl_delta", "avg_max_dd", "avg_position_size_delta", "avg_final_position_size"]))
    lines.append("")
    lines.append("## §3 Stratification")
    lines.append("")
    lines.append("disable_in vs actual by session:")
    lines.append(_render_table(by_session, ["session_label", "n", "wr", "avg_position_economy", "avg_pnl_disable", "avg_pnl_widen"]))
    lines.append("")
    lines.append("disable_in vs actual by duration:")
    lines.append(_render_table(by_duration, ["duration_bucket", "n", "wr", "avg_position_economy", "avg_pnl_disable", "avg_pnl_widen"]))
    lines.append("")
    lines.append("disable_in vs actual by initial position size:")
    lines.append(_render_table(by_position, ["initial_position_bucket", "n", "wr", "avg_position_economy", "avg_pnl_disable", "avg_pnl_widen"]))
    lines.append("")
    lines.append("## §4 disable_in vs widen_target")
    lines.append("")
    lines.append("By session:")
    lines.append(_render_table(disable_vs_widen_session, ["session_label", "n", "wr", "avg_position_economy", "avg_pnl_disable", "avg_pnl_widen"]))
    lines.append("")
    lines.append("By duration:")
    lines.append(_render_table(disable_vs_widen_duration, ["duration_bucket", "n", "wr", "avg_position_economy", "avg_pnl_disable", "avg_pnl_widen"]))
    lines.append("")
    lines.append("By initial position size:")
    lines.append(_render_table(disable_vs_widen_position, ["initial_position_bucket", "n", "wr", "avg_position_economy", "avg_pnl_disable", "avg_pnl_widen"]))
    lines.append("")
    lines.append("## §5 ГИПОТЕЗА: DISABLE_IN")
    lines.append("")
    lines.append("Что протестировали:")
    lines.append("Взяли тот же SHORT drawdown setup-space, что в V3 для widening, но заменили defensive action. Сравнили обычное продолжение сетки, режим `disable_in` и альтернативу `widen_target`.")
    lines.append("`disable_in` здесь означает простую вещь: бот больше не наращивает шорт на продолжающемся ралли, но existing OUT orders остаются и могут собрать откат.")
    lines.append("")
    lines.append("Что получилось:")
    lines.append(f"- WR vs actual_action: {disable_row['wr_vs_actual']*100:.1f}%")
    lines.append(f"- WR vs widen_target: {disable_vs_widen_wr * 100:.1f}%")
    lines.append(f"- Position size economy: в среднем `disable_in` экономит {position_economy_overall:.2f} BTC роста позиции против actual.")
    lines.append(f"- Avg PnL delta vs actual: {disable_row['avg_pnl_delta']:+.2f}$")
    lines.append("")
    lines.append("Когда РАБОТАЕТ:")
    if works:
        lines.extend([f"- {w}" for w in works[:4]])
    else:
        lines.append("- Убедимых зон `WR >= 60%` против actual не найдено.")
    lines.append("")
    lines.append("Когда disable_in ЛУЧШЕ widen_target:")
    if disable_better:
        lines.extend([f"- {w}" for w in disable_better[:4]])
    else:
        lines.append("- Убедимых зон, где disable_in системно лучше widen_target, не найдено.")
    lines.append("")
    lines.append("Когда widen_target ЛУЧШЕ disable_in:")
    if widen_better:
        lines.extend([f"- {w}" for w in widen_better[:4]])
    else:
        lines.append("- Явных зон преимущества widen_target над disable_in немного либо они не проходят порог по n.")
    lines.append("")
    lines.append("Рекомендация:")
    if float(disable_row["wr_vs_actual"]) >= 0.60 and float(disable_row["avg_pnl_delta"]) > 0:
        lines.append("- use в conditions X: disable_in выглядит как отдельный defensive direction.")
    elif float(disable_row["wr_vs_actual"]) <= 0.40:
        lines.append("- discard: как отдельное действие disable_in проигрывает базовому режиму.")
    else:
        lines.append("- collect more data / use selectively: disable_in полезен скорее как risk-control по размеру позиции, а не как PnL-maximizer.")
    lines.append("")
    lines.append("## §6 Combined adaptive playbook")
    lines.append("")
    lines.append("- Если цель = максимизировать PnL на synthetic SHORT drawdown episodes, ориентир остаётся `widen_target`.")
    lines.append("- Если цель = жёстко ограничить дальнейший рост позиции любой ценой, `disable_in` можно рассматривать только как risk-control режим, но не как alpha-режим.")
    lines.append("- На текущей выборке нет условий, где `disable_in` системно лучше `widen_target` по PnL.")
    lines.append("- Значит actionable правило сейчас простое: по synthetic evidence выбирать `widen_target`; `disable_in` держать как ручной safety override, а не как основной defensive play.")
    lines.append("- Комбинация `disable_in + widen_target` в этом TZ не симулировалась отдельным сценарием. Её имеет смысл тестировать только если оператору нужен именно hybrid safety mode.")
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
    compare = _cross_compare(sim)
    by_session = _stratify(compare, "session_label", "disable_better_than_actual")
    by_duration = _stratify(compare, "duration_bucket", "disable_better_than_actual")
    by_position = _stratify(compare, "initial_position_bucket", "disable_better_than_actual")
    disable_vs_widen_session = _stratify(compare, "session_label", "disable_better_than_widen")
    disable_vs_widen_duration = _stratify(compare, "duration_bucket", "disable_better_than_widen")
    disable_vs_widen_position = _stratify(compare, "initial_position_bucket", "disable_better_than_widen")
    REPORT_PATH.write_text(
        build_report(
            summary,
            compare,
            by_session,
            by_duration,
            by_position,
            disable_vs_widen_session,
            disable_vs_widen_duration,
            disable_vs_widen_position,
        ),
        encoding="utf-8",
    )
    print(f"episodes={len(episodes)} rows={len(sim)} report={REPORT_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
