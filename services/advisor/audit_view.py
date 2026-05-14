"""Audit view — health snapshot for /audit Telegram command.

Runs the same checks the operator manually does today: state file freshness,
detector fire/block ratios, paper-trade activity by setup_type, DL event
volume per rule. Designed to surface 'what's silently broken' in <30 seconds.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(".")
APP_LOG = Path("logs/app.log")


def _file_age_min(p: Path) -> Optional[float]:
    if not p.exists():
        return None
    return (datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) / 60.0


def _count_lines(p: Path, since: Optional[datetime] = None) -> int:
    if not p.exists():
        return 0
    n = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            if since:
                try:
                    e = json.loads(line)
                    ts = e.get("ts")
                    if ts:
                        e_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if e_dt < since:
                            continue
                except Exception:
                    continue
            n += 1
    except OSError:
        return 0
    return n


def _detector_log_stats() -> dict[str, dict]:
    """Parse logs/app.log tail for detector fire / combo_block ratios."""
    if not APP_LOG.exists():
        return {}
    try:
        # Read last ~5 MB to catch ~24h of activity
        size = APP_LOG.stat().st_size
        chunk = min(5 * 1024 * 1024, size)
        with APP_LOG.open("rb") as fh:
            fh.seek(-chunk, 2)
            data = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return {}

    stats: dict[str, dict] = {}
    fired_re = re.compile(r"setup_detector\.new_setup type=(\S+)")
    blocked_re = re.compile(r"setup_detector\.combo_blocked type=(\S+)")
    for line in data.splitlines():
        m = fired_re.search(line)
        if m:
            t = m.group(1)
            stats.setdefault(t, {"fired": 0, "blocked": 0})["fired"] += 1
            continue
        m = blocked_re.search(line)
        if m:
            t = m.group(1)
            stats.setdefault(t, {"fired": 0, "blocked": 0})["blocked"] += 1
    return stats


def _dl_recent_summary(hours: int = 24) -> dict:
    p = Path("state/decision_log/decisions.jsonl")
    if not p.exists():
        return {"primary_total": 0, "by_rule": {}}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    primary_count = 0
    by_rule: Counter[str] = Counter()
    try:
        for line in p.read_text(encoding="utf-8").splitlines()[-5000:]:
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
                if e_dt < cutoff:
                    continue
            except Exception:
                continue
            if e.get("severity") == "PRIMARY":
                primary_count += 1
                by_rule[e.get("rule_id", "?")] += 1
    except OSError:
        pass
    return {"primary_total": primary_count, "by_rule": dict(by_rule)}


def build_audit_text() -> str:
    """Compose /audit message — at-a-glance health snapshot."""
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_1h = now - timedelta(hours=1)

    lines: list[str] = []
    lines.append(f"🔍 AUDIT — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # ── State file freshness
    lines.append("📁 STATE FILE FRESHNESS")
    checks = [
        ("setups.jsonl", Path("state/setups.jsonl"), 30),    # threshold min
        ("paper_trades.jsonl", Path("state/paper_trades.jsonl"), 60),
        ("deriv_live.json", Path("state/deriv_live.json"), 10),
        ("regime_state.json", Path("state/regime_state.json"), 30),
        ("regime_v2_state.json", Path("state/regime_v2_state.json"), 30),
        ("decision_log/decisions.jsonl", Path("state/decision_log/decisions.jsonl"), 15),
        ("margin_automated.jsonl", Path("state/margin_automated.jsonl"), 5),
    ]
    for label, p, max_age_min in checks:
        age = _file_age_min(p)
        if age is None:
            lines.append(f"  ❌ {label}: missing")
        elif age > max_age_min:
            lines.append(f"  ⚠️ {label}: {age:.0f}min old (>{max_age_min} threshold)")
        else:
            lines.append(f"  ✅ {label}: {age:.0f}min old")
    lines.append("")

    # ── Detector fire/block ratios
    lines.append("🎯 SETUP DETECTOR (logs sample)")
    det_stats = _detector_log_stats()
    if not det_stats:
        lines.append("  no recent detector events in log sample")
    else:
        sorted_stats = sorted(det_stats.items(), key=lambda kv: -(kv[1]["fired"] + kv[1]["blocked"]))
        for t, s in sorted_stats[:10]:
            total = s["fired"] + s["blocked"]
            block_pct = round(100 * s["blocked"] / max(1, total))
            warn = " ⚠️" if s["blocked"] > 0 and s["fired"] == 0 else ""
            lines.append(f"  {t:<28} fired={s['fired']:>3} blocked={s['blocked']:>3} ({block_pct}%){warn}")
    lines.append("")

    # ── Paper trader activity
    lines.append("📊 PAPER TRADER (24h)")
    paper_p = Path("state/paper_trades.jsonl")
    if paper_p.exists():
        events_24h = []
        try:
            for line in paper_p.read_text(encoding="utf-8").splitlines():
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
                    if e_dt < cutoff_24h:
                        continue
                except Exception:
                    continue
                events_24h.append(e)
        except OSError:
            pass
        opens = [e for e in events_24h if e.get("action") == "OPEN"]
        closes = [e for e in events_24h if e.get("action") in ("TP1", "TP2", "SL", "EXPIRE", "TIME_STOP")]
        wins = [e for e in closes if (e.get("realized_pnl_usd") or 0) > 0]
        net = sum(e.get("realized_pnl_usd") or 0 for e in closes)
        lines.append(f"  Opens: {len(opens)} | Closes: {len(closes)} (W{len(wins)})")
        lines.append(f"  Net PnL: ${net:+,.0f}")
        # By pair
        by_pair = Counter(e.get("pair") or "BTCUSDT" for e in opens)
        if by_pair:
            pairs_str = ", ".join(f"{k}:{v}" for k, v in by_pair.items())
            lines.append(f"  Pairs: {pairs_str}")
    else:
        lines.append("  no journal")
    lines.append("")

    # ── Decision Layer summary
    dl = _dl_recent_summary(hours=24)
    lines.append(f"🚦 DECISION LAYER (24h PRIMARY)")
    if dl["primary_total"] == 0:
        lines.append("  no PRIMARY events")
    else:
        lines.append(f"  Total: {dl['primary_total']}")
        if dl["by_rule"]:
            top = sorted(dl["by_rule"].items(), key=lambda kv: -kv[1])[:6]
            for k, v in top:
                lines.append(f"    {k}: {v}")
    lines.append("")

    # ── Issues summary
    issues: list[str] = []
    setups_age = _file_age_min(Path("state/setups.jsonl"))
    if setups_age is not None and setups_age > 60:
        issues.append(f"setups.jsonl stale ({setups_age:.0f}min) — detectors not writing?")
    if det_stats:
        all_blocked = [t for t, s in det_stats.items() if s["fired"] == 0 and s["blocked"] > 0]
        if all_blocked:
            issues.append(f"100% blocked: {', '.join(all_blocked[:3])}")
    if dl["primary_total"] > 50:
        issues.append(f"DL volume high ({dl['primary_total']}/24h) — review per-rule cooldown")

    if issues:
        lines.append("⚠️ ATTENTION")
        for i in issues:
            lines.append(f"  • {i}")
    else:
        lines.append("✅ No critical issues detected.")

    return "\n".join(lines)
