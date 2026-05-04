"""Run the LONG TP sweep and emit raw JSON for the report."""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.backtest.long_tp_sweep import run_full_sweep, load_1h_with_regime, TP_VALUES_PCT

t0 = time.time()
df = load_1h_with_regime()
print(f"Dataset: {len(df)} 1h bars, {df.index[0]} to {df.index[-1]}")
cells = run_full_sweep(df)
print(f"\n=== LONG TP SWEEP - 5 TP x 4 windows = 20 cells ===\n")
print(f"{'TP':>5}  {'Period':>10}  {'Bars':>5}  {'MaxPos(BTC)':>11}  "
      f"{'MaxDD($)':>10}  {'GrossPnL($)':>11}  {'NetPnL($)':>10}  {'Cycles':>7}  {'AvgCyc(h)':>10}")
print("-" * 110)
for c in cells:
    print(f"{c.tp_pct:>5.2f}  {c.period_label:>10s}  {c.n_bars:>5d}  "
          f"{c.max_position_btc:>11.4f}  {c.max_dd_usd:>10.0f}  "
          f"{c.pnl_usd_gross:>11.0f}  {c.pnl_usd_net:>10.0f}  "
          f"{c.n_cycles:>7d}  {c.avg_cycle_hours:>10.2f}")
print(f"\nelapsed: {time.time()-t0:.1f}s")

# Persist raw
out = []
for c in cells:
    out.append({
        "tp_pct": c.tp_pct, "period_label": c.period_label, "n_bars": c.n_bars,
        "pnl_btc_gross": c.pnl_btc_gross, "pnl_usd_gross": c.pnl_usd_gross,
        "pnl_usd_net": c.pnl_usd_net, "commission_usd": c.commission_usd,
        "max_position_btc": c.max_position_btc, "max_dd_usd": c.max_dd_usd,
        "n_cycles": c.n_cycles, "avg_cycle_hours": c.avg_cycle_hours,
        "equity_curve_usd": c.equity_curve_usd,
        "equity_curve_index": c.equity_curve_index,
        "edge_cases": c.edge_cases,
    })
Path("docs/RESEARCH").mkdir(parents=True, exist_ok=True)
Path("docs/RESEARCH/_long_tp_sweep_raw.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("raw: docs/RESEARCH/_long_tp_sweep_raw.json")
