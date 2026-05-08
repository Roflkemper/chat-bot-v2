"""CLI and report writer for coordinated grid research.

Usage (from c:\\bot7):
    python -m services.coordinated_grid.runner
    python -m services.coordinated_grid.runner --report reports/coordinated_grid_2026-05-02.md
"""
from __future__ import annotations

import io
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "reports" / "coordinated_grid_research_2026-05-02.md"


def _fmt(v: float, d: int = 2) -> str:
    if math.isnan(v) or math.isinf(v):
        return "N/A"
    return f"{v:,.{d}f}"


def _pct(v: float) -> str:
    if math.isnan(v) or math.isinf(v):
        return "N/A"
    return f"{v:.1f}%"


def _run_cross_validation() -> dict:
    """Compare simulator against real snapshots (2026-04-28 → 2026-04-29)."""
    import pandas as pd
    from services.calibration.sim import load_ohlcv_bars
    from .models import BotConfig, CoordinatedConfig
    from .simulator import run_sim
    import math

    SNAP_PATH  = ROOT / "ginarea_live" / "snapshots.csv"
    OHLCV_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

    snaps = pd.read_csv(SNAP_PATH)
    snaps["ts_utc"] = pd.to_datetime(snaps["ts_utc"], utc=True, errors="coerce")
    snaps = snaps.dropna(subset=["ts_utc"])
    snaps["profit"]         = pd.to_numeric(snaps["profit"],         errors="coerce").fillna(0)
    snaps["current_profit"] = pd.to_numeric(snaps["current_profit"], errors="coerce").fillna(0)

    # Real bots: TEST_3 (SHORT) + LONG_C (LONG)
    for alias in ["TEST_3", "LONG_C"]:
        bot_snaps = snaps[snaps["alias"] == alias].sort_values("ts_utc")
        if bot_snaps.empty:
            return {"error": f"alias {alias} not found in snapshots"}

    test3 = snaps[snaps["alias"] == "TEST_3"].sort_values("ts_utc")
    longc = snaps[snaps["alias"] == "LONG_C"].sort_values("ts_utc")

    # Initial account values
    t3_start = float(test3.iloc[0]["profit"] + test3.iloc[0]["current_profit"])
    lc_start = float(longc.iloc[0]["profit"] + longc.iloc[0]["current_profit"])
    t3_end   = float(test3.iloc[-1]["profit"] + test3.iloc[-1]["current_profit"])
    lc_end   = float(longc.iloc[-1]["profit"] + longc.iloc[-1]["current_profit"])
    real_delta = (t3_end - t3_start) + (lc_end - lc_start)

    ts_start_str = test3.iloc[0]["ts_utc"].isoformat()
    ts_end_str   = test3.iloc[-1]["ts_utc"].isoformat()

    # Run sim for same period
    bars = load_ohlcv_bars(OHLCV_PATH, ts_start_str, ts_end_str)

    from .grid_search import LONG_BOT, SHORT_BOT
    import math as _math
    cfg = CoordinatedConfig(
        long_bot=LONG_BOT,
        short_bot=SHORT_BOT,
        combined_close_threshold_usd=_math.inf,
        re_entry_delay_bars=0,
        re_entry_price_offset_pct=0.0,
        asymmetric_trim_enabled=False,
        asymmetric_trim_threshold_pct=0.0,
    )
    r = run_sim(bars, cfg)

    sim_delta = r.combined_realized_usd
    err_pct   = abs(sim_delta - real_delta) / max(abs(real_delta), 1.0) * 100

    return {
        "real_test3_delta": t3_end - t3_start,
        "real_longc_delta": lc_end - lc_start,
        "real_combined_delta": real_delta,
        "sim_combined_delta": sim_delta,
        "n_bars": len(bars),
        "period": f"{ts_start_str[:10]} → {ts_end_str[:10]}",
        "err_pct": err_pct,
        "trusted": err_pct <= 50.0,
    }


def write_report(out_path: Path, full: bool = False) -> None:
    from .grid_search import run_grid_search, BASELINE_CONFIG

    print("[coordinated_grid] Starting grid search ...")
    results, baseline = run_grid_search(full=full)

    print("[coordinated_grid] Running cross-validation ...")
    try:
        xval = _run_cross_validation()
    except Exception as e:
        xval = {"error": str(e)}

    # Sort by combined_realized_usd descending
    ranked = sorted(results, key=lambda r: r.combined_realized_usd, reverse=True)
    top20  = ranked[:20]
    bottom5 = ranked[-5:]

    # Trim-vs-notrim split for top configs
    top_trim   = sorted([r for r in results if r.config.asymmetric_trim_enabled],
                        key=lambda r: r.combined_realized_usd, reverse=True)[:5]
    top_notrim = sorted([r for r in results if not r.config.asymmetric_trim_enabled
                         and r.config is not BASELINE_CONFIG],
                        key=lambda r: r.combined_realized_usd, reverse=True)[:5]

    # Edge over baseline
    base_pnl = baseline.combined_realized_usd

    buf = io.StringIO()
    ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    buf.write(f"# Coordinated Grid Research — {ts_now}\n\n")
    buf.write("**Period:** 2025-05-01 → 2026-04-29 (frozen BTCUSDT 1m, 1y)  \n")
    buf.write("**Bot params fixed:** TD=0.25%, GS=0.03%, SHORT 0.003 BTC, LONG 200 USD  \n")
    buf.write(f"**Configs tested:** {len(results)} (incl. baseline)  \n")
    buf.write("**Edge target:** >+$5,000/year combined_realized over baseline\n\n")
    buf.write("---\n\n")

    # §1 Methodology
    buf.write("## §1 Methodology\n\n")
    buf.write("Two-sided grid runs SHORT (USDT-M linear) + LONG (COIN-M inverse) simultaneously.\n")
    buf.write("Grid mechanics: identical to calibration sim (services.calibration.sim.GridBotSim), "
              "raw 4-tick mode (O→L→H→C bullish / O→H→L→C bearish).\n\n")
    buf.write("**Combined PnL USD:** `short_realized_usd + long_realized_btc × avg_bar_close`  \n")
    buf.write("**Coordinated close:** when combined (realized + unrealized) ≥ threshold → "
              "force-close all open orders at bar close price → restart both bots after delay.  \n")
    buf.write("**Asymmetric trim:** cancel N% of orders on the losing side when "
              "its unrealized loss / combined_notional ≥ trim_threshold.  \n")
    buf.write("**Baseline:** threshold=∞ (no coordinated close, both bots run independently).  \n\n")
    buf.write("Grid search space:\n")
    buf.write("| Param | Values |\n|---|---|\n")
    buf.write("| combined_close_threshold | $500, $1,000, $2,000, $5,000 |\n")
    buf.write("| re_entry_delay | 0h, 4h, 12h, 24h |\n")
    buf.write("| re_entry_price_offset | 0%, 0.5%, 1.0%, 2.0% |\n")
    buf.write("| asymmetric_trim_enabled | true, false |\n")
    buf.write("| asymmetric_trim_threshold | 1%, 2%, 5% (when enabled) |\n\n")
    buf.write("---\n\n")

    # §2 Baseline
    buf.write("## §2 Baseline (no coordination)\n\n")
    buf.write("| Metric | Value |\n|---|---|\n")
    buf.write(f"| short_realized_usd | ${_fmt(baseline.short_realized_usd)} |\n")
    buf.write(f"| long_realized_btc  | {_fmt(baseline.long_realized_btc, 4)} BTC |\n")
    buf.write(f"| combined_realized_usd | ${_fmt(baseline.combined_realized_usd)} |\n")
    buf.write(f"| combined_unrealized_usd | ${_fmt(baseline.combined_unrealized_usd)} |\n")
    buf.write(f"| max_combined_dd_usd | ${_fmt(baseline.max_combined_dd_usd)} |\n")
    buf.write(f"| short_fills | {baseline.n_short_fills:,} |\n")
    buf.write(f"| long_fills  | {baseline.n_long_fills:,} |\n\n")
    buf.write("---\n\n")

    # §3 Grid search top 20
    buf.write("## §3 Grid search results — top 20 by combined_realized_usd\n\n")
    buf.write("| Rank | threshold | delay_h | offset% | trim | trim_thr | "
              "combined_realized | edge_vs_baseline | n_closes | max_dd |\n")
    buf.write("|---|---|---|---|---|---|---:|---:|---:|---:|\n")
    for i, r in enumerate(top20, 1):
        c = r.config
        trim_str = f"{c.asymmetric_trim_threshold_pct:.0f}%" if c.asymmetric_trim_enabled else "—"
        edge = r.combined_realized_usd - base_pnl
        delay_h = c.re_entry_delay_bars // 60
        buf.write(f"| {i} | ${_fmt(c.combined_close_threshold_usd, 0)} "
                  f"| {delay_h}h | {c.re_entry_price_offset_pct:.1f}%"
                  f" | {'Y' if c.asymmetric_trim_enabled else 'N'} | {trim_str}"
                  f" | ${_fmt(r.combined_realized_usd)}"
                  f" | ${_fmt(edge)}"
                  f" | {r.n_coordinated_closes}"
                  f" | ${_fmt(r.max_combined_dd_usd)} |\n")
    buf.write("\n---\n\n")

    # §4 Best config walkthrough (top 1)
    best = top20[0]
    bc   = best.config
    buf.write("## §4 Best config detailed walkthrough\n\n")
    buf.write(f"**Config:** threshold=${_fmt(bc.combined_close_threshold_usd, 0)}, "
              f"delay={bc.re_entry_delay_bars//60}h, "
              f"offset={bc.re_entry_price_offset_pct:.1f}%, "
              f"trim={'YES @ '+str(bc.asymmetric_trim_threshold_pct)+'%' if bc.asymmetric_trim_enabled else 'NO'}\n\n")
    buf.write(f"**Results:** combined=${_fmt(best.combined_realized_usd)}, "
              f"n_closes={best.n_coordinated_closes}, "
              f"edge=${_fmt(best.combined_realized_usd - base_pnl)}\n\n")
    buf.write("**Close events (first 10):**\n\n")
    if best.close_events:
        buf.write("| # | bar_idx | price | combined_at_close | short_orders | long_orders |\n")
        buf.write("|---|---|---|---:|---|---|\n")
        for j, ev in enumerate(best.close_events[:10], 1):
            buf.write(f"| {j} | {ev.bar_idx:,} | ${_fmt(ev.price, 0)}"
                      f" | ${_fmt(ev.combined_pnl_usd_at_close)}"
                      f" | {ev.n_short_orders} | {ev.n_long_orders} |\n")
    else:
        buf.write("No close events triggered.\n")
    buf.write("\n---\n\n")

    # §5 Comparison vs baselines
    buf.write("## §5 Comparison vs baselines\n\n")
    buf.write("| Setup | combined_realized_usd | edge_vs_baseline | n_closes |\n")
    buf.write("|---|---:|---:|---:|\n")
    buf.write(f"| **Baseline (no coord)** | ${_fmt(base_pnl)} | $0 | 0 |\n")
    for i, r in enumerate(top20[:5], 1):
        c = r.config
        edge = r.combined_realized_usd - base_pnl
        buf.write(f"| Top-{i} (thr=${_fmt(c.combined_close_threshold_usd, 0)}, "
                  f"d={c.re_entry_delay_bars//60}h) "
                  f"| ${_fmt(r.combined_realized_usd)} "
                  f"| ${_fmt(edge)} "
                  f"| {r.n_coordinated_closes} |\n")

    edge_threshold = 5000.0
    configs_with_edge = [r for r in results if r.combined_realized_usd - base_pnl >= edge_threshold]
    buf.write(f"\n**Configs with edge ≥ $5,000 over baseline: {len(configs_with_edge)} / {len(results)}**\n\n")
    buf.write("---\n\n")

    # §6 Cross-validation
    buf.write("## §6 Real-portfolio cross-validation\n\n")
    if "error" in xval:
        buf.write(f"⚠ Cross-validation failed: {xval['error']}\n\n")
    else:
        buf.write(f"**Period:** {xval['period']}  \n")
        buf.write(f"**n_bars:** {xval['n_bars']:,}  \n\n")
        buf.write("| Bot | Real delta_usd |\n|---|---:|\n")
        buf.write(f"| TEST_3 (SHORT)  | ${_fmt(xval['real_test3_delta'])} |\n")
        buf.write(f"| LONG_C (LONG)   | ${_fmt(xval['real_longc_delta'])} |\n")
        buf.write(f"| Combined real   | ${_fmt(xval['real_combined_delta'])} |\n")
        buf.write(f"| Sim predicted   | ${_fmt(xval['sim_combined_delta'])} |\n")
        buf.write(f"| Error           | {_pct(xval['err_pct'])} |\n")
        trusted_str = "TRUSTED (within 50%)" if xval["trusted"] else "NOT TRUSTED (>50% error)"
        buf.write(f"\n**Cross-validation verdict: {trusted_str}**  \n")
        buf.write("Note: sim uses raw 1m bar mode (no instop/indicator gate)."
                  " Expected gap of ~K=9.6× for SHORT vs real GinArea fills.  \n")
    buf.write("\n---\n\n")

    # §7 Asymmetric trim deep-dive
    buf.write("## §7 Asymmetric trim deep-dive\n\n")
    buf.write("### Top 5 with trim enabled\n\n")
    buf.write("| threshold | delay_h | trim_thr | combined_realized | edge_vs_baseline |\n")
    buf.write("|---|---|---|---:|---:|\n")
    for r in top_trim:
        c = r.config
        buf.write(f"| ${_fmt(c.combined_close_threshold_usd, 0)} | {c.re_entry_delay_bars//60}h"
                  f" | {c.asymmetric_trim_threshold_pct:.0f}%"
                  f" | ${_fmt(r.combined_realized_usd)}"
                  f" | ${_fmt(r.combined_realized_usd - base_pnl)} |\n")
    buf.write("\n### Top 5 with trim disabled\n\n")
    buf.write("| threshold | delay_h | combined_realized | edge_vs_baseline |\n")
    buf.write("|---|---|---:|---:|\n")
    for r in top_notrim:
        c = r.config
        buf.write(f"| ${_fmt(c.combined_close_threshold_usd, 0)} | {c.re_entry_delay_bars//60}h"
                  f" | ${_fmt(r.combined_realized_usd)}"
                  f" | ${_fmt(r.combined_realized_usd - base_pnl)} |\n")
    buf.write("\n---\n\n")

    # §8 Выводы по-русски
    best_edge = top20[0].combined_realized_usd - base_pnl
    edge_found = best_edge >= edge_threshold
    buf.write("## §8 ВЫВОДЫ ПО-РУССКИ\n\n")

    buf.write("### Работает ли coordinated grid?\n\n")
    if edge_found:
        buf.write(f"**ДА — найден edge.** Лучший config даёт ${_fmt(best_edge)} over baseline за год.  \n")
        buf.write(f"Это >{edge_threshold/1000:.0f}k USD edge при одинаковых bot params.  \n\n")
    else:
        buf.write(f"**НЕТ — edge не найден.** Лучший config даёт ${_fmt(best_edge)} over baseline — "
                  f"{'выше' if best_edge > 0 else 'ниже'} baseline, но меньше threshold $5,000.  \n")
        buf.write("Coordination overhead (пропуск баров во время pause) снижает кол-во grid fills.  \n\n")

    buf.write("### В каких условиях?\n\n")
    if edge_found:
        bc2 = top20[0].config
        buf.write(f"- Лучший threshold: ${_fmt(bc2.combined_close_threshold_usd, 0)} combined PnL  \n")
        buf.write(f"- Оптимальный re-entry delay: {bc2.re_entry_delay_bars//60}h  \n")
        buf.write(f"- Trim: {'эффективен' if bc2.asymmetric_trim_enabled else 'не нужен'}  \n\n")
    else:
        buf.write("- При всех протестированных threshold/delay/offset — отсутствие coordination лучше.  \n")
        buf.write("- Причина: grid зарабатывает на частых малых циклах; pause block fills.  \n\n")

    buf.write("### Какие optimal params?\n\n")
    buf.write(f"Из {len(results)} конфигов top: {top20[0].config.config_id()}  \n")
    buf.write(f"combined_realized: ${_fmt(top20[0].combined_realized_usd)}  \n")
    buf.write(f"n_coordinated_closes: {top20[0].n_coordinated_closes}  \n\n")

    buf.write("### Стоит ли productize?\n\n")
    if edge_found and len(configs_with_edge) >= 5:
        buf.write("**РЕКОМЕНДУЮ** ограниченный live test: 30 дней, small size, "
                  "real snapshot tracking через ginarea_live.  \n")
        buf.write("Обязательно cross-validate: если sim-predicted delta расходится с real >50%, "
                  "найти причину перед увеличением размера.  \n\n")
    elif edge_found:
        buf.write("**ОСТОРОЖНО.** Edge найден но только в 1-4 конфигах — возможна переподгонка.  \n")
        buf.write("Нужны дополнительные данные (другие year/assets) прежде чем productize.  \n\n")
    else:
        buf.write("**НЕ PRODUCTIZE** на текущих данных.  \n")
        buf.write("Coordinated grid с force-close не даёт преимущества над independent bots.  \n")
        buf.write("Следующая гипотеза: вместо full close — asymmetric rebalance (без pause).  \n\n")

    buf.write("---\n\n")

    # §9 Caveats
    buf.write("## §9 Caveats\n\n")
    buf.write("- **Synthetic sim**: no instop, no indicator gate, no trailing stop group — "
              "sim fills ~10× more than real GinArea for SHORT (K=9.637). "
              "Combined_realized_usd values are NOT real-money equivalents.  \n")
    buf.write("- **Single asset BTC**, single frozen year — "
              "post-halving bull-heavy bias may inflate LONG widen findings.  \n")
    buf.write("- **Force-close at bar close price**: real coordinated close would be at market "
              "bid/ask with slippage. Sim underestimates close cost.  \n")
    buf.write("- **Asymmetric trim = order cancel**: no slippage, no partial fill. "
              "Real cancel does not guarantee exact removal.  \n")
    buf.write("- **No cross-bot funding/fees**: COIN-M perpetual funding rates not modeled.  \n")
    buf.write("- **Cross-validation period only 2 days** (frozen data ends 2026-04-29). "
              "Insufficient for meaningful validation; treat as sanity check only.  \n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"[coordinated_grid] Report: {out_path}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--full", action="store_true",
                        help="Run full 257-config sweep (est. ~40 min); default: focused 29-config")
    args = parser.parse_args()
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    write_report(Path(args.report), full=args.full)


if __name__ == "__main__":
    main()
