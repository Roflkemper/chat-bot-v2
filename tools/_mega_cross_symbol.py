"""Cross-symbol mega-pair backtest (TZ #3, 2026-05-10).

Hypothesis: if dump_reversal + pdl_bounce confluence works on BTC (PF 1.40
on 2y), maybe it works on ETH/XRP too. Diversification across symbols.

Approach:
  1. Run mega-pair backtest on each symbol's 1m frozen data:
     - BTCUSDT (proven)
     - ETHUSDT
     - XRPUSDT
  2. Same params: SL=0.8% TP1=2.5RR window=60min dedup=4h
  3. Compare PF/PnL/WR per symbol.
  4. Verdict: which symbols deserve mega-pair wire?
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_detectors_honest import (  # noqa: E402
    _build_aggregations, _emit_setups, _simulate_trade, _StubCtx,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "MEGA_CROSS_SYMBOL.md"

LOOKBACK_DAYS = 365
WINDOW_MIN = 60
DEDUP_HOURS = 4
SL_PCT = 0.8
TP1_RR = 2.5
TP2_RR = 5.0
N_FOLDS = 4

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
CONSTITUENTS = ("detect_long_dump_reversal", "detect_long_pdl_bounce")


def _load_1m(symbol: str) -> pd.DataFrame:
    p = ROOT / "backtests" / "frozen" / f"{symbol}_1m_2y.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    return df.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)


def _find_triggers(emits, df_1m):
    dump = emits.get("detect_long_dump_reversal", [])
    pdl = emits.get("detect_long_pdl_bounce", [])
    if not dump or not pdl:
        return []
    window_ms = WINDOW_MIN * 60 * 1000
    dedup_ms = DEDUP_HOURS * 3600 * 1000
    triggers = []
    last = None
    for p in pdl:
        if last is not None and (p["ts"] - last) < dedup_ms:
            continue
        nearby = [d for d in dump if abs(d["ts"] - p["ts"]) <= window_ms]
        if not nearby:
            continue
        dump_match = max(nearby, key=lambda d: d["ts"])
        trigger_ts = max(p["ts"], dump_match["ts"])
        idx = int(np.searchsorted(df_1m["ts"].values, trigger_ts, side="right")) - 1
        if idx < 0 or idx >= len(df_1m):
            continue
        entry = float(df_1m["close"].iloc[idx])
        if entry <= 0:
            continue
        triggers.append({
            "bar_idx": idx, "ts": trigger_ts, "side": "long",
            "setup_type": "mega_long", "entry": entry,
            "sl": entry * (1 - SL_PCT / 100),
            "tp1": entry * (1 + SL_PCT * TP1_RR / 100),
            "tp2": entry * (1 + SL_PCT * TP2_RR / 100),
            "window_min": 240,
        })
        last = trigger_ts
    return triggers


def _summary(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "pf": 0.0, "total_pnl_pct": 0.0, "avg_pnl_pct": 0.0}
    df = pd.DataFrame(trades)
    n = len(df)
    wins = df[df["pnl_pct"] > 0]["pnl_pct"].sum()
    losses = -df[df["pnl_pct"] < 0]["pnl_pct"].sum()
    pf = (wins / losses) if losses > 0 else (999.0 if wins > 0 else 0.0)
    return {
        "n": n,
        "wr": round((df["pnl_pct"] > 0).sum() / n * 100, 1),
        "pf": round(pf, 3),
        "total_pnl_pct": round(df["pnl_pct"].sum(), 2),
        "avg_pnl_pct": round(df["pnl_pct"].mean(), 4),
    }


def _walk_forward(triggers, df_1m, n_folds=N_FOLDS):
    fold_size = len(df_1m) // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else len(df_1m)
        ftr = [t for t in triggers if start <= t["bar_idx"] < end]
        trades = []
        for t in ftr:
            r = _simulate_trade(t, df_1m)
            trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        out.append({"fold": k + 1, **_summary(trades)})
    return out


def main() -> int:
    rows = []
    fold_rows = []

    from services.setup_detector.setup_types import DETECTOR_REGISTRY

    # Patch _emit_setups to use the symbol's pair
    for symbol in SYMBOLS:
        print(f"\n=== {symbol} ===")
        df_1m = _load_1m(symbol)
        if df_1m.empty:
            print(f"[{symbol}] no data, skip")
            continue
        print(f"[{symbol}] {len(df_1m):,} 1m bars")
        df_15m, df_1h = _build_aggregations(df_1m)

        # Override pair in _emit_setups context — we need to monkeypatch the
        # _StubCtx to use this symbol's pair for proper detector behavior
        # (some detectors check ctx.pair; default in _emit_setups is "BTCUSDT").
        # We'll do a minimal local copy of _emit_setups with pair override.
        emits = {}
        for det_fn in DETECTOR_REGISTRY:
            if det_fn.__name__ not in CONSTITUENTS:
                continue
            # Custom emit: same as _emit_setups but with symbol-specific pair
            local = _emit_with_pair(det_fn, df_1m, df_15m, df_1h, pair=symbol)
            emits[det_fn.__name__] = local
            print(f"  {det_fn.__name__}: {len(local)} emits")

        if not all(emits.get(c) for c in CONSTITUENTS):
            print(f"[{symbol}] one constituent has 0 emits, skip")
            rows.append({"symbol": symbol, "n_triggers": 0, "PF": 0,
                         "total_pnl_pct": 0, "verdict": "no_data"})
            continue

        trigs = _find_triggers(emits, df_1m)
        print(f"[{symbol}] {len(trigs)} mega triggers")
        if not trigs:
            rows.append({"symbol": symbol, "n_triggers": 0, "PF": 0,
                         "total_pnl_pct": 0, "verdict": "no_triggers"})
            continue

        trades = []
        for t in trigs:
            r = _simulate_trade(t, df_1m)
            trades.append({"ts": t["ts"], "outcome": r.outcome, "pnl_pct": r.pnl_pct})
        s = _summary(trades)
        wf = _walk_forward(trigs, df_1m)
        pos = sum(1 for f in wf if f["pf"] >= 1.3 and f["n"] >= 5)
        verdict = ("STABLE" if s["pf"] >= 1.4 and pos >= 3 else
                   "MARGINAL" if s["pf"] >= 1.2 and pos >= 2 else
                   "OVERFIT")
        rows.append({
            "symbol": symbol, "n_triggers": s["n"], "WR": s["wr"], "PF": s["pf"],
            "total_pnl_pct": s["total_pnl_pct"], "wf_pos_folds": f"{pos}/{N_FOLDS}",
            "verdict": verdict,
        })
        for f in wf:
            f["symbol"] = symbol
            fold_rows.append(f)
        print(f"[{symbol}] PF={s['pf']}, PnL={s['total_pnl_pct']}%, WF {pos}/{N_FOLDS}, "
              f"verdict={verdict}")

    df_out = pd.DataFrame(rows)
    df_folds = pd.DataFrame(fold_rows)

    md = []
    md.append("# Cross-symbol mega-pair backtest")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d | **Constituents:** dump_reversal + pdl_bounce")
    md.append(f"**Trade params:** SL=-{SL_PCT}% TP1=+{SL_PCT*TP1_RR}% TP2=+{SL_PCT*TP2_RR}% hold=240min")
    md.append("")
    md.append("## Per-symbol summary")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Walk-forward folds per symbol")
    md.append("")
    if len(df_folds):
        md.append(df_folds.to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    stable = df_out[df_out["verdict"] == "STABLE"]
    if len(stable) > 1:
        md.append(f"✅ **Multi-symbol diversification works:** {len(stable)} symbols "
                  f"give STABLE mega-pair edge. Wire each symbol's mega in setup_detector.")
    elif len(stable) == 1:
        sym = stable.iloc[0]["symbol"]
        md.append(f"🟡 **Only {sym} is STABLE.** Mega-pair edge is BTC-specific so far.")
    else:
        md.append(f"❌ **No symbol gives STABLE mega-pair edge** in this backtest. "
                  f"BTC PF was 1.4 over 2y but apparently breaks when applied per-symbol "
                  f"with same params.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[mega-cross] wrote {OUT_MD}")
    return 0


def _emit_with_pair(detector, df_1m, df_15m, df_1h, pair: str, freq_bars: int = 60):
    """Mirror of _emit_setups but with pair override and basic context."""
    from services.setup_detector.setup_types import PortfolioSnapshot
    emits = []
    n = len(df_1m)
    min_1h_bars = 250
    min_15m_bars = 100
    ts_1m = df_1m["ts"].values
    ts_1h = df_1h["ts"].values
    ts_15m = df_15m["ts"].values
    for i in range(0, n, freq_bars):
        if i < 60 * 24:
            continue
        h_idx = np.searchsorted(ts_1h, ts_1m[i], side="right") - 1
        if h_idx < min_1h_bars:
            continue
        m15_idx = np.searchsorted(ts_15m, ts_1m[i], side="right") - 1
        if m15_idx < min_15m_bars:
            continue
        sub_1h = df_1h.iloc[max(0, h_idx - min_1h_bars):h_idx + 1].reset_index(drop=True)
        sub_15m = df_15m.iloc[max(0, m15_idx - min_15m_bars):m15_idx + 1].reset_index(drop=True)
        sub_1m = df_1m.iloc[max(0, i - 200):i + 1].reset_index(drop=True)
        ctx = _StubCtx(
            pair=pair,
            current_price=float(df_1m["close"].iloc[i]),
            regime_label="range_wide",
            session_label="ny_am",
            ohlcv_1m=sub_1m, ohlcv_1h=sub_1h, ohlcv_15m=sub_15m,
        )
        try:
            setup = detector(ctx)
        except Exception:
            continue
        if setup is None: continue
        if setup.setup_type.value.startswith("p15_"): continue
        if setup.entry_price is None or setup.stop_price is None or setup.tp1_price is None:
            continue
        emits.append({
            "bar_idx": i, "ts": int(df_1m["ts"].iloc[i]),
            "setup_type": setup.setup_type.value,
            "side": "long" if "long" in setup.setup_type.value else "short",
            "entry": float(setup.entry_price), "sl": float(setup.stop_price),
            "tp1": float(setup.tp1_price),
            "tp2": float(setup.tp2_price) if setup.tp2_price else float(setup.tp1_price),
            "window_min": int(setup.window_minutes or 240),
        })
    return emits


if __name__ == "__main__":
    sys.exit(main())
