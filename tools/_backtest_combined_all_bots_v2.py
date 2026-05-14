"""B2 v2: Combined vs baseline — per-window honest analysis.

Прошлая версия (_backtest_combined_all_bots.py) показывала средние DD=$0 для
большинства ботов и создавала впечатление что combined не работает. Причина:
средние сглаживают редкие плохие окна где combined реально помогает.

V2 показывает:
  - **per-window delta**: разница combined - baseline по каждому окну
  - **worst-case** окна для каждого бота (где combined важен)
  - **interventions count** per window (если 0 — combined не сработал, окно спокойное)
  - **decision matrix**: бот → wins / losses / неутрально по окнам

Чтобы решение «мигрировать или нет» строилось на **поведении в плохие моменты**,
а не на «среднем» через спокойные периоды.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import os as _os
sys.path.insert(0, _os.environ.get("CODEX_SRC",
    r"C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src"))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
PARAMS_CSV = ROOT / "ginarea_live" / "params.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "COMBINED_ALL_BOTS_V2.md"
OUT_CSV = ROOT / "state" / "combined_all_bots_v2.csv"

BOTS = {
    "5196832375": "TEST_1",
    "5017849873": "TEST_2",
    "4524162672": "TEST_3",
    "5188321731": "ШОРТ-ОБЪЁМ",
    "6399265299": "GPT_SHORT_1.1%",
    "5773124036": "ЛОНГ-ОБЪЁМ",
    "5154651487": "ЛОНГ-ХЕДЖ",
}


def load_bot_config(bot_id: str) -> dict | None:
    df = pd.read_csv(PARAMS_CSV)
    df["bot_id"] = df["bot_id"].astype(str).str.replace(".0", "", regex=False)
    sub = df[df["bot_id"] == bot_id].sort_values("ts_utc")
    if sub.empty:
        return None
    last = sub.iloc[-1]
    raw = json.loads(last["raw_params_json"])
    side_int = raw.get("side")
    side_name = "long" if side_int == 1 else "short"
    contract_type = "inverse" if side_int == 1 else "linear"
    order_size = float(raw.get("q", {}).get("minQ", 0.001) or 0.001)
    ind_thr = 0.3
    ind_period = 30
    in_block = raw.get("in", {}) or {}
    start = in_block.get("start", {}) or {}
    cnds = start.get("cnds", []) or []
    if cnds and cnds[0].get("items"):
        item = cnds[0]["items"][0]
        ind_thr = float(item.get("p", 0.3))
        params = cnds[0].get("params", {}) or {}
        ind_period = int(params.get("d", 30))
    border = raw.get("border", {}) or {}
    bottom = border.get("bottom") if border else None
    top = border.get("top") if border else None
    return {
        "bot_id": bot_id,
        "alias": str(last.get("alias", bot_id)),
        "side": side_name,
        "contract_type": contract_type,
        "order_size": order_size,
        "order_count": int(raw.get("maxOp", 200)),
        "grid_step_pct": float(raw.get("gs", 0.03)),
        "target_profit_pct": float(raw.get("gap", {}).get("tog", 0.25)),
        "min_stop_pct": float(raw.get("gap", {}).get("minS", 0.01)),
        "max_stop_pct": float(raw.get("gap", {}).get("maxS", 0.04)),
        "instop_pct": float(raw.get("gap", {}).get("isg", 0.0)),
        "boundaries_lower": 0.0 if bottom is None else float(bottom),
        "boundaries_upper": 0.0 if top is None else float(top),
        "indicator_period": ind_period,
        "indicator_threshold_pct": ind_thr,
        "dsblin": bool(raw.get("dsblin", False)),
        "leverage": 100,
    }


def make_intervention_rules(scenario: str) -> list:
    from services.managed_grid_sim.intervention_rules import (
        PauseEntriesOnUnrealizedThreshold, ResumeEntriesOnPullback,
        PartialUnloadOnRetracement, RaiseBoundaryOnConfirmedTrend,
    )
    if scenario == "baseline":
        return []
    rules = [
        PauseEntriesOnUnrealizedThreshold(
            unrealized_threshold_pct_of_depo=-30.0, hold_time_minutes=5),
        ResumeEntriesOnPullback(
            pullback_from_peak_pct=50.0, hold_minutes_after_peak=10),
        PartialUnloadOnRetracement(
            unrealized_pct_threshold=5.0, retracement_from_peak_pct=40.0,
            unload_fraction=0.3),
        RaiseBoundaryOnConfirmedTrend(
            delta_1h_threshold_pct=0.5, hold_above_boundary_minutes=30,
            new_boundary_offset_pct=2.0),
    ]
    return rules


def load_bars_window(start_idx: int, n_bars: int) -> list:
    from backtest_lab.engine_v2.bot import OHLCBar
    df = pd.read_csv(DATA_1M)
    sub = df.iloc[start_idx:start_idx + n_bars]
    bars = []
    for _, r in sub.iterrows():
        ts = pd.Timestamp(r["ts"] / 1000, unit="s", tz="UTC")
        bars.append(OHLCBar(
            ts=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]),
            volume=float(r["volume"]),
        ))
    return bars


def run_scenario(cfg: dict, bars: list, scenario: str) -> dict:
    from services.managed_grid_sim import ManagedGridSimRunner, ManagedRunConfig
    from services.managed_grid_sim.regime_classifier import RegimeClassifier

    runner = ManagedGridSimRunner()
    rc = RegimeClassifier()
    rules = make_intervention_rules(scenario)
    run_cfg = ManagedRunConfig(
        bot_configs=[cfg], bars=bars, intervention_rules=rules,
        regime_classifier=rc, run_id=f"v2_{scenario}",
        strict_mode=False,
    )
    try:
        result = runner.run(run_cfg)
    except Exception as exc:
        return {"error": str(exc), "scenario": scenario}
    fees = result.total_volume_usd * 0.00019 * 2
    return {
        "scenario": scenario,
        "realized_net": round(result.final_realized_pnl_usd - fees, 2),
        "unrealized": round(result.final_unrealized_pnl_usd, 2),
        "volume": round(result.total_volume_usd, 0),
        "trades": result.total_trades,
        "max_dd_usd": round(result.max_drawdown_usd, 2),
        "interventions": result.total_interventions,
    }


def main() -> int:
    df = pd.read_csv(DATA_1M)
    print(f"[combined-all-v2] frozen 1m: {len(df):,} bars")
    bars_per_week = 7 * 24 * 60
    n_windows = 11

    all_windows = []
    for w in range(n_windows):
        end_idx = len(df) - w * bars_per_week
        start_idx = max(0, end_idx - bars_per_week)
        if start_idx == 0:
            break
        all_windows.append((w + 1, start_idx, end_idx))

    print(f"[combined-all-v2] {len(all_windows)} окон × 7 дней")
    print(f"[combined-all-v2] {len(BOTS)} ботов\n")

    all_runs: list[dict] = []
    for bot_id, alias in BOTS.items():
        cfg = load_bot_config(bot_id)
        if cfg is None:
            continue
        print(f"=== {alias} ({cfg['side']}, {cfg['contract_type']}) ===")
        for w, start_idx, end_idx in all_windows:
            bars = load_bars_window(start_idx, bars_per_week)
            base = run_scenario(cfg, bars, "baseline")
            comb = run_scenario(cfg, bars, "combined")
            if "error" in base or "error" in comb:
                continue
            row = {
                "bot": alias, "bot_id": bot_id, "side": cfg["side"], "window": w,
                "base_vol": base["volume"], "comb_vol": comb["volume"],
                "base_dd": base["max_dd_usd"], "comb_dd": comb["max_dd_usd"],
                "base_net": base["realized_net"], "comb_net": comb["realized_net"],
                "comb_intvs": comb["interventions"],
                "base_trades": base["trades"], "comb_trades": comb["trades"],
            }
            row["dd_delta"] = row["comb_dd"] - row["base_dd"]   # отрицательное = combined лучше
            row["vol_delta_pct"] = ((row["comb_vol"] / row["base_vol"] * 100)
                                     if row["base_vol"] > 0 else 100)
            row["net_delta"] = row["comb_net"] - row["base_net"]
            all_runs.append(row)
        # Per-bot summary
        bot_runs = [r for r in all_runs if r["bot"] == alias]
        if bot_runs:
            n_dd_improved = sum(1 for r in bot_runs if r["dd_delta"] < -10)
            n_dd_neutral = sum(1 for r in bot_runs if -10 <= r["dd_delta"] <= 10)
            n_dd_worsened = sum(1 for r in bot_runs if r["dd_delta"] > 10)
            avg_intvs = np.mean([r["comb_intvs"] for r in bot_runs])
            avg_vol_kept = np.mean([r["vol_delta_pct"] for r in bot_runs])
            print(f"  окон с улучшением DD>$10: {n_dd_improved}/{len(bot_runs)}  "
                  f"avg_intvs={avg_intvs:.0f}  avg_vol_kept={avg_vol_kept:.0f}%")

    # CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_runs).to_csv(OUT_CSV, index=False)

    # Per-window detail printed
    print(f"\n{'='*120}")
    print("PER-WINDOW DELTA: combined - baseline (только окна где combined вмешивался)")
    print(f"{'='*120}")
    print(f"{'bot':<18} {'win':<4} {'side':<6} "
          f"{'base_DD':>9} {'comb_DD':>9} {'DD_Δ':>9} "
          f"{'base_vol':>9} {'comb_vol':>9} {'vol%':>5} "
          f"{'net_Δ':>8} {'intvs':>6}")
    print("-" * 120)
    for r in all_runs:
        if r["comb_intvs"] == 0:
            continue   # combined не вмешивался — спокойное окно
        print(f"{r['bot']:<18} {r['window']:<4} {r['side']:<6} "
              f"${r['base_dd']:>+8.0f} ${r['comb_dd']:>+8.0f} ${r['dd_delta']:>+8.0f} "
              f"${r['base_vol']:>8,.0f} ${r['comb_vol']:>8,.0f} {r['vol_delta_pct']:>4.0f}% "
              f"${r['net_delta']:>+7.0f} {r['comb_intvs']:>6}")

    # Decision matrix
    print(f"\n{'='*100}")
    print("DECISION MATRIX")
    print(f"{'='*100}")
    print(f"{'bot':<20} {'side':<6} {'окон_DD>10':>11} {'окон_neutral':>13} {'окон_DD<-10':>12} "
          f"{'avg_vol_kept':>12} {'verdict':>15}")
    print("-" * 100)

    decision_rows = []
    df_runs = pd.DataFrame(all_runs)
    for alias in df_runs["bot"].unique():
        sub = df_runs[df_runs["bot"] == alias]
        n = len(sub)
        n_improved = (sub["dd_delta"] < -10).sum()
        n_neutral = ((sub["dd_delta"] >= -10) & (sub["dd_delta"] <= 10)).sum()
        n_worsened = (sub["dd_delta"] > 10).sum()
        avg_vol = sub["vol_delta_pct"].mean()
        avg_intvs = sub["comb_intvs"].mean()
        side = sub.iloc[0]["side"]
        # Verdict logic:
        #   - Если в ≥30% окон combined улучшил DD на >$10 → МИГРИРОВАТЬ
        #   - Иначе если ≥1 окно улучшено и нет ухудшений → возможно
        #   - Иначе оставить как есть
        improvement_ratio = n_improved / n if n > 0 else 0
        if improvement_ratio >= 0.30 and avg_vol >= 50:
            verdict = "✅ МИГРИРОВАТЬ"
        elif improvement_ratio >= 0.15 and n_worsened == 0:
            verdict = "🟡 опционально"
        else:
            verdict = "❌ оставить"
        decision_rows.append({
            "bot": alias, "side": side, "n_windows": n,
            "n_improved": n_improved, "n_neutral": n_neutral, "n_worsened": n_worsened,
            "avg_vol_kept_pct": avg_vol, "avg_intvs": avg_intvs, "verdict": verdict,
        })
        print(f"{alias:<20} {side:<6} {f'{n_improved}/{n}':>11} "
              f"{f'{n_neutral}/{n}':>13} {f'{n_worsened}/{n}':>12} "
              f"{avg_vol:>11.0f}% {verdict:>15}")

    # MD report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Combined vs baseline на всех ботах — per-window analysis (B2 v2)",
        "",
        f"**Дата:** 2026-05-09  **Engine:** managed_grid_sim (calibrated)",
        f"**Данные:** BTC 1m × {len(all_windows)} окон по 7 дней",
        f"**Скрипт:** `tools/_backtest_combined_all_bots_v2.py`",
        "",
        "## Decision matrix",
        "",
        "Verdict считается так:",
        "- Если в **≥30% окон** combined улучшил DD на >$10 + объём сохранён ≥50% → **МИГРИРОВАТЬ**",
        "- Если ≥15% окон улучшено и **нет ухудшений** → опционально",
        "- Иначе — оставить как есть",
        "",
        "| Бот | Side | Окон с улучш. DD | Нейтрально | Ухудшилось | Объём сохр. | Verdict |",
        "|---|:---:|:---:|:---:|:---:|---:|:---:|",
    ]
    for d in decision_rows:
        lines.append(f"| **{d['bot']}** | {d['side']} | "
                     f"{d['n_improved']}/{d['n_windows']} | "
                     f"{d['n_neutral']}/{d['n_windows']} | "
                     f"{d['n_worsened']}/{d['n_windows']} | "
                     f"{d['avg_vol_kept_pct']:.0f}% | {d['verdict']} |")

    # Per-window только активные
    lines.append("\n## Per-window: окна с активными интервенциями\n")
    lines.append("| Бот | Окно | Side | base DD | comb DD | DD Δ | base vol | comb vol | vol% | net Δ | intvs |")
    lines.append("|---|:---:|:---:|---:|---:|---:|---:|---:|:---:|---:|:---:|")
    for r in all_runs:
        if r["comb_intvs"] == 0:
            continue
        lines.append(f"| {r['bot']} | {r['window']} | {r['side']} | "
                     f"${r['base_dd']:+.0f} | ${r['comb_dd']:+.0f} | "
                     f"**${r['dd_delta']:+.0f}** | "
                     f"${r['base_vol']:,.0f} | ${r['comb_vol']:,.0f} | "
                     f"{r['vol_delta_pct']:.0f}% | ${r['net_delta']:+.0f} | {r['comb_intvs']} |")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[combined-all-v2] MD → {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
