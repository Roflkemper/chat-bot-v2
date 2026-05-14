"""Ночной батч исследования grid_coordinator на разных TF + walk-forward + PnL-sim.

Запускается оператором перед уходом — пишет финальный отчёт в
docs/STRATEGIES/NIGHT_RESEARCH_2026-05-10.md.

Этапы:
  1. 15m TF retro (90д) — все сигналы + проверка 12 экстремумов оператора +
     intraday-flushes (21 апр 19:46, 29 апр 10:30) которые 1h не ловит.
  2. 1h baseline (90д) — для сравнения с 15m.
  3. 4h TF — крупные развороты, ожидаем выше precision но реже сигналы.
  4. Multi-TF confluence — сигнал засчитывается если 15m+1h согласованы.
  5. Доп. сигнал #6 'low_vol_rally_top' (26 мар) — добавить к 15m только в этом
     отдельном прогоне, посмотреть улучшение.
  6. Walk-forward на 1h — train на первых 60d, test на последних 30d. OOS
     precision — реальная мера (in-sample оптимистичен).
  7. PnL simulation — на каждом TF: вход SHORT/LONG по score>=4, TP +1%, SL -0.5%.
     Holding period max 240мин. Считаем чистый PnL после fee 0.04%/round-trip.
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
except (AttributeError, ValueError):
    pass

from services.grid_coordinator.loop import evaluate_exhaustion  # noqa: E402

DATA_BTC_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
DATA_ETH_1H = ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv"
DATA_DERIV = ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "NIGHT_RESEARCH_2026-05-10.md"

LOOKBACK_DAYS = 90
HORIZONS_MIN = (60, 120, 240)
SUCCESS_PCT = 0.3   # >0.3% в нужную сторону = TRUE
FAIL_PCT = 0.3
SCORE_THRESHOLDS = (3, 4)

# Operator-named extrema (12 events with corrected interpretations)
EXTREMA = [
    ("2026-03-17 01:35", "high", "17 Mar very fat"),
    ("2026-03-26 00:49", "high", "26 Mar (low-vol distribution top, -6.9% drop)"),
    ("2026-04-12 22:30", "low",  "12 Apr fat low"),
    ("2026-04-14 14:32", "high", "14 Apr (+7.5% rally peak)"),
    ("2026-04-17 16:23", "high", "17 Apr"),
    ("2026-04-20 00:00", "low",  "20 Apr fat low"),
    ("2026-04-21 19:46", "low",  "21 Apr (intraday flush)"),
    ("2026-04-22 16:05", "high", "22 Apr"),
    ("2026-04-27 01:01", "high", "27 Apr"),
    ("2026-04-28 14:41", "low",  "28 Apr"),
    ("2026-04-29 10:30", "high", "29 Apr (intraday spike)"),
    ("2026-04-29 18:10", "low",  "29 Apr fat low"),
]


def _build_tf(df_1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    df = df_1m.set_index("ts_utc").resample(rule).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()
    return df


def _load_data():
    df = pd.read_csv(DATA_BTC_1M)
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    cutoff = df["ts_utc"].max() - pd.Timedelta(days=LOOKBACK_DAYS)
    df = df[df["ts_utc"] >= cutoff].reset_index(drop=True)

    eth = pd.read_csv(DATA_ETH_1H)
    if "ts_utc" not in eth.columns:
        eth["ts_utc"] = pd.to_datetime(eth["ts"], unit="ms", utc=True)
    else:
        eth["ts_utc"] = pd.to_datetime(eth["ts_utc"], utc=True)

    deriv = pd.read_parquet(DATA_DERIV)
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)
    deriv = deriv.set_index("ts_utc").sort_index()
    return df, eth, deriv


def _deriv_at(deriv_df: pd.DataFrame, ts: pd.Timestamp) -> dict:
    if ts < deriv_df.index[0] or ts > deriv_df.index[-1]:
        return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
    try:
        row = deriv_df.loc[deriv_df.index.asof(ts)]
    except (KeyError, ValueError):
        return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}

    def _f(v, default=0.0):
        try:
            f = float(v)
            return default if pd.isna(f) else f
        except (TypeError, ValueError):
            return default

    return {
        "oi_change_1h_pct": _f(row.get("oi_change_1h_pct"), 0.0),
        "funding_rate_8h": _f(row.get("funding_rate_8h"), 0.0),
        "global_ls_ratio": _f(row.get("global_ls_ratio"), 1.0),
    }


def _scan_tf(df_tf: pd.DataFrame, eth: pd.DataFrame, deriv: pd.DataFrame,
             window_bars: int, eval_func=None) -> pd.DataFrame:
    """Идём по барам, для каждого бара считаем score; возвращаем все сигналы score>=2."""
    if eval_func is None:
        eval_func = evaluate_exhaustion
    rows = []
    if len(df_tf) <= window_bars:
        return pd.DataFrame(columns=["ts", "direction", "score", "price", "rsi", "mfi", "vol_z"])
    for i in range(window_bars, len(df_tf)):
        sub = df_tf.iloc[i - window_bars:i + 1].reset_index(drop=True)
        ts = sub.iloc[-1]["ts_utc"]
        # ETH window — ETH у нас всегда 1h
        eth_w = eth[eth["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        ev = eval_func(sub, sub_eth, {"BTCUSDT": _deriv_at(deriv, ts)})
        for direction in ("upside", "downside"):
            score = ev[f"{direction}_score"]
            if score >= 2:
                rows.append({
                    "ts": ts,
                    "direction": direction,
                    "score": score,
                    "price": float(sub.iloc[-1]["close"]),
                    "rsi": ev["details"]["rsi_btc_now"],
                    "mfi": ev["details"]["mfi_btc_now"],
                    "vol_z": ev["details"]["vol_z_now"],
                })
    if not rows:
        return pd.DataFrame(columns=["ts", "direction", "score", "price", "rsi", "mfi", "vol_z"])
    return pd.DataFrame(rows)


def _evaluate_outcomes(signals: pd.DataFrame, df_1m: pd.DataFrame) -> pd.DataFrame:
    """Для каждого сигнала смотрим что было через 60/120/240 минут."""
    if signals is None or len(signals) == 0:
        return pd.DataFrame(columns=["ts", "direction", "score", "horizon_min", "move_pct", "verdict"])
    out = []
    df_1m_idx = df_1m.set_index("ts_utc").sort_index()
    for _, sig in signals.iterrows():
        ts = sig["ts"]
        price0 = sig["price"]
        for h in HORIZONS_MIN:
            target = ts + pd.Timedelta(minutes=h)
            if target > df_1m_idx.index[-1]:
                continue
            try:
                price1 = df_1m_idx.loc[df_1m_idx.index.asof(target)]["close"]
            except (KeyError, IndexError):
                continue
            move_pct = (price1 / price0 - 1) * 100
            # upside-сигнал считается для SHORT-входа: правильно если цена ПАДАЕТ
            if sig["direction"] == "upside":
                if move_pct <= -SUCCESS_PCT: verdict = "TRUE"
                elif move_pct >= FAIL_PCT: verdict = "FALSE"
                else: verdict = "NEUTRAL"
            else:  # downside для LONG-входа: правильно если цена РАСТЁТ
                if move_pct >= SUCCESS_PCT: verdict = "TRUE"
                elif move_pct <= -FAIL_PCT: verdict = "FALSE"
                else: verdict = "NEUTRAL"
            out.append({
                "ts": ts,
                "direction": sig["direction"],
                "score": int(sig["score"]),
                "horizon_min": h,
                "move_pct": round(move_pct, 3),
                "verdict": verdict,
            })
    return pd.DataFrame(out)


def _check_extrema(signals: pd.DataFrame, label: str) -> dict:
    hits = []
    for ts_str, kind, descr in EXTREMA:
        target = pd.Timestamp(ts_str, tz="UTC")
        need = "upside" if kind == "high" else "downside"
        # ±4h окно
        win = signals[(signals["ts"] >= target - pd.Timedelta(hours=4)) &
                      (signals["ts"] <= target + pd.Timedelta(hours=4)) &
                      (signals["direction"] == need) &
                      (signals["score"] >= 3)]
        if len(win):
            best_score = int(win["score"].max())
            hits.append({"event": ts_str, "kind": kind, "descr": descr,
                         "hit": True, "best_score": best_score, "n_signals": len(win)})
        else:
            hits.append({"event": ts_str, "kind": kind, "descr": descr,
                         "hit": False, "best_score": 0, "n_signals": 0})
    n_hit = sum(1 for h in hits if h["hit"])
    return {"label": label, "n_hit": n_hit, "n_total": len(hits), "details": hits}


def _verdict_summary(out: pd.DataFrame) -> pd.DataFrame:
    if out is None or len(out) == 0:
        return pd.DataFrame(columns=["direction", "horizon", "score>=", "TRUE", "FALSE", "NEUTRAL", "precision_%", "avg_move_%"])
    rows = []
    for direction in ("upside", "downside"):
        for h in HORIZONS_MIN:
            for s in SCORE_THRESHOLDS:
                sub = out[(out["direction"] == direction) &
                         (out["horizon_min"] == h) &
                         (out["score"] >= s)]
                if not len(sub):
                    continue
                t = (sub["verdict"] == "TRUE").sum()
                f = (sub["verdict"] == "FALSE").sum()
                n = (sub["verdict"] == "NEUTRAL").sum()
                tot = t + f
                prec = (t / tot * 100) if tot > 0 else float("nan")
                rows.append({
                    "direction": direction, "horizon": h, "score>=": s,
                    "TRUE": t, "FALSE": f, "NEUTRAL": n,
                    "precision_%": round(prec, 1) if not np.isnan(prec) else None,
                    "avg_move_%": round(sub["move_pct"].mean(), 3),
                })
    return pd.DataFrame(rows)


def _pnl_sim(signals: pd.DataFrame, df_1m: pd.DataFrame, score_min: int = 4,
             tp_pct: float = 1.0, sl_pct: float = 0.5, fee_round_trip_pct: float = 0.165,
             max_hold_min: int = 240) -> dict:
    """Симуляция: на каждом сигнале >=score_min открываем позу, выходим по TP/SL/timeout."""
    df_idx = df_1m.set_index("ts_utc").sort_index()
    trades = []
    for _, sig in signals.iterrows():
        if sig["score"] < score_min:
            continue
        ts0 = sig["ts"]
        price0 = sig["price"]
        end = ts0 + pd.Timedelta(minutes=max_hold_min)
        # 1m bars в окне
        try:
            window = df_idx.loc[ts0:end]
        except (KeyError, IndexError):
            continue
        if len(window) < 2:
            continue
        # SHORT для upside, LONG для downside
        if sig["direction"] == "upside":
            tp_price = price0 * (1 - tp_pct / 100)
            sl_price = price0 * (1 + sl_pct / 100)
        else:
            tp_price = price0 * (1 + tp_pct / 100)
            sl_price = price0 * (1 - sl_pct / 100)
        exit_price = float(window.iloc[-1]["close"])
        exit_reason = "TIMEOUT"
        for _, bar in window.iterrows():
            if sig["direction"] == "upside":
                if bar["low"] <= tp_price:
                    exit_price = tp_price; exit_reason = "TP"; break
                if bar["high"] >= sl_price:
                    exit_price = sl_price; exit_reason = "SL"; break
            else:
                if bar["high"] >= tp_price:
                    exit_price = tp_price; exit_reason = "TP"; break
                if bar["low"] <= sl_price:
                    exit_price = sl_price; exit_reason = "SL"; break
        gross_pct = ((price0 - exit_price) / price0 * 100) if sig["direction"] == "upside" else \
                    ((exit_price - price0) / price0 * 100)
        net_pct = gross_pct - fee_round_trip_pct
        trades.append({"ts": ts0, "dir": sig["direction"], "score": int(sig["score"]),
                       "exit_reason": exit_reason, "gross_%": round(gross_pct, 3),
                       "net_%": round(net_pct, 3)})
    if not trades:
        return {"n_trades": 0, "summary": {}}
    tdf = pd.DataFrame(trades)
    return {
        "n_trades": len(tdf),
        "n_tp": int((tdf["exit_reason"] == "TP").sum()),
        "n_sl": int((tdf["exit_reason"] == "SL").sum()),
        "n_timeout": int((tdf["exit_reason"] == "TIMEOUT").sum()),
        "win_rate_%": round((tdf["net_%"] > 0).sum() / len(tdf) * 100, 1),
        "avg_net_%": round(tdf["net_%"].mean(), 3),
        "median_net_%": round(tdf["net_%"].median(), 3),
        "total_net_%": round(tdf["net_%"].sum(), 2),
        "best": round(tdf["net_%"].max(), 3),
        "worst": round(tdf["net_%"].min(), 3),
    }


def _walk_forward(df_1h: pd.DataFrame, eth: pd.DataFrame, deriv: pd.DataFrame,
                  df_1m: pd.DataFrame, train_days: int = 60, test_days: int = 30) -> dict:
    """Train: первые 60 дней, Test: следующие 30 дней. Просто scan + метрики на test."""
    cutoff = df_1h["ts_utc"].max() - pd.Timedelta(days=test_days)
    train_df = df_1h[df_1h["ts_utc"] < cutoff].reset_index(drop=True)
    test_df = df_1h[df_1h["ts_utc"] >= cutoff].reset_index(drop=True)
    sigs_test = _scan_tf(test_df, eth, deriv, window_bars=50)
    if not len(sigs_test):
        return {"train_days": train_days, "test_days": test_days, "summary": "no test signals"}
    out = _evaluate_outcomes(sigs_test, df_1m)
    summary = _verdict_summary(out)
    return {
        "train_days": train_days, "test_days": test_days,
        "n_signals_test": int(len(sigs_test[sigs_test["score"] >= 3])),
        "summary_table": summary.to_dict(orient="records"),
    }


# 6th signal — low-volume rally distribution top
def _evaluate_with_low_vol_top(btc, eth, deriv):
    """Оборачивает evaluate_exhaustion и добавляет 6й up-сигнал.

    low_vol_rally_top: текущий close >= 12-bar high И средний vol_z последних
    8 баров < -0.3 (низкий объём при росте = distribution).
    """
    base = evaluate_exhaustion(btc, eth, deriv)
    if btc is None or len(btc) < 35:
        return base
    close = btc["close"].astype(float)
    high = btc["high"].astype(float)
    volume = btc["volume"].astype(float)
    vol_mean = volume.rolling(20).mean()
    vol_std = volume.rolling(20).std().replace(0, 1e-9)
    vz = ((volume - vol_mean) / vol_std).fillna(0)
    last_close = float(close.iloc[-1])
    high_12 = float(high.iloc[-12:].max())
    avg_vz_8 = float(vz.iloc[-8:].mean())
    is_low_vol_top = (last_close >= high_12 * 0.999) and (avg_vz_8 < -0.3)
    if is_low_vol_top:
        base["upside_score"] = min(5, base["upside_score"] + 1)
        base["details"]["up_signals"]["low_vol_rally_top"] = True
    return base


def main() -> int:
    print("[night] loading data...")
    df_1m, eth, deriv = _load_data()
    print(f"[night] BTC 1m: {len(df_1m):,} ({df_1m['ts_utc'].iloc[0]} -> {df_1m['ts_utc'].iloc[-1]})")
    print(f"[night] ETH 1h: {len(eth):,}")
    print(f"[night] deriv 1h: {len(deriv):,}")

    df_15m = _build_tf(df_1m, "15min")
    df_1h = _build_tf(df_1m, "1h")
    df_4h = _build_tf(df_1m, "4h")
    print(f"[night] TF bars: 15m={len(df_15m):,}  1h={len(df_1h):,}  4h={len(df_4h):,}")

    results = {}

    # --- 1. 15m TF
    print("\n[night] 1) Scanning 15m TF...")
    sigs_15m = _scan_tf(df_15m, eth, deriv, window_bars=50)
    out_15m = _evaluate_outcomes(sigs_15m, df_1m)
    results["15m"] = {
        "n_signals_total": int(len(sigs_15m)),
        "n_signals_3plus": int(len(sigs_15m[sigs_15m["score"] >= 3])),
        "n_signals_4plus": int(len(sigs_15m[sigs_15m["score"] >= 4])),
        "extrema": _check_extrema(sigs_15m, "15m"),
        "verdicts": _verdict_summary(out_15m).to_dict(orient="records"),
        "pnl_score4_tp1_sl05": _pnl_sim(sigs_15m, df_1m, score_min=4),
        "pnl_score3_tp1_sl05": _pnl_sim(sigs_15m, df_1m, score_min=3),
    }
    print(f"  15m: {results['15m']['n_signals_3plus']} signals (>=3), "
          f"caught {results['15m']['extrema']['n_hit']}/12 extrema")

    # --- 2. 1h baseline
    print("\n[night] 2) Scanning 1h TF (baseline)...")
    sigs_1h = _scan_tf(df_1h, eth, deriv, window_bars=50)
    out_1h = _evaluate_outcomes(sigs_1h, df_1m)
    results["1h"] = {
        "n_signals_total": int(len(sigs_1h)),
        "n_signals_3plus": int(len(sigs_1h[sigs_1h["score"] >= 3])),
        "n_signals_4plus": int(len(sigs_1h[sigs_1h["score"] >= 4])),
        "extrema": _check_extrema(sigs_1h, "1h"),
        "verdicts": _verdict_summary(out_1h).to_dict(orient="records"),
        "pnl_score4_tp1_sl05": _pnl_sim(sigs_1h, df_1m, score_min=4),
        "pnl_score3_tp1_sl05": _pnl_sim(sigs_1h, df_1m, score_min=3),
    }
    print(f"  1h: {results['1h']['n_signals_3plus']} signals (>=3), "
          f"caught {results['1h']['extrema']['n_hit']}/12 extrema")

    # --- 3. 4h TF
    print("\n[night] 3) Scanning 4h TF...")
    sigs_4h = _scan_tf(df_4h, eth, deriv, window_bars=30)
    out_4h = _evaluate_outcomes(sigs_4h, df_1m)
    results["4h"] = {
        "n_signals_total": int(len(sigs_4h)),
        "n_signals_3plus": int(len(sigs_4h[sigs_4h["score"] >= 3])),
        "n_signals_4plus": int(len(sigs_4h[sigs_4h["score"] >= 4])),
        "extrema": _check_extrema(sigs_4h, "4h"),
        "verdicts": _verdict_summary(out_4h).to_dict(orient="records"),
        "pnl_score4_tp1_sl05": _pnl_sim(sigs_4h, df_1m, score_min=4),
        "pnl_score3_tp1_sl05": _pnl_sim(sigs_4h, df_1m, score_min=3),
    }
    print(f"  4h: {results['4h']['n_signals_3plus']} signals (>=3), "
          f"caught {results['4h']['extrema']['n_hit']}/12 extrema")

    # --- 4. Multi-TF confluence: 15m signal where 1h also has same-direction signal within 1h window
    print("\n[night] 4) Multi-TF confluence (15m + 1h)...")
    sig_15m_strong = sigs_15m[sigs_15m["score"] >= 3].copy()
    sig_1h_strong = sigs_1h[sigs_1h["score"] >= 3].copy()
    confluence = []
    for _, s in sig_15m_strong.iterrows():
        nearby_1h = sig_1h_strong[
            (abs((sig_1h_strong["ts"] - s["ts"]).dt.total_seconds()) <= 3600) &
            (sig_1h_strong["direction"] == s["direction"])
        ]
        if len(nearby_1h):
            confluence.append({
                "ts": s["ts"], "direction": s["direction"],
                "score_15m": int(s["score"]),
                "score_1h": int(nearby_1h["score"].max()),
                "price": float(s["price"]),
            })
    conf_df = pd.DataFrame(confluence)
    if len(conf_df):
        conf_df["score"] = conf_df[["score_15m", "score_1h"]].min(axis=1)
        out_conf = _evaluate_outcomes(conf_df, df_1m)
        results["confluence_15m_1h"] = {
            "n_signals": int(len(conf_df)),
            "extrema": _check_extrema(conf_df, "confluence"),
            "verdicts": _verdict_summary(out_conf).to_dict(orient="records"),
            "pnl_score3_tp1_sl05": _pnl_sim(conf_df, df_1m, score_min=3),
        }
        print(f"  confluence: {len(conf_df)} signals, caught "
              f"{results['confluence_15m_1h']['extrema']['n_hit']}/12 extrema")
    else:
        results["confluence_15m_1h"] = {"n_signals": 0, "note": "no confluence"}
        print("  confluence: 0 signals")

    # --- 5. 6й сигнал low_vol_rally_top
    print("\n[night] 5) +6th signal low_vol_rally_top on 1h...")
    sigs_1h_v2 = _scan_tf(df_1h, eth, deriv, window_bars=50, eval_func=_evaluate_with_low_vol_top)
    out_1h_v2 = _evaluate_outcomes(sigs_1h_v2, df_1m)
    results["1h_with_low_vol_top"] = {
        "n_signals_3plus": int(len(sigs_1h_v2[sigs_1h_v2["score"] >= 3])),
        "n_signals_4plus": int(len(sigs_1h_v2[sigs_1h_v2["score"] >= 4])),
        "extrema": _check_extrema(sigs_1h_v2, "1h+lowvol"),
        "verdicts": _verdict_summary(out_1h_v2).to_dict(orient="records"),
        "pnl_score4_tp1_sl05": _pnl_sim(sigs_1h_v2, df_1m, score_min=4),
    }
    print(f"  1h+lowvol: {results['1h_with_low_vol_top']['n_signals_3plus']} signals, "
          f"caught {results['1h_with_low_vol_top']['extrema']['n_hit']}/12 extrema")

    # --- 6. Walk-forward на 1h (train 60d / test 30d)
    print("\n[night] 6) Walk-forward 1h (60/30)...")
    results["walkforward_1h"] = _walk_forward(df_1h, eth, deriv, df_1m, train_days=60, test_days=30)
    print(f"  walkforward complete")

    # --- write report
    print(f"\n[night] writing {OUT_MD}...")
    _write_md(results)
    print("[night] DONE")
    return 0


def _fmt_extrema(ext: dict) -> str:
    lines = [f"**{ext['n_hit']}/{ext['n_total']} extrema caught (score>=3, ±4h)**", ""]
    lines.append("| Date UTC | Type | Caught | Best score | N near |")
    lines.append("|---|---|---|---|---|")
    for d in ext["details"]:
        check = "[OK]" if d["hit"] else "[MISS]"
        lines.append(f"| {d['event']} | {d['kind']} | {check} | "
                     f"{d['best_score'] if d['hit'] else '-'} | {d['n_signals']} |")
    lines.append("")
    return "\n".join(lines)


def _fmt_verdicts(verdicts: list) -> str:
    if not verdicts:
        return "_no signals_"
    df = pd.DataFrame(verdicts)
    return df.to_markdown(index=False)


def _fmt_pnl(pnl: dict) -> str:
    if not pnl or pnl.get("n_trades", 0) == 0:
        return "_no trades_"
    return ("- Trades: {n_trades} (TP={n_tp}, SL={n_sl}, timeout={n_timeout})\n"
            "- Win rate: {win_rate_%}%, avg net {avg_net_%}%, median {median_net_%}%\n"
            "- Total net: **{total_net_%}%** (best {best}%, worst {worst}%)").format(**pnl)


def _write_md(results: dict) -> None:
    md = []
    md.append(f"# Grid_coordinator night research — 2026-05-10")
    md.append("")
    md.append(f"**Lookback:** 90 days | **Operator extrema tested:** 12 | "
              f"**Score thresholds:** 3 / 4 | **Horizons:** 60/120/240 min")
    md.append("")
    md.append(f"**PnL setup:** TP +1%, SL -0.5%, max hold 240m, fee 0.165% round-trip")
    md.append("")

    section_order = [
        ("15m", "## 1. 15m TF"),
        ("1h", "## 2. 1h TF (baseline)"),
        ("4h", "## 3. 4h TF"),
        ("confluence_15m_1h", "## 4. Multi-TF confluence (15m + 1h)"),
        ("1h_with_low_vol_top", "## 5. 1h with extra signal `low_vol_rally_top`"),
    ]
    for key, title in section_order:
        if key not in results:
            continue
        r = results[key]
        md.append(title)
        md.append("")
        if "n_signals_3plus" in r:
            md.append(f"- Signals score>=3: **{r['n_signals_3plus']}**")
            md.append(f"- Signals score>=4: **{r.get('n_signals_4plus','n/a')}**")
        elif "n_signals" in r:
            md.append(f"- Confluent signals: **{r['n_signals']}**")
        md.append("")
        if "extrema" in r:
            md.append(_fmt_extrema(r["extrema"]))
        if "verdicts" in r:
            md.append("**Verdict matrix:**\n")
            md.append(_fmt_verdicts(r["verdicts"]))
            md.append("")
        for pnl_key in ["pnl_score3_tp1_sl05", "pnl_score4_tp1_sl05"]:
            if pnl_key in r:
                tag = "score>=3" if "3" in pnl_key else "score>=4"
                md.append(f"**PnL ({tag}):**")
                md.append("")
                md.append(_fmt_pnl(r[pnl_key]))
                md.append("")

    # Walk-forward
    if "walkforward_1h" in results:
        wf = results["walkforward_1h"]
        md.append("## 6. Walk-forward 1h (60d train / 30d test)")
        md.append("")
        md.append(f"- Train days: {wf['train_days']}")
        md.append(f"- Test days: {wf['test_days']}")
        md.append(f"- Test signals (score>=3): {wf.get('n_signals_test','?')}")
        md.append("")
        md.append("**Out-of-sample verdict matrix:**")
        md.append("")
        md.append(_fmt_verdicts(wf.get("summary_table", [])))
        md.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
