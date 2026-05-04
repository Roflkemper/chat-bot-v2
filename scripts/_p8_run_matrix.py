"""Run the full P8 expansion matrix and emit raw JSON for the report."""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.backtest.expansion_research import run_full_matrix, load_4h_with_regime

t0 = time.time()
df = load_4h_with_regime()
results = run_full_matrix(df_4h=df)
print()
print("=== 5x3 MATRIX (DISTRIBUTION skipped - no episodes in dataset) ===\n")
print("Variant | Regime    | Bars  | Eps  | PnL($)     | maxDD%  | Sortino | Trades")
print("--------+-----------+-------+------+------------+---------+---------+-------")
for r in results:
    print(f"{r.variant}       | {r.regime:<9s} | {r.n_bars:5d} | {r.n_episodes:4d} | "
          f"{r.pnl_usd:10.2f} | {r.max_dd_pct:6.2f}% | {str(r.sortino):>7s} | {r.n_trades:5d}")
print(f"\nelapsed: {time.time()-t0:.1f}s")

# Persist raw + edge cases
out = []
for r in results:
    out.append({
        "variant": r.variant, "regime": r.regime, "n_bars": r.n_bars, "n_episodes": r.n_episodes,
        "pnl_usd": r.pnl_usd, "max_dd_pct": r.max_dd_pct, "sortino": r.sortino,
        "n_trades": r.n_trades, "mean_episode_bars": r.mean_episode_bars,
        "side_used": r.side_used, "edge_cases": r.edge_cases, "notes": r.notes,
    })
Path("docs/RESEARCH").mkdir(parents=True, exist_ok=True)
Path("docs/RESEARCH/_p8_raw_results.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("\nraw: docs/RESEARCH/_p8_raw_results.json")
