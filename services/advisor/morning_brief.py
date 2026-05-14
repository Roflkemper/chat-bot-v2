"""Morning brief — executive summary for the operator's daily routine.

The operator's typical day starts with: rates, news, SNP correlation,
session levels, liquidations, /advise, and then they build a plan. This
module replaces those 5+ commands with one /morning_brief that surfaces:

  1. ACTION (single-line: HOLD / REDUCE / ADD / WAIT) — the bottom line
  2. NIGHT EVENTS — cascade liquidations + setup confirmations during last 12h
  3. CURRENT STATE — price, regime, RSI, GRID PAUSE signal, MARGIN
  4. BEST ACTIVE SETUP — the single highest-PF setup right now (not all 9 papers)
  5. CALENDAR — upcoming session opens (Warsaw/SNP) + funding
  6. RISK — margin distance to liq, drawdown picture

This is NOT a replacement for /advise — that one stays as the deep-dive view.
/morning_brief is for the 30-second daily scan.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LIQ_LIVE_CSV = Path("market_live/liquidations.csv")
SETUPS_PATH = Path("state/setups.jsonl")
PAPER_TRADES_PATH = Path("state/paper_trades.jsonl")
REGIME_STATE_PATH = Path("state/regime_state.json")
STATE_LATEST_PATH = Path("docs/STATE/state_latest.json")

# Sessions in UTC (matches advisor v2 session windows).
_SESSIONS = (
    ("Asia",   0, 9),
    ("London", 7, 16),
    ("NY-AM",  13, 22),
)

# Cascade thresholds matched against backtest TZ (post-cascade backtest).
CASCADE_BTC_THRESHOLD = 5.0   # >=5 BTC in 5min = strong cascade (n=103, 73% pct_up 12h)


# ─── helpers ──────────────────────────────────────────────────────────────

def _load_jsonl(p: Path, since: datetime | None = None) -> list[dict]:
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if since:
                ts = e.get("ts")
                if not ts:
                    continue
                try:
                    e_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if e_dt < since:
                        continue
                except Exception:
                    continue
            out.append(e)
    except OSError:
        return []
    return out


def _detect_recent_cascades(now_utc: datetime, lookback_hours: int = 12) -> list[dict]:
    """Find liquidation cascades in last N hours.

    Cascade = >=CASCADE_BTC_THRESHOLD BTC of one-sided liquidations within any
    rolling 5-minute window. Returns list of cascades sorted by ts descending.
    """
    if not LIQ_LIVE_CSV.exists():
        return []
    try:
        import pandas as pd
        df = pd.read_csv(LIQ_LIVE_CSV)
        if df.empty or "ts_utc" not in df.columns:
            return []
        df["ts"] = pd.to_datetime(df["ts_utc"], utc=True)
        df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
        cutoff = now_utc - timedelta(hours=lookback_hours)
        df = df[df["ts"] >= cutoff]
        if df.empty:
            return []

        cascades: list[dict] = []
        for side_label, side_filter in (("long_liq", "short"), ("short_liq", "long")):
            # NB: Bybit 'side' = the liquidated position side. 'short' here means
            # SHORT positions force-closed (forced buys, market rallies).
            sub = df[df["side"] == side_filter].sort_values("ts").reset_index(drop=True)
            if sub.empty:
                continue
            # Slide a 5-minute window via timestamp.
            tss = sub["ts"].values
            qtys = sub["qty"].values
            i = 0
            while i < len(sub):
                window_end = tss[i] + pd.Timedelta(minutes=5).to_timedelta64()
                j = i
                cum_qty = 0.0
                while j < len(sub) and tss[j] <= window_end:
                    cum_qty += qtys[j]
                    j += 1
                if cum_qty >= CASCADE_BTC_THRESHOLD:
                    # Force UTC tz on timestamps so downstream subtractions don't blow up.
                    ts_start = pd.Timestamp(tss[i])
                    ts_end = pd.Timestamp(tss[j - 1])
                    if ts_start.tzinfo is None:
                        ts_start = ts_start.tz_localize("UTC")
                    if ts_end.tzinfo is None:
                        ts_end = ts_end.tz_localize("UTC")
                    cascades.append({
                        "kind": side_label,   # long_liq | short_liq
                        "qty": float(cum_qty),
                        "ts_start": ts_start.to_pydatetime(),
                        "ts_end": ts_end.to_pydatetime(),
                        "price_at_start": float(sub.iloc[i]["price"]),
                    })
                    # Skip past this window to avoid double-counting.
                    i = j
                else:
                    i += 1
        cascades.sort(key=lambda c: c["ts_start"], reverse=True)
        return cascades
    except Exception:
        logger.exception("morning_brief.cascade_detection_failed")
        return []


def _next_session_opens(now_utc: datetime) -> list[tuple[str, datetime]]:
    """Return upcoming session opens within next 24h, ordered by time."""
    out = []
    today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    for label, start_h, _ in _SESSIONS:
        for day_offset in (0, 1):
            open_dt = today + timedelta(days=day_offset, hours=start_h)
            if open_dt > now_utc:
                out.append((label, open_dt))
                break
    out.sort(key=lambda x: x[1])
    return out


def _load_active_setups(now_utc: datetime, hours: int = 6) -> list[dict]:
    """Return high-confidence setups from last N hours (newest first)."""
    cutoff = now_utc - timedelta(hours=hours)
    setups = _load_jsonl(SETUPS_PATH, since=cutoff)
    return sorted(setups, key=lambda s: s.get("ts", ""), reverse=True)


def _load_recent_paper_closes(now_utc: datetime, hours: int = 24) -> list[dict]:
    """Closed paper trades in last N hours."""
    cutoff = now_utc - timedelta(hours=hours)
    events = _load_jsonl(PAPER_TRADES_PATH, since=cutoff)
    return [e for e in events if e.get("action") in ("TP1", "TP2", "SL", "EXPIRE", "TIME_STOP")]


def _read_state_latest() -> dict:
    if not STATE_LATEST_PATH.exists():
        return {}
    try:
        return json.loads(STATE_LATEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_regime_summary() -> dict | None:
    if not REGIME_STATE_PATH.exists():
        return None
    try:
        data = json.loads(REGIME_STATE_PATH.read_text(encoding="utf-8"))
        btc = data.get("symbols", {}).get("BTCUSDT", {})
        if not btc:
            return None
        return {
            "current": btc.get("current_primary"),
            "since": btc.get("primary_since"),
            "age_bars": btc.get("regime_age_bars"),
        }
    except Exception:
        return None


# ─── action recommendation ────────────────────────────────────────────────

def _setup_climate(
    pause_signal: dict,
    regime: dict | None,
    features: dict,
    cascades: list[dict],
) -> list[tuple[str, str, str]]:
    """Hot/Cold rating for each major setup category.

    Returns list of (category, status, reason) tuples. status is one of:
      🔥 HOT      — conditions favourable, take signals seriously
      🟡 NEUTRAL — mixed picture, use normal sizing
      ❄️ COLD    — conditions unfavourable, skip / reduce size

    Categories:
      LONG_GRID   — running long-side grid bots
      SHORT_GRID  — running short-side grid bots
      LONG_DIV    — taking divergence-based long setups
      SHORT_NEW   — opening fresh short positions
      POST_CASCADE — taking cascade-reversal trades
    """
    out: list[tuple[str, str, str]] = []
    regime_str = (regime or {}).get("current") or ""
    is_trend_up = regime_str in ("TREND_UP", "IMPULSE_UP")
    is_trend_down = regime_str in ("TREND_DOWN", "IMPULSE_DOWN")
    rsi_1h = features.get("rsi_14")
    funding = features.get("funding_rate")
    short_pause = pause_signal.get("short_pause", False)
    long_pause = pause_signal.get("long_pause", False)

    now = datetime.now(timezone.utc)
    fresh_strong_cascade = any(
        c["qty"] >= CASCADE_BTC_THRESHOLD and (now - c["ts_start"]).total_seconds() < 6 * 3600
        for c in cascades
    )

    # ── LONG_GRID
    if long_pause:
        out.append(("LONG_GRID", "❄️ COLD", "BTC падает >2% за час — паузу LONG-ботам"))
    elif is_trend_down:
        out.append(("LONG_GRID", "❄️ COLD", "режим trend_down — LONG-боты ловят ножи"))
    elif is_trend_up:
        out.append(("LONG_GRID", "🔥 HOT", "режим trend_up — LONG-боты на тренде"))
    else:
        out.append(("LONG_GRID", "🟡 NEUTRAL", "range — обычный режим"))

    # ── SHORT_GRID
    if short_pause:
        out.append(("SHORT_GRID", "❄️ COLD", "BTC растёт >2% за час — паузу SHORT-ботам"))
    elif is_trend_up:
        out.append(("SHORT_GRID", "❄️ COLD", "режим trend_up — SHORT-боты против тренда"))
    elif is_trend_down:
        out.append(("SHORT_GRID", "🔥 HOT", "режим trend_down — SHORT-боты на тренде"))
    else:
        out.append(("SHORT_GRID", "🟡 NEUTRAL", "range — обычный режим"))

    # ── LONG_DIV (наши divergence detectors)
    # Backtest: на bull-биасном периоде PF=1.78, с BoS = PF=4.49.
    # Hot если: rsi oversold (<35) ИЛИ свежий long_liq cascade ИЛИ regime trend_up
    # Cold если: rsi overbought (>70) И regime trend_down
    if rsi_1h is not None and rsi_1h < 35:
        out.append(("LONG_DIV", "🔥 HOT", f"RSI {rsi_1h:.0f} перепродан — divergence чаще ловит дно"))
    elif fresh_strong_cascade and any(c["kind"] == "long_liq" for c in cascades):
        out.append(("LONG_DIV", "🔥 HOT", "свежий long-liq cascade — backtest 73% pct_up"))
    elif is_trend_down and rsi_1h is not None and rsi_1h > 70:
        out.append(("LONG_DIV", "❄️ COLD", "downtrend + RSI overbought — divergence не работает"))
    elif is_trend_down:
        out.append(("LONG_DIV", "🟡 NEUTRAL", "downtrend — div-сигналы рискованнее, требуй BoS-confirm"))
    else:
        out.append(("LONG_DIV", "🟡 NEUTRAL", "стандартные условия"))

    # ── SHORT_NEW (открыть новый short)
    # Наш backtest показал: SHORT side НЕТ EDGE на bull-биасе. Honest stance:
    # отговариваем новые шорты, кроме явных rally-fade условий.
    if is_trend_up:
        out.append(("SHORT_NEW", "❄️ COLD", "trend_up — backtest: short divergence без edge"))
    elif rsi_1h is not None and rsi_1h > 75:
        out.append(("SHORT_NEW", "🟡 NEUTRAL", f"RSI {rsi_1h:.0f} overbought — rally-fade возможен"))
    else:
        out.append(("SHORT_NEW", "❄️ COLD", "общий bull-bias 2y — short setups дают PF<1"))

    # ── POST_CASCADE
    if fresh_strong_cascade:
        # Отдельная категория — есть условие = HOT
        kind = next((c["kind"] for c in cascades if c["qty"] >= CASCADE_BTC_THRESHOLD), None)
        kind_word = "long-liq cascade" if kind == "long_liq" else "short-liq cascade" if kind == "short_liq" else "cascade"
        out.append(("POST_CASCADE", "🔥 HOT", f"свежий {kind_word} ≥{CASCADE_BTC_THRESHOLD} BTC — окно открыто 12h"))
    else:
        out.append(("POST_CASCADE", "❄️ COLD", "каскадов нет — нет триггера"))

    return out


def _recommend_action(
    cascades: list[dict],
    pause_signal: dict,
    setups: list[dict],
    regime: dict | None,
) -> tuple[str, str]:
    """Return (action_label, one_line_reason).

    Priority order:
      1. GRID PAUSE active → REDUCE (most urgent)
      2. Strong cascade in last 6h with no setup yet → WATCH
      3. Confirmed high-PF setup just printed → ADD
      4. Otherwise → HOLD
    """
    now = datetime.now(timezone.utc)

    if pause_signal.get("short_pause"):
        return ("REDUCE / PAUSE SHORT", f"BTC +{pause_signal['change_60m_pct']:.2f}% за час, {pause_signal['trend_bars_up']} bull-свечей")
    if pause_signal.get("long_pause"):
        return ("REDUCE / PAUSE LONG", f"BTC {pause_signal['change_60m_pct']:+.2f}% за час, {pause_signal['trend_bars_down']} bear-свечей")

    # Confirmed high-PF setup printed in last 4h?
    fresh_cutoff = now - timedelta(hours=4)
    high_pf_types = {"long_div_bos_confirmed", "long_div_bos_15m"}
    fresh_high_pf = []
    for s in setups:
        ts = s.get("ts")
        if not ts:
            continue
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if ts_dt < fresh_cutoff:
                continue
        except Exception:
            continue
        if s.get("setup_type") in high_pf_types:
            fresh_high_pf.append(s)
    if fresh_high_pf:
        s = fresh_high_pf[0]
        stype = s.get("setup_type", "?")
        entry = s.get("entry_price", 0)
        return ("ADD LONG", f"{stype} confirmed @ {entry:.0f} (backtest PF=4-5)")

    # Strong cascade with no immediate confirmed setup
    strong_cascade_recent = [
        c for c in cascades
        if c["qty"] >= CASCADE_BTC_THRESHOLD and (now - c["ts_start"]).total_seconds() < 6 * 3600
    ]
    if strong_cascade_recent:
        c = strong_cascade_recent[0]
        kind_ru = "long-liquidations (рынок упал)" if c["kind"] == "long_liq" else "short-liquidations (рынок вырос)"
        return ("WATCH", f"Каскад {c['qty']:.0f} BTC ({kind_ru}) — backtest 73% pct_up 12h")

    return ("HOLD", "Спокойный рынок, нет триггеров для действий")


# ─── main builder ─────────────────────────────────────────────────────────

def build_morning_brief() -> str:
    """Compose the executive summary message."""
    from services.advisor.advisor_v2 import (
        _classify_v2_live,
        _compute_pause_signal,
        _read_features_last,
        _read_last_price,
        _read_margin_block,
    )

    now = datetime.now(timezone.utc)
    lines: list[str] = []

    # ── Header
    lines.append(f"🌅 MORNING BRIEF — {now.strftime('%Y-%m-%d %H:%M UTC')}")

    price_info = _read_last_price()
    if price_info:
        price, age_min = price_info
        lines.append(f"BTC {price:,.0f} | data {age_min:.0f}min old")
    else:
        lines.append("⚠️ Нет live price")
    lines.append("")

    # ── 1. ACTION (top-line bottom-line)
    pause_signal = _compute_pause_signal()
    cascades = _detect_recent_cascades(now, lookback_hours=12)
    setups = _load_active_setups(now, hours=6)
    regime = _read_regime_summary()

    action, reason = _recommend_action(cascades, pause_signal, setups, regime)
    lines.append("┌─────────────────────────────────────")
    lines.append(f"│ ▶ ДЕЙСТВИЕ: {action}")
    lines.append(f"│   {reason}")
    lines.append("└─────────────────────────────────────")
    lines.append("")

    # ── 2. NIGHT EVENTS (last 12h)
    if cascades:
        lines.append("🌙 СОБЫТИЯ ЗА НОЧЬ (12h)")
        for c in cascades[:3]:
            ts_h = (now - c["ts_start"]).total_seconds() / 3600.0
            kind_emoji = "🟢" if c["kind"] == "long_liq" else "🔴"
            kind_word = "long-liq (упали)" if c["kind"] == "long_liq" else "short-liq (выросли)"
            lines.append(f"  {kind_emoji} {ts_h:.1f}h назад: каскад {c['qty']:.1f} BTC ({kind_word}) @ ${c['price_at_start']:,.0f}")
        if len(cascades) > 3:
            lines.append(f"  ... и ещё {len(cascades) - 3} каскад(ов)")
        lines.append("")

    # ── 3. CURRENT STATE
    lines.append("📊 ТЕКУЩЕЕ ПОЛОЖЕНИЕ")
    if regime:
        lines.append(f"  Режим: {regime.get('current', '?')} ({regime.get('age_bars', 0)} баров)")
    features = _read_features_last()
    rsi_1h = features.get("rsi_14")
    if rsi_1h is not None:
        rsi_word = "перекуплен" if rsi_1h > 70 else "перепродан" if rsi_1h < 30 else "нейтрально"
        lines.append(f"  RSI 1h: {rsi_1h:.0f} ({rsi_word})")
    funding = features.get("funding_rate")
    if funding is not None:
        lines.append(f"  Funding: {funding * 100:+.4f}%")
    margin = _read_margin_block()
    if margin:
        coef = margin.get("coefficient")
        avail = margin.get("available_margin_usd")
        dist = margin.get("distance_to_liquidation_pct")
        if coef is not None:
            lines.append(f"  Margin: coef {coef:.2f}, ${avail:,.0f} avail, dist liq {dist:.1f}%")
    if pause_signal.get("change_60m_pct") is not None:
        ch = pause_signal["change_60m_pct"]
        if pause_signal.get("short_pause") or pause_signal.get("long_pause"):
            lines.append(f"  🚨 GRID PAUSE: триггер активен (BTC {ch:+.2f}% за час)")
        else:
            lines.append(f"  ✅ GRID PAUSE: спокойно (BTC {ch:+.2f}% за час, порог ±2%)")

    # SNP correlation (S&P 500 futures via yfinance, 5min cache).
    try:
        from services.advisor.snp_feed import get_snp_snapshot
        snp = get_snp_snapshot()
        if snp.error and not snp.last_close:
            lines.append(f"  S&P futures: данные недоступны ({snp.error[:40]})")
        elif snp.last_close:
            ch1h = f"{snp.change_1h_pct:+.2f}%" if snp.change_1h_pct is not None else "n/a"
            ch24h = f"{snp.change_24h_pct:+.2f}%" if snp.change_24h_pct is not None else "n/a"
            line = f"  S&P futures: {snp.last_close:,.0f} ({ch1h} 1h / {ch24h} 24h)"
            if snp.is_stale:
                line += " ⚠️ stale"
            lines.append(line)
            if snp.correlation_24h is not None:
                corr = snp.correlation_24h
                if corr > 0.5:
                    word = "сильная положительная — risk-on/off в синхроне"
                elif corr > 0.2:
                    word = "умеренная положительная — частичная корреляция"
                elif corr > -0.2:
                    word = "слабая — BTC двигается независимо"
                elif corr > -0.5:
                    word = "умеренная отрицательная — расходимся"
                else:
                    word = "сильная отрицательная — противофаза"
                lines.append(f"  BTC↔S&P 24h corr: {corr:+.2f} ({word})")
    except Exception:
        logger.exception("morning_brief.snp_block_failed")
    lines.append("")

    # ── 4. SETUP CLIMATE (Hot/Cold ratings)
    climate = _setup_climate(pause_signal, regime, features, cascades)
    lines.append("🌡️ КЛИМАТ ДЛЯ СЕТАПОВ")
    for category, status, reason in climate:
        lines.append(f"  {status}  {category:<12} — {reason}")
    lines.append("")

    # ── 5. BEST ACTIVE SETUP (один лучший, не все 9)
    high_conf = [s for s in setups if s.get("confidence_pct", 0) >= 70]
    if high_conf:
        # Prefer high-PF detector types when present
        priority_types = ["long_div_bos_confirmed", "long_div_bos_15m", "long_multi_divergence"]
        best = None
        for ptype in priority_types:
            for s in high_conf:
                if s.get("setup_type") == ptype:
                    best = s
                    break
            if best:
                break
        if best is None:
            best = high_conf[0]
        stype = best.get("setup_type", "?")
        entry = best.get("entry_price")
        sl = best.get("stop_price")
        tp1 = best.get("tp1_price")
        conf = best.get("confidence_pct", 0)
        rr = best.get("risk_reward")
        lines.append("🎯 ЛУЧШИЙ АКТИВНЫЙ СЕТАП")
        lines.append(f"  {stype} @ {entry:.0f} | SL {sl:.0f} | TP1 {tp1:.0f} | conf {conf:.0f}% RR {rr}")
        if "div_bos" in stype:
            lines.append(f"  ⭐ Backtest PF=4-5, walk-forward stable")
        lines.append("")
    else:
        lines.append("🎯 СЕТАПЫ: нет с conf≥70% за последние 6h")
        lines.append("")

    # ── 5. PAPER TRADES статистика за ночь
    closes = _load_recent_paper_closes(now, hours=24)
    if closes:
        wins = [e for e in closes if (e.get("realized_pnl_usd") or 0) > 0]
        losses = [e for e in closes if (e.get("realized_pnl_usd") or 0) < 0]
        net = sum(e.get("realized_pnl_usd") or 0 for e in closes)
        lines.append(f"📜 PAPER TRADES за 24h: {len(closes)} закрытых (W{len(wins)}/L{len(losses)}), PnL ${net:+.0f}")
        lines.append("")

    # ── 6. CALENDAR
    lines.append("📅 БЛИЖАЙШИЕ СОБЫТИЯ")
    sessions = _next_session_opens(now)
    for label, dt in sessions[:3]:
        delta_h = (dt - now).total_seconds() / 3600.0
        marker = " ⭐" if label in ("London", "NY-AM") else ""
        lines.append(f"  {label} open: {dt.strftime('%H:%M UTC')} (через {delta_h:.1f}h){marker}")
    # Funding rate next (always 00:00, 08:00, 16:00 UTC for Binance)
    next_funding = None
    for h in (0, 8, 16):
        candidate = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate > now:
            next_funding = candidate
            break
    if next_funding is None:
        next_funding = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta_h = (next_funding - now).total_seconds() / 3600.0
    lines.append(f"  Funding: {next_funding.strftime('%H:%M UTC')} (через {delta_h:.1f}h)")

    return "\n".join(lines)
