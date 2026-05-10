"""P-15 auto-tuner — Stage D3.

Каждые 7 дней:
  1. Берёт последние 30 дней BTC 1m данных.
  2. Прогоняет grid search по R∈[0.2, 0.5], K∈[0.5, 2.0], dd_cap∈[2.0, 5.0]
     через simulate_p15_harvest для SHORT и LONG.
  3. Находит лучшие параметры по PF (с минимумом N≥30 трейдов).
  4. Сравнивает с текущими (P15_R_PCT, P15_K_PCT, P15_DD_CAP_PCT в p15_rolling.py).
  5. Если новые параметры существенно лучше (PF улучшение ≥0.3 + N достаточно):
       - пишет TG-предложение «обновить R=0.3→0.4 K=1.0→1.2, ожидаемый PF 4.32→4.85»
       - НЕ автомат — оператор сам решает менять или нет.
  6. Лог в state/p15_tuner_history.jsonl

Schedule: weekly via Task Scheduler.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Reuse the existing simulate function
from _backtest_p15_honest_v2 import simulate_p15_harvest  # noqa: E402

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
HISTORY = ROOT / "state" / "p15_tuner_history.jsonl"

# Current production params (read from source to avoid drift)
P15_RB = ROOT / "services" / "setup_detector" / "p15_rolling.py"
LOOKBACK_DAYS = 30
MIN_TRADES = 30  # need at least N to trust new params

# Grid search ranges
R_GRID = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]
K_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
DD_GRID = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]

# Improvement threshold to suggest update
PF_IMPROVE_MIN = 0.3
PNL_IMPROVE_MIN = 100.0  # USD


def _read_current_params() -> dict[str, float]:
    """Parse R, K, dd_cap from p15_rolling.py source."""
    params = {"R_PCT": 0.3, "K_PCT": 1.0, "DD_CAP_PCT": 3.0}
    if not P15_RB.exists(): return params
    txt = P15_RB.read_text(encoding="utf-8")
    for key in ("R_PCT", "K_PCT", "DD_CAP_PCT"):
        for line in txt.splitlines():
            if f"P15_{key}" in line and "=" in line and not line.strip().startswith("#"):
                try:
                    val = line.split("=", 1)[1].split("#", 1)[0].strip()
                    params[key] = float(val)
                    break
                except (ValueError, IndexError):
                    pass
    return params


def _build_15m_from_1m(df_1m: pd.DataFrame) -> pd.DataFrame:
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df_15m = df.set_index("ts_utc").resample("15min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()
    return df_15m


def _eval_params(df_15m: pd.DataFrame, R: float, K: float, dd: float) -> dict:
    """Evaluate one (R, K, dd_cap) combo on both directions, return summary."""
    short = simulate_p15_harvest(df_15m, R_pct=R, K_pct=K, dd_cap_pct=dd, direction="short")
    long_ = simulate_p15_harvest(df_15m, R_pct=R, K_pct=K, dd_cap_pct=dd, direction="long")
    return {
        "R": R, "K": K, "dd_cap": dd,
        "short_pnl": short.realized_pnl_usd,
        "short_pf": short.profit_factor,
        "short_n": short.n_trades,
        "long_pnl": long_.realized_pnl_usd,
        "long_pf": long_.profit_factor,
        "long_n": long_.n_trades,
        "combined_pnl": short.realized_pnl_usd + long_.realized_pnl_usd,
        "min_n": min(short.n_trades, long_.n_trades),
    }


def _grid_search(df_15m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(R_GRID) * len(K_GRID) * len(DD_GRID)
    n = 0
    for R in R_GRID:
        for K in K_GRID:
            for dd in DD_GRID:
                n += 1
                if n % 30 == 0:
                    print(f"[tuner] grid {n}/{total}")
                try:
                    rows.append(_eval_params(df_15m, R, K, dd))
                except Exception as exc:
                    print(f"[tuner] eval failed R={R} K={K} dd={dd}: {exc}")
    return pd.DataFrame(rows)


def _send_tg(text: str) -> None:
    try:
        import requests
        from config import BOT_TOKEN, CHAT_ID
        chat_ids = [p.strip() for p in str(CHAT_ID or "").replace(";", ",").split(",") if p.strip()]
        for cid in chat_ids:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": text}, timeout=10,
                )
            except Exception:
                pass
    except Exception:
        pass


def _append_history(record: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def main() -> int:
    print(f"[tuner] loading 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    df_15m = _build_15m_from_1m(df_1m)
    print(f"[tuner] {len(df_15m)} 15m bars over {LOOKBACK_DAYS}d")

    cur = _read_current_params()
    print(f"[tuner] current params: R={cur['R_PCT']}, K={cur['K_PCT']}, dd={cur['DD_CAP_PCT']}")
    cur_eval = _eval_params(df_15m, cur["R_PCT"], cur["K_PCT"], cur["DD_CAP_PCT"])
    print(f"[tuner] current PF: short={cur_eval['short_pf']:.2f} long={cur_eval['long_pf']:.2f}, "
          f"combined PnL ${cur_eval['combined_pnl']:.0f}")

    print("[tuner] grid search...")
    grid = _grid_search(df_15m)
    if grid.empty:
        print("[tuner] grid empty"); return 1

    # Filter by min_n trades
    eligible = grid[grid["min_n"] >= MIN_TRADES].copy()
    if eligible.empty:
        print(f"[tuner] no params with min_n >= {MIN_TRADES}, relaxing to 10")
        eligible = grid[grid["min_n"] >= 10].copy()
    if eligible.empty:
        print("[tuner] still no eligible params, abort")
        _append_history({"ts": datetime.now(timezone.utc).isoformat(),
                         "status": "no_eligible", "current": cur, "current_eval": cur_eval})
        return 0

    # Rank by combined_pnl + average PF
    eligible["score"] = eligible["combined_pnl"] + eligible[["short_pf", "long_pf"]].mean(axis=1) * 100
    best = eligible.sort_values("score", ascending=False).iloc[0]

    pf_avg_cur = (cur_eval["short_pf"] + cur_eval["long_pf"]) / 2
    pf_avg_best = (best["short_pf"] + best["long_pf"]) / 2

    pf_uplift = pf_avg_best - pf_avg_cur
    pnl_uplift = best["combined_pnl"] - cur_eval["combined_pnl"]

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": LOOKBACK_DAYS,
        "current": cur,
        "current_eval": cur_eval,
        "best": {"R": float(best["R"]), "K": float(best["K"]), "dd_cap": float(best["dd_cap"])},
        "best_eval": {
            "short_pf": float(best["short_pf"]),
            "long_pf": float(best["long_pf"]),
            "combined_pnl": float(best["combined_pnl"]),
            "min_n": int(best["min_n"]),
        },
        "pf_uplift": float(pf_uplift),
        "pnl_uplift": float(pnl_uplift),
    }

    if pf_uplift >= PF_IMPROVE_MIN and pnl_uplift >= PNL_IMPROVE_MIN:
        msg = (
            f"🎯 P-15 auto-tuner: предложение обновить параметры\n\n"
            f"ТЕКУЩИЕ: R={cur['R_PCT']}, K={cur['K_PCT']}, dd={cur['DD_CAP_PCT']}\n"
            f"  short PF {cur_eval['short_pf']:.2f}, long PF {cur_eval['long_pf']:.2f}, "
            f"combined PnL ${cur_eval['combined_pnl']:+.0f}\n\n"
            f"ЛУЧШИЕ (на 30д): R={best['R']}, K={best['K']}, dd={best['dd_cap']}\n"
            f"  short PF {best['short_pf']:.2f}, long PF {best['long_pf']:.2f}, "
            f"combined PnL ${best['combined_pnl']:+.0f}\n"
            f"  N: short={int(best['short_n'])}, long={int(best['long_n'])}\n\n"
            f"Уплифт: avg PF +{pf_uplift:.2f}, PnL +${pnl_uplift:.0f}\n\n"
            f"Не автомат. Если хочешь — обнови P15_R_PCT/K_PCT/DD_CAP_PCT "
            f"в services/setup_detector/p15_rolling.py."
        )
        record["status"] = "suggest_update"
    else:
        msg = (
            f"📊 P-15 auto-tuner: текущие параметры в порядке\n\n"
            f"R={cur['R_PCT']}, K={cur['K_PCT']}, dd={cur['DD_CAP_PCT']}\n"
            f"avg PF {pf_avg_cur:.2f}, combined PnL ${cur_eval['combined_pnl']:+.0f} (30d)\n\n"
            f"Лучшие на 30д давали бы +PF {pf_uplift:.2f} / +${pnl_uplift:.0f} — "
            f"меньше порога ({PF_IMPROVE_MIN} PF / ${PNL_IMPROVE_MIN}). Не меняем."
        )
        record["status"] = "no_change"

    print(msg)
    _send_tg(msg)
    _append_history(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
