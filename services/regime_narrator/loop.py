"""Hourly regime narrator service — calls Anthropic Haiku 4.5 for briefing.

Architecture:
  1. Aggregate context deterministically (Python, not LLM):
       - regime A from state/regime_state.json
       - regime B from state/regime_shadow.jsonl (last verdict)
       - deriv_live snapshot (OI, funding, taker, LS-ratio)
       - last 6h price action: BTC close, range, volatility
       - recent setups: top 5 by strength in last 6h
       - DL primary events: count by type in last 6h
  2. Build prompt from template + context dict
  3. Call Claude Haiku 4.5 with prompt caching enabled on system prompt
  4. Send narrative to TG + append to state/regime_narrator_audit.jsonl

Hard guardrails:
  - interval_sec >= 1800 (min 30 min between calls — cost protection)
  - max_tokens=500 (output budget)
  - on API error: log warn, skip this cycle, don't retry within window
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "state" / "regime_narrator_audit.jsonl"
DERIV_LIVE_PATH = ROOT / "state" / "deriv_live.json"
REGIME_A_PATH = ROOT / "state" / "regime_state.json"
REGIME_B_PATH = ROOT / "state" / "regime_shadow.jsonl"
SETUPS_PATH = ROOT / "state" / "setups.jsonl"
DL_LOG_PATH = ROOT / "state" / "decision_log" / "decisions.jsonl"

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 500
DEFAULT_INTERVAL_SEC = 3600   # 1 hour
MIN_INTERVAL_SEC = 1800        # hard floor to prevent cost runaway

SYSTEM_PROMPT = """Ты — quant analyst, читаешь снимок крипторынка и пишешь 4-5 \
предложений narrative для оператора торгового бота на BTC. Стиль: \
разговорный, на русском, без markdown, без emoji кроме одного в начале \
первой строки. Структура:
  1. Что наблюдаешь (regime, прайс, движение за 6h)
  2. Что значит для ботов оператора (LONG inverse + 3 SHORT linear на BTC)
  3. Опасности или возможности в ближайшие 2-4 часа

Никогда не давай trade signals. Никогда не говори "купи/продай". Только \
описание состояния и рисков для существующих позиций. Помни: оператор \
ведёт grid-bots на BitMEX, накапливает SHORT при росте и LONG при \
падении — спайки против direction = main risk."""


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_last_jsonl(path: Path, n: int = 1) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with path.open(encoding="utf-8") as f:
            try:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 50_000))
                if size > 50_000:
                    f.readline()  # discard partial
                lines = f.readlines()
            except OSError:
                lines = []
        for raw in lines[-n:]:
            try:
                out.append(json.loads(raw))
            except (ValueError, TypeError):
                continue
    except OSError:
        pass
    return out


def _recent_setups(window_min: int = 360, top_k: int = 5) -> list[dict]:
    """Top-K recent setups by strength × confidence in the last `window_min`."""
    if not SETUPS_PATH.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)
    out: list[dict] = []
    try:
        with SETUPS_PATH.open(encoding="utf-8") as f:
            try:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 200_000))
                if size > 200_000:
                    f.readline()
                lines = f.readlines()
            except OSError:
                lines = []
        for raw in lines:
            try:
                rec = json.loads(raw)
            except (ValueError, TypeError):
                continue
            ts_str = rec.get("detected_at") or ""
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts < cutoff:
                continue
            out.append(rec)
    except OSError:
        return []
    out.sort(key=lambda r: -(int(r.get("strength", 0) or 0)
                              * float(r.get("confidence_pct", 0) or 0)))
    return out[:top_k]


def _dl_event_counts(window_min: int = 360) -> dict[str, int]:
    """Count PRIMARY DL events by rule_id in last `window_min`."""
    if not DL_LOG_PATH.exists():
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)
    counts: dict[str, int] = {}
    try:
        with DL_LOG_PATH.open(encoding="utf-8") as f:
            try:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 200_000))
                if size > 200_000:
                    f.readline()
                lines = f.readlines()
            except OSError:
                lines = []
        for raw in lines:
            try:
                rec = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if rec.get("severity") != "PRIMARY":
                continue
            ts_str = rec.get("ts") or ""
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts < cutoff:
                continue
            rid = str(rec.get("rule_id", "?"))
            counts[rid] = counts.get(rid, 0) + 1
    except OSError:
        pass
    return counts


def _btc_6h_summary() -> dict:
    """Last 6h BTC summary: close now, 6h-ago close, range, vol z-score."""
    try:
        from core.data_loader import load_klines
        df = load_klines(symbol="BTCUSDT", timeframe="1h", limit=30)
        if df is None or len(df) < 7:
            return {}
        last6 = df.iloc[-6:]
        close_now = float(df["close"].iloc[-1])
        close_6h = float(df["close"].iloc[-7]) if len(df) >= 7 else close_now
        change_pct = (close_now - close_6h) / close_6h * 100 if close_6h else 0
        hi6 = float(last6["high"].max())
        lo6 = float(last6["low"].min())
        vol_recent = float(last6["volume"].sum())
        vol_avg6h_30 = float(df.iloc[-30:]["volume"].sum()) / 5 if len(df) >= 30 else vol_recent
        vol_ratio = vol_recent / max(vol_avg6h_30, 1.0)
        return {
            "close_now": close_now,
            "close_6h_ago": close_6h,
            "change_6h_pct": round(change_pct, 2),
            "high_6h": hi6,
            "low_6h": lo6,
            "range_6h_pct": round((hi6 - lo6) / close_now * 100, 2),
            "volume_ratio_6h_vs_30h_avg": round(vol_ratio, 2),
        }
    except Exception:
        logger.exception("regime_narrator.btc_summary_failed")
        return {}


def _build_context() -> dict:
    """Aggregate full market context for the LLM."""
    regime_a = _read_json(REGIME_A_PATH) or {}
    btc_section = regime_a.get("symbols", {}).get("BTCUSDT", {}) if isinstance(regime_a, dict) else {}

    last_b = _read_last_jsonl(REGIME_B_PATH, n=1)
    regime_b_verdict = last_b[0].get("verdict_b") if last_b else None

    deriv = _read_json(DERIV_LIVE_PATH) or {}
    btc_deriv = deriv.get("BTCUSDT", {}) if isinstance(deriv, dict) else {}

    setups = _recent_setups()
    dl_counts = _dl_event_counts()
    btc_summary = _btc_6h_summary()

    return {
        "now_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regime_a": btc_section.get("current_primary"),
        "regime_a_age_bars": btc_section.get("regime_age_bars"),
        "regime_a_modifiers": list((btc_section.get("active_modifiers") or {}).keys()),
        "regime_b": regime_b_verdict,
        "btc_summary_6h": btc_summary,
        "deriv_live": {
            "oi_change_1h_pct": btc_deriv.get("oi_change_1h_pct"),
            "funding_rate_8h": btc_deriv.get("funding_rate_8h"),
            "taker_buy_pct": btc_deriv.get("taker_buy_pct"),
            "taker_sell_pct": btc_deriv.get("taker_sell_pct"),
            "global_ls_ratio": btc_deriv.get("global_ls_ratio"),
            "top_trader_ls_ratio": btc_deriv.get("top_trader_ls_ratio"),
        },
        "recent_setups_top5": [
            {"type": s.get("setup_type"), "pair": s.get("pair"),
             "strength": s.get("strength"), "confidence_pct": s.get("confidence_pct")}
            for s in setups
        ],
        "dl_primary_events_6h": dl_counts,
    }


def _build_prompt(ctx: dict) -> str:
    return (
        "Снимок рынка BTC на " + ctx["now_utc"] + ":\n\n"
        + json.dumps(ctx, ensure_ascii=False, indent=2)
        + "\n\nНапиши briefing по правилам system prompt."
    )


def _call_haiku(system: str, user: str) -> str | None:
    """Call Anthropic Haiku 4.5 with prompt caching on system prompt."""
    try:
        import anthropic
    except ImportError:
        logger.error("regime_narrator.anthropic_not_installed")
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("regime_narrator.api_key_missing — set ANTHROPIC_API_KEY in .env")
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        # Prompt caching: mark system prompt as cacheable (24h TTL).
        # Saves ~40% input cost since system prompt is identical every call.
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": user}],
        )
        if resp.content and len(resp.content) > 0:
            return resp.content[0].text
        return None
    except Exception as e:
        logger.error("regime_narrator.api_error: %s", e)
        return None


def _audit_append(rec: dict) -> None:
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except OSError:
        logger.exception("regime_narrator.audit_failed")


async def regime_narrator_loop(stop_event: asyncio.Event, *, send_fn=None,
                                interval_sec: int = DEFAULT_INTERVAL_SEC) -> None:
    """Hourly loop. Aggregates context → calls Haiku → sends to TG.

    Disabled if REGIME_NARRATOR_ENABLED env var is set to '0' / 'false' / 'no'.
    """
    if interval_sec < MIN_INTERVAL_SEC:
        logger.warning("regime_narrator.interval_too_small=%ds, clamping to %ds",
                       interval_sec, MIN_INTERVAL_SEC)
        interval_sec = MIN_INTERVAL_SEC

    enabled_str = os.getenv("REGIME_NARRATOR_ENABLED", "1").lower()
    if enabled_str in ("0", "false", "no", "off"):
        logger.info("regime_narrator.disabled via REGIME_NARRATOR_ENABLED env")
        # Sleep forever (until stop_event)
        await stop_event.wait()
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # 2026-05-10: throttle this warning to once per day max via sentinel file.
        # Was logging at WARN every app_runner restart (30+ times/day).
        sentinel = ROOT / "state" / ".regime_narrator_warned.txt"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        from datetime import date
        today = date.today().isoformat()
        last = sentinel.read_text(encoding="utf-8").strip() if sentinel.exists() else ""
        if last != today:
            logger.warning(
                "regime_narrator.no_api_key — set ANTHROPIC_API_KEY in .env to enable. "
                "Service will idle until restart."
            )
            try:
                sentinel.write_text(today, encoding="utf-8")
            except OSError:
                pass
        else:
            logger.info("regime_narrator.no_api_key (already warned today, idling silently)")
        await stop_event.wait()
        return

    if send_fn is None:
        logger.warning("regime_narrator.no_send_fn — narratives will only be audit-logged")

    logger.info("regime_narrator.start interval=%ds model=%s", interval_sec, MODEL)

    while not stop_event.is_set():
        try:
            ctx = _build_context()
            user_prompt = _build_prompt(ctx)
            narrative = _call_haiku(SYSTEM_PROMPT, user_prompt)
            if narrative:
                logger.info("regime_narrator.fire len=%d", len(narrative))
                if send_fn is not None:
                    try:
                        send_fn(narrative)
                    except Exception:
                        logger.exception("regime_narrator.send_failed")
                _audit_append({
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "narrative": narrative,
                    "context": ctx,
                })
            else:
                logger.info("regime_narrator.skip_no_narrative")
        except Exception:
            logger.exception("regime_narrator.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
