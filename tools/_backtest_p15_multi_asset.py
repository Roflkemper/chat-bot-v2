"""P-15 across BTC / ETH / XRP — multi-asset backtest.

Reuses _backtest_p15_full.simulate_harvest with best params (R=0.3, K=1.0,
dd_cap=3.0). Tests on each asset's 1h data over 2y. Reports PnL, PF,
Sharpe, walk-forward stability per asset.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from _backtest_p15_full import simulate_harvest, walk_forward  # noqa: E402

ASSETS = [
    ("BTCUSDT", "backtests/frozen/BTCUSDT_1h_2y.csv"),
    ("ETHUSDT", "backtests/frozen/ETHUSDT_1h_2y.csv"),
    ("XRPUSDT", "backtests/frozen/XRPUSDT_1h_2y.csv"),
]

PARAMS = dict(R_pct=0.3, K_pct=1.0, dd_cap_pct=3.0)


def main() -> int:
    print("=" * 100)
    print("P-15 MULTI-ASSET BACKTEST (1h, 2y, R=0.3, K=1.0, dd_cap=3.0)")
    print("=" * 100)
    print(f"{'asset':<10} | {'dir':<5} | {'N':>5} | {'WR%':>5} | {'PF':>5} | {'avg$':>6} | {'PnL$':>9} | {'Sharpe':>6} | folds_pos/4")
    print("-" * 100)

    summary = {}

    for asset, path in ASSETS:
        if not Path(path).exists():
            print(f"{asset:<10} | NO DATA at {path}")
            continue
        df = pd.read_csv(path).reset_index(drop=True)
        for direction in ("long", "short"):
            m = simulate_harvest(df, direction=direction, **PARAMS)
            # Walk-forward 4 folds
            wf = walk_forward(df, simulate_harvest,
                              dict(direction=direction, **PARAMS), n_folds=4)
            folds_positive = sum(1 for f in wf if f["total"] > 0)
            pf = f"{m['PF']:.2f}" if m['PF'] != float('inf') else " inf"
            print(f"{asset:<10} | {direction:<5} | {m['N']:>5} | "
                  f"{m['WR']:>5.1f} | {pf:>5} | {m['avg']:>+6.1f} | "
                  f"{m['total']:>+9.0f} | {m['sharpe']:>6.2f} | {folds_positive}/4")
            summary[(asset, direction)] = {
                "N": m["N"], "WR": m["WR"], "PF": m["PF"],
                "PnL": m["total"], "sharpe": m["sharpe"],
                "folds_positive": folds_positive,
            }

    # Acceptance per (asset, direction)
    print()
    print("=" * 100)
    print("ACCEPTANCE per asset (PF>1.5 + folds>=3/4 positive => CONFIRMED for production)")
    print("=" * 100)
    confirmed = []
    rejected = []
    for (asset, dir_), m in summary.items():
        ok_pf = m["PF"] >= 1.5
        ok_wf = m["folds_positive"] >= 3
        verdict = "CONFIRMED" if (ok_pf and ok_wf) else "REJECTED"
        status = []
        if not ok_pf:
            status.append(f"PF={m['PF']:.2f}<1.5")
        if not ok_wf:
            status.append(f"folds={m['folds_positive']}/4<3")
        suffix = f" ({', '.join(status)})" if status else ""
        print(f"  {asset} {dir_:<5} -> {verdict}{suffix}")
        if verdict == "CONFIRMED":
            confirmed.append(f"{asset}/{dir_}")
        else:
            rejected.append(f"{asset}/{dir_}")

    print()
    print(f"CONFIRMED ({len(confirmed)}): {', '.join(confirmed)}")
    if rejected:
        print(f"REJECTED ({len(rejected)}): {', '.join(rejected)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
