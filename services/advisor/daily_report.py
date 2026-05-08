"""Daily and weekly automated reports.

Two scheduled jobs:
  - Daily report at 21:00 UTC: covers last 24h (paper trades P&L by setup type,
    cascades, regime changes, DL PRIMARY events, top opportunities).
    Also persisted to docs/reports/daily/YYYY-MM-DD.md for historical memory.
  - Weekly report on Sundays at 21:00 UTC: covers last 7 days with
    aggregations, surfacing patterns ('SHORTs only worked in trend_down',
    'long_pdl_bounce 100% WR').

Both push to Telegram and write a markdown file. Markdown lives in
docs/reports/{daily,weekly}/ and gets gitignored to avoid bloat (operator
keeps them locally).
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PAPER_TRADES_PATH = Path("state/paper_trades.jsonl")
SETUPS_PATH = Path("state/setups.jsonl")
DECISIONS_PATH = Path("state/decision_log/decisions.jsonl")
LIQ_PATH = Path("market_live/liquidations.csv")

DAILY_DIR = Path("docs/reports/daily")
WEEKLY_DIR = Path("docs/reports/weekly")


def _read_jsonl(p: Path, since: datetime) -> list[dict]:
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


# ─── shared analytics ────────────────────────────────────────────────────

def _paper_summary(events: list[dict]) -> dict:
    """Return summary of paper trades over events: opens/closes, P&L by type."""
    opens = [e for e in events if e.get("action") == "OPEN"]
    closes = [e for e in events if e.get("action") in ("TP1", "TP2", "SL", "EXPIRE", "TIME_STOP")]

    wins = [e for e in closes if (e.get("realized_pnl_usd") or 0) > 0]
    losses = [e for e in closes if (e.get("realized_pnl_usd") or 0) < 0]
    net = sum(e.get("realized_pnl_usd") or 0 for e in closes)
    wr = round(100 * len(wins) / max(1, len(closes)), 1)

    # Per-setup-type breakdown
    by_type: dict[str, dict] = {}
    for e in closes:
        st = e.get("setup_type", "?")
        d = by_type.setdefault(st, {"closes": 0, "wins": 0, "net": 0.0})
        d["closes"] += 1
        if (e.get("realized_pnl_usd") or 0) > 0:
            d["wins"] += 1
        d["net"] += e.get("realized_pnl_usd") or 0

    # Per-pair breakdown
    by_pair: dict[str, int] = Counter()
    for e in opens:
        by_pair[e.get("pair") or "BTCUSDT"] += 1

    operator_confirmed = [e for e in opens if e.get("operator_confirmed") is True]

    # Split confirmed vs auto by trade_id linkage (for weekly comparison).
    confirmed_ids = {e.get("trade_id") for e in operator_confirmed if e.get("trade_id")}
    confirmed_closes = [e for e in closes if e.get("trade_id") in confirmed_ids]
    auto_closes = [e for e in closes if e.get("trade_id") not in confirmed_ids]

    def _agg(evs: list[dict]) -> dict:
        if not evs:
            return {"n": 0, "wins": 0, "wr_pct": 0.0, "net_pnl_usd": 0.0}
        w = sum(1 for e in evs if (e.get("realized_pnl_usd") or 0) > 0)
        n = sum(e.get("realized_pnl_usd") or 0 for e in evs)
        return {
            "n": len(evs),
            "wins": w,
            "wr_pct": round(100 * w / max(1, len(evs)), 1),
            "net_pnl_usd": round(n, 2),
        }

    return {
        "n_opens": len(opens),
        "n_closes": len(closes),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate_pct": wr,
        "net_pnl_usd": round(net, 2),
        "by_setup_type": by_type,
        "by_pair": dict(by_pair),
        "operator_confirmed_count": len(operator_confirmed),
        "auto_open_count": len(opens) - len(operator_confirmed),
        "confirmed_perf": _agg(confirmed_closes),
        "auto_perf": _agg(auto_closes),
    }


def _decision_layer_summary(events: list[dict]) -> dict:
    """Aggregate DL events by rule_id + severity."""
    primary = [e for e in events if e.get("severity") == "PRIMARY"]
    by_rule = Counter(e.get("rule_id", "?") for e in primary)
    return {
        "primary_total": len(primary),
        "by_rule": dict(by_rule),
    }


def _setup_summary(events: list[dict]) -> dict:
    """Aggregate setup_detector outputs by setup_type and pair."""
    by_type = Counter(e.get("setup_type", "?") for e in events)
    by_pair = Counter(e.get("pair") or "BTCUSDT" for e in events)
    high_conf = [e for e in events if (e.get("confidence_pct") or 0) >= 70]
    return {
        "total": len(events),
        "high_conf_70plus": len(high_conf),
        "by_setup_type": dict(by_type),
        "by_pair": dict(by_pair),
    }


def _cascades_count(now_utc: datetime, lookback_hours: int) -> dict:
    """Count cascades >=5 BTC in window. Returns {long_liq_count, short_liq_count}."""
    if not LIQ_PATH.exists():
        return {"long_liq_count": 0, "short_liq_count": 0}
    try:
        import pandas as pd
        df = pd.read_csv(LIQ_PATH)
        if df.empty or "ts_utc" not in df.columns:
            return {"long_liq_count": 0, "short_liq_count": 0}
        df["ts"] = pd.to_datetime(df["ts_utc"], utc=True)
        df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
        cutoff = now_utc - timedelta(hours=lookback_hours)
        df = df[df["ts"] >= cutoff]
        if df.empty:
            return {"long_liq_count": 0, "short_liq_count": 0}

        cascades = {"long_liq_count": 0, "short_liq_count": 0}
        for label, side_filter in (("long_liq_count", "short"), ("short_liq_count", "long")):
            sub = df[df["side"] == side_filter].sort_values("ts").reset_index(drop=True)
            if sub.empty:
                continue
            tss = sub["ts"].values
            qtys = sub["qty"].values
            i = 0
            while i < len(sub):
                window_end = tss[i] + pd.Timedelta(minutes=5).to_timedelta64()
                j = i
                cum = 0.0
                while j < len(sub) and tss[j] <= window_end:
                    cum += qtys[j]
                    j += 1
                if cum >= 5.0:
                    cascades[label] += 1
                    i = j
                else:
                    i += 1
        return cascades
    except Exception:
        logger.exception("daily_report.cascade_count_failed")
        return {"long_liq_count": 0, "short_liq_count": 0}


# ─── builders ────────────────────────────────────────────────────────────

def build_daily_report(now: Optional[datetime] = None) -> str:
    """Build a 24h summary covering paper trades + cascades + DL + setups."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    paper_events = _read_jsonl(PAPER_TRADES_PATH, since)
    setup_events = _read_jsonl(SETUPS_PATH, since)
    dl_events = _read_jsonl(DECISIONS_PATH, since)

    p = _paper_summary(paper_events)
    s = _setup_summary(setup_events)
    d = _decision_layer_summary(dl_events)
    casc = _cascades_count(now, 24)

    lines: list[str] = []
    lines.append(f"📅 DAILY REPORT — {now.strftime('%Y-%m-%d')}")
    lines.append(f"window: last 24h ending {now.strftime('%H:%M UTC')}")
    lines.append("")

    # Paper trades — the bottom line
    lines.append("💰 PAPER TRADES")
    if p["n_closes"] == 0:
        lines.append(f"  {p['n_opens']} opens, no closes yet")
    else:
        lines.append(f"  Opens: {p['n_opens']} | Closes: {p['n_closes']} (W{p['n_wins']}/L{p['n_losses']})")
        lines.append(f"  Win rate: {p['win_rate_pct']}% | Net PnL: ${p['net_pnl_usd']:+,.0f}")
        if p["operator_confirmed_count"] > 0:
            lines.append(f"  Operator-confirmed opens: {p['operator_confirmed_count']}")
    if p["by_setup_type"]:
        lines.append("  By setup type:")
        sorted_types = sorted(p["by_setup_type"].items(), key=lambda kv: kv[1]["net"], reverse=True)
        for stype, st in sorted_types:
            wr_t = round(100 * st["wins"] / max(1, st["closes"]), 0)
            lines.append(f"    {stype:<24} N={st['closes']:>2} WR={wr_t:>3.0f}% net=${st['net']:+,.0f}")
    if p["by_pair"]:
        pairs_str = ", ".join(f"{k}:{v}" for k, v in p["by_pair"].items())
        lines.append(f"  By pair: {pairs_str}")
    lines.append("")

    # Setup detector activity
    lines.append("🎯 SETUP DETECTOR")
    if s["total"] == 0:
        lines.append("  No new setups in 24h.")
    else:
        lines.append(f"  Total: {s['total']} | High-conf (>=70%): {s['high_conf_70plus']}")
        if s["by_setup_type"]:
            top = sorted(s["by_setup_type"].items(), key=lambda kv: -kv[1])[:5]
            lines.append("  Top types: " + ", ".join(f"{k}={v}" for k, v in top))
        if s["by_pair"]:
            pairs_str = ", ".join(f"{k}:{v}" for k, v in s["by_pair"].items())
            lines.append(f"  By pair: {pairs_str}")
    lines.append("")

    # Decision Layer
    lines.append("🚦 DECISION LAYER (24h PRIMARY)")
    if d["primary_total"] == 0:
        lines.append("  No PRIMARY events.")
    else:
        lines.append(f"  Total PRIMARY: {d['primary_total']}")
        if d["by_rule"]:
            rules_str = ", ".join(f"{k}:{v}" for k, v in sorted(d["by_rule"].items()))
            lines.append(f"  By rule: {rules_str}")
    lines.append("")

    # Cascades
    lines.append("🌊 LIQUIDATION CASCADES (>=5 BTC in 5min)")
    lines.append(f"  long-liq cascades (price drops): {casc['long_liq_count']}")
    lines.append(f"  short-liq cascades (price rallies): {casc['short_liq_count']}")
    lines.append("")

    # Verdict
    lines.append("📌 BOTTOM LINE")
    if p["n_closes"] > 0:
        if p["net_pnl_usd"] > 0:
            lines.append(f"  ✅ Profitable day: ${p['net_pnl_usd']:+,.0f} on {p['n_closes']} trades.")
        elif p["net_pnl_usd"] < 0:
            lines.append(f"  ⚠️ Losing day: ${p['net_pnl_usd']:+,.0f} on {p['n_closes']} trades.")
        else:
            lines.append(f"  Flat day: net 0 on {p['n_closes']} trades.")
    else:
        lines.append("  Quiet day — no trades closed.")

    return "\n".join(lines)


def build_weekly_report(now: Optional[datetime] = None) -> str:
    """7-day deep aggregation. Designed for Sunday 21:00 UTC."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=7)

    paper_events = _read_jsonl(PAPER_TRADES_PATH, since)
    setup_events = _read_jsonl(SETUPS_PATH, since)
    dl_events = _read_jsonl(DECISIONS_PATH, since)

    p = _paper_summary(paper_events)
    s = _setup_summary(setup_events)
    d = _decision_layer_summary(dl_events)
    casc = _cascades_count(now, 24 * 7)

    lines: list[str] = []
    lines.append(f"📊 WEEKLY REPORT — week ending {now.strftime('%Y-%m-%d')}")
    lines.append(f"window: last 7 days ending {now.strftime('%H:%M UTC')}")
    lines.append("")

    # Paper trades — main P&L view
    lines.append("💰 PAPER TRADES — week summary")
    if p["n_closes"] == 0:
        lines.append("  No closed trades this week.")
    else:
        lines.append(f"  Opens: {p['n_opens']} | Closes: {p['n_closes']} (W{p['n_wins']}/L{p['n_losses']})")
        lines.append(f"  Week WR: {p['win_rate_pct']}% | Net: ${p['net_pnl_usd']:+,.0f}")
        if p["operator_confirmed_count"] > 0:
            lines.append(f"  Operator-confirmed: {p['operator_confirmed_count']}")
        # Average PnL per trade
        avg_pnl = p["net_pnl_usd"] / max(1, p["n_closes"])
        lines.append(f"  Avg PnL per trade: ${avg_pnl:+,.1f}")

        # Confirmed vs auto comparison — answers "is operator picking better?"
        cp, ap = p.get("confirmed_perf") or {}, p.get("auto_perf") or {}
        if (cp.get("n") or 0) + (ap.get("n") or 0) > 0:
            lines.append("")
            lines.append("⚖️ CONFIRMED vs AUTO (closed trades, week)")
            lines.append("  source       | N  | WR%  |   net$  | avg$/trade")
            lines.append("  -------------|----|------|---------|-----------")
            for label, src in (("operator", cp), ("auto-open", ap)):
                n = src.get("n", 0)
                if n == 0:
                    lines.append(f"  {label:<12} |  0 |   -  |       0 |        -")
                    continue
                avg = src["net_pnl_usd"] / max(1, n)
                lines.append(
                    f"  {label:<12} | {n:>2} | {src['wr_pct']:>4.1f} | "
                    f"{src['net_pnl_usd']:>+7,.0f} | {avg:>+8.1f}"
                )
            # Edge verdict
            if (cp.get("n") or 0) >= 5 and (ap.get("n") or 0) >= 5:
                avg_c = cp["net_pnl_usd"] / cp["n"]
                avg_a = ap["net_pnl_usd"] / ap["n"]
                if avg_c > avg_a + 5:
                    lines.append("  → operator filter adds edge (avg PnL higher).")
                elif avg_a > avg_c + 5:
                    lines.append("  → auto-open performs better; review confirm criteria.")
                else:
                    lines.append("  → no significant edge between sources this week.")

    # Per-type honest leaderboard (sorted by net P&L)
    if p["by_setup_type"]:
        lines.append("")
        lines.append("🏆 SETUP TYPE LEADERBOARD (closed trades, week)")
        lines.append("  setup_type             | N  |  W/L  | WR%  |   net$")
        lines.append("  -----------------------|----|-------|------|-------")
        sorted_types = sorted(p["by_setup_type"].items(), key=lambda kv: kv[1]["net"], reverse=True)
        for stype, st in sorted_types:
            wr_t = round(100 * st["wins"] / max(1, st["closes"]), 0)
            wl = f"{st['wins']}/{st['closes']-st['wins']}"
            lines.append(f"  {stype:<22} | {st['closes']:>2} | {wl:>5} | {wr_t:>4.0f} | {st['net']:>+6,.0f}")
    lines.append("")

    # Setup detector
    lines.append("🎯 SETUP DETECTOR — week activity")
    if s["total"] == 0:
        lines.append("  No setups generated.")
    else:
        lines.append(f"  Total: {s['total']} | High-conf (>=70%): {s['high_conf_70plus']}")
        if s["by_pair"]:
            pairs_str = ", ".join(f"{k}:{v}" for k, v in s["by_pair"].items())
            lines.append(f"  By pair: {pairs_str}")
        # Top 8 types
        if s["by_setup_type"]:
            lines.append("  Top types:")
            top = sorted(s["by_setup_type"].items(), key=lambda kv: -kv[1])[:8]
            for k, v in top:
                lines.append(f"    {k}: {v}")
    lines.append("")

    # Decision Layer summary
    lines.append("🚦 DECISION LAYER — week PRIMARY events")
    if d["primary_total"] == 0:
        lines.append("  No PRIMARY events.")
    else:
        lines.append(f"  Total: {d['primary_total']}")
        if d["by_rule"]:
            for k, v in sorted(d["by_rule"].items()):
                lines.append(f"    {k}: {v}")
    lines.append("")

    # Cascades
    lines.append("🌊 LIQUIDATION CASCADES — week")
    lines.append(f"  long-liq (drops): {casc['long_liq_count']}")
    lines.append(f"  short-liq (rallies): {casc['short_liq_count']}")
    lines.append("")

    # Patterns / lessons (data-driven)
    lines.append("💡 LESSONS")
    if p["by_setup_type"]:
        # Best and worst by net PnL
        sorted_types = sorted(p["by_setup_type"].items(), key=lambda kv: kv[1]["net"], reverse=True)
        if sorted_types:
            best = sorted_types[0]
            lines.append(f"  Best: {best[0]} (net ${best[1]['net']:+,.0f} on {best[1]['closes']} trades)")
        if len(sorted_types) > 1:
            worst = sorted_types[-1]
            if worst[1]["net"] < 0:
                lines.append(f"  Worst: {worst[0]} (net ${worst[1]['net']:+,.0f} on {worst[1]['closes']} trades)")

    return "\n".join(lines)


# ─── persistence ─────────────────────────────────────────────────────────

def save_daily_report(text: str, now: Optional[datetime] = None) -> Path:
    now = now or datetime.now(timezone.utc)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    p = DAILY_DIR / f"{now.strftime('%Y-%m-%d')}.md"
    p.write_text(text, encoding="utf-8")
    return p


def save_weekly_report(text: str, now: Optional[datetime] = None) -> Path:
    now = now or datetime.now(timezone.utc)
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    iso_year, iso_week, _ = now.isocalendar()
    p = WEEKLY_DIR / f"{iso_year}-W{iso_week:02d}.md"
    p.write_text(text, encoding="utf-8")
    return p
