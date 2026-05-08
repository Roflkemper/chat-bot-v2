"""15m setups view — Telegram /setups_15m command for manual trading.

Shows only setups whose setup_type ends with '_15m' (i.e. 15-minute timeframe
detectors), plus paper-trade performance scoped to those setups.

Detectors covered (production as of 2026-05-08):
  - long_div_bos_15m   PF=5.01 hold_4h, WR=74%, walk-forward stable
  - short_div_bos_15m  PF=3.85 hold_1h, WR=72%, walk-forward stable

Both are bullish/bearish multi-indicator divergence + BoS confirmation on
15m bars. Edge proven on 2y BTCUSDT 1h backtest split into 4 folds.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SETUPS_PATH = Path("state/setups.jsonl")
PAPER_TRADES_PATH = Path("state/paper_trades.jsonl")

# Setup types whose timeframe is 15m (suffix-based — extensible).
SETUP_TYPES_15M = ("long_div_bos_15m", "short_div_bos_15m")


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


def _format_setup_line(s: dict) -> str:
    stype = s.get("setup_type", "?")
    side = "LONG" if stype.startswith("long_") else "SHORT" if stype.startswith("short_") else "?"
    entry = s.get("entry_price")
    sl = s.get("stop_price")
    tp1 = s.get("tp1_price")
    tp2 = s.get("tp2_price")
    conf = s.get("confidence_pct", 0)
    rr = s.get("risk_reward")
    ts = s.get("ts", "")
    # Compute "X h ago"
    age_str = ""
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta_h = (now - dt).total_seconds() / 3600.0
            age_str = f" ({delta_h:.1f}h ago)"
        except Exception:
            pass
    entry_s = f"{entry:.0f}" if entry else "?"
    sl_s = f"{sl:.0f}" if sl else "?"
    tp1_s = f"{tp1:.0f}" if tp1 else "?"
    tp2_s = f"{tp2:.0f}" if tp2 else "?"
    return (
        f"  {side} @ {entry_s} | SL {sl_s} | TP1 {tp1_s} | TP2 {tp2_s} | "
        f"conf {conf:.0f}% RR {rr}{age_str}"
    )


def build_setups_15m_text() -> str:
    """Compose /setups_15m message: today's 15m setups + paper performance."""
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    lines: list[str] = []
    lines.append(f"⏱ 15m SETUPS — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("Detectors:")
    lines.append("  🟢 long_div_bos_15m  — bullish divergence + BoS up")
    lines.append("     Backtest PF=5.01 hold_4h, WR=74%, walk-forward stable")
    lines.append("  🔴 short_div_bos_15m — bearish divergence + BoS down")
    lines.append("     Backtest PF=3.85 hold_1h, WR=72%, walk-forward stable")
    lines.append("")

    # ── Active setups in last 24h
    setups = _load_jsonl(SETUPS_PATH, since=cutoff_24h)
    fifteen_m = [s for s in setups if s.get("setup_type") in SETUP_TYPES_15M]
    fifteen_m.sort(key=lambda s: s.get("ts", ""), reverse=True)

    if fifteen_m:
        lines.append(f"🎯 АКТИВНЫЕ 15m СЕТАПЫ за 24h ({len(fifteen_m)}):")
        for s in fifteen_m[:10]:
            lines.append(_format_setup_line(s))
        if len(fifteen_m) > 10:
            lines.append(f"  ... ещё {len(fifteen_m) - 10} (показаны последние 10)")
    else:
        lines.append("🎯 За 24 часа 15m-сетапов не было.")
        lines.append("   Это редкий сигнал — backtest показывает ~1.5 в неделю на сторону.")
        lines.append("   Бот пушнёт автоматически как только сработает.")
    lines.append("")

    # ── Paper trades performance scoped to 15m setups
    paper_events = _load_jsonl(PAPER_TRADES_PATH)
    # Group OPEN events to find which trades came from 15m setups, then look at their closes.
    trade_ids_15m: set[str] = set()
    for e in paper_events:
        if e.get("action") == "OPEN" and e.get("setup_type") in SETUP_TYPES_15M:
            tid = e.get("trade_id")
            if tid:
                trade_ids_15m.add(tid)

    closes_15m = [
        e for e in paper_events
        if e.get("trade_id") in trade_ids_15m
        and e.get("action") in ("TP1", "TP2", "SL", "EXPIRE", "TIME_STOP")
    ]
    opens_15m_active = [
        e for e in paper_events
        if e.get("setup_type") in SETUP_TYPES_15M
        and e.get("action") == "OPEN"
        and e.get("trade_id") not in {c.get("trade_id") for c in closes_15m}
    ]

    if closes_15m or opens_15m_active:
        lines.append("📜 PAPER TRADES — 15m only")
        if opens_15m_active:
            lines.append(f"  🔓 Open: {len(opens_15m_active)}")
        if closes_15m:
            wins = [e for e in closes_15m if (e.get("realized_pnl_usd") or 0) > 0]
            losses = [e for e in closes_15m if (e.get("realized_pnl_usd") or 0) < 0]
            net = sum(e.get("realized_pnl_usd") or 0 for e in closes_15m)
            wr = 100 * len(wins) / max(1, len(closes_15m))
            lines.append(f"  Closed: {len(closes_15m)} (W{len(wins)}/L{len(losses)})")
            lines.append(f"  Win rate: {wr:.1f}% | Net PnL: ${net:+.0f}")
            # Per-side breakdown
            for stype in SETUP_TYPES_15M:
                # Map trade_id back to setup_type via opens
                stype_tids = {e.get("trade_id") for e in paper_events
                              if e.get("action") == "OPEN" and e.get("setup_type") == stype}
                stype_closes = [e for e in closes_15m if e.get("trade_id") in stype_tids]
                if not stype_closes:
                    continue
                stype_wins = [e for e in stype_closes if (e.get("realized_pnl_usd") or 0) > 0]
                stype_net = sum(e.get("realized_pnl_usd") or 0 for e in stype_closes)
                stype_wr = 100 * len(stype_wins) / max(1, len(stype_closes))
                lines.append(
                    f"    {stype}: N={len(stype_closes)} WR={stype_wr:.0f}% net=${stype_net:+.0f}"
                )
    else:
        lines.append("📜 PAPER TRADES — 15m: пока нет данных")
        lines.append("   Paper-trader откроет виртуальную сделку как только detector сработает.")

    return "\n".join(lines)
