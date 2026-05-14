from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DECISIONS_PATH = ROOT / "data" / "operator_journal" / "decisions.parquet"
SNAPSHOTS_PATH = ROOT / "ginarea_live" / "snapshots.csv"
PARAMS_PATH = ROOT / "ginarea_live" / "params.csv"
ICT_PATH = ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"
MANUAL_DECISIONS_PATH = ROOT / "data" / "operator_journal" / "manual_decisions.jsonl"
REPORT_PATH = ROOT / "reports" / "defensive_actions_research_v2_real_snapshots_2026-05-02.md"

SIDE_MAP = {1: "long", 2: "short"}
PROVEN_WR = 0.60
ANTI_WR = 0.40
MIN_PATTERN_N = 10
KEYWORDS = ("exhaustion", "продажи", "resistance", "пятница", "макро", "displacement", "breakout", "ob")


@dataclass(slots=True)
class BotState:
    ts: pd.Timestamp
    bot_id: str
    alias: str | None
    side: str | None
    position: float
    average_price: float
    current_profit: float
    realized_profit: float


def _load_decisions() -> pd.DataFrame:
    df = pd.read_parquet(DECISIONS_PATH).copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df.sort_values(["ts", "bot_id", "field"]).reset_index(drop=True)


def _load_snapshots() -> pd.DataFrame:
    df = pd.read_csv(SNAPSHOTS_PATH)
    df["ts"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).copy()
    df["bot_id"] = pd.to_numeric(df["bot_id"], errors="coerce").astype("Int64").astype(str)
    for col in ("position", "profit", "current_profit", "average_price", "liquidation_price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["bot_id", "ts"]).reset_index(drop=True)


def _load_params() -> pd.DataFrame:
    df = pd.read_csv(PARAMS_PATH)
    df["ts"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).copy()
    df["bot_id"] = df["bot_id"].astype(str)
    df["side"] = pd.to_numeric(df["side"], errors="coerce")
    return df.sort_values(["bot_id", "ts"]).reset_index(drop=True)


def _load_market() -> pd.DataFrame:
    df = pd.read_parquet(ICT_PATH).copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("ICT parquet must have DatetimeIndex")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df.sort_index()
    out = df[["close", "session_active", "dist_to_pdh_pct", "dist_to_nearest_unmitigated_high_pct"]].copy()
    out["roc_1h_pct"] = out["close"].pct_change(60) * 100.0
    out["roc_4h_pct"] = out["close"].pct_change(240) * 100.0
    out["roc_24h_pct"] = out["close"].pct_change(1440) * 100.0
    out["atr_1h"] = (
        df["high"].sub(df["low"]).rolling(60, min_periods=20).mean()
    )
    out["atr_4h"] = (
        df["high"].sub(df["low"]).rolling(240, min_periods=60).mean()
    )
    delta = out["close"].diff()
    gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_1h"] = 100 - (100 / (1 + rs))
    return out


def _latest_before(group: pd.DataFrame, ts: pd.Timestamp) -> pd.Series | None:
    subset = group[group["ts"] <= ts]
    if subset.empty:
        return None
    return subset.iloc[-1]


def _path_until(group: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    subset = group[(group["ts"] >= start) & (group["ts"] <= end)].copy()
    return subset.sort_values("ts")


def _infer_category(row: pd.Series, side: str | None) -> str:
    field = str(row["field"])
    old_value = row["old_value"]
    new_value = row["new_value"]
    if field == "state":
        old_s = str(old_value)
        new_s = str(new_value)
        if old_s == "running" and new_s == "stopped":
            if side == "long":
                return "close_long"
            if side == "short":
                return "close_short"
            return "other"
        if old_s == "running" and new_s == "paused":
            return "pause"
        if old_s in {"paused", "stopped"} and new_s == "running":
            return "resume"
        return "other"
    if field == "border_top":
        try:
            return "raise_boundary" if float(new_value) > float(old_value) else "other"
        except Exception:
            return "other"
    if field == "border_bottom":
        try:
            if float(new_value) < float(old_value):
                return "lower_boundary"
            if float(new_value) > float(old_value):
                return "raise_boundary"
        except Exception:
            pass
        return "other"
    if field == "target":
        return "change_target"
    if field == "order_size":
        return "change_size"
    return "other"


def _regime_bucket(roc_24h: float | None) -> str:
    if roc_24h is None or (isinstance(roc_24h, float) and math.isnan(roc_24h)):
        return "unknown"
    if roc_24h >= 2.0:
        return "trend_up_strong"
    if roc_24h > 0.0:
        return "trend_up_mild"
    if roc_24h <= -2.0:
        return "trend_down_strong"
    if roc_24h < 0.0:
        return "trend_down_mild"
    return "flat"


def _dd_profile(unrealized: float | None, liq_distance_pct: float | None) -> str:
    if unrealized is None or pd.isna(unrealized):
        return "unknown"
    if liq_distance_pct is not None and not pd.isna(liq_distance_pct) and liq_distance_pct < 15.0:
        return "liq_risk"
    if unrealized < 0:
        return "in_drawdown"
    return "in_profit_or_flat"


def _inverse_pnl(position: float, entry_price: float, future_price: float, side: str) -> float:
    if position == 0 or entry_price <= 0 or future_price <= 0:
        return 0.0
    qty = abs(position)
    if side == "short":
        return qty * (1.0 / future_price - 1.0 / entry_price)
    return qty * (1.0 / entry_price - 1.0 / future_price)


def _calibration_factor(state: BotState, current_price: float) -> float:
    theoretical = _inverse_pnl(state.position, state.average_price, current_price, state.side or "short")
    if abs(theoretical) < 1e-12:
        return 1.0
    factor = state.current_profit / theoretical
    if not math.isfinite(factor) or abs(factor) > 1000:
        return 1.0
    return factor


def _mark_to_market_delta(
    state: BotState,
    current_price: float,
    future_price: float,
    factor: float,
    hold_fraction: float,
) -> float:
    future_unreal = factor * _inverse_pnl(state.position * hold_fraction, state.average_price, future_price, state.side or "short")
    current_unreal = state.current_profit * hold_fraction
    return future_unreal - current_unreal


def _mark_to_market_path(
    market_path: pd.DataFrame,
    state: BotState,
    current_price: float,
    factor: float,
    hold_fraction: float,
) -> tuple[float, float | None]:
    deltas: list[float] = []
    recovery_h: float | None = None
    start_ts = market_path.index[0] if not market_path.empty else None
    for ts, row in market_path.iterrows():
        delta = _mark_to_market_delta(state, current_price, float(row["close"]), factor, hold_fraction)
        deltas.append(delta)
        if recovery_h is None and delta >= 0 and start_ts is not None:
            recovery_h = (ts - start_ts).total_seconds() / 3600.0
    if not deltas:
        return 0.0, None
    return float(min(deltas)), recovery_h


def _observed_path(snapshot_path: pd.DataFrame, base_total: float) -> tuple[float, float | None]:
    if snapshot_path.empty:
        return 0.0, None
    deltas = snapshot_path["profit"].fillna(0.0) + snapshot_path["current_profit"].fillna(0.0) - base_total
    recovery_h: float | None = None
    start_ts = pd.Timestamp(snapshot_path["ts"].iloc[0])
    for ts, delta in zip(snapshot_path["ts"], deltas):
        if recovery_h is None and float(delta) >= 0:
            recovery_h = (pd.Timestamp(ts) - start_ts).total_seconds() / 3600.0
    return float(deltas.min()), recovery_h


def _resolve_bot_state(decision: pd.Series, snapshots_by_bot: dict[str, pd.DataFrame], params_by_bot: dict[str, pd.DataFrame]) -> BotState | None:
    bot_id = str(decision["bot_id"])
    snap_group = snapshots_by_bot.get(bot_id)
    if snap_group is None:
        return None
    snap = _latest_before(snap_group, pd.Timestamp(decision["ts"]))
    if snap is None:
        return None
    params_group = params_by_bot.get(bot_id)
    params = _latest_before(params_group, pd.Timestamp(decision["ts"])) if params_group is not None else None
    alias = decision.get("alias")
    if (alias is None or pd.isna(alias)) and params is not None:
        alias = params.get("alias")
    side = None
    if params is not None and pd.notna(params.get("side")):
        side = SIDE_MAP.get(int(params["side"]))
    return BotState(
        ts=pd.Timestamp(snap["ts"]),
        bot_id=bot_id,
        alias=None if alias is None or pd.isna(alias) else str(alias),
        side=side,
        position=float(snap.get("position") or 0.0),
        average_price=float(snap.get("average_price") or 0.0),
        current_profit=float(snap.get("current_profit") or 0.0),
        realized_profit=float(snap.get("profit") or 0.0),
    )


def _future_price(market: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    subset = market[market.index <= ts]
    if subset.empty:
        return None
    return float(subset["close"].iloc[-1])


def _simulate_one(
    decision: pd.Series,
    state: BotState,
    market: pd.DataFrame,
    snapshots_by_bot: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    current_price = _future_price(market, pd.Timestamp(decision["ts"]))
    if current_price is None:
        return []
    factor = _calibration_factor(state, current_price)
    bot_group = snapshots_by_bot[state.bot_id]
    base_total = state.realized_profit + state.current_profit
    category = str(decision["action_category"])

    rows: list[dict[str, Any]] = []
    for label, hours in (("1h", 1), ("4h", 4), ("24h", 24)):
        end_ts = pd.Timestamp(decision["ts"]) + pd.Timedelta(hours=hours)
        future_price = _future_price(market, end_ts)
        if future_price is None:
            continue
        market_path = market[(market.index >= pd.Timestamp(decision["ts"])) & (market.index <= end_ts)][["close"]]
        snapshot_path = _path_until(bot_group, pd.Timestamp(decision["ts"]), end_ts)
        actual_delta = 0.0
        if not snapshot_path.empty:
            final_row = snapshot_path.iloc[-1]
            actual_delta = float(final_row["profit"] + final_row["current_profit"] - base_total)
        actual_max_dd, actual_recovery_h = _observed_path(snapshot_path, base_total)

        do_nothing_delta = _mark_to_market_delta(state, current_price, future_price, factor, 1.0)
        do_nothing_max_dd, do_nothing_recovery_h = _mark_to_market_path(market_path, state, current_price, factor, 1.0)

        emergency_close_delta = 0.0
        emergency_max_dd = 0.0
        emergency_recovery_h = 0.0

        if category in {"close_long", "close_short"}:
            opposite_delta = do_nothing_delta
            opposite_max_dd = do_nothing_max_dd
            opposite_recovery_h = do_nothing_recovery_h
            partial_delta = _mark_to_market_delta(state, current_price, future_price, factor, 0.75)
            partial_max_dd, partial_recovery_h = _mark_to_market_path(market_path, state, current_price, factor, 0.75)
        else:
            opposite_delta = do_nothing_delta
            opposite_max_dd = do_nothing_max_dd
            opposite_recovery_h = do_nothing_recovery_h
            partial_delta = (actual_delta + do_nothing_delta) / 2.0
            partial_max_dd = min(actual_max_dd, do_nothing_max_dd) / 2.0
            partial_recovery_h = None

        rows.extend(
            [
                _alt_row(decision, state, label, "actual_action", actual_delta, actual_max_dd, actual_recovery_h, do_nothing_delta),
                _alt_row(decision, state, label, "do_nothing", do_nothing_delta, do_nothing_max_dd, do_nothing_recovery_h, do_nothing_delta),
                _alt_row(decision, state, label, "opposite_action", opposite_delta, opposite_max_dd, opposite_recovery_h, do_nothing_delta),
                _alt_row(decision, state, label, "partial_action", partial_delta, partial_max_dd, partial_recovery_h, do_nothing_delta),
                _alt_row(decision, state, label, "emergency_close", emergency_close_delta, emergency_max_dd, emergency_recovery_h, do_nothing_delta),
            ]
        )
    return rows


def _alt_row(
    decision: pd.Series,
    state: BotState,
    horizon: str,
    alternative: str,
    pnl_delta: float,
    max_dd: float,
    recovery_h: float | None,
    baseline_delta: float,
) -> dict[str, Any]:
    return {
        "decision_ts": pd.Timestamp(decision["ts"]),
        "bot_id": state.bot_id,
        "alias": state.alias,
        "side": state.side,
        "action_category": decision["action_category"],
        "alternative": alternative,
        "horizon": horizon,
        "pnl_delta": pnl_delta,
        "pnl_delta_vs_do_nothing": pnl_delta - baseline_delta,
        "max_dd_during_horizon": max_dd,
        "recovery_time_hours": recovery_h,
        "session_active": decision["session_active"],
        "roc_24h_pct": decision["roc_24h_pct"],
        "regime_bucket": decision["regime_bucket"],
        "dd_profile": decision["dd_profile"],
        "dist_to_pdh_pct": decision["dist_to_pdh_pct"],
        "dist_to_nearest_unmitigated_high_pct": decision["dist_to_nearest_unmitigated_high_pct"],
    }


def _attach_real_context(decisions: pd.DataFrame, market: pd.DataFrame, snapshots: pd.DataFrame, params: pd.DataFrame) -> pd.DataFrame:
    out = decisions.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)

    params_meta = params[["ts", "bot_id", "alias", "side"]].sort_values(["bot_id", "ts"])
    snapshots_meta = snapshots[["ts", "bot_id", "alias"]].sort_values(["bot_id", "ts"])
    out["bot_id"] = out["bot_id"].astype(str)

    alias_by_bot = params_meta.dropna(subset=["alias"]).groupby("bot_id").tail(1)[["bot_id", "alias"]]
    alias_lookup = alias_by_bot.set_index("bot_id")["alias"].to_dict()
    out["alias"] = out["alias"].where(out["alias"].notna(), out["bot_id"].map(alias_lookup))

    market_reset = market.rename_axis("market_ts").reset_index()
    out = pd.merge_asof(out.sort_values("ts"), market_reset.sort_values("market_ts"), left_on="ts", right_on="market_ts", direction="backward")
    rename_map = {
        "close": "market_price",
        "session_active_y": "session_active",
        "dist_to_pdh_pct_y": "dist_to_pdh_pct_live",
        "dist_to_nearest_unmitigated_high_pct_y": "dist_to_nearest_unmitigated_high_pct_live",
        "roc_1h_pct_y": "roc_1h_pct_live",
        "roc_4h_pct_y": "roc_4h_pct_live",
        "atr_1h_y": "atr_1h_live",
        "rsi_1h_y": "rsi_1h_live",
    }
    out = out.rename(columns=rename_map)
    out["price"] = out["market_price"].where(out["market_price"].notna(), out["price"])
    out["session_active"] = out["session_active"].where(out["session_active"].notna(), out.get("session_active_x"))
    out["dist_to_pdh_pct"] = out["dist_to_pdh_pct_live"].where(out["dist_to_pdh_pct_live"].notna(), out.get("dist_to_pdh_pct_x"))
    out["dist_to_nearest_unmitigated_high_pct"] = out["dist_to_nearest_unmitigated_high_pct_live"].where(
        out["dist_to_nearest_unmitigated_high_pct_live"].notna(),
        out.get("dist_to_nearest_unmitigated_high_pct_x"),
    )
    out["roc_1h_pct"] = out["roc_1h_pct_live"].where(out["roc_1h_pct_live"].notna(), out.get("roc_1h_pct_x"))
    out["roc_4h_pct"] = out["roc_4h_pct_live"].where(out["roc_4h_pct_live"].notna(), out.get("roc_4h_pct_x"))
    out["atr_1h"] = out["atr_1h_live"].where(out["atr_1h_live"].notna(), out.get("atr_1h_x"))
    out["rsi_1h"] = out["rsi_1h_live"].where(out["rsi_1h_live"].notna(), out.get("rsi_1h_x"))

    side_map = (
        params_meta.dropna(subset=["side"])
        .groupby("bot_id")
        .tail(1)[["bot_id", "side"]]
        .assign(side_label=lambda d: d["side"].astype(int).map(SIDE_MAP))
    )
    out = out.merge(side_map[["bot_id", "side_label"]], on="bot_id", how="left")
    out["action_category"] = out.apply(lambda row: _infer_category(row, row.get("side_label")), axis=1)
    out["regime_bucket"] = out["roc_24h_pct"].apply(_regime_bucket)
    out["dd_profile"] = out.apply(lambda row: _dd_profile(row.get("unrealized_pnl"), row.get("distance_to_liq_pct")), axis=1)
    return out


def _aggregate(actual_rows: pd.DataFrame) -> pd.DataFrame:
    summary = (
        actual_rows[actual_rows["horizon"] == "24h"]
        .groupby("action_category")
        .agg(
            n=("action_category", "size"),
            wr_vs_baseline=("pnl_delta_vs_do_nothing", lambda s: float((s > 0).mean()) if len(s) else np.nan),
            avg_delta_usd=("pnl_delta_vs_do_nothing", "mean"),
            median_delta_usd=("pnl_delta_vs_do_nothing", "median"),
            q25_delta_usd=("pnl_delta_vs_do_nothing", lambda s: float(s.quantile(0.25))),
            q75_delta_usd=("pnl_delta_vs_do_nothing", lambda s: float(s.quantile(0.75))),
        )
        .reset_index()
        .sort_values(["wr_vs_baseline", "n"], ascending=[False, False])
    )
    return summary


def _cross_table(actual_rows: pd.DataFrame, dim: str) -> pd.DataFrame:
    grouped = (
        actual_rows[actual_rows["horizon"] == "24h"]
        .groupby(["action_category", dim])
        .agg(
            n=("action_category", "size"),
            wr=("pnl_delta_vs_do_nothing", lambda s: float((s > 0).mean()) if len(s) else np.nan),
            avg_delta=("pnl_delta_vs_do_nothing", "mean"),
        )
        .reset_index()
        .sort_values(["action_category", "wr"], ascending=[True, False])
    )
    return grouped


def _extract_patterns(actual_rows: pd.DataFrame) -> list[dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    for dim in ("session_active", "regime_bucket", "dd_profile"):
        g = _cross_table(actual_rows, dim)
        if g.empty:
            continue
        g = g.rename(columns={dim: "value"})
        g["dimension"] = dim
        frames.append(g)
    if not frames:
        return []
    all_groups = pd.concat(frames, ignore_index=True)
    all_groups = all_groups[all_groups["n"] >= MIN_PATTERN_N].copy()
    patterns: list[dict[str, Any]] = []
    for _, row in all_groups.iterrows():
        wr = float(row["wr"])
        avg_delta = float(row["avg_delta"])
        if abs(avg_delta) < 1e-9:
            continue
        if wr >= PROVEN_WR:
            status = "proven pattern"
        elif wr <= ANTI_WR:
            status = "anti-pattern"
        else:
            continue
        expr = f"action_category == '{row['action_category']}' and {row['dimension']} == '{row['value']}'"
        patterns.append(
            {
                "action_category": row["action_category"],
                "dimension": row["dimension"],
                "value": row["value"],
                "n": int(row["n"]),
                "wr": wr,
                "avg_delta": avg_delta,
                "status": status,
                "detector_name": f"DEFENSIVE_{str(row['action_category']).upper()}_{str(row['value']).upper()}".replace("-", "_"),
                "expr": expr,
            }
        )
    patterns.sort(key=lambda x: (0 if x["status"] == "proven pattern" else 1, -x["wr"] if x["status"] == "proven pattern" else x["wr"]))
    return patterns


def _render_table(df: pd.DataFrame, columns: list[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for _, row in df.iterrows():
        vals: list[str] = []
        for col in columns:
            value = row[col]
            if isinstance(value, float):
                if "wr" in col:
                    vals.append(f"{value * 100:.1f}%")
                else:
                    vals.append(f"{value:.2f}")
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _manual_keyword_section() -> str:
    if not MANUAL_DECISIONS_PATH.exists():
        return "Skipped: `manual_decisions.jsonl` absent.\n"
    rows: list[dict[str, Any]] = []
    with MANUAL_DECISIONS_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if len(rows) < 5:
        return f"Skipped: only {len(rows)} manual decisions available (<5).\n"
    counts = {kw: 0 for kw in KEYWORDS}
    for row in rows:
        text = str(row.get("notes") or "").lower()
        for kw in KEYWORDS:
            if kw.lower() in text:
                counts[kw] += 1
    body = ["Keyword counts from manual notes:"]
    for kw, count in counts.items():
        body.append(f"- `{kw}`: {count}")
    return "\n".join(body) + "\n"


def build_report(summary: pd.DataFrame, session_cross: pd.DataFrame, regime_cross: pd.DataFrame, dd_cross: pd.DataFrame, patterns: list[dict[str, Any]], v1_summary: str) -> str:
    lines: list[str] = []
    lines.append("# Defensive Actions Research V2 — Real Snapshots")
    lines.append("")
    lines.append("## §1 Methodology")
    lines.append("")
    lines.append("- Source episodes: all 71 records from `data/operator_journal/decisions.parquet`.")
    lines.append("- Real bot state comes from tracker snapshots (`ginarea_live/snapshots.csv`) and params history (`ginarea_live/params.csv`).")
    lines.append("- Market / ICT context is re-attached from `data/ict_levels/BTCUSDT_ict_levels_1m.parquet`, because the original extractor used stale frozen market data once tracker crossed frozen coverage.")
    lines.append("- `actual_action` uses observed account-value path per bot: `profit + current_profit` over 1h/4h/24h after the decision.")
    lines.append("- `do_nothing`, `partial_action`, and `emergency_close` are counterfactual mark-to-market proxies from the pre-decision state. For non-close decisions this is a static-hold baseline, not a full future fill simulation.")
    lines.append("- This is honest real-history evidence, but not a full bot-execution replay. Findings should be treated as operator-behavior extraction, not exact execution attribution.")
    lines.append("")
    lines.append("## §2 Per-category aggregation")
    lines.append("")
    lines.append(_render_table(summary, ["action_category", "n", "wr_vs_baseline", "avg_delta_usd", "median_delta_usd", "q25_delta_usd", "q75_delta_usd"]))
    lines.append("")
    lines.append("## §3 ICT/session/regime stratification")
    lines.append("")
    lines.append("By session:")
    lines.append(_render_table(session_cross, ["action_category", "session_active", "n", "wr", "avg_delta"]))
    lines.append("")
    lines.append("By regime:")
    lines.append(_render_table(regime_cross, ["action_category", "regime_bucket", "n", "wr", "avg_delta"]))
    lines.append("")
    lines.append("By position state:")
    lines.append(_render_table(dd_cross, ["action_category", "dd_profile", "n", "wr", "avg_delta"]))
    lines.append("")
    lines.append("## §4 Operator patterns")
    lines.append("")
    if not patterns:
        lines.append("No proven patterns and no anti-patterns met the threshold (`n>=10`, `WR>=60%` or `WR<=40%`) at current sample size.")
    else:
        for pat in patterns:
            lines.append(
                f"- `{pat['status']}`: `{pat['action_category']}` when `{pat['dimension']}={pat['value']}` "
                f"won {pat['wr']*100:.1f}% with `n={pat['n']}` and `avg_delta={pat['avg_delta']:+.2f}`."
            )
    lines.append("")
    lines.append("## §5 V1 vs V2 comparison")
    lines.append("")
    lines.append(v1_summary)
    lines.append("")
    lines.append("Main read-through:")
    lines.append("- V1 synthetic research found no strong edge in partial close / hold / counter-hedge; V2 real snapshots should be used as the higher-priority evidence layer.")
    lines.append("- If V2 also fails to produce `WR>=60%` patterns at `n>=10`, the honest conclusion is that current operator behavior is still below rule-extraction quality for productization.")
    lines.append("- `EMERGENCY_CLOSE` stayed the most promising family conceptually, but V2 only validates it if real stop/close categories show edge against mark-to-market hold.")
    lines.append("")
    lines.append("## §6 Recommended trigger conditions")
    lines.append("")
    proven_patterns = [p for p in patterns if p["status"] == "proven pattern"]
    if not proven_patterns:
        lines.append("No proven patterns at current sample size. Recommended handoff: keep collecting decisions, improve state labeling, and only productize after a category or subgroup crosses `n>=10` and `WR>=60%`.")
    else:
        for pat in proven_patterns:
            lines.append(f"### {pat['detector_name']}")
            lines.append("")
            lines.append(f"- Trigger: `{pat['expr']}`")
            lines.append(f"- Expected WR: {pat['wr']*100:.1f}%")
            lines.append(f"- Avg PnL delta vs do_nothing: {pat['avg_delta']:+.2f}")
            lines.append(f"- Sample: n={pat['n']}")
            lines.append(f"- Combo-filter stratification seed: `{pat['dimension']}={pat['value']}`")
            lines.append("")
    lines.append("## §7 Confidence assessment")
    lines.append("")
    lines.append("| category_or_pattern | assessment | rationale |")
    lines.append("|---|---|---|")
    for _, row in summary.iterrows():
        wr = float(row["wr_vs_baseline"])
        n = int(row["n"])
        avg_delta = float(row["avg_delta_usd"])
        iqr = float(row["q75_delta_usd"] - row["q25_delta_usd"])
        if abs(avg_delta) < 1e-9 and abs(iqr) < 1e-9:
            assessment = "non-informative"
            rationale = "no measurable exposure change in sampled episodes"
        elif n < MIN_PATTERN_N:
            assessment = "needs more data"
            rationale = f"n={n} < {MIN_PATTERN_N}"
        elif wr >= PROVEN_WR:
            assessment = "production-ready"
            rationale = f"WR {wr*100:.1f}%"
        elif wr <= ANTI_WR:
            assessment = "anti-pattern"
            rationale = f"WR {wr*100:.1f}%"
        else:
            assessment = "inconclusive"
            rationale = f"WR {wr*100:.1f}% around noise band"
        lines.append(f"| {row['action_category']} | {assessment} | {rationale} |")
    lines.append("")
    lines.append("## §8 Caveats")
    lines.append("")
    lines.append("- Single asset: BTC only.")
    lines.append("- Sample is still very small: 71 decision records total, and several categories are much smaller.")
    lines.append("- Counterfactuals for non-close actions are static-hold proxies, not a full multi-bot order replay.")
    lines.append("- Several early decisions have missing alias labeling in the extracted parquet; v2 re-attaches alias/side from params history where possible.")
    lines.append("- Manual decision text mining was optional and is currently limited.")
    lines.append("")
    lines.append("## Optional Notes Mining")
    lines.append("")
    lines.append(_manual_keyword_section())
    return "\n".join(lines)


def main() -> None:
    decisions = _load_decisions()
    snapshots = _load_snapshots()
    params = _load_params()
    market = _load_market()

    decisions = _attach_real_context(decisions, market, snapshots, params)
    snapshots_by_bot = {bot_id: group.copy() for bot_id, group in snapshots.groupby("bot_id", sort=False)}
    params_by_bot = {bot_id: group.copy() for bot_id, group in params.groupby("bot_id", sort=False)}

    rows: list[dict[str, Any]] = []
    processed = 0
    for _, decision in decisions.iterrows():
        state = _resolve_bot_state(decision, snapshots_by_bot, params_by_bot)
        if state is None:
            continue
        processed += 1
        rows.extend(_simulate_one(decision, state, market, snapshots_by_bot))

    sim = pd.DataFrame(rows)
    actual = sim[sim["alternative"] == "actual_action"].copy()
    summary = _aggregate(actual)
    session_cross = _cross_table(actual, "session_active")
    regime_cross = _cross_table(actual, "regime_bucket")
    dd_cross = _cross_table(actual, "dd_profile")
    patterns = _extract_patterns(actual)

    v1_summary = (
        "- V1 synthetic results: `PARTIAL_CLOSE_ON_RETRACE` 51.0% WR (`n=577`), `HOLD_THROUGH_NOISE` 50.6% (`n=421`), "
        "`COUNTER_HEDGE_ON_DD` 48.0% (`n=354`), `EMERGENCY_CLOSE` 63.6% but only `n=11`.\n"
        "- V2 re-centers the question on real operator behavior from tracker snapshots rather than synthetic basket states."
    )
    report = build_report(summary, session_cross, regime_cross, dd_cross, patterns, v1_summary)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"processed_decisions={processed} simulated_rows={len(sim)} report={REPORT_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
