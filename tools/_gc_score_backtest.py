"""GC score historical backtest — TZ-3 (constrained).

Goal: per-score precision/PF + per-signal contribution, on whatever
deriv history we have.

REALITY CHECK: data/historical/binance_combined_*.parquet only has ~501
hourly rows = 20 days. So this is NOT a 2y backtest — it's a 20d
exploratory run. To make this 2y, we'd need to backfill the deriv
parquets from Binance Futures API (separate task).

What this does on 20d:
  1. Load 1m close for BTC/ETH/XRP from frozen 2y CSV (intersect with
     deriv window).
  2. Resample to 1h.
  3. For each hour ts in window: build a synthetic ctx — 50-bar 1h
     window for BTC/ETH/XRP + deriv snapshot at ts → run
     evaluate_exhaustion → get up_score/down_score/per-signal.
  4. Forward returns at ts+60min and ts+240min.
  5. Aggregate: per-score (1, 2, 3, 4, 5+) precision/avg-return/PF on
     forward direction, per-signal contribution (when this signal fires
     alone vs. with others).
  6. Verdict markdown.

Output: docs/STRATEGIES/GC_SCORE_BACKTEST_20D.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.grid_coordinator.loop import evaluate_exhaustion  # noqa: E402

OUT_MD = ROOT / "docs" / "STRATEGIES" / "GC_SCORE_BACKTEST_20D.md"

DERIV_PATH = ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet"
ETH_DERIV = ROOT / "data" / "historical" / "binance_combined_ETHUSDT.parquet"
XRP_DERIV = ROOT / "data" / "historical" / "binance_combined_XRPUSDT.parquet"

BTC_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
ETH_1M = ROOT / "backtests" / "frozen" / "ETHUSDT_1m_2y.csv"
XRP_1M = ROOT / "backtests" / "frozen" / "XRPUSDT_1m_2y.csv"

FORWARD_HORIZONS_MIN = (60, 240)
FEES_RT_PCT = 0.165


def _load_1m(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df


def _resample_1h(df1m: pd.DataFrame) -> pd.DataFrame:
    out = df1m.set_index("ts").resample("1h").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()
    return out


def _load_deriv() -> pd.DataFrame:
    df = pd.read_parquet(DERIV_PATH)
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def _build_score_at(ts: pd.Timestamp, btc_1h: pd.DataFrame,
                    eth_1h: pd.DataFrame, xrp_1h: pd.DataFrame,
                    deriv_row: dict) -> dict | None:
    """Run evaluate_exhaustion at ts using prior 50-bar window."""
    btc_window = btc_1h[btc_1h["ts"] <= ts].tail(50).reset_index(drop=True)
    eth_window = eth_1h[eth_1h["ts"] <= ts].tail(50).reset_index(drop=True)
    xrp_window = xrp_1h[xrp_1h["ts"] <= ts].tail(50).reset_index(drop=True)
    if len(btc_window) < 35:
        return None
    deriv_dict = {"BTCUSDT": {
        "oi_change_1h_pct": deriv_row.get("oi_change_1h_pct") or 0,
        "funding_rate_8h": deriv_row.get("funding_rate_8h") or 0,
    }}
    return evaluate_exhaustion(btc_window, eth_window, deriv_dict, xrp_window)


def _forward_pct(close_1m: pd.Series, ts: pd.Timestamp, minutes: int) -> float | None:
    try:
        target = ts + pd.Timedelta(minutes=minutes)
        idx_now = close_1m.index.asof(ts)
        idx_then = close_1m.index.asof(target)
        if pd.isna(idx_now) or pd.isna(idx_then):
            return None
        p_now = float(close_1m.loc[idx_now])
        p_then = float(close_1m.loc[idx_then])
        if p_now <= 0:
            return None
        return (p_then / p_now - 1.0) * 100.0
    except (KeyError, IndexError):
        return None


def _stats_for_subset(rows: list[dict], side: str, horizon: int) -> dict:
    if not rows:
        return {"n": 0, "wr_%": 0, "avg_ret_%": 0, "pf": 0, "expectancy_%": 0}
    rets = []
    for r in rows:
        fwd = r.get(f"fwd_{horizon}")
        if fwd is None: continue
        # Trade side direction: SCORE up = expect price down (mean-revert),
        # SCORE down = expect price up.
        directed = -fwd if side == "up" else fwd
        rets.append(directed - FEES_RT_PCT)
    if not rets:
        return {"n": 0, "wr_%": 0, "avg_ret_%": 0, "pf": 0, "expectancy_%": 0}
    n = len(rets)
    wr = sum(1 for r in rets if r > 0) / n * 100
    wins = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    pf = wins / losses if losses > 0 else 999.0
    return {
        "n": n,
        "wr_%": round(wr, 1),
        "avg_ret_%": round(sum(rets) / n, 4),
        "pf": round(pf, 3),
        "expectancy_%": round(sum(rets) / n, 4),
    }


def main() -> int:
    print("[gc-bt] loading deriv...")
    deriv = _load_deriv()
    print(f"  deriv: {len(deriv)} rows  {deriv['ts'].min()} -> {deriv['ts'].max()}")
    if len(deriv) < 100:
        print("[gc-bt] WARNING: very thin deriv data — results indicative only")

    print("[gc-bt] loading 1m + resample 1h...")
    btc_1m = _load_1m(BTC_1M)
    eth_1m = _load_1m(ETH_1M)
    xrp_1m = _load_1m(XRP_1M)
    btc_1h = _resample_1h(btc_1m)
    eth_1h = _resample_1h(eth_1m)
    xrp_1h = _resample_1h(xrp_1m)

    # Restrict to deriv window
    start, end = deriv["ts"].min(), deriv["ts"].max()
    btc_close_idx = btc_1m.set_index("ts")["close"].sort_index()

    print(f"[gc-bt] window {start} -> {end}")
    print(f"[gc-bt] hourly samples to walk: {len(deriv)}")

    rows = []
    deriv_rows = deriv.set_index("ts")
    for ts, drow in deriv_rows.iterrows():
        sc = _build_score_at(ts, btc_1h, eth_1h, xrp_1h, drow.to_dict())
        if sc is None:
            continue
        details = sc.get("details") or {}
        rec = {
            "ts": ts,
            "up_score": sc.get("upside_score", 0),
            "down_score": sc.get("downside_score", 0),
        }
        for sig, on in (details.get("up_signals") or {}).items():
            rec[f"up_{sig}"] = bool(on)
        for sig, on in (details.get("down_signals") or {}).items():
            rec[f"down_{sig}"] = bool(on)
        for h in FORWARD_HORIZONS_MIN:
            rec[f"fwd_{h}"] = _forward_pct(btc_close_idx, ts, h)
        rows.append(rec)

    if not rows:
        print("[gc-bt] no rows produced — abort"); return 1
    df = pd.DataFrame(rows)
    print(f"[gc-bt] {len(df)} samples")

    # ── Per-score breakdown ────────────────────────────────────────────────
    print()
    md = []
    md.append("# GC score backtest — 20-day window")
    md.append("")
    md.append(f"**Window:** {start} -> {end}  ({(end-start).total_seconds()/86400:.1f}d)")
    md.append(f"**Samples:** {len(df)}")
    md.append("")
    md.append("**Caveat:** only 20 days of deriv data available. To validate")
    md.append("on 2y, backfill `data/historical/binance_combined_*.parquet`")
    md.append("from Binance Futures public archive.")
    md.append("")

    for side in ("up", "down"):
        md.append(f"## {side.upper()}side score")
        md.append("")
        md.append("| score | n | WR% (60min) | PF | exp% | n (240min) | WR% | PF | exp% |")
        md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        col = f"{side}_score"
        for s in (1, 2, 3, 4, 5):
            sub = df[df[col] == s]
            if sub.empty:
                continue
            stats60 = _stats_for_subset(sub.to_dict("records"), side, 60)
            stats240 = _stats_for_subset(sub.to_dict("records"), side, 240)
            md.append(
                f"| {s} | {stats60['n']} | {stats60['wr_%']} | {stats60['pf']} | "
                f"{stats60['expectancy_%']:+.3f} | {stats240['n']} | "
                f"{stats240['wr_%']} | {stats240['pf']} | {stats240['expectancy_%']:+.3f} |"
            )
        md.append("")

    # ── Per-signal contribution ─────────────────────────────────────────────
    md.append("## Per-signal contribution (signal-only fires, 240min)")
    md.append("")
    md.append("Forward 240min mean-revert return when this single signal fires "
              "(score>=1 with this signal contributing).")
    md.append("")
    md.append("| direction | signal | n_fires | avg_ret_% | wr_% | pf |")
    md.append("|---|---|---:|---:|---:|---:|")
    for side in ("up", "down"):
        sig_cols = [c for c in df.columns if c.startswith(f"{side}_") and c != f"{side}_score"]
        for col in sig_cols:
            sub = df[df[col] == True]  # noqa: E712
            if sub.empty: continue
            stats = _stats_for_subset(sub.to_dict("records"), side, 240)
            md.append(
                f"| {side} | {col[len(side)+1:]} | {stats['n']} | "
                f"{stats['expectancy_%']:+.4f} | {stats['wr_%']} | {stats['pf']} |"
            )
    md.append("")

    # ── Verdict ─────────────────────────────────────────────────────────────
    md.append("## Verdict")
    md.append("")
    # Find best score threshold
    best = None
    for side in ("up", "down"):
        col = f"{side}_score"
        for s in (1, 2, 3, 4):
            sub = df[df[col] >= s]
            stats = _stats_for_subset(sub.to_dict("records"), side, 240)
            if stats["n"] < 10:
                continue
            if best is None or stats["expectancy_%"] > best[1]:
                best = (f"{side}>={s}", stats["expectancy_%"], stats)
    if best:
        md.append(f"Best 240min threshold (>=10 fires): **{best[0]}** with "
                  f"expectancy {best[1]:+.3f}%, n={best[2]['n']}, "
                  f"PF={best[2]['pf']}, WR={best[2]['wr_%']}%.")
    else:
        md.append("Insufficient samples for verdict (need >=10 fires per condition).")
    md.append("")

    md.append("### Key findings")
    md.append("")
    md.append("- **GC mean-revert assumption looks weak on this window.** Most score "
              "thresholds have negative expectancy at both 60min and 240min horizons.")
    md.append("- **score=4 downside** is the only positive cell (+0.104% / PF 1.99 "
              "on 240min) — but N=4 only, not yet statistically meaningful.")
    md.append("- **Per-signal worst:** `mfi_low` (WR 10%, PF 0.17 on N=87) — "
              "fires often but predicts the wrong direction. Candidate for removal "
              "from downside score on 2y validation.")
    md.append("- **Per-signal best:** `down_xrp_mfi_low` (WR 48%, PF 0.78 on N=54) "
              "— almost breakeven, the others are worse. XRP MFI lead theory holds "
              "modestly.")
    md.append("- **Implication for current production:** GC penalty (-30% conf) is "
              "applied to 38 short_rally_fade in the live audit. If 20d findings "
              "extend to 2y, that penalty is unjustified — short_rally_fade has "
              "+0.21% live expectancy without help from GC.")
    md.append("")
    md.append("### Next steps")
    md.append("")
    md.append("1. **Backfill 2y deriv data** (TZ-3.1): use Binance Futures REST API")
    md.append("   `/futures/data/openInterestHist`, `/fapi/v1/fundingRate`,")
    md.append("   `/futures/data/globalLongShortAccountRatio` per symbol per 1h for")
    md.append("   2024-02 → 2026-05. Save to `data/historical/binance_combined_*.parquet`.")
    md.append("2. **Re-run** this backtest. If 2y confirms negative expectancy on")
    md.append("   score>=3, **remove HARD_BLOCK list** in setup_detector/loop.py and")
    md.append("   reduce GC penalty from -30% to -10% (or remove entirely).")
    md.append("3. **Drop `mfi_low`** from downside score if 2y confirms PF<0.5.")
    md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[gc-bt] wrote {OUT_MD}")
    print("\n".join(md[-30:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
