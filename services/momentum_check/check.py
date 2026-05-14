"""/momentum_check builder + renderer.

Single source of truth для intraday-снимка рынка.

Components:
- session: Asia / London / NY_AM / NY_PM (через ict_killzones)
- 15m & 1h movement character: импульс/откат/боковик/истощение
- volume trend (rolling N candles vs baseline)
- RSI divergence (через event_detectors/rsi_divergence)
- recent liquidations (читает market_live/liquidations.csv)
- OI / funding / premium (state/deriv_live.json)
- taker imbalance если есть в parquet features

Output: dict + Russian-language Telegram message.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_LIQ_CSV = _ROOT / "market_live" / "liquidations.csv"
_DERIV_LIVE = _ROOT / "state" / "deriv_live.json"
_MARKET_1M = _ROOT / "market_live" / "market_1m.csv"
_MARKET_15M = _ROOT / "market_live" / "market_15m.csv"
_MARKET_1H = _ROOT / "market_live" / "market_1h.csv"


# ── Session detection ─────────────────────────────────────────────────

def _current_session(now_utc: datetime) -> str:
    """Asia/London/NY_AM/NY_PM. ICT killzones (UTC)."""
    h = now_utc.hour
    if 0 <= h < 7:
        return "ASIA"
    if 7 <= h < 12:
        return "LONDON"
    if 12 <= h < 16:
        return "NY_AM"
    if 16 <= h < 21:
        return "NY_PM"
    return "ASIA"  # 21-24 UTC = Asia opening


def _session_start(now_utc: datetime) -> datetime:
    """When current session began (for VWAP/range stats since session)."""
    h = now_utc.hour
    today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    if 0 <= h < 7:
        return today
    if 7 <= h < 12:
        return today.replace(hour=7)
    if 12 <= h < 16:
        return today.replace(hour=12)
    if 16 <= h < 21:
        return today.replace(hour=16)
    return today.replace(hour=21)


# ── OHLCV loaders ──────────────────────────────────────────────────────

def _load_csv_tail(path: Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return rows[-n:]
    except OSError:
        return []


# ── Movement character ────────────────────────────────────────────────

def _classify_movement(rows: list[dict]) -> dict:
    """rows = N последних 15m или 1h candles. Returns character + stats."""
    if not rows or len(rows) < 5:
        return {"character": "no_data", "n_bars": len(rows)}

    closes = [float(r.get("close", 0) or 0) for r in rows]
    opens = [float(r.get("open", 0) or 0) for r in rows]
    highs = [float(r.get("high", 0) or 0) for r in rows]
    lows = [float(r.get("low", 0) or 0) for r in rows]
    vols = [float(r.get("volume", 0) or 0) for r in rows]

    if not all(closes) or not all(opens):
        return {"character": "data_invalid", "n_bars": len(rows)}

    move_pct = (closes[-1] / closes[0] - 1) * 100

    # Range / ATR style
    bar_ranges = [(highs[i] - lows[i]) / closes[i] * 100 for i in range(len(rows))]
    avg_range = sum(bar_ranges) / len(bar_ranges)
    last_range = bar_ranges[-1]

    # Last 3 vs prev 3 momentum
    if len(closes) >= 6:
        last3_move = (closes[-1] / closes[-4] - 1) * 100
        prev3_move = (closes[-4] / closes[-7] if len(closes) >= 7 else closes[-6] - 1) * 100 if len(closes) >= 7 else 0
    else:
        last3_move = move_pct / 2
        prev3_move = 0

    # Volume trend: last 3 vs prev 3
    if len(vols) >= 6:
        last3_vol = sum(vols[-3:]) / 3
        prev3_vol = sum(vols[-6:-3]) / 3
        vol_trend_pct = (last3_vol / prev3_vol - 1) * 100 if prev3_vol > 0 else 0
    else:
        vol_trend_pct = 0

    # Direction
    if move_pct > 0.4:
        direction = "up"
    elif move_pct < -0.4:
        direction = "down"
    else:
        direction = "flat"

    # Character
    character = _movement_character(
        move_pct=move_pct,
        last3_move=last3_move,
        prev3_move=prev3_move,
        avg_range=avg_range,
        last_range=last_range,
        vol_trend_pct=vol_trend_pct,
    )

    return {
        "character": character,
        "direction": direction,
        "n_bars": len(rows),
        "move_pct": round(move_pct, 2),
        "last3_move_pct": round(last3_move, 2),
        "vol_trend_pct": round(vol_trend_pct, 1),
        "avg_range_pct": round(avg_range, 3),
        "last_range_pct": round(last_range, 3),
        "last_close": closes[-1],
    }


def _movement_character(
    move_pct: float,
    last3_move: float,
    prev3_move: float,
    avg_range: float,
    last_range: float,
    vol_trend_pct: float,
) -> str:
    """Категоризация движения как character."""
    abs_move = abs(move_pct)

    # Chop: small overall move + small ranges
    if abs_move < 0.3 and avg_range < 0.4:
        return "CHOP"  # боковик / шум

    # Strong impulse: large move + ranges expanding
    if abs_move > 1.5 and last_range > avg_range * 1.3:
        return "STRONG_IMPULSE"

    # Continued momentum: last3 same direction, larger than prev3
    if (move_pct > 0 and last3_move > prev3_move + 0.2) or \
       (move_pct < 0 and last3_move < prev3_move - 0.2):
        return "MOMENTUM"

    # Exhaustion: move was strong but last3 reverses + volume falling
    if abs_move > 0.8:
        if (move_pct > 0 and last3_move < 0) or (move_pct < 0 and last3_move > 0):
            return "EXHAUSTED_REVERSAL"
        if vol_trend_pct < -20 and abs(last3_move) < abs_move / 3:
            return "EXHAUSTED_FADING"

    # Pullback within trend
    if abs_move > 0.5 and (
        (move_pct > 0 and last3_move < 0 and abs(last3_move) < move_pct / 2)
        or (move_pct < 0 and last3_move > 0 and abs(last3_move) < abs(move_pct) / 2)
    ):
        return "PULLBACK"

    # Default
    return "DRIFT"


# ── Liquidations summary ──────────────────────────────────────────────

def _liquidation_pressure(now_utc: datetime, windows: tuple[int, ...] = (5, 15, 60)) -> dict:
    """Аггрегирует liquidations за окна (минут).

    Returns: dict per window with long/short btc + count + recency.
    """
    if not _LIQ_CSV.exists():
        return {"available": False, "reason": "no_file"}

    out: dict = {"available": True, "windows": {}}
    try:
        with _LIQ_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except OSError:
        return {"available": False, "reason": "read_failed"}

    if not rows:
        return {"available": True, "windows": {}, "note": "empty_file"}

    last_ts_str = rows[-1].get("ts_utc", "")
    try:
        last_ts = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
        out["last_event_age_min"] = round((now_utc - last_ts).total_seconds() / 60, 1)
    except (ValueError, KeyError):
        out["last_event_age_min"] = None

    for w_min in windows:
        cutoff = now_utc - timedelta(minutes=w_min)
        long_btc = 0.0
        short_btc = 0.0
        n = 0
        for r in rows:
            try:
                ts = datetime.fromisoformat(r.get("ts_utc", "").replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
                qty = float(r.get("qty") or 0)
                if qty <= 0:
                    continue
                side = (r.get("side") or "").lower()
                if side == "long":
                    long_btc += qty
                elif side == "short":
                    short_btc += qty
                n += 1
            except (ValueError, TypeError):
                continue
        out["windows"][f"{w_min}m"] = {
            "n": n,
            "long_btc": round(long_btc, 4),
            "short_btc": round(short_btc, 4),
            "net_btc": round(long_btc - short_btc, 4),  # +ve = больше long-liq (squeeze down? нет, это long-positions liquidated → wider sell pressure)
        }
    return out


# ── Deriv flow ────────────────────────────────────────────────────────

def _volume_profile_zones() -> dict:
    """Compute simple 24h volume profile: POC + 70% value area.

    Uses last 24h of 1m bars from market_live/market_1m.csv.
    POC = price level with highest traded volume.
    Value area = 70% of volume around POC.
    """
    out: dict = {}
    try:
        import pandas as pd
        rows = _load_csv_tail(_MARKET_1M, 1440)  # 24h × 60min
        if len(rows) < 100:
            return out
        df = pd.DataFrame(rows)
        for col in ("close", "volume", "high", "low"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close", "volume"])
        if df.empty:
            return out
        # Bin prices into N buckets, sum volume
        n_bins = 50
        price_min = float(df["low"].min()) if "low" in df.columns else float(df["close"].min())
        price_max = float(df["high"].max()) if "high" in df.columns else float(df["close"].max())
        if price_max <= price_min:
            return out
        bin_size = (price_max - price_min) / n_bins
        bins: list[float] = [0.0] * n_bins
        for _, row in df.iterrows():
            close = float(row["close"])
            vol = float(row["volume"])
            idx = min(int((close - price_min) / bin_size), n_bins - 1)
            if idx >= 0:
                bins[idx] += vol
        if max(bins) <= 0:
            return out
        poc_idx = bins.index(max(bins))
        poc_price = price_min + (poc_idx + 0.5) * bin_size

        # Value area 70%: extend symmetrically from POC until 70% volume captured
        total_vol = sum(bins)
        target = 0.7 * total_vol
        vol_in_va = bins[poc_idx]
        lo, hi = poc_idx, poc_idx
        while vol_in_va < target and (lo > 0 or hi < n_bins - 1):
            if lo > 0 and (hi >= n_bins - 1 or bins[lo - 1] >= bins[hi + 1]):
                lo -= 1
                vol_in_va += bins[lo]
            elif hi < n_bins - 1:
                hi += 1
                vol_in_va += bins[hi]
            else:
                break
        va_low = price_min + lo * bin_size
        va_high = price_min + (hi + 1) * bin_size
        last_close = float(df["close"].iloc[-1])

        out["poc_price"] = round(poc_price, 1)
        out["va_low"] = round(va_low, 1)
        out["va_high"] = round(va_high, 1)
        out["last_close"] = round(last_close, 1)
        out["dist_to_poc_pct"] = round((last_close / poc_price - 1) * 100, 2) if poc_price > 0 else None
        # Position vs VA
        if last_close > va_high:
            out["position_vs_va"] = "above"
        elif last_close < va_low:
            out["position_vs_va"] = "below"
        else:
            out["position_vs_va"] = "inside"
    except Exception:
        logger.debug("_volume_profile_zones failed", exc_info=True)
    return out


def _structural_levels() -> dict:
    """Read PDH/PDL/session levels from forecast features parquet (если свежий)."""
    out: dict = {}
    try:
        import pandas as pd
        df = pd.read_parquet(_ROOT / "data" / "forecast_features" / "full_features_1y.parquet")
        if df.empty:
            return out
        last = df.iloc[-1]
        for col in ("dist_to_pdh_pct", "dist_to_pdl_pct",
                    "asia_high_broken", "asia_low_broken",
                    "london_high_broken", "london_low_broken",
                    "ny_am_high_broken", "ny_am_low_broken",
                    "bars_since_london_high_break", "bars_since_ny_am_high_break"):
            if col in df.columns:
                v = last.get(col)
                if pd.notna(v):
                    out[col] = float(v) if not isinstance(v, bool) else bool(v)
    except Exception:
        logger.debug("_structural_levels failed", exc_info=True)
    return out


def _deriv_flow() -> dict:
    if not _DERIV_LIVE.exists():
        return {"available": False}
    try:
        data = json.loads(_DERIV_LIVE.read_text(encoding="utf-8"))
        btc = data.get("BTCUSDT", {}) or {}
        return {
            "available": True,
            "funding_8h": btc.get("funding_rate_8h"),
            "oi_change_1h_pct": btc.get("oi_change_1h_pct"),
            "premium_pct": btc.get("premium_pct"),
            "mark_price": btc.get("mark_price"),
            "ts": data.get("last_updated", ""),
            # Long/Short market sentiment (2026-05-07)
            "global_long_account_pct": btc.get("global_long_account_pct"),
            "global_short_account_pct": btc.get("global_short_account_pct"),
            "top_trader_long_pct": btc.get("top_trader_long_pct"),
            "top_trader_short_pct": btc.get("top_trader_short_pct"),
            "taker_buy_pct": btc.get("taker_buy_pct"),
            "taker_sell_pct": btc.get("taker_sell_pct"),
            "bybit_long_pct": btc.get("bybit_long_pct"),
            "bybit_short_pct": btc.get("bybit_short_pct"),
        }
    except (OSError, json.JSONDecodeError):
        return {"available": False}


# ── RSI divergence ─────────────────────────────────────────────────────

def _check_divergence(rows_15m: list[dict], rows_1h: list[dict]) -> dict:
    """Use existing event_detectors/rsi_divergence if pandas available."""
    out = {"15m": None, "1h": None}
    try:
        import pandas as pd
        from services.market_intelligence.event_detectors.rsi_divergence import detect_rsi_divergence

        for label, rows in (("15m", rows_15m), ("1h", rows_1h)):
            if len(rows) < 30:
                continue
            df = pd.DataFrame(rows)
            for col in ("close", "high", "low", "open", "volume"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            try:
                sig = detect_rsi_divergence(df)
                if sig and sig.div_type and str(sig.div_type) != "DivType.NONE":
                    out[label] = {
                        "type": str(sig.div_type).split(".")[-1],
                        "note": getattr(sig, "note", ""),
                    }
            except Exception:
                logger.debug("divergence check failed for %s", label, exc_info=True)
    except ImportError:
        pass
    return out


# ── Aggregation ────────────────────────────────────────────────────────

@dataclass
class MomentumSnapshot:
    generated_at: str
    session: str
    minutes_into_session: int
    last_close: float
    move_15m: dict
    move_1h: dict
    divergence: dict
    liquidations: dict
    deriv: dict
    verdict: str
    notes: list[str]
    structural: dict = None  # type: ignore
    volume_profile: dict = None  # type: ignore


def build_momentum_check(now_utc: Optional[datetime] = None) -> MomentumSnapshot:
    now = now_utc or datetime.now(timezone.utc)
    sess = _current_session(now)
    sess_start = _session_start(now)
    sess_min = int((now - sess_start).total_seconds() / 60)

    # 15m candles — берём 20 бар (5 часов)
    rows_15m = _load_csv_tail(_MARKET_15M, 20)
    rows_1h = _load_csv_tail(_MARKET_1H, 24)
    rows_1m = _load_csv_tail(_MARKET_1M, 60)

    move_15m = _classify_movement(rows_15m)
    move_1h = _classify_movement(rows_1h)

    last_close = move_15m.get("last_close") or move_1h.get("last_close") or 0
    if not last_close and rows_1m:
        last_close = float(rows_1m[-1].get("close") or 0)

    divergence = _check_divergence(rows_15m, rows_1h)
    liquidations = _liquidation_pressure(now)
    deriv = _deriv_flow()

    verdict, notes = _build_verdict(
        sess=sess, move_15m=move_15m, move_1h=move_1h,
        divergence=divergence, liquidations=liquidations, deriv=deriv,
    )

    structural = _structural_levels()
    volume_profile = _volume_profile_zones()

    return MomentumSnapshot(
        generated_at=now.isoformat(timespec="seconds"),
        session=sess,
        minutes_into_session=sess_min,
        last_close=last_close,
        move_15m=move_15m,
        move_1h=move_1h,
        divergence=divergence,
        liquidations=liquidations,
        deriv=deriv,
        verdict=verdict,
        notes=notes,
        structural=structural,
        volume_profile=volume_profile,
    )


def _build_verdict(*, sess: str, move_15m: dict, move_1h: dict,
                   divergence: dict, liquidations: dict, deriv: dict) -> tuple[str, list[str]]:
    """Compose short verdict + supporting notes."""
    notes: list[str] = []
    char_15 = move_15m.get("character", "no_data")
    char_1h = move_1h.get("character", "no_data")

    # Headline verdict
    if char_15 == "STRONG_IMPULSE":
        verdict_head = f"СИЛЬНЫЙ ИМПУЛЬС ({move_15m.get('direction', '?')}) на 15m"
    elif char_15 == "EXHAUSTED_REVERSAL":
        verdict_head = "ИСТОЩЕНИЕ + РАЗВОРОТ на 15m"
    elif char_15 == "EXHAUSTED_FADING":
        verdict_head = "ИСТОЩЕНИЕ (объём падает, движение замедляется)"
    elif char_15 == "MOMENTUM":
        verdict_head = f"МОМЕНТУМ ({move_15m.get('direction', '?')})"
    elif char_15 == "PULLBACK":
        verdict_head = "ОТКАТ внутри тренда"
    elif char_15 == "CHOP":
        verdict_head = "БОКОВИК / шум"
    else:
        verdict_head = f"ДРИФТ ({move_15m.get('direction', 'flat')})"

    # Confluence notes
    if char_15 == char_1h and char_15 not in ("CHOP", "DRIFT"):
        notes.append(f"15m и 1h согласованы: {char_15}")
    elif char_1h in ("MOMENTUM", "STRONG_IMPULSE") and char_15 in ("PULLBACK", "EXHAUSTED_FADING"):
        notes.append(f"1h={char_1h}, 15m={char_15} — pullback/fade в большем тренде")

    # Divergence
    div_15 = divergence.get("15m") if isinstance(divergence, dict) else None
    div_1h = divergence.get("1h") if isinstance(divergence, dict) else None
    if div_15:
        notes.append(f"⚠️ RSI divergence 15m: {div_15.get('type')}")
    if div_1h:
        notes.append(f"⚠️ RSI divergence 1h: {div_1h.get('type')}")

    # Volume trend
    vol_15 = move_15m.get("vol_trend_pct", 0) or 0
    if vol_15 < -25:
        notes.append(f"Объём падает ({vol_15:+.0f}% на последних свечах)")
    elif vol_15 > 30:
        notes.append(f"Объём растёт ({vol_15:+.0f}%)")

    # Liquidations
    if liquidations.get("available") and liquidations.get("windows"):
        w15 = liquidations["windows"].get("15m", {})
        if w15.get("n", 0) > 0:
            net_btc = w15.get("net_btc", 0)
            if w15.get("long_btc", 0) > 0.5:
                notes.append(f"Liquidations 15m: long-side {w15['long_btc']:.2f} BTC ликвидировано (sell pressure)")
            if w15.get("short_btc", 0) > 0.5:
                notes.append(f"Liquidations 15m: short-side {w15['short_btc']:.2f} BTC ликвидировано (buy pressure)")
        else:
            notes.append("Liquidations 15m: тихо")

    # Deriv
    if deriv.get("available"):
        funding = deriv.get("funding_8h")
        oi = deriv.get("oi_change_1h_pct")
        prem = deriv.get("premium_pct")
        if funding is not None:
            f_pct = funding * 100
            if f_pct > 0.01:
                notes.append(f"Funding {f_pct:+.4f}% — longs платят (потенциал short squeeze ниже)")
            elif f_pct < -0.01:
                notes.append(f"Funding {f_pct:+.4f}% — shorts платят (потенциал long squeeze)")
        if oi is not None and abs(oi) > 0.5:
            notes.append(f"OI 1h: {oi:+.2f}%")
        if prem is not None and abs(prem) > 0.05:
            notes.append(f"Premium {prem:+.3f}% (mark vs index)")

        # Long/Short extreme — contrarian setup
        gl = deriv.get("global_long_account_pct")
        gs = deriv.get("global_short_account_pct")
        tl = deriv.get("top_trader_long_pct")
        ts_pct = deriv.get("top_trader_short_pct")
        tb = deriv.get("taker_buy_pct")
        tk_s = deriv.get("taker_sell_pct")

        # Скос > 60% в одну сторону — толпа crowded, обычно контра
        if gl is not None and gl >= 60:
            notes.append(f"⚠️ Толпа в LONG ({gl}%) — обычно контра, риск short squeeze ВНИЗ")
        elif gs is not None and gs >= 60:
            notes.append(f"⚠️ Толпа в SHORT ({gs}%) — обычно контра, риск long squeeze ВВЕРХ")

        # Top traders ≠ retail — это смартмани сигнал
        if tl is not None and gl is not None and abs(tl - gl) >= 5:
            if tl > gl:
                notes.append(f"Топ-трейдеры в LONG ({tl}%) больше чем толпа ({gl}%) — bullish бис от смартмани")
            else:
                notes.append(f"Топ-трейдеры в SHORT ({ts_pct}%) больше чем толпа ({gs}%) — bearish бис от смартмани")

        # Taker экстремум — сильное направленное давление прямо сейчас
        if tb is not None and tb >= 65:
            notes.append(f"Taker buy {tb}% — сильное покупательское давление сейчас")
        elif tk_s is not None and tk_s >= 65:
            notes.append(f"Taker sell {tk_s}% — сильное продавательское давление сейчас")

    # Session context
    if sess in ("LONDON", "NY_AM"):
        notes.append(f"Сессия {sess} — высокая ликвидность")
    elif sess == "ASIA":
        notes.append(f"Сессия {sess} — обычно более тонкие движения")

    return verdict_head, notes


# ── Renderer ──────────────────────────────────────────────────────────

def format_momentum_check(snap: MomentumSnapshot) -> str:
    """Render Russian-language Telegram message."""
    lines = []
    ts_short = snap.generated_at[11:16]  # HH:MM
    lines.append(f"⚡ MOMENTUM CHECK | {ts_short} UTC")
    lines.append("")
    lines.append(f"Сессия: {snap.session} (+{snap.minutes_into_session}min)")
    lines.append(f"Цена: ${snap.last_close:,.1f}")
    lines.append("")

    # Verdict
    lines.append(f"📌 {snap.verdict}")
    lines.append("")

    # 15m / 1h breakdown
    m15 = snap.move_15m
    m1h = snap.move_1h
    if m15.get("character") not in ("no_data", "data_invalid"):
        lines.append(
            f"15m: {m15.get('character', '?')} | "
            f"move {m15.get('move_pct', 0):+.2f}% | "
            f"vol_trend {m15.get('vol_trend_pct', 0):+.0f}%"
        )
    if m1h.get("character") not in ("no_data", "data_invalid"):
        lines.append(
            f"1h:  {m1h.get('character', '?')} | "
            f"move {m1h.get('move_pct', 0):+.2f}% | "
            f"vol_trend {m1h.get('vol_trend_pct', 0):+.0f}%"
        )
    lines.append("")

    # Liquidations
    if snap.liquidations.get("available") and snap.liquidations.get("windows"):
        w = snap.liquidations["windows"]
        lines.append("Liquidations (long/short BTC):")
        for label, key in [("5m", "5m"), ("15m", "15m"), ("60m", "60m")]:
            wd = w.get(key, {})
            if wd.get("n", 0) > 0:
                lines.append(
                    f"  {label}: n={wd.get('n', 0)} "
                    f"long={wd.get('long_btc', 0):.2f} "
                    f"short={wd.get('short_btc', 0):.2f}"
                )
            else:
                lines.append(f"  {label}: тихо")
        last_age = snap.liquidations.get("last_event_age_min")
        if last_age is not None:
            lines.append(f"  последняя liq: {last_age:.0f}min назад")
        lines.append("")

    # Deriv
    if snap.deriv.get("available"):
        funding = snap.deriv.get("funding_8h")
        oi = snap.deriv.get("oi_change_1h_pct")
        prem = snap.deriv.get("premium_pct")
        deriv_parts = []
        if funding is not None:
            deriv_parts.append(f"funding {funding * 100:+.4f}%")
        if oi is not None:
            deriv_parts.append(f"OI 1h {oi:+.2f}%")
        if prem is not None:
            deriv_parts.append(f"premium {prem:+.3f}%")
        if deriv_parts:
            lines.append(f"Deriv: {' | '.join(deriv_parts)}")
            lines.append("")

    # Volume profile zones (C2, 2026-05-07): POC + value area
    if snap.volume_profile and snap.volume_profile.get("poc_price"):
        vp = snap.volume_profile
        position = vp.get("position_vs_va")
        pos_text = {"above": "ВЫШЕ value area", "below": "НИЖЕ value area", "inside": "внутри value area"}.get(position, position)
        lines.append("Volume Profile (24h):")
        lines.append(f"  POC: ${vp['poc_price']:,.0f} (дистанция {vp.get('dist_to_poc_pct', 0):+.2f}%)")
        lines.append(f"  Value area: ${vp['va_low']:,.0f} — ${vp['va_high']:,.0f}")
        lines.append(f"  Цена сейчас: {pos_text}")
        lines.append("")

    # Structural levels (C1, 2026-05-07): PDH/PDL + sessions
    if snap.structural:
        st = snap.structural
        struct_parts = []
        pdh = st.get("dist_to_pdh_pct")
        pdl = st.get("dist_to_pdl_pct")
        if pdh is not None:
            if abs(pdh) < 0.2:
                struct_parts.append(f"⚠️ Близко к PDH ({pdh:+.2f}%) — пробой/откат")
            elif pdh < 0:
                struct_parts.append(f"PDH выше на {abs(pdh):.2f}%")
        if pdl is not None:
            if abs(pdl) < 0.2:
                struct_parts.append(f"⚠️ Близко к PDL ({pdl:+.2f}%) — пробой/откат")
            elif pdl > 0:
                struct_parts.append(f"PDL ниже на {abs(pdl):.2f}%")
        breaks = []
        if st.get("london_high_broken"):
            breaks.append("London high")
        if st.get("london_low_broken"):
            breaks.append("London low")
        if st.get("ny_am_high_broken"):
            breaks.append("NY-AM high")
        if st.get("ny_am_low_broken"):
            breaks.append("NY-AM low")
        if breaks:
            struct_parts.append(f"Пробиты: {', '.join(breaks)}")
        if struct_parts:
            lines.append("Структура (PDH/PDL + сессии):")
            for x in struct_parts:
                lines.append(f"  • {x}")
            lines.append("")

    # Market Long/Short ratio (рыночная дельта позиций)
    if snap.deriv.get("available"):
        gl = snap.deriv.get("global_long_account_pct")
        gs = snap.deriv.get("global_short_account_pct")
        tl = snap.deriv.get("top_trader_long_pct")
        ts = snap.deriv.get("top_trader_short_pct")
        tb = snap.deriv.get("taker_buy_pct")
        tk_s = snap.deriv.get("taker_sell_pct")
        bl = snap.deriv.get("bybit_long_pct")
        bs = snap.deriv.get("bybit_short_pct")
        if gl is not None or tl is not None or tb is not None:
            lines.append("Long/Short рынок (BTC):")
            if gl is not None and gs is not None:
                lines.append(f"  Binance все: {gl}% long / {gs}% short")
            if tl is not None and ts is not None:
                lines.append(f"  Binance топ-трейдеры: {tl}% long / {ts}% short")
            if tb is not None and tk_s is not None:
                lines.append(f"  Taker (5m volume): {tb}% buy / {tk_s}% sell")
            if bl is not None and bs is not None:
                lines.append(f"  Bybit: {bl}% long / {bs}% short")
            lines.append("")

    # Notes
    if snap.notes:
        lines.append("Сигналы:")
        for n in snap.notes:
            lines.append(f"  • {n}")

    lines.append("")
    lines.append("─" * 30)
    lines.append("Это observation. Используй с /advise для общей картины.")

    return "\n".join(lines)
