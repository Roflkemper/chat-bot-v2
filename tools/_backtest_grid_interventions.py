"""Backtest grid bots WITH interventions on calibrated engine_v2.

После валидации движка (tools/_validate_engine_short_objem.py):
  - объём engine vs real:     ±14% — годится для оптимизации потока
  - trades engine vs real:    ±20% — годится
  - PnL engine vs real:        нестабильно на коротких окнах — НЕ оптимизируем по нему

Поэтому оптимизируем по:
  1. Volume traded (target: maximize)
  2. Max drawdown (target: minimize)
  3. Max position (target: cap at safe level)
  4. Position freezing time (% времени с позицией без новых IN)

Сравниваем 4 сценария на одном конфиге (ШОРТ ОБЬЕМ params):
  - BASELINE: без интервенций
  - PAUSE_ON_TREND: пауза новых IN если 1h move > +0.5% для SHORT
  - PARTIAL_UNLOAD_ON_RETRACE: частичная выгрузка после пика unrealized
  - COMBINED: pause + partial_unload вместе

Прогон: 11 окон × 7d на BTC 1m frozen (2024-02 → 2026-05).

Результат: docs/STRATEGIES/GRID_INTERVENTIONS_v1.md
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
sys.path.insert(0, r"C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src")

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass


def load_short_objem_config() -> dict:
    df = pd.read_csv(ROOT / "ginarea_live" / "params.csv")
    df["bot_id"] = df["bot_id"].astype(str).str.replace(".0", "", regex=False)
    sub = df[df["bot_id"] == "5188321731"].sort_values("ts_utc")
    last = sub.iloc[-1]
    raw = json.loads(last["raw_params_json"])
    return {
        "bot_id": "SHORT_OBJEM",
        "alias": "SHORT_OBJEM",
        "side": "short",
        "contract_type": "linear",
        "order_size": float(raw["q"]["minQ"]),
        "order_count": int(raw["maxOp"]),
        "grid_step_pct": float(raw["gs"]),
        "target_profit_pct": float(raw["gap"]["tog"]),
        "min_stop_pct": float(raw["gap"]["minS"]),
        "max_stop_pct": float(raw["gap"]["maxS"]),
        "instop_pct": float(raw["gap"]["isg"]),
        "boundaries_lower": 0.0,
        "boundaries_upper": 0.0,
        "indicator_period": int(raw["in"]["start"]["cnds"][0]["params"]["d"]),
        "indicator_threshold_pct": float(raw["in"]["start"]["cnds"][0]["items"][0]["p"]),
        "dsblin": False,
        "leverage": 100,
    }


def load_bars_window(start_idx: int, n_bars: int) -> list:
    """Загрузка n_bars 1-минутных баров начиная с start_idx из frozen 2y."""
    from backtest_lab.engine_v2.bot import OHLCBar
    df = pd.read_csv(ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv")
    sub = df.iloc[start_idx:start_idx + n_bars]
    bars = []
    for _, r in sub.iterrows():
        ts = pd.Timestamp(r["ts"] / 1000, unit="s", tz="UTC")
        bars.append(OHLCBar(
            ts=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["volume"]),
        ))
    return bars


def make_intervention_rules(scenario: str) -> list:
    """Создаёт набор правил интервенций для сценария."""
    from services.managed_grid_sim.intervention_rules import (
        PauseEntriesOnUnrealizedThreshold,
        ResumeEntriesOnPullback,
        PartialUnloadOnRetracement,
        RaiseBoundaryOnConfirmedTrend,
    )
    if scenario == "baseline":
        return []
    rules = []
    if scenario in ("pause_on_drawdown", "combined"):
        # SHORT bot теряет deньги когда цена идёт вверх → unrealized отрицательный.
        # Пауза новых IN когда unrealized < -$30 и держим 5+ мин в просадке.
        rules.append(PauseEntriesOnUnrealizedThreshold(
            unrealized_threshold_pct_of_depo=-30.0,
            hold_time_minutes=5,
        ))
        # Возврат когда был пик >0 и теперь pullback >50% от него
        rules.append(ResumeEntriesOnPullback(
            pullback_from_peak_pct=50.0,
            hold_minutes_after_peak=10,
        ))
    if scenario in ("partial_unload_on_retrace", "combined"):
        # Частично выгружаем 30% позиции если был пик unrealized > $5
        # и сейчас retracement >40% от пика.
        rules.append(PartialUnloadOnRetracement(
            unrealized_pct_threshold=5.0,
            retracement_from_peak_pct=40.0,
            unload_fraction=0.3,
        ))
    if scenario in ("trend_chase", "combined"):
        # Поднимаем верхнюю границу если 1h move > +0.5% и держим 30 мин.
        rules.append(RaiseBoundaryOnConfirmedTrend(
            delta_1h_threshold_pct=0.5,
            hold_above_boundary_minutes=30,
            new_boundary_offset_pct=2.0,
        ))
    return rules


def run_scenario(cfg: dict, bars: list, scenario: str) -> dict:
    """Один прогон. Возвращает метрики."""
    from services.managed_grid_sim import ManagedGridSimRunner, ManagedRunConfig
    from services.managed_grid_sim.regime_classifier import RegimeClassifier

    runner = ManagedGridSimRunner()
    rc = RegimeClassifier()
    rules = make_intervention_rules(scenario)
    run_cfg = ManagedRunConfig(
        bot_configs=[cfg],
        bars=bars,
        intervention_rules=rules,
        regime_classifier=rc,
        run_id=f"grid_int_{scenario}",
        strict_mode=False,
    )
    result = runner.run(run_cfg)
    # Empirical fee correction
    fees = result.total_volume_usd * 0.00019 * 2
    return {
        "scenario": scenario,
        "n_bars": result.bar_count,
        "realized_raw": round(result.final_realized_pnl_usd, 2),
        "realized_net": round(result.final_realized_pnl_usd - fees, 2),
        "unrealized": round(result.final_unrealized_pnl_usd, 2),
        "volume": round(result.total_volume_usd, 0),
        "trades": result.total_trades,
        "max_dd_usd": round(result.max_drawdown_usd, 2),
        "max_dd_pct": round(result.max_drawdown_pct, 2),
        "interventions": result.total_interventions,
    }


def main() -> int:
    cfg = load_short_objem_config()
    print(f"[CONFIG] ШОРТ ОБЬЕМ params loaded:")
    for k in ("order_size", "order_count", "grid_step_pct", "target_profit_pct",
              "min_stop_pct", "max_stop_pct", "instop_pct"):
        print(f"  {k} = {cfg[k]}")

    df = pd.read_csv(ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv")
    print(f"[DATA] frozen 1m: {len(df)} bars total")

    bars_per_week = 7 * 24 * 60
    n_windows = 11
    print(f"[RUN] {n_windows} окон × 7 дней (1m bars)")

    scenarios = ["baseline", "pause_on_drawdown", "partial_unload_on_retrace",
                 "trend_chase", "combined"]
    print(f"[RUN] {len(scenarios)} сценариев на каждое окно\n")

    all_runs: list[dict] = []
    for w in range(n_windows):
        end_idx = len(df) - w * bars_per_week
        start_idx = max(0, end_idx - bars_per_week)
        if start_idx == 0:
            break
        bars = load_bars_window(start_idx, bars_per_week)
        print(f"=== Окно {w+1}/{n_windows} (bars {start_idx}-{end_idx}, {len(bars)} bars) ===")
        for scen in scenarios:
            try:
                m = run_scenario(cfg, bars, scen)
                m["window"] = w + 1
                all_runs.append(m)
                print(f"  {scen:<28}  vol=${m['volume']:>9,.0f}  net=${m['realized_net']:>+8.2f}  "
                      f"unrl=${m['unrealized']:>+8.2f}  DD=${m['max_dd_usd']:>+8.2f}  "
                      f"trades={m['trades']:>3}  int={m['interventions']:>3}")
            except Exception as exc:
                print(f"  {scen:<28}  ERROR: {exc}")
                all_runs.append({"window": w + 1, "scenario": scen, "error": str(exc)})

    # Aggregate
    print(f"\n{'=' * 90}")
    print("AGGREGATE: средние и худшие значения по 11 окнам")
    print(f"{'=' * 90}")
    by_scen: dict[str, list[dict]] = {}
    for r in all_runs:
        if "error" in r:
            continue
        by_scen.setdefault(r["scenario"], []).append(r)

    summary = []
    print(f"  {'scenario':<28}  {'avg_vol':>10}  {'avg_net':>9}  {'worst_DD':>10}  {'avg_int':>8}")
    print("  " + "-" * 80)
    for scen in scenarios:
        runs = by_scen.get(scen, [])
        if not runs:
            continue
        avg_vol = np.mean([r["volume"] for r in runs])
        avg_net = np.mean([r["realized_net"] for r in runs])
        worst_dd = min(r["max_dd_usd"] for r in runs) if runs else 0
        avg_int = np.mean([r["interventions"] for r in runs])
        summary.append({
            "scenario": scen, "avg_volume": avg_vol, "avg_net_pnl": avg_net,
            "worst_dd": worst_dd, "avg_interventions": avg_int,
        })
        print(f"  {scen:<28}  ${avg_vol:>9,.0f}  ${avg_net:>+8.2f}  ${worst_dd:>+9.2f}  {avg_int:>8.1f}")

    # MD report
    out_md = ROOT / "docs" / "STRATEGIES" / "GRID_INTERVENTIONS_v1.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Grid Interventions v1 — backtest results",
        "",
        f"**Date:** 2026-05-09",
        f"**Engine:** engine_v2 + managed_grid_sim (calibrated)",
        f"**Data:** BTCUSDT 1m × {n_windows} окон по 7 дней",
        f"**Config:** ШОРТ ОБЬЕМ live params (id 5188321731)",
        f"**Fee model:** empirical 0.038% round-trip (calibrated против live ШОРТ ОБЬЕМ)",
        "",
        "## Engine validation",
        "",
        "Bash `tools/_validate_engine_short_objem.py` подтвердил:",
        "- volume: ±14% от real (приемлемо для оптимизации потока)",
        "- trades: ±20% от real (приемлемо)",
        "- PnL: нестабильно на коротких окнах (поэтому оптимизируем по volume/DD, не PnL)",
        "",
        "## Сценарии",
        "",
        "1. **baseline** — без интервенций (как сейчас работает ШОРТ ОБЬЕМ)",
        "2. **pause_on_drawdown** — пауза новых IN при unrealized < -$30, возврат после pullback >50%",
        "3. **partial_unload_on_retrace** — частичная выгрузка 30% позиции если был пик >$5 unrealized и retracement >40%",
        "4. **trend_chase** — поднимаем верхнюю границу при 1h move > +0.5% (не дать боту замёрзнуть)",
        "5. **combined** — pause + partial_unload + trend_chase",
        "",
        "## Aggregate (среднее за окно 7d)",
        "",
        "| Сценарий | Avg Volume | Avg Net PnL | Worst DD | Avg Interventions |",
        "|---|---:|---:|---:|---:|",
    ]
    for s in summary:
        lines.append(f"| `{s['scenario']}` | ${s['avg_volume']:,.0f} | "
                     f"${s['avg_net_pnl']:+.2f} | ${s['worst_dd']:+.2f} | "
                     f"{s['avg_interventions']:.1f} |")

    lines += ["", "## Per-window breakdown", "", "| Окно | Сценарий | Vol | Net | Unrl | DD | Trades | Int |",
              "|:---:|---|---:|---:|---:|---:|---:|---:|"]
    for r in all_runs:
        if "error" in r:
            continue
        lines.append(f"| {r['window']} | `{r['scenario']}` | ${r['volume']:,.0f} | "
                     f"${r['realized_net']:+.2f} | ${r['unrealized']:+.2f} | "
                     f"${r['max_dd_usd']:+.2f} | {r['trades']} | {r['interventions']} |")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[OUTPUT] {out_md.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
