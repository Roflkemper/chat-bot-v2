"""B2: Backtest 'combined' interventions на всех 8+ конфигах ботов оператора.

Исходник combined был только для ШОРТ ОБЪЁМ (best vs baseline 3.6× меньше DD).
Теперь — на каждом боте отдельно: TEST_1/2/3, ШОРТ-ОБЪЁМ, ЛОНГ-ОБЪЁМ, ЛОНГ-B/C/D-ХЕДЖ.

Каждый бот имеет свой live config в ginarea_live/params.csv. Прогоняем 4 сценария
× 11 окон по 7 дней BTC 1m на calibrated engine_v2 + managed_grid_sim.

Output: docs/STRATEGIES/COMBINED_ALL_BOTS.md — таблица решения "мигрировать какие".
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
import os as _os  # 2026-05-11 mac-portable
sys.path.insert(0, _os.environ.get("CODEX_SRC",
    r"C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src"))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
PARAMS_CSV = ROOT / "ginarea_live" / "params.csv"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "COMBINED_ALL_BOTS.md"

# Боты для тестирования
BOTS = {
    "5196832375": "TEST_1",
    "5017849873": "TEST_2",
    "4524162672": "TEST_3",
    "5188321731": "ШОРТ-ОБЪЁМ",
    "6399265299": "GPT_SHORT_1.1%",  # SHORT с обширной активностью
    "5188321731": "ШОРТ-ОБЪЁМ",
    "5773124036": "ЛОНГ-ОБЪЁМ",
    "5154651487": "ЛОНГ-ХЕДЖ",
    # LONG-B и LONG-C — inverse contracts, могут не работать в текущем
    # engine_v2 без доработки. Пробуем.
}


def load_bot_config(bot_id: str) -> dict | None:
    """Извлекаем последний живой конфиг бота из params.csv."""
    df = pd.read_csv(PARAMS_CSV)
    df["bot_id"] = df["bot_id"].astype(str).str.replace(".0", "", regex=False)
    sub = df[df["bot_id"] == bot_id].sort_values("ts_utc")
    if sub.empty:
        return None
    last = sub.iloc[-1]
    raw = json.loads(last["raw_params_json"])

    # Side determination
    side_int = raw.get("side")
    if side_int == 1:
        side_name = "long"
        contract_type = "inverse"
    else:
        side_name = "short"
        contract_type = "linear"

    # Order size — для linear minQ в BTC, для inverse в USD
    order_size = float(raw.get("q", {}).get("minQ", 0.001) or 0.001)

    # Indicator threshold
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
    rules = []
    if scenario in ("pause_on_drawdown", "combined"):
        rules.append(PauseEntriesOnUnrealizedThreshold(
            unrealized_threshold_pct_of_depo=-30.0, hold_time_minutes=5))
        rules.append(ResumeEntriesOnPullback(
            pullback_from_peak_pct=50.0, hold_minutes_after_peak=10))
    if scenario in ("partial_unload_on_retrace", "combined"):
        rules.append(PartialUnloadOnRetracement(
            unrealized_pct_threshold=5.0, retracement_from_peak_pct=40.0,
            unload_fraction=0.3))
    if scenario in ("trend_chase", "combined"):
        rules.append(RaiseBoundaryOnConfirmedTrend(
            delta_1h_threshold_pct=0.5, hold_above_boundary_minutes=30,
            new_boundary_offset_pct=2.0))
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
        regime_classifier=rc, run_id=f"all_bots_{scenario}",
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
    print(f"[combined-all] frozen 1m: {len(df):,} bars")

    bars_per_week = 7 * 24 * 60
    n_windows = 11

    scenarios = ["baseline", "combined"]  # фокус: baseline vs combined

    # Pre-build all bars
    all_windows = []
    for w in range(n_windows):
        end_idx = len(df) - w * bars_per_week
        start_idx = max(0, end_idx - bars_per_week)
        if start_idx == 0:
            break
        all_windows.append((w + 1, start_idx, end_idx))

    print(f"[combined-all] {len(all_windows)} окон × 7 дней")
    print(f"[combined-all] боты: {len(BOTS)}")

    all_runs: list[dict] = []
    for bot_id, alias in BOTS.items():
        print(f"\n=== {alias} ({bot_id}) ===")
        cfg = load_bot_config(bot_id)
        if cfg is None:
            print(f"  config not found, skip")
            continue
        if cfg["contract_type"] == "inverse":
            print(f"  ⚠️ inverse contract — engine_v2 пока поддерживает но осторожно")
        print(f"  side={cfg['side']} target={cfg['target_profit_pct']}% "
              f"grid={cfg['grid_step_pct']}% size={cfg['order_size']}")

        for w, start_idx, end_idx in all_windows:
            bars = load_bars_window(start_idx, bars_per_week)
            for scen in scenarios:
                r = run_scenario(cfg, bars, scen)
                if "error" in r:
                    print(f"  win{w} {scen}: ERROR {r['error']}")
                    continue
                r["window"] = w
                r["bot"] = alias
                r["bot_id"] = bot_id
                r["side"] = cfg["side"]
                all_runs.append(r)
        # Aggregate per bot
        bot_runs = [r for r in all_runs if r.get("bot") == alias]
        for scen in scenarios:
            rs = [r for r in bot_runs if r["scenario"] == scen]
            if not rs:
                continue
            avg_vol = np.mean([r["volume"] for r in rs])
            avg_net = np.mean([r["realized_net"] for r in rs])
            worst_dd = min(r["max_dd_usd"] for r in rs)
            print(f"  {scen:<10}  avg_vol=${avg_vol:>9,.0f}  "
                  f"avg_net=${avg_net:>+8.2f}  worst_DD=${worst_dd:>+9.2f}")

    # Summary
    print(f"\n{'='*100}")
    print("FINAL SUMMARY: combined vs baseline per bot")
    print(f"{'='*100}")
    print(f"{'bot':<22}  {'side':<6}  {'baseline_vol':>13}  {'combined_vol':>13}  "
          f"{'vol_ratio':>10}  {'baseline_DD':>12}  {'combined_DD':>12}  {'DD_ratio':>10}")
    print("-" * 110)

    df_runs = pd.DataFrame(all_runs)
    summary_rows: list[dict] = []
    if not df_runs.empty:
        for alias in df_runs["bot"].unique():
            sub = df_runs[df_runs["bot"] == alias]
            base = sub[sub["scenario"] == "baseline"]
            comb = sub[sub["scenario"] == "combined"]
            if base.empty or comb.empty:
                continue
            side = sub.iloc[0]["side"]
            base_vol = base["volume"].mean()
            comb_vol = comb["volume"].mean()
            vol_ratio = (comb_vol / base_vol * 100) if base_vol else 0
            base_dd = base["max_dd_usd"].min()
            comb_dd = comb["max_dd_usd"].min()
            dd_ratio = (comb_dd / base_dd * 100) if base_dd != 0 else 100
            base_net = base["realized_net"].mean()
            comb_net = comb["realized_net"].mean()
            summary_rows.append({
                "bot": alias, "side": side,
                "baseline_vol": base_vol, "combined_vol": comb_vol,
                "vol_ratio_pct": vol_ratio,
                "baseline_DD": base_dd, "combined_DD": comb_dd,
                "DD_ratio_pct": dd_ratio,
                "baseline_net": base_net, "combined_net": comb_net,
            })
            print(f"{alias:<22}  {side:<6}  ${base_vol:>11,.0f}  ${comb_vol:>11,.0f}  "
                  f"{vol_ratio:>9.0f}%  ${base_dd:>+10.0f}  ${comb_dd:>+10.0f}  "
                  f"{dd_ratio:>9.0f}%")

    # MD
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Combined-стратегия на всех конфигах ботов (B2)",
        "",
        f"**Дата:** 2026-05-09  **Engine:** managed_grid_sim (calibrated)",
        f"**Данные:** BTC 1m × {len(all_windows)} окон по 7 дней",
        "",
        "## Рекомендации по миграции",
        "",
        "| Бот | Side | Avg vol baseline | Avg vol combined | Объём сохр. | Worst DD baseline | Worst DD combined | DD улучш. |",
        "|---|:---:|---:|---:|:---:|---:|---:|:---:|",
    ]
    for s in summary_rows:
        vol_kept = f"{s['vol_ratio_pct']:.0f}%"
        dd_imprv = f"{100 - s['DD_ratio_pct']:.0f}% меньше" if s['DD_ratio_pct'] < 100 else "хуже"
        lines.append(f"| **{s['bot']}** | {s['side']} | ${s['baseline_vol']:,.0f} | "
                     f"${s['combined_vol']:,.0f} | {vol_kept} | "
                     f"${s['baseline_DD']:+,.0f} | ${s['combined_DD']:+,.0f} | "
                     f"{dd_imprv} |")

    lines += [
        "",
        "## Решение по миграции",
        "",
        "Бот мигрируем на combined если:",
        "1. Объём сохраняется ≥ 50% от baseline",
        "2. DD улучшается ≥ 30%",
        "3. Net PnL не хуже baseline более чем на $200/неделя",
        "",
    ]
    for s in summary_rows:
        criteria_1 = s["vol_ratio_pct"] >= 50
        criteria_2 = (100 - s["DD_ratio_pct"]) >= 30
        criteria_3 = (s["combined_net"] - s["baseline_net"]) >= -200
        passed = sum([criteria_1, criteria_2, criteria_3])
        verdict = "✅ МИГРИРОВАТЬ" if passed >= 2 else "❌ оставить как есть"
        lines.append(f"- **{s['bot']}** ({s['side']}): {passed}/3 критериев — {verdict}")
        lines.append(f"  - объём: {s['vol_ratio_pct']:.0f}% от baseline ({'✓' if criteria_1 else '✗'})")
        lines.append(f"  - DD: {100-s['DD_ratio_pct']:.0f}% меньше ({'✓' if criteria_2 else '✗'})")
        lines.append(f"  - PnL diff: ${s['combined_net'] - s['baseline_net']:+.0f}/нед ({'✓' if criteria_3 else '✗'})")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[combined-all] MD → {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
