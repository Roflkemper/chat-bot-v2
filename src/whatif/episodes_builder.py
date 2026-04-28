"""Build multi-asset episodes.parquet from 1m OHLCV for BTC/ETH/XRP.

Usage:
    python -m src.whatif.episodes_builder --symbols BTC,ETH,XRP
    python -m src.whatif.episodes_builder --symbols BTC          # BTC-only (legacy)
    python -m src.whatif.episodes_builder --symbols BTC,ETH,XRP --dry-run

Inputs:
    frozen/BTCUSDT_1m.parquet  OR  backtests/frozen/BTCUSDT_1m_2y.csv
    frozen/ETHUSDT_1m.parquet  (downloaded from Binance if missing)
    frozen/XRPUSDT_1m.parquet  (downloaded from Binance if missing)

Outputs:
    frozen/labels/episodes.parquet            (BTC+ETH+XRP combined)
    frozen/labels/episodes.parquet.legacy     (old file renamed, if existed)
    frozen/_metadata.json                     (ts ranges, source, download_date)
    whatif_results/EPISODES_MULTIASSET_<date>.md
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.episodes.extractor import (
    ALL_EPISODE_TYPES,
    _cast_schema,
    _empty_episodes_df,
    extract_from_dataframe,
)
from src.whatif.binance_klines_downloader import download_klines

log = logging.getLogger(__name__)

SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "XRP": "XRPUSDT",
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "XRPUSDT": "XRPUSDT",
}

# Episode types extracted by this builder.
# profit_lock_opportunity and consolidation_after_move use minute-based lookbacks
# in the extractor's state machine and don't work correctly at 1h granularity.
DEFAULT_EPISODE_TYPES = [
    "rally_strong",
    "rally_critical",
    "dump_strong",
    "dump_critical",
    "no_pullback_up_3h",
    "no_pullback_down_3h",
]

_REPORT_DIR = ROOT / "whatif_results"
_FROZEN_DIR = ROOT / "frozen"
_BTC_CSV = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
_EPISODES_OUT = ROOT / "frozen" / "labels" / "episodes.parquet"
_DEFAULT_DAYS = 366


# ── Minimal feature computation ───────────────────────────────────────────────

def _wilder_atr(df_1h: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df_1h["high"]
    low = df_1h["low"]
    prev_close = df_1h["close"].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def _consec_streak(series_bool: pd.Series) -> pd.Series:
    """Vectorised consecutive True-bar counter."""
    vals = series_bool.values
    st = np.zeros(len(vals), dtype=float)
    for i in range(1, len(vals)):
        st[i] = (st[i - 1] + 1.0) if vals[i] else 0.0
    return pd.Series(st, index=series_bool.index)


def _kz_label(hour: int) -> str:
    if hour < 7:
        return "ASIA"
    if hour < 12:
        return "LONDON"
    if hour < 17:
        return "NYAM"
    if hour < 20:
        return "NYLU"
    return "NYPM"


def compute_features_1m(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Compute episode-detection features at 1m granularity.

    delta_1h_pct is computed as close.pct_change(60) on the 1m series, which
    is a rolling 60-minute return. This matches the original feature pipeline
    and captures intra-hour moves that 1h close-to-close misses.

    The extractor's state machine iterates ~525k rows/year per episode type
    (~10s for 6 types on BTC), which is acceptable for the multi-asset builder.

    Returns DataFrame with 1m UTC DatetimeIndex and columns:
        close, high, low, delta_1h_pct, atr_pct_1h,
        kz_active, consec_1h_up, consec_1h_down, consec_bull, consec_bear
    """
    df = df_1m[["open", "high", "low", "close", "volume"]].copy().sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    # Rolling 60-min return (matches original feature pipeline delta_1h_pct)
    df["delta_1h_pct"] = df["close"].pct_change(60) * 100.0

    # 1h bars for ATR and streak features
    df_1h = df.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])

    atr_1h = _wilder_atr(df_1h)
    atr_pct_1h = atr_1h / df_1h["close"] * 100.0

    up_1h = df_1h["close"] > df_1h["close"].shift(1)
    down_1h = df_1h["close"] < df_1h["close"].shift(1)
    streak_up = _consec_streak(up_1h)
    streak_down = _consec_streak(down_1h)

    # Map 1h features back to 1m index (shift +1 no look-ahead, then ffill)
    idx_1m = df.index
    df["atr_pct_1h"] = atr_pct_1h.shift(1).reindex(idx_1m, method="ffill")

    streak_up_1m = streak_up.shift(1).reindex(idx_1m, method="ffill").fillna(0)
    streak_down_1m = streak_down.shift(1).reindex(idx_1m, method="ffill").fillna(0)
    # Both names: alias (consec_1h_up) and direct .get() (consec_bull) paths in extractor
    df["consec_1h_up"] = streak_up_1m
    df["consec_bull"] = streak_up_1m
    df["consec_1h_down"] = streak_down_1m
    df["consec_bear"] = streak_down_1m

    df["kz_active"] = [_kz_label(h) for h in df.index.hour]

    return df[[
        "close", "high", "low",
        "delta_1h_pct", "atr_pct_1h",
        "kz_active",
        "consec_1h_up", "consec_1h_down",
        "consec_bull", "consec_bear",
    ]]


def compute_features_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Compute features at 1h granularity (for quick preview / dry-run only).

    WARNING: 1h close-to-close delta misses intra-hour moves → produces fewer
    rally/dump episodes than the 1m version. Use compute_features_1m for production.
    """
    df = df_1m[["open", "high", "low", "close", "volume"]].copy().sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df_1h = df.resample("1h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    df_1h["delta_1h_pct"] = df_1h["close"].pct_change(1) * 100.0
    atr_1h = _wilder_atr(df_1h)
    df_1h["atr_pct_1h"] = atr_1h / df_1h["close"] * 100.0
    up = df_1h["close"] > df_1h["close"].shift(1)
    down = df_1h["close"] < df_1h["close"].shift(1)
    df_1h["consec_1h_up"] = _consec_streak(up)
    df_1h["consec_bull"] = df_1h["consec_1h_up"]
    df_1h["consec_1h_down"] = _consec_streak(down)
    df_1h["consec_bear"] = df_1h["consec_1h_down"]
    df_1h["kz_active"] = [_kz_label(h) for h in df_1h.index.hour]
    return df_1h[["close", "high", "low", "delta_1h_pct", "atr_pct_1h",
                  "kz_active", "consec_1h_up", "consec_1h_down", "consec_bull", "consec_bear"]]


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_parquet_1m(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


def _load_btc_csv(path: Path, days_back: int = _DEFAULT_DAYS) -> pd.DataFrame:
    log.info("Loading BTC 1m CSV: %s", path)
    df = pd.read_csv(
        path,
        usecols=["ts", "open", "high", "low", "close", "volume"],
        dtype={"ts": "int64"},
    )
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.index.name = "ts"
    df = df.drop(columns=["ts"]).sort_index()
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_back)
    return df[df.index >= cutoff]


def load_1m_ohlcv(
    symbol: str,
    frozen_dir: Path = _FROZEN_DIR,
    days_back: int = _DEFAULT_DAYS,
    download_missing: bool = True,
) -> pd.DataFrame:
    parquet_path = frozen_dir / f"{symbol}_1m.parquet"

    if symbol == "BTCUSDT":
        if parquet_path.exists():
            df = _load_parquet_1m(parquet_path)
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_back)
            return df[df.index >= cutoff]
        if _BTC_CSV.exists():
            return _load_btc_csv(_BTC_CSV, days_back)
        raise FileNotFoundError(f"BTC source not found: {parquet_path} or {_BTC_CSV}")

    if parquet_path.exists():
        return _load_parquet_1m(parquet_path)

    if download_missing:
        log.info("Downloading %s 1m klines (this may take ~10 min)...", symbol)
        print(f"\nDownloading {symbol} 1m klines ({days_back} days)...")
        download_klines(symbol, days_back=days_back, frozen_dir=frozen_dir)
        return _load_parquet_1m(parquet_path)

    raise FileNotFoundError(f"Missing {symbol} data: {parquet_path}")


# ── Main builder ──────────────────────────────────────────────────────────────

def build_episodes(
    symbols: list[str] | None = None,
    frozen_dir: Path = _FROZEN_DIR,
    output: Path = _EPISODES_OUT,
    episode_types: list[str] | None = None,
    days_back: int = _DEFAULT_DAYS,
    dry_run: bool = False,
    download_missing: bool = True,
) -> pd.DataFrame:
    """Build multi-asset episodes.parquet.

    Returns: combined episodes DataFrame (all symbols).
    """
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
    episode_types = episode_types or DEFAULT_EPISODE_TYPES

    log.info("Building episodes: symbols=%s types=%s days=%d", symbols, episode_types, days_back)
    print(f"\n=== Episodes Builder ===")
    print(f"Symbols : {symbols}")
    print(f"Types   : {episode_types}")
    print(f"Days    : {days_back}")
    print(f"Dry-run : {dry_run}\n")

    # Regression baseline: capture BTC episode count before rebuild
    btc_before: int | None = None
    if output.exists():
        try:
            old_df = pd.read_parquet(output)
            btc_before = int((old_df["symbol"] == "BTCUSDT").sum()) if "symbol" in old_df.columns else 0
        except Exception:
            btc_before = None

    frames: list[pd.DataFrame] = []
    metadata: dict = {
        "build_date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days_back": days_back,
        "episode_types": episode_types,
        "symbols": {},
    }

    for symbol in symbols:
        print(f"[{symbol}] Loading 1m data...")
        try:
            df_1m = load_1m_ohlcv(symbol, frozen_dir, days_back, download_missing)
        except FileNotFoundError as exc:
            log.error("Skipping %s: %s", symbol, exc)
            print(f"  ERROR: {exc}")
            continue

        ts_start = df_1m.index.min()
        ts_end = df_1m.index.max()
        print(f"  {symbol}: {len(df_1m):,} bars  {ts_start.date()} to {ts_end.date()}")

        print(f"[{symbol}] Computing features ({len(df_1m):,} 1m bars)...")
        try:
            df_feat = compute_features_1m(df_1m)
        except Exception as exc:
            log.error("Feature computation failed for %s: %s", symbol, exc)
            print(f"  ERROR: {exc}")
            continue

        print(f"[{symbol}] Extracting episodes...")
        eps, warnings = extract_from_dataframe(df_feat, symbol, episode_types)
        for w in warnings:
            log.warning("%s", w)

        counts = eps.groupby("episode_type").size().to_dict() if not eps.empty else {}
        print(f"  Episodes: {counts}")

        if not eps.empty:
            frames.append(eps)

        btc_parquet = frozen_dir / "BTCUSDT_1m.parquet"
        src = (
            str(btc_parquet) if (symbol == "BTCUSDT" and btc_parquet.exists())
            else str(_BTC_CSV) if symbol == "BTCUSDT"
            else str(frozen_dir / f"{symbol}_1m.parquet")
        )
        metadata["symbols"][symbol] = {
            "source": src,
            "bars": len(df_1m),
            "ts_start": ts_start.strftime("%Y-%m-%d"),
            "ts_end": ts_end.strftime("%Y-%m-%d"),
            "episodes": {k: int(v) for k, v in counts.items()},
        }

    if not frames:
        log.error("No episodes extracted for any symbol")
        return _empty_episodes_df()

    all_eps = pd.concat(frames, axis=0, ignore_index=True)
    all_eps = _cast_schema(all_eps).sort_values("ts_start", kind="stable").reset_index(drop=True)

    # Regression check
    btc_after = int((all_eps["symbol"] == "BTCUSDT").sum())
    if btc_before is not None:
        print(f"\nRegression check: BTC episodes before={btc_before}  after={btc_after}")
        # BTC-only migration: old file had profit_lock_opportunity only (no rally/dump)
        # After builder: should have all requested types for BTC
        regression_pass = btc_after >= 10  # at minimum 10 BTC episodes expected
    else:
        regression_pass = btc_after >= 10
    metadata["regression"] = {
        "btc_before": btc_before,
        "btc_after": btc_after,
        "pass": regression_pass,
    }

    print(f"\nTotal episodes: {len(all_eps)}")
    _print_summary(all_eps)
    _sanity_check(all_eps)

    if dry_run:
        print("\n[dry-run] Not saving files.")
        return all_eps

    # Rename old episodes to .legacy
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        legacy = output.with_suffix(".parquet.legacy")
        output.rename(legacy)
        log.info("Renamed old episodes → %s", legacy)

    all_eps.to_parquet(output, compression="zstd", compression_level=3, index=False)
    log.info("Wrote %d episodes → %s", len(all_eps), output)
    print(f"\nSaved: {output}")

    # metadata.json
    meta_path = frozen_dir / "_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    # Report
    report_path = _generate_report(all_eps, metadata, _REPORT_DIR)
    print(f"Report: {report_path}")

    return all_eps


# ── Report generation ─────────────────────────────────────────────────────────

def _print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        return
    counts = df.groupby(["symbol", "episode_type"]).size().reset_index(name="count")
    print("\nEpisode distribution:")
    print(counts.to_string(index=False))


def _sanity_check(df: pd.DataFrame) -> None:
    expected = {
        "rally_strong": (30, 300),
        "rally_critical": (5, 80),
        "dump_strong": (20, 250),
        "dump_critical": (5, 80),
    }
    issues: list[str] = []
    for sym in df["symbol"].unique():
        sym_df = df[df["symbol"] == sym]
        for ep_type, (lo, hi) in expected.items():
            count = int((sym_df["episode_type"] == ep_type).sum())
            if count == 0:
                issues.append(f"  WARN: {sym}/{ep_type} = 0 (expected {lo}-{hi})")
            elif not (lo <= count <= hi):
                issues.append(f"  WARN: {sym}/{ep_type} = {count} outside [{lo},{hi}]")
    if issues:
        print("\nSanity warnings:")
        for issue in issues:
            print(issue)
            log.warning("%s", issue.strip())
    else:
        print("\nSanity check: OK (all episode counts within expected ranges)")


def _generate_report(df: pd.DataFrame, meta: dict, report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    out = report_dir / f"EPISODES_MULTIASSET_{date_str}.md"

    lines: list[str] = [
        f"# EPISODES_MULTIASSET — {date_str}",
        "",
        f"**Build date:** {meta['build_date']}  ",
        f"**Days back:** {meta['days_back']}  ",
        f"**Episode types:** {', '.join(meta['episode_types'])}  ",
        f"**Total episodes:** {len(df)}  ",
        "",
        "## Episode counts by symbol and type",
        "",
    ]

    if not df.empty:
        counts = df.groupby(["symbol", "episode_type"]).size().reset_index(name="count")
        lines.append("| symbol | episode_type | count |")
        lines.append("|--------|-------------|-------|")
        for _, row in counts.iterrows():
            lines.append(f"| {row['symbol']} | {row['episode_type']} | {row['count']} |")
        lines.append("")

    lines += [
        "## Symbol details",
        "",
    ]
    for symbol, info in meta["symbols"].items():
        lines += [
            f"### {symbol}",
            f"- Source: `{info['source']}`",
            f"- Bars: {info['bars']:,}",
            f"- Range: {info['ts_start']} → {info['ts_end']}",
            "",
        ]

    lines += [
        "## Magnitude sanity (rally_critical per symbol)",
        "",
    ]
    if not df.empty:
        rc = df[df["episode_type"] == "rally_critical"]
        if not rc.empty:
            mag = rc.groupby("symbol")["magnitude"].agg(["mean", "min", "max", "count"])
            lines.append("| symbol | mean_mag | min_mag | max_mag | count |")
            lines.append("|--------|----------|---------|---------|-------|")
            for sym, row in mag.iterrows():
                lines.append(
                    f"| {sym} | {row['mean']:.2f}% | {row['min']:.2f}% | {row['max']:.2f}% | {int(row['count'])} |"
                )
            lines.append("")

    lines += [
        "## Regression check (BTC)",
        "",
        f"| metric | value |",
        f"|--------|-------|",
        f"| BTC episodes before rebuild | {meta['regression']['btc_before']} |",
        f"| BTC episodes after rebuild | {meta['regression']['btc_after']} |",
        f"| PASS | {'✓' if meta['regression']['pass'] else '✗'} |",
        "",
    ]

    lines += [
        "## Average magnitude per symbol/type",
        "",
    ]
    if not df.empty:
        agg = df.groupby(["symbol", "episode_type"])["magnitude"].mean().reset_index()
        lines.append("| symbol | episode_type | avg_magnitude |")
        lines.append("|--------|-------------|--------------|")
        for _, row in agg.iterrows():
            lines.append(f"| {row['symbol']} | {row['episode_type']} | {row['magnitude']:.2f}% |")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m src.whatif.episodes_builder",
        description="Build multi-asset episodes.parquet",
    )
    p.add_argument(
        "--symbols",
        default="BTC,ETH,XRP",
        help="Comma-separated symbols: BTC,ETH,XRP or BTCUSDT,ETHUSDT,XRPUSDT",
    )
    p.add_argument(
        "--episode-types",
        default="default",
        help="'default' (rally/dump/no_pullback/profit_lock) or comma-separated list or 'all'",
    )
    p.add_argument("--days", type=int, default=_DEFAULT_DAYS, help="Days of history")
    p.add_argument("--frozen-dir", default=str(_FROZEN_DIR))
    p.add_argument("--output", default=str(_EPISODES_OUT))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-download", action="store_true", help="Fail if ETH/XRP data missing")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)

    symbols = [
        SYMBOL_MAP.get(s.strip().upper(), s.strip().upper())
        for s in args.symbols.split(",")
        if s.strip()
    ]

    if args.episode_types == "default":
        episode_types = DEFAULT_EPISODE_TYPES
    elif args.episode_types == "all":
        episode_types = list(ALL_EPISODE_TYPES)
    else:
        episode_types = [t.strip() for t in args.episode_types.split(",") if t.strip()]

    build_episodes(
        symbols=symbols,
        frozen_dir=Path(args.frozen_dir),
        output=Path(args.output),
        episode_types=episode_types,
        days_back=args.days,
        dry_run=args.dry_run,
        download_missing=not args.no_download,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
