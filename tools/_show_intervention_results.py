"""Показ детальных per-window результатов бэктеста интервенций."""
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
md = (ROOT / "docs" / "STRATEGIES" / "GRID_INTERVENTIONS_v1.md").read_text(encoding="utf-8")

rows = []
pattern = re.compile(
    r"\|\s*(\d+)\s*\|\s*`(\w+)`\s*\|\s*\$([\d,]+)\s*\|\s*\$([+-]?[\d.]+)\s*\|\s*\$([+-]?[\d.]+)\s*\|\s*\$([+-]?[\d.]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
)
for line in md.split("\n"):
    m = pattern.search(line)
    if m:
        rows.append({
            "window": int(m.group(1)),
            "scenario": m.group(2),
            "volume": int(m.group(3).replace(",", "")),
            "net": float(m.group(4)),
            "unrl": float(m.group(5)),
            "dd": float(m.group(6)),
            "trades": int(m.group(7)),
            "interv": int(m.group(8)),
        })

df = pd.DataFrame(rows)
print(f"Total records: {len(df)} (11 окон × 5 сценариев = 55 ожидаемых)\n")

print("=" * 100)
print("VOLUME per window (тыс. $)")
print("=" * 100)
piv = df.pivot(index="window", columns="scenario", values="volume") / 1000
print(piv.round(0).to_string())

print()
print("=" * 100)
print("NET PnL per window ($)")
print("=" * 100)
piv = df.pivot(index="window", columns="scenario", values="net")
print(piv.round(1).to_string())

print()
print("=" * 100)
print("Max single-window DD per window ($)")
print("=" * 100)
piv = df.pivot(index="window", columns="scenario", values="dd")
print(piv.round(1).to_string())

print()
print("=" * 100)
print("Trades per window")
print("=" * 100)
piv = df.pivot(index="window", columns="scenario", values="trades")
print(piv.round(0).to_string())

print()
print("=" * 100)
print("Interventions per window (сколько раз сработали правила)")
print("=" * 100)
piv = df.pivot(index="window", columns="scenario", values="interv")
print(piv.round(0).to_string())

print()
print("=" * 100)
print("AGGREGATE (всё вместе по 11 окнам)")
print("=" * 100)
agg = df.groupby("scenario").agg(
    avg_vol_k=("volume", lambda x: x.mean()/1000),
    sum_vol_k=("volume", lambda x: x.sum()/1000),
    avg_net=("net", "mean"),
    worst_net=("net", "min"),
    avg_dd=("dd", "mean"),
    worst_dd=("dd", "min"),
    avg_trades=("trades", "mean"),
    avg_interv=("interv", "mean"),
).round(1)
print(agg.to_string())

print()
print("=" * 100)
print("РАЗНИЦА vs baseline (per-window)")
print("=" * 100)
for scen in ["pause_on_drawdown", "partial_unload_on_retrace", "trend_chase", "combined"]:
    print(f"\n>>> {scen} vs baseline <<<")
    base = df[df["scenario"] == "baseline"].set_index("window")
    s = df[df["scenario"] == scen].set_index("window")
    diff = pd.DataFrame({
        "vol_keep_pct": (s["volume"] / base["volume"] * 100).round(1),
        "net_diff": (s["net"] - base["net"]).round(1),
        "dd_diff": (s["dd"] - base["dd"]).round(1),
    })
    print(diff.to_string())
