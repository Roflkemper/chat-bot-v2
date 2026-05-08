"""Advisor v0.2 — рыночный анализатор с выводами и торговыми сетапами.

Without operator position. Without liquidation distance.
WITH: regime multi-TF, momentum, flow, OI/funding, session levels,
active setup detector signals, concrete trade ideas.

Output is decision-ready: "что вижу + что значит + конкретные уровни +
условия входа/выхода + почему".
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REGIME_PATH = Path("state/regime_state.json")
LIVE_1M = Path("market_live/market_1m.csv")
SETUPS_PATH = Path("state/setups.jsonl")
PAPER_TRADES_PATH = Path("state/paper_trades.jsonl")

# Active-setup rendering. ENTRY_BUCKET_PCT collapses near-duplicate setups
# of the same type whose entry prices are within ~0.3% of each other —
# setup_detector emits the same condition every poll cycle while it's live,
# so without bucketing the operator sees 5+ identical rows.
ENTRY_BUCKET_PCT = 0.003
HIGH_CONF_THRESHOLD = 60
TOP_CLUSTERS = 5

# Watch-block thresholds (advisor_v2 _build_watch_block).
FUNDING_DEEP_NEG_PCT = -0.008  # below this → squeeze potential
FUNDING_OVERHEAT_PCT = 0.015   # above this → longs overheated
OI_FLAT_ABS_PCT = 0.5          # |Δ| below this → flat, breakout incoming
OI_DIV_Z_THRESHOLD = 1.5       # |z| above this → divergence worth tracking

# TODO(reuse): the clustering below reimplements DedupLayer.evaluate_cluster
# (services/telegram/dedup_layer.py:149+). Consider routing through it for
# consistency with telegram dedup; deferred — different output shape.


def _load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_last_price() -> tuple[float, float] | None:
    """Return (price, age_min) from market_1m.csv or None."""
    if not LIVE_1M.exists():
        return None
    try:
        with LIVE_1M.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            block = min(8192, size)
            fh.seek(-block, 2)
            data = fh.read().decode("utf-8", errors="replace")
        last = None
        last_ts = None
        for line in data.splitlines():
            if not line.strip() or line.startswith("ts_utc"):
                continue
            parts = line.split(",")
            if len(parts) >= 5:
                last_ts = parts[0]
                last = float(parts[4])
        if last is None:
            return None
        # Compute age
        try:
            ts = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
            return last, age
        except Exception:
            return last, 999.0
    except (OSError, ValueError):
        return None


def _load_recent_setups(within_hours: int = 6) -> list[dict]:
    """Recent setups from setup_detector journal."""
    if not SETUPS_PATH.exists():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - within_hours * 3600
    out = []
    try:
        for line in SETUPS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                ts_str = d.get("detected_at", "")
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts.timestamp() >= cutoff:
                    out.append(d)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
    except OSError:
        pass
    return out


def _load_open_paper_trades() -> list[dict]:
    """Currently open paper trades."""
    if not PAPER_TRADES_PATH.exists():
        return []
    by_id = {}
    try:
        for line in PAPER_TRADES_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                tid = e.get("trade_id")
                if not tid:
                    continue
                if e.get("action") == "OPEN":
                    by_id[tid] = e
                elif e.get("action") in ("TP2", "SL", "EXPIRE", "CANCEL"):
                    by_id.pop(tid, None)
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return list(by_id.values())


def _classify_v2_live() -> dict:
    """Use regime_classifier_v2 multi-timeframe view + persist to regime_v2_state.json."""
    try:
        from services.regime_classifier_v2.multi_timeframe import build_and_persist_view
        v = build_and_persist_view(symbol="BTCUSDT")
        return {
            "4h": (v.bar_4h.state_v2 if v.bar_4h else None,
                   v.bar_4h.indicators if v.bar_4h else {}),
            "1h": (v.bar_1h.state_v2 if v.bar_1h else None,
                   v.bar_1h.indicators if v.bar_1h else {}),
            "15m": (v.bar_15m.state_v2 if v.bar_15m else None,
                    v.bar_15m.indicators if v.bar_15m else {}),
            "diverge": v.macro_micro_diverge,
        }
    except Exception:
        logger.exception("advisor_v2.regime_classify_failed")
        return {}


def _read_features_last() -> dict:
    """Last bar of full_features_1y for momentum/flow/OI/funding.

    2026-05-07 fix: parquet `full_features_1y.parquet` обновляется НЕ live (последнее
    обновление обычно >24h назад). Поэтому OI/funding signal в advisor показывал
    устаревшие данные. Live override: `state/deriv_live.json` (обновляется каждые
    5 мин из services/deriv_live/) переписывает funding_rate, oi_delta_1h, premium_pct.
    """
    out = {}
    # 1) Read parquet (исторические features — RSI, taker_imbalance, session levels, etc.)
    try:
        import pandas as pd
        df = pd.read_parquet("data/forecast_features/full_features_1y.parquet")
        if not df.empty:
            last = df.iloc[-1]
            for col in (
                "rsi_14", "rsi_zone_int", "rsi_divergence_5h",
                "cci_overbought", "cci_oversold",
                "oi_delta_1h", "oi_price_div_1h_z",
                "taker_imbalance_1h", "taker_imbalance_15m", "taker_imbalance_5m",
                "ls_long_extreme", "ls_short_extreme",
                "asia_high_broken", "asia_low_broken",
                "london_high_broken", "london_low_broken",
                "ny_am_high_broken", "ny_am_low_broken",
                "bars_since_london_high_break", "bars_since_ny_am_high_break",
                "bars_since_london_low_break", "bars_since_ny_am_low_break",
                "volume_acceleration", "rvol_20", "realized_vol_pctile_24h",
                "dist_to_pdh_pct", "dist_to_pdl_pct",
                "vol_profile_poc_dist_pct", "vol_profile_position",
                "funding_rate", "funding_z",
            ):
                if col in df.columns:
                    v = last.get(col)
                    if pd.notna(v):
                        out[col] = float(v)
    except Exception:
        logger.exception("advisor_v2.features_load_failed")

    # 2) LIVE override from state/deriv_live.json (Binance REST poll, 5min cadence).
    # Заменяет stale parquet значения на свежие для OI / funding.
    try:
        import json as _json
        from pathlib import Path as _Path
        live_path = _Path("state/deriv_live.json")
        if live_path.exists():
            data = _json.loads(live_path.read_text(encoding="utf-8"))
            btc = data.get("BTCUSDT", {}) or {}
            # funding_rate (8h period) — live override
            if "funding_rate_8h" in btc:
                out["funding_rate"] = float(btc["funding_rate_8h"])
                out["_funding_source"] = "deriv_live"
            # OI 1h delta — live override
            if "oi_change_1h_pct" in btc:
                out["oi_delta_1h"] = float(btc["oi_change_1h_pct"])
                out["_oi_source"] = "deriv_live"
            # Premium (mark vs index) — новый сигнал, не было в parquet
            if "premium_pct" in btc:
                out["premium_pct"] = float(btc["premium_pct"])
            # Long/Short ratio market sentiment (2026-05-07)
            for k in ("global_long_account_pct", "global_short_account_pct",
                      "top_trader_long_pct", "top_trader_short_pct",
                      "taker_buy_pct", "taker_sell_pct",
                      "bybit_long_pct", "bybit_short_pct"):
                if k in btc:
                    out[k] = btc[k]
            out["_deriv_live_ts"] = data.get("last_updated", "")
    except Exception:
        logger.exception("advisor_v2.deriv_live_load_failed")

    return out


def _interpret_momentum(f: dict) -> list[str]:
    """Convert momentum indicators into trader-readable observations."""
    out = []
    rsi = f.get("rsi_14")
    if rsi is not None:
        if rsi > 70:
            out.append(f"RSI 1h {rsi:.0f} — перекуплен")
        elif rsi < 30:
            out.append(f"RSI 1h {rsi:.0f} — перепродан")
        else:
            out.append(f"RSI 1h {rsi:.0f} — нейтрально")
    if f.get("rsi_divergence_5h"):
        out.append("⚠️ RSI divergence (5h) — обнаружена")
    if f.get("cci_overbought"):
        out.append("CCI overbought — momentum exhaustion возможен")
    if f.get("cci_oversold"):
        out.append("CCI oversold — momentum exhaustion возможен")
    return out


def _interpret_flow(f: dict) -> list[str]:
    out = []
    ti_1h = f.get("taker_imbalance_1h")
    ti_15m = f.get("taker_imbalance_15m")
    ti_5m = f.get("taker_imbalance_5m")
    if ti_1h is not None:
        sign = "buy" if ti_1h > 0 else "sell"
        out.append(f"Taker 1h: {ti_1h*100:+.1f}% ({sign} pressure)")
    if ti_15m is not None and ti_1h is not None and (ti_15m * ti_1h < 0):
        out.append("⚠️ Flow flip — 15m расходится с 1h по направлению")
    vol_accel = f.get("volume_acceleration")
    if vol_accel is not None:
        if vol_accel < -0.5:
            out.append(f"Volume падает (accel {vol_accel:+.0%})")
        elif vol_accel > 0.5:
            out.append(f"Volume растёт (accel {vol_accel:+.0%})")
    rvp = f.get("realized_vol_pctile_24h")
    if rvp is not None:
        if rvp > 0.8:
            out.append(f"Vol percentile 24h: {rvp:.0%} — высокая волатильность")
        elif rvp < 0.2:
            out.append(f"Vol percentile 24h: {rvp:.0%} — низкая волатильность")
    return out


def _interpret_oi_funding(f: dict) -> list[str]:
    out = []
    oi = f.get("oi_delta_1h")
    if oi is not None:
        if abs(oi) > 1.0:
            sign = "растёт" if oi > 0 else "падает"
            out.append(f"OI 1h: {oi:+.2f}% ({sign} быстро)")
        else:
            out.append(f"OI 1h: {oi:+.2f}% (flat)")
    oi_div_z = f.get("oi_price_div_1h_z")
    if oi_div_z is not None and abs(oi_div_z) > 1.5:
        sign = "цена растёт + OI падает" if oi_div_z < 0 else "цена падает + OI растёт"
        out.append(f"⚠️ OI/price divergence z={oi_div_z:+.1f} ({sign})")
    funding = f.get("funding_rate")
    if funding is not None:
        funding_8h_pct = funding * 100  # parquet stores per-period rate
        if abs(funding_8h_pct) < 0.005:
            out.append(f"Funding: {funding_8h_pct:+.4f}% (нейтрально)")
        elif funding_8h_pct < -0.008:
            out.append(f"Funding: {funding_8h_pct:+.4f}% — глубоко negative (longs платят меньше, может быть squeeze)")
        elif funding_8h_pct > 0.008:
            out.append(f"Funding: {funding_8h_pct:+.4f}% — положительный (longs платят shorts)")
        else:
            out.append(f"Funding: {funding_8h_pct:+.4f}%")
    if f.get("ls_long_extreme"):
        out.append("⚠️ LS ratio: long extreme — толпа в long, contrarian short setup")
    if f.get("ls_short_extreme"):
        out.append("⚠️ LS ratio: short extreme — толпа в short, contrarian long setup")
    # Premium (mark vs index) — новый сигнал из live deriv poll (2026-05-07)
    premium = f.get("premium_pct")
    if premium is not None:
        if abs(premium) < 0.02:
            pass  # neutral, не спамим
        elif premium > 0.05:
            out.append(f"Premium {premium:+.3f}% — perp выше spot (long bias)")
        elif premium < -0.05:
            out.append(f"Premium {premium:+.3f}% — perp ниже spot (short bias)")
    # Live source marker (для прозрачности, видеть откуда данные)
    if f.get("_funding_source") == "deriv_live":
        out.append("_(funding/OI: live Binance, обновляется каждые 5 мин)_")
    return out


def _interpret_global_market(f: dict) -> list[str]:
    """BTC.D + total mcap context (C3)."""
    out: list[str] = []
    try:
        import json as _json
        from pathlib import Path as _Path
        p = _Path("state/deriv_live.json")
        if not p.exists():
            return out
        data = _json.loads(p.read_text(encoding="utf-8"))
        g = data.get("global", {}) or {}
        btc_d = g.get("btc_dominance_pct")
        eth_d = g.get("eth_dominance_pct")
        mcap_chg = g.get("mcap_change_24h_pct")
        total = g.get("total_mcap_usd")
        if btc_d is not None:
            out.append(f"BTC.D {btc_d}%, ETH.D {eth_d}% — деньги {'в BTC' if btc_d > 55 else 'в альтах' if btc_d < 50 else 'распределены'}")
        if mcap_chg is not None:
            arrow = "↑" if mcap_chg > 0 else "↓"
            out.append(f"Total mcap 24h {arrow} {mcap_chg:+.2f}% (${total/1e12:.2f}T)" if total else f"Total mcap 24h {arrow} {mcap_chg:+.2f}%")
    except Exception:
        logger.debug("global_market failed", exc_info=True)
    return out


def _interpret_flip_history(f: dict) -> list[str]:
    """Funding/premium flip history + OI spike (A1+A2+A4)."""
    out: list[str] = []
    try:
        from services.deriv_live.flip_tracker import detect_flips, detect_oi_spike

        flips = detect_flips()
        if flips.get("funding"):
            ff = flips["funding"]
            streak = ff.get("current_streak_hours")
            sign_word = "положительный" if ff["current_sign"] == "+" else "отрицательный"
            if streak is not None:
                last_val = ff["last_flip"]["value"] * 100
                out.append(
                    f"Funding-flip: {sign_word} {streak:.1f}ч (был {last_val:+.4f}%)"
                )
        if flips.get("premium"):
            pp = flips["premium"]
            streak = pp.get("current_streak_hours")
            sign_word = "положительный (perp выше spot)" if pp["current_sign"] == "+" else "отрицательный (perp ниже spot)"
            if streak is not None:
                out.append(f"Premium-flip: {sign_word}, {streak:.1f}ч")

        spike = detect_oi_spike()
        if spike:
            arrow = "↑" if spike["direction"] == "up" else "↓"
            out.append(f"OI 15min {arrow} {spike['oi_change_15min_pct']:+.2f}% — крупные позиции {'открываются' if spike['direction'] == 'up' else 'закрываются'}")
    except Exception:
        logger.exception("advisor_v2.flip_history_failed")
    return out


def _interpret_long_short(f: dict) -> list[str]:
    """Long/Short market sentiment (Binance global + top traders + Bybit + taker)."""
    out: list[str] = []
    gl = f.get("global_long_account_pct")
    gs = f.get("global_short_account_pct")
    tl = f.get("top_trader_long_pct")
    ts_pct = f.get("top_trader_short_pct")
    tb = f.get("taker_buy_pct")
    tk_s = f.get("taker_sell_pct")
    bl = f.get("bybit_long_pct")
    bs = f.get("bybit_short_pct")

    if gl is not None and gs is not None:
        out.append(f"Binance все аккаунты: {gl}% long / {gs}% short")
    if tl is not None and ts_pct is not None:
        out.append(f"Binance топ-трейдеры (по объёму): {tl}% long / {ts_pct}% short")
    if bl is not None and bs is not None:
        out.append(f"Bybit: {bl}% long / {bs}% short")
    if tb is not None and tk_s is not None:
        out.append(f"Taker volume (последние 5 мин): {tb}% buy / {tk_s}% sell")

    # Trader-actionable insights
    if gl is not None and gl >= 60:
        out.append(f"⚠️ Толпа в LONG ({gl}%) — crowded long, риск short squeeze ВНИЗ")
    elif gs is not None and gs >= 60:
        out.append(f"⚠️ Толпа в SHORT ({gs}%) — crowded short, риск long squeeze ВВЕРХ")

    if tl is not None and gl is not None and (tl - gl) >= 5:
        out.append(f"  Топ-трейдеры более bullish ({tl}% vs толпа {gl}%) — смартмани bias UP")
    elif ts_pct is not None and gs is not None and (ts_pct - gs) >= 5:
        out.append(f"  Топ-трейдеры более bearish ({ts_pct}% vs толпа {gs}%) — смартмани bias DOWN")

    if tb is not None and tb >= 65:
        out.append(f"🔵 Taker buy {tb}% — сильное покупательское давление прямо сейчас")
    elif tk_s is not None and tk_s >= 65:
        out.append(f"🔴 Taker sell {tk_s}% — сильное продавательское давление прямо сейчас")

    return out


def _interpret_session_levels(f: dict) -> list[str]:
    out = []
    breaks = []
    if f.get("asia_high_broken"):
        breaks.append("Asia high")
    if f.get("london_high_broken"):
        breaks.append("London high")
    if f.get("ny_am_high_broken"):
        breaks.append("NY-AM high")
    if breaks:
        out.append(f"Пробиты вверх: {', '.join(breaks)}")
    breaks_low = []
    if f.get("asia_low_broken"):
        breaks_low.append("Asia low")
    if f.get("london_low_broken"):
        breaks_low.append("London low")
    if f.get("ny_am_low_broken"):
        breaks_low.append("NY-AM low")
    if breaks_low:
        out.append(f"Пробиты вниз: {', '.join(breaks_low)}")
    # Bars since fresh = setup retest opportunity
    bars_since_l_h = f.get("bars_since_london_high_break")
    if bars_since_l_h is not None and 0 < bars_since_l_h < 8:
        out.append(f"London high пробит {bars_since_l_h:.0f} баров назад — свежий retest setup")
    bars_since_ny_h = f.get("bars_since_ny_am_high_break")
    if bars_since_ny_h is not None and 0 < bars_since_ny_h < 8:
        out.append(f"NY-AM high пробит {bars_since_ny_h:.0f} баров назад — свежий retest setup")
    bars_since_l_l = f.get("bars_since_london_low_break")
    if bars_since_l_l is not None and 0 < bars_since_l_l < 8:
        out.append(f"London low пробит {bars_since_l_l:.0f} баров назад — свежий retest")
    return out


def _compute_risk_score(regime: dict, f: dict) -> dict:
    """Aggregate risk score 0-10 для трейдера.

    Считаем баллы:
    - SHORT_RISK (риск падения): bull regime divergent с micro down, taker sell ext,
      crowded long, premium negative, OI declining
    - LONG_RISK (риск squeeze вверх): crowded short, taker buy extreme, OI rising,
      funding negative deep

    Возвращает: {short_risk: 0-10, long_risk: 0-10, dominant: 'short'|'long'|'neutral', reasons: [...]}
    """
    short_risk = 0
    long_risk = 0
    short_reasons: list[str] = []
    long_reasons: list[str] = []

    # Regime
    primary_4h = (regime.get("4h") or (None, {}))[0]
    primary_15m = (regime.get("15m") or (None, {}))[0]
    is_macro_up = primary_4h in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP")
    is_macro_down = primary_4h in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN")
    is_micro_up = primary_15m in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP")
    is_micro_down = primary_15m in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN")

    if is_macro_up and is_micro_up:
        long_risk += 1
        long_reasons.append("4h+15m тренд вверх")
    if is_macro_down and is_micro_down:
        short_risk += 1
        short_reasons.append("4h+15m тренд вниз")

    # L/S extreme — contrarian
    gl = f.get("global_long_account_pct")
    gs = f.get("global_short_account_pct")
    if gl is not None and gl >= 60:
        short_risk += 2
        short_reasons.append(f"толпа в LONG {gl}% (crowded — squeeze ВНИЗ)")
    elif gs is not None and gs >= 60:
        long_risk += 2
        long_reasons.append(f"толпа в SHORT {gs}% (crowded — squeeze ВВЕРХ)")
    elif gs is not None and gs >= 55:
        long_risk += 1
        long_reasons.append(f"толпа в SHORT {gs}% (близко к crowded)")

    # Top trader bias
    tl = f.get("top_trader_long_pct")
    ts_pct = f.get("top_trader_short_pct")
    if tl is not None and gl is not None and (tl - gl) >= 5:
        long_risk += 1
        long_reasons.append("топ-трейдеры более bullish чем толпа")
    elif ts_pct is not None and gs is not None and (ts_pct - gs) >= 5:
        short_risk += 1
        short_reasons.append("топ-трейдеры более bearish чем толпа")

    # Taker pressure now
    tb = f.get("taker_buy_pct")
    tk_s = f.get("taker_sell_pct")
    if tb is not None and tb >= 65:
        long_risk += 2
        long_reasons.append(f"taker buy {tb}% — давление вверх СЕЙЧАС")
    elif tk_s is not None and tk_s >= 65:
        short_risk += 2
        short_reasons.append(f"taker sell {tk_s}% — давление вниз СЕЙЧАС")

    # Funding
    funding = f.get("funding_rate")
    if funding is not None:
        f_pct = funding * 100
        if f_pct < -0.01:
            long_risk += 1
            long_reasons.append(f"funding {f_pct:+.4f}% (shorts платят — squeeze potential)")
        elif f_pct > 0.01:
            short_risk += 1
            short_reasons.append(f"funding {f_pct:+.4f}% (longs платят — overcrowded)")

    # Premium (mark vs index)
    premium = f.get("premium_pct")
    if premium is not None:
        if premium < -0.05:
            short_risk += 1
            short_reasons.append(f"premium {premium:+.3f}% (perp ниже spot — sell pressure)")
        elif premium > 0.05:
            long_risk += 1
            long_reasons.append(f"premium {premium:+.3f}% (perp выше spot — buy pressure)")

    # OI direction
    oi = f.get("oi_delta_1h")
    if oi is not None and abs(oi) > 1.0:
        # OI растёт сильно + либо tracking тренд, либо contrarian risk
        if oi > 1.0 and is_macro_up:
            long_risk += 1
            long_reasons.append(f"OI 1h {oi:+.2f}% — тренд усиливается")
        elif oi < -1.0:
            # OI быстро падает = массовое закрытие, может быть конец движения
            pass  # neutral, не считаем

    # Cap at 10
    short_risk = min(short_risk, 10)
    long_risk = min(long_risk, 10)

    if short_risk > long_risk and short_risk >= 3:
        dominant = "short_risk"  # риск падения цены
    elif long_risk > short_risk and long_risk >= 3:
        dominant = "long_risk"  # риск squeeze вверх
    else:
        dominant = "neutral"

    return {
        "short_risk": short_risk,
        "long_risk": long_risk,
        "dominant": dominant,
        "short_reasons": short_reasons,
        "long_reasons": long_reasons,
    }


def _format_risk_block(rs: dict) -> list[str]:
    """Render risk score block."""
    out: list[str] = []
    sr = rs["short_risk"]
    lr = rs["long_risk"]
    dom = rs["dominant"]

    if dom == "short_risk":
        emoji = "🔴"
        headline = f"Риск ВНИЗ выше ({sr}/10) чем риск ВВЕРХ ({lr}/10)"
        action = "Не агрессивно докидывать LONG. Защитные настройки шортовых ботов оправданы."
    elif dom == "long_risk":
        emoji = "🟢"
        headline = f"Риск ВВЕРХ выше ({lr}/10) чем риск ВНИЗ ({sr}/10)"
        action = "Не агрессивно докидывать SHORT. Возможен squeeze rally."
    else:
        emoji = "⚪"
        headline = f"Риски сбалансированы (вверх {lr}/10, вниз {sr}/10)"
        action = "Без явного направления. Range-режим, никаких aggressive moves."

    out.append(f"{emoji} {headline}")
    out.append(f"   Действие: {action}")
    if rs["long_reasons"]:
        out.append(f"   Факторы за рост ({lr}/10):")
        for r in rs["long_reasons"][:4]:
            out.append(f"     + {r}")
    if rs["short_reasons"]:
        out.append(f"   Факторы за падение ({sr}/10):")
        for r in rs["short_reasons"][:4]:
            out.append(f"     - {r}")
    return out


def _summary_verdict(regime: dict, f: dict, setups: list[dict]) -> tuple[str, list[str]]:
    """Compute one-line verdict + supporting reasoning."""
    reasons = []
    primary_4h = (regime.get("4h") or (None, {}))[0]
    primary_1h = (regime.get("1h") or (None, {}))[0]
    primary_15m = (regime.get("15m") or (None, {}))[0]

    is_macro_up = primary_4h in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP")
    is_macro_down = primary_4h in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN")
    is_micro_up = primary_15m in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP")
    is_micro_down = primary_15m in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN")

    # High-confidence setups (conf >= 60)
    high_conf_setups = [s for s in setups if s.get("confidence_pct", 0) >= 60]
    long_setups = [s for s in high_conf_setups if s.get("setup_type", "").startswith("long_")]
    short_setups = [s for s in high_conf_setups if s.get("setup_type", "").startswith("short_")]

    # Verdict logic (decision-oriented):
    if not is_macro_up and not is_macro_down:
        verdict = "БОКОВИК — без направления"
        reasons.append("4h в RANGE/COMPRESSION — нет тренда")
    elif is_macro_up and is_micro_up:
        verdict = "BULL CONFLUENCE — macro и micro вверх"
        reasons.append(f"4h={primary_4h}, 15m={primary_15m} — оба бычьи")
    elif is_macro_down and is_micro_down:
        verdict = "BEAR CONFLUENCE — macro и micro вниз"
        reasons.append(f"4h={primary_4h}, 15m={primary_15m} — оба медвежьи")
    elif is_macro_up and is_micro_down:
        verdict = "MACRO BULL / MICRO PULLBACK — потенциальный buy-the-dip"
        reasons.append(f"4h={primary_4h}, но 15m={primary_15m} — coiling в macro тренде")
    elif is_macro_down and is_micro_up:
        verdict = "MACRO BEAR / MICRO RALLY — потенциальный rally-to-fade"
        reasons.append(f"4h={primary_4h}, но 15m={primary_15m} — отскок в downtrend")
    else:
        verdict = "СМЕШАННЫЙ КОНТЕКСТ"
        reasons.append(f"4h={primary_4h}, 1h={primary_1h}, 15m={primary_15m}")

    # Setup confluence
    if len(long_setups) >= 2:
        reasons.append(f"+{len(long_setups)} активных LONG сетапов confidence ≥60")
    if len(short_setups) >= 2:
        reasons.append(f"+{len(short_setups)} активных SHORT сетапов confidence ≥60")

    # OI/funding confluence
    oi_div_z = f.get("oi_price_div_1h_z")
    if oi_div_z is not None:
        if oi_div_z < -1.5:
            reasons.append(f"OI/price div z={oi_div_z:.1f} — short squeeze setup possible")
        elif oi_div_z > 1.5:
            reasons.append(f"OI/price div z={oi_div_z:+.1f} — long crowdedness signal")
    if f.get("ls_long_extreme") and is_macro_up:
        reasons.append("⚠️ Long extreme в bull тренде — risk of squeeze down")
    if f.get("ls_short_extreme") and is_macro_down:
        reasons.append("⚠️ Short extreme в bear тренде — risk of squeeze up")

    return verdict, reasons


def _read_margin_block() -> dict | None:
    """Read margin block from state_latest.json (set by state_snapshot_loop).

    Source: state/manual_overrides/margin_overrides.jsonl ← /margin operator command.
    """
    try:
        import json as _json
        from pathlib import Path as _Path
        p = _Path("docs/STATE/state_latest.json")
        if not p.exists():
            return None
        data = _json.loads(p.read_text(encoding="utf-8"))
        return data.get("margin")
    except Exception:
        return None


def build_advisor_v2_text() -> str:
    """Compose full advisor v2 message."""
    now = datetime.now(timezone.utc)
    price_info = _read_last_price()
    regime = _classify_v2_live()
    features = _read_features_last()
    setups = _load_recent_setups(within_hours=6)
    open_papers = _load_open_paper_trades()

    lines = []
    lines.append(f"🎯 ADVISOR v0.2 — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    if price_info:
        price, age_min = price_info
        if age_min > 10:
            lines.append(f"⚠️ BTC {price:,.0f} | data {age_min:.0f}min old (stale!)")
        else:
            lines.append(f"BTC {price:,.0f} | data fresh ({age_min:.0f}min)")
    else:
        lines.append("⚠️ Нет live price feed")

    # ── Verdict (top of message — decision first)
    verdict, reasoning = _summary_verdict(regime, features, setups)
    lines.append("")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📌 ВЕРДИКТ: {verdict}")
    for r in reasoning:
        lines.append(f"   • {r}")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━")

    # ── Risk Score (D1, 2026-05-07): сводная оценка рисков по всем сигналам
    risk = _compute_risk_score(regime, features)
    lines.append("")
    lines.append("🎯 RISK SCORE")
    for x in _format_risk_block(risk):
        lines.append(f"  {x}")

    # ── Margin status (TZ-MARGIN-COEFFICIENT-INPUT-WIRE 2026-05-07)
    # Operator sets via /margin <coef> <available> <dist>. Stale > 6h = warn.
    margin_block = _read_margin_block()
    if margin_block:
        lines.append("")
        lines.append("💰 MARGIN (operator-supplied)")
        coef = margin_block.get("coefficient")
        avail = margin_block.get("available_margin_usd")
        dist = margin_block.get("distance_to_liquidation_pct")
        age_min = margin_block.get("data_age_minutes", 0)
        if coef is not None:
            lines.append(f"  Margin coef: {coef:.4f} | Available: ${avail:,.0f} | Dist to liq: {dist:.1f}%")
        if age_min > 360:  # > 6h
            lines.append(f"  ⚠️ Margin data {age_min/60:.1f}h old — обнови через /margin")
        elif age_min > 60:
            lines.append(f"  Margin data {age_min:.0f}min old")

    # ── Regime multi-TF
    lines.append("")
    lines.append("РЕЖИМ (multi-TF)")
    for tf in ("4h", "1h", "15m"):
        state, ind = regime.get(tf, (None, {}))
        if state is None:
            lines.append(f"  {tf}: нет данных")
            continue
        slope = ind.get("ema50_slope_pct")
        dist = ind.get("dist_to_ema200_pct")
        slope_str = f"slope {slope:+.2f}%" if slope is not None else ""
        dist_str = f"dist EMA200 {dist:+.2f}%" if dist is not None else ""
        lines.append(f"  {tf}: {state} | {slope_str} | {dist_str}".strip())
    if regime.get("diverge"):
        lines.append("  ⚠️ Macro ≠ Micro")

    # ── Momentum
    momentum = _interpret_momentum(features)
    if momentum:
        lines.append("")
        lines.append("МОМЕНТУМ")
        for m in momentum:
            lines.append(f"  • {m}")

    # ── Flow / orderflow
    flow = _interpret_flow(features)
    if flow:
        lines.append("")
        lines.append("FLOW / OBJECTIVE PRESSURE")
        for f in flow:
            lines.append(f"  • {f}")

    # ── OI / funding
    oi_funding = _interpret_oi_funding(features)
    if oi_funding:
        lines.append("")
        lines.append("OI / FUNDING / КРАУДНОСТЬ")
        for x in oi_funding:
            lines.append(f"  • {x}")

    # ── Global market (C3): BTC dominance + total mcap
    glob = _interpret_global_market(features)
    if glob:
        lines.append("")
        lines.append("РЫНОК ГЛОБАЛЬНО")
        for x in glob:
            lines.append(f"  • {x}")

    # ── Flip history (A1+A2+A4): funding/premium streak + OI spike
    flip = _interpret_flip_history(features)
    if flip:
        lines.append("")
        lines.append("ИСТОРИЯ FLIP / SPIKE")
        for x in flip:
            lines.append(f"  • {x}")

    # ── Long/Short ratio (рыночная дельта)
    ls = _interpret_long_short(features)
    if ls:
        lines.append("")
        lines.append("LONG/SHORT РЫНОК")
        for x in ls:
            lines.append(f"  • {x}")

    # ── Session levels
    sess = _interpret_session_levels(features)
    if sess:
        lines.append("")
        lines.append("УРОВНИ СЕССИЙ")
        for s in sess:
            lines.append(f"  • {s}")

    # ── Active setups. Setup_detector fires the same condition every poll
    # cycle while it's live, producing 5+ near-duplicate rows. Cluster by
    # (setup_type, entry-bucket of ENTRY_BUCKET_PCT) and render the most
    # recent snapshot per cluster with an ×N counter.
    high_conf = [s for s in setups if s.get("confidence_pct", 0) >= HIGH_CONF_THRESHOLD]
    if high_conf:
        lines.append("")
        lines.append(f"🎯 АКТИВНЫЕ СЕТАПЫ (≥{HIGH_CONF_THRESHOLD}% conf, последние 6h)")

        # Bucket grows with price so ENTRY_BUCKET_PCT stays meaningful across
        # symbols: log(entry)/log(1+pct) gives the index of a 0.3%-wide bin.
        log_step = math.log1p(ENTRY_BUCKET_PCT)

        clusters: dict[tuple[str, int], list[dict]] = {}
        for s in high_conf:
            entry = s.get("entry_price")
            if not entry or entry <= 0:
                continue
            stype = s.get("setup_type", "?")
            bucket = int(math.log(entry) / log_step)
            clusters.setdefault((stype, bucket), []).append(s)

        latest_per_cluster = [
            (max(cl, key=lambda x: x.get("ts") or ""), len(cl))
            for cl in clusters.values()
        ]
        latest_per_cluster.sort(key=lambda pair: pair[0].get("ts") or "", reverse=True)

        for s, n in latest_per_cluster[:TOP_CLUSTERS]:
            stype = s.get("setup_type", "?")
            entry = s.get("entry_price")
            sl = s.get("stop_price")
            tp1 = s.get("tp1_price")
            tp2 = s.get("tp2_price")
            conf = s.get("confidence_pct", 0)
            rr = s.get("risk_reward")
            entry_str = f"{entry:.0f}" if entry else "?"
            sl_str = f"{sl:.0f}" if sl else "?"
            tp1_str = f"{tp1:.0f}" if tp1 else "?"
            tp2_str = f"{tp2:.0f}" if tp2 else "?"
            rr_str = f"RR {rr}" if rr else ""
            count_str = f" ×{n}" if n > 1 else ""
            lines.append(
                f"  {stype}{count_str}: {entry_str} | SL {sl_str} | "
                f"TP1 {tp1_str} | TP2 {tp2_str} | conf {conf:.0f}% {rr_str}"
            )
    else:
        lines.append("")
        lines.append(f"🎯 АКТИВНЫЕ СЕТАПЫ: нет (последние 6h, conf ≥{HIGH_CONF_THRESHOLD}%)")

    # ── Open paper trades
    if open_papers:
        lines.append("")
        lines.append(f"📊 PAPER TRADES (открыто {len(open_papers)})")
        for tr in open_papers[:5]:
            side = "LONG" if tr.get("side") == "long" else "SHORT"
            entry = tr.get("entry") or 0
            tp1 = tr.get("tp1") or 0
            stype = tr.get("setup_type", "?")
            lines.append(f"  {side} @ {entry:.0f} → TP1 {tp1:.0f} | {stype}")

    # ── What to watch — only render triggers that match current state.
    watch: list[str] = []

    funding = features.get("funding_rate")
    if funding is not None:
        funding_pct = funding * 100
        if funding_pct < FUNDING_DEEP_NEG_PCT:
            watch.append(f"Funding flip к ≥0 (сейчас {funding_pct:+.4f}% — глубоко negative, потенциал squeeze)")
        elif funding_pct > FUNDING_OVERHEAT_PCT:
            watch.append(f"Funding flip к ≤0 (сейчас {funding_pct:+.4f}% — перегрев longs)")

    oi = features.get("oi_delta_1h")
    if oi is not None and abs(oi) < OI_FLAT_ABS_PCT:
        watch.append("OI 1h breakout (сейчас flat — пробой ±1% даст направление)")

    oi_div_z = features.get("oi_price_div_1h_z")
    if oi_div_z is not None and abs(oi_div_z) > OI_DIV_Z_THRESHOLD:
        sign = "цена↑ + OI↓ — слабое движение" if oi_div_z < 0 else "цена↓ + OI↑ — поджимают шорты"
        watch.append(f"OI/price divergence z={oi_div_z:+.1f} ({sign}) — ждать resync")

    if regime.get("diverge"):
        watch.append("Macro ≠ Micro — ждать выравнивания TF (см. блок РЕЖИМ)")

    if watch:
        lines.append("")
        lines.append("👀 ЧТО ОТСЛЕЖИВАТЬ")
        for w in watch:
            lines.append(f"  • {w}")

    # ── Persist audit entry (TZ-ADVISE-AUDIT 2026-05-07)
    try:
        from services.advisor.audit import log_advise_call
        regime_states = {tf: (regime.get(tf, (None, {}))[0]) for tf in ("4h", "1h", "15m")}
        log_advise_call(
            verdict=verdict,
            reasoning=list(reasoning),
            regime_4h=regime_states.get("4h"),
            regime_1h=regime_states.get("1h"),
            regime_15m=regime_states.get("15m"),
            macro_micro_diverge=bool(regime.get("diverge")),
            btc_price=(price_info[0] if price_info else None),
            setups_count=len(setups),
            open_paper_trades=len(open_papers),
        )
    except Exception:
        pass  # never block /advise on audit-write failure

    return "\n".join(lines)
