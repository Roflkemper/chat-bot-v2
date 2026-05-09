"""TEST_3 TP-flat dry-run vs real comparison (Variant 4 task).

Reads:
  state/test3_tpflat_paper.jsonl    — sim trades from services.test3_tpflat_simulator
  ginarea_live/snapshots.csv         — TEST_3 real bot snapshots (1-2 min cadence)

Computes side-by-side metrics over the simulation window:
  - realized PnL (sim vs real-delta-realized)
  - drawdown (sim equity curve max-DD vs real current_profit min)
  - volume traded (sim notional vs real trade_volume delta)
  - n trades (sim n_tp + n_forced vs real in_filled_count delta)
  - PnL/$volume bps efficiency

Output: docs/TEST3_TPFLAT_COMPARISON.md + state/test3_tpflat_compare.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAPER_A_PATH = ROOT / "state" / "test3_tpflat_paper.jsonl"   # TP=$10 variant
PAPER_B_PATH = ROOT / "state" / "test3_tpflat_b_paper.jsonl"  # TP=$5 variant
SNAP_PATH = ROOT / "ginarea_live" / "snapshots.csv"
OUT_MD = ROOT / "docs" / "TEST3_TPFLAT_COMPARISON.md"
OUT_HISTORY = ROOT / "state" / "test3_tpflat_compare.jsonl"

TEST3_BOT_ID = "4524162672"  # TEST_3 GinArea bot ID (from snapshots.csv)
# Backward compat alias
PAPER_PATH = PAPER_A_PATH


def _load_paper(path: Path = PAPER_A_PATH) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except (ValueError, TypeError):
                continue
    return out


def _paper_metrics(events: list[dict]) -> dict:
    """Compute sim metrics from paper journal."""
    if not events:
        return {"n_trades": 0, "n_tp": 0, "n_forced": 0, "realized_pnl": 0.0,
                "max_dd": 0.0, "volume": 0.0, "first_ts": None, "last_ts": None,
                "fees_paid": 0.0}

    closes = [e for e in events if e.get("event") in ("CLOSE_TP", "CLOSE_FORCED")]
    n_tp = sum(1 for c in closes if c.get("event") == "CLOSE_TP")
    n_forced = sum(1 for c in closes if c.get("event") == "CLOSE_FORCED")

    pnl_total = float(sum(c.get("pnl_usd", 0) for c in closes))
    fees = float(sum(c.get("fees_usd", 0) for c in closes))

    # Equity curve for max drawdown
    eq = [0.0]
    for c in closes:
        eq.append(eq[-1] + c.get("pnl_usd", 0))
    eq_arr = np.array(eq)
    peak = np.maximum.accumulate(eq_arr)
    max_dd = float((eq_arr - peak).min())

    # Volume: each OPEN + each CLOSE = base_size_usd
    opens = [e for e in events if e.get("event") == "OPEN"]
    base_size = float(opens[0].get("size_usd", 1000.0)) if opens else 1000.0
    n_legs = len(opens)
    volume = float(n_legs * 2 * base_size)  # open + close

    return {
        "n_trades": len(closes),
        "n_tp": n_tp,
        "n_forced": n_forced,
        "realized_pnl": round(pnl_total, 2),
        "max_dd": round(max_dd, 2),
        "volume": round(volume, 0),
        "first_ts": events[0].get("ts"),
        "last_ts": events[-1].get("ts"),
        "fees_paid": round(fees, 2),
    }


def _real_metrics(snap_path: Path, bot_id: str,
                  start_ts: datetime, end_ts: datetime) -> dict:
    """Compute TEST_3 real-bot metrics over [start_ts, end_ts] from snapshots."""
    if not snap_path.exists():
        return {"error": f"{snap_path} not found"}
    df = pd.read_csv(snap_path)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc"])
    df["bot_id"] = df["bot_id"].astype(str).str.replace(".0", "", regex=False)
    sub = df[df["bot_id"] == bot_id].sort_values("ts_utc")
    sub = sub[(sub["ts_utc"] >= start_ts) & (sub["ts_utc"] <= end_ts)]
    if sub.empty:
        return {"error": f"no TEST_3 snapshots in window {start_ts} → {end_ts}"}

    for col in ("profit", "current_profit", "in_filled_count",
                "out_filled_count", "trade_volume"):
        sub[col] = pd.to_numeric(sub[col], errors="coerce").fillna(0.0)

    first = sub.iloc[0]
    last = sub.iloc[-1]
    realized = float(last["profit"]) - float(first["profit"])
    unrealized_now = float(last["current_profit"])
    # Approx max drawdown from current_profit history (mark-to-market)
    cp = sub["current_profit"].values.astype(float)
    cum_realized = sub["profit"].values.astype(float) - float(first["profit"])
    equity = cum_realized + cp
    peak = np.maximum.accumulate(equity)
    max_dd = float((equity - peak).min())

    in_count = int(float(last["in_filled_count"]) - float(first["in_filled_count"]))
    out_count = int(float(last["out_filled_count"]) - float(first["out_filled_count"]))
    vol = float(last["trade_volume"]) - float(first["trade_volume"])

    return {
        "n_in": in_count,
        "n_out": out_count,
        "realized_pnl": round(realized, 2),
        "unrealized_now": round(unrealized_now, 2),
        "max_dd": round(max_dd, 2),
        "volume": round(vol, 0),
        "first_ts": first["ts_utc"].isoformat(),
        "last_ts": last["ts_utc"].isoformat(),
    }


def _format_pct_diff(sim: float, real: float) -> str:
    if abs(real) < 0.01:
        return "n/a"
    diff_pct = (sim - real) / abs(real) * 100
    return f"{diff_pct:+.0f}%"


def _format_report(paper_m: dict, real_m: dict, args: argparse.Namespace) -> str:
    lines: list[str] = []
    lines.append("# TEST_3 TP-flat dry-run vs Real comparison")
    lines.append("")
    lines.append(f"**Window:** {paper_m.get('first_ts')} → {paper_m.get('last_ts')}")
    lines.append(f"**Sim params:** TP=$10, immediate, dd_cap=3%, base=$1000")
    lines.append(f"**Real bot:** TEST_3 (id {TEST3_BOT_ID}, SHORT linear BTCUSDT, "
                 f"target=0.25%, instop=0.030)")
    lines.append("")

    if "error" in real_m:
        lines.append(f"## ❌ {real_m['error']}")
        return "\n".join(lines)

    lines.append("## Side-by-side")
    lines.append("")
    lines.append("| Metric | Sim (TP-flat paper) | Real (TEST_3) | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Realized PnL ($) | {paper_m['realized_pnl']:+.2f} | "
                 f"{real_m['realized_pnl']:+.2f} | "
                 f"{_format_pct_diff(paper_m['realized_pnl'], real_m['realized_pnl'])} |")
    lines.append(f"| Max drawdown ($) | {paper_m['max_dd']:+.2f} | "
                 f"{real_m['max_dd']:+.2f} | "
                 f"{_format_pct_diff(paper_m['max_dd'], real_m['max_dd'])} |")
    lines.append(f"| Volume traded ($) | {paper_m['volume']:.0f} | "
                 f"{real_m['volume']:.0f} | "
                 f"{_format_pct_diff(paper_m['volume'], real_m['volume'])} |")
    sim_n = paper_m["n_trades"]
    real_n = real_m["n_in"]
    lines.append(f"| N trades | {sim_n} ({paper_m['n_tp']}TP/{paper_m['n_forced']}F) | "
                 f"{real_n} (in) | {_format_pct_diff(sim_n, real_n)} |")
    sim_eff = (paper_m["realized_pnl"] / paper_m["volume"] * 10000) if paper_m["volume"] > 0 else 0.0
    real_eff = (real_m["realized_pnl"] / real_m["volume"] * 10000) if real_m["volume"] > 0 else 0.0
    lines.append(f"| PnL/Vol (bps) | {sim_eff:+.1f} | {real_eff:+.1f} | "
                 f"{_format_pct_diff(sim_eff, real_eff)} |")
    lines.append("")

    lines.append("## Verdict for migration decision")
    lines.append("")
    days = 0
    try:
        t0 = datetime.fromisoformat(str(paper_m["first_ts"]).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(paper_m["last_ts"]).replace("Z", "+00:00"))
        days = (t1 - t0).total_seconds() / 86400
    except (ValueError, TypeError):
        pass
    lines.append(f"Window: ~{days:.1f} days")
    if days < args.min_days:
        lines.append(f"\n⚠️ **Insufficient sample** — operator request was 7d minimum, "
                     f"only {days:.1f}d collected. Decision should wait.")
        return "\n".join(lines)

    # 3 criteria for TP-flat win
    pnl_ratio = (paper_m["realized_pnl"] / max(real_m["realized_pnl"], 0.01)
                 if real_m["realized_pnl"] > 0 else 999)
    dd_ratio = (paper_m["max_dd"] / real_m["max_dd"]
                if real_m["max_dd"] < -0.01 else 999)
    vol_ratio = (paper_m["volume"] / max(real_m["volume"], 0.01)
                 if real_m["volume"] > 0 else 0)
    pnl_ok = pnl_ratio >= 0.7   # within 30% of real PnL
    dd_ok = dd_ratio < 0.5      # at most 50% of real DD
    vol_ok = vol_ratio >= 0.5   # at least 50% of real volume

    score = sum([pnl_ok, dd_ok, vol_ok])
    lines.append("")
    lines.append(f"- PnL within 30% of real: {'✅' if pnl_ok else '❌'} ({pnl_ratio:.2f}×)")
    lines.append(f"- DD ≤ 50% of real:         {'✅' if dd_ok else '❌'} ({dd_ratio:.2f}×)")
    lines.append(f"- Volume ≥ 50% of real:    {'✅' if vol_ok else '❌'} ({vol_ratio:.2f}×)")
    lines.append("")
    if score >= 2:
        lines.append("**Verdict:** ✅ migrate TEST_3 → TP-flat (2-of-3 criteria met)")
    else:
        lines.append("**Verdict:** ❌ keep TEST_3 grid-bag (not enough advantage)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-days", type=float, default=7.0,
                    help="Minimum sample window for verdict (default 7)")
    ap.add_argument("--bot-id", default=TEST3_BOT_ID)
    args = ap.parse_args()

    events_a = _load_paper(PAPER_A_PATH)
    events_b = _load_paper(PAPER_B_PATH)
    if not events_a and not events_b:
        text = ("❌ /test3_tpflat_compare: оба paper журнала пусты "
                "(state/test3_tpflat_paper.jsonl, "
                "state/test3_tpflat_b_paper.jsonl) — sim ещё не накопил trades.")
        print(text)
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(text, encoding="utf-8")
        return 0

    sections: list[str] = []
    history_rec: dict = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    for label, events in (("A (TP=$10)", events_a), ("B (TP=$5)", events_b)):
        if not events:
            sections.append(f"## {label}\n\nNo events yet.\n")
            continue
        paper_m = _paper_metrics(events)
        if paper_m["first_ts"] is None:
            sections.append(f"## {label}\n\nNo close events.\n")
            continue
        t0 = datetime.fromisoformat(str(paper_m["first_ts"]).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(paper_m["last_ts"]).replace("Z", "+00:00"))
        real_m = _real_metrics(SNAP_PATH, args.bot_id, t0, t1)
        body = _format_report(paper_m, real_m, args)
        # Promote h1 to h2, prepend variant label
        body = body.replace("# TEST_3 TP-flat dry-run vs Real comparison",
                            f"## {label} vs Real")
        sections.append(body)
        history_rec[f"variant_{label[0].lower()}"] = {"paper": paper_m, "real": real_m}

    text = ("# TEST_3 TP-flat A/B comparison vs Real\n\n"
            "Two TP-flat variants are dry-run alongside real TEST_3:\n"
            "- **A:** TP=$10, immediate, dd_cap=3% (operator's primary candidate)\n"
            "- **B:** TP=$5, immediate, dd_cap=3% (higher-frequency alt)\n\n"
            + "\n\n".join(sections))

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(text, encoding="utf-8")
    print(f"wrote {OUT_MD}")

    OUT_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with OUT_HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(history_rec, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
