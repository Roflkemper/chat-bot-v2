"""Daily KPI report for bot7 — reads pipeline_metrics + p15_equity + GC audit
and posts a compact funnel + top anomalies to Telegram via done.py.

Schedule: Windows Task Scheduler daily 09:00 local time (06:00 UTC summer /
07:00 UTC winter — close enough). Reports "yesterday" UTC window.

Sections:
  1. Pipeline funnel: candidates → after-strength → after-combo → after-dedup
                       → after-GC → emitted
  2. Top drop reasons (per stage_outcome)
  3. GC audit: boost/penalty/block/pass-through counts + per-detector
  4. P-15 equity Δ (sum realized PnL since yesterday 00:00 UTC)
  5. Anomalies:
       - detectors that fired yesterday but not today (silent regression)
       - drop reasons that doubled vs. 7-day average
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "state" / "pipeline_metrics.jsonl"
GC_AUDIT = ROOT / "state" / "gc_confirmation_audit.jsonl"
P15_EQUITY = ROOT / "state" / "p15_equity.jsonl"

WINDOW_HOURS = 24


def _read_jsonl_in_window(path: Path, window_start: datetime,
                          window_end: datetime) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_raw = rec.get("ts") or rec.get("detected_at")
            if not ts_raw: continue
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if window_start <= ts < window_end:
                out.append(rec)
    return out


def _funnel(metrics: list[dict]) -> dict[str, int]:
    """Reconstruct pipeline funnel from per-event records.

    Each setup goes through stages; we count records per stage_outcome.
    A setup that's emitted has produced multiple records (gc_*, mtf_*,
    finally emitted). To avoid double-counting, count each stage outcome
    independently as drops + emits."""
    counts = Counter(m.get("stage_outcome") for m in metrics)
    return dict(counts)


def _top_drop_reasons(metrics: list[dict], n: int = 5) -> list[tuple[str, int]]:
    drops = Counter()
    for m in metrics:
        reason = m.get("drop_reason")
        outcome = m.get("stage_outcome", "")
        if reason and outcome not in ("gc_aligned", "gc_neutral", "mtf_aligned",
                                       "mtf_neutral", "emitted"):
            drops[f"{outcome}: {reason}"] += 1
    return drops.most_common(n)


def _gc_breakdown(audit: list[dict]) -> tuple[Counter, dict]:
    decisions = Counter()
    by_type = defaultdict(Counter)
    for r in audit:
        d = str(r.get("decision", "")).split("(")[0].strip()
        decisions[d] += 1
        by_type[r.get("setup_type", "?")][d] += 1
    return decisions, dict(by_type)


def _p15_equity_delta(events: list[dict]) -> float:
    """Sum realized_pnl_usd from p15_equity events in window."""
    total = 0.0
    for e in events:
        v = e.get("realized_pnl_usd")
        if v is not None:
            try: total += float(v)
            except (TypeError, ValueError): pass
    return total


def _p15_breakdown_by_leg(events: list[dict]) -> dict[str, dict]:
    """Group P-15 events by (pair, direction) → {open: n, harvest: n,
    close: n, realized_pnl: $}."""
    out: dict[str, dict] = {}
    for e in events:
        key = f"{e.get('pair', '?')}:{e.get('direction', '?')}"
        if key not in out:
            out[key] = {"open": 0, "harvest": 0, "close": 0, "pnl": 0.0}
        stage = (e.get("stage") or "").upper()
        if stage in ("OPEN", "HARVEST", "CLOSE"):
            out[key][stage.lower()] += 1
        v = e.get("realized_pnl_usd")
        if v is not None:
            try: out[key]["pnl"] += float(v)
            except (TypeError, ValueError): pass
    return out


def _p15_current_legs() -> list[dict]:
    """Read state/p15_state.json and return only in_pos legs with DD alerts."""
    state_path = ROOT / "state" / "p15_state.json"
    if not state_path.exists():
        return []
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    now = datetime.now(timezone.utc)
    out = []
    for key, leg in raw.items():
        if not isinstance(leg, dict) or not leg.get("in_pos"):
            continue
        try:
            pair, direction = key.split(":", 1)
        except ValueError:
            continue
        opened_at_raw = leg.get("opened_at_ts", "")
        age_h = None
        try:
            dt = datetime.fromisoformat(opened_at_raw.replace("Z", "+00:00"))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            age_h = (now - dt).total_seconds() / 3600
        except (ValueError, AttributeError):
            pass
        dd = float(leg.get("cum_dd_pct", 0))
        out.append({
            "key": key, "pair": pair, "direction": direction,
            "layers": int(leg.get("layers", 0)),
            "size_usd": float(leg.get("total_size_usd", 0)),
            "dd_pct": dd, "age_h": age_h,
            "alert": dd > 2.0 and (age_h or 0) > 24,
        })
    return out


def _emitted_setups_by_type(metrics: list[dict]) -> Counter:
    return Counter(
        m.get("setup_type", "?") for m in metrics
        if m.get("stage_outcome") == "emitted"
    )


def _compute_alerts(metrics: list[dict], p15_events: list[dict],
                     current_legs: list[dict], now: datetime) -> list[str]:
    """Surface anomalies that need operator attention.

    Returns one line per alert. Empty list if all is healthy.
    """
    out: list[str] = []
    emitted = sum(1 for m in metrics if m.get("stage_outcome") == "emitted")
    failures = sum(1 for m in metrics if m.get("stage_outcome") == "detector_failed")

    # 0 setups emitted in 24h is concerning (we usually see 10+/day even on quiet
    # markets). Could mean: bot down, regime so flat that all filters block,
    # combo_filter misconfigured, or a wedged loop.
    if not metrics:
        out.append("[CRIT] 0 pipeline events in 24h — bot may be down")
    elif emitted == 0:
        out.append("[WARN] 0 setups emitted in 24h — all candidates blocked")
    elif emitted < 3:
        out.append(f"[INFO] only {emitted} setup(s) emitted in 24h — quiet market")

    # Detector exceptions firing repeatedly = bug.
    if failures >= 10:
        # Count by detector name (drop_reason carries it).
        by_det: dict[str, int] = {}
        for m in metrics:
            if m.get("stage_outcome") == "detector_failed":
                key = str(m.get("drop_reason") or "?")
                by_det[key] = by_det.get(key, 0) + 1
        top = sorted(by_det.items(), key=lambda kv: -kv[1])[:3]
        details = ", ".join(f"{k}={v}" for k, v in top)
        out.append(f"[BUG] {failures} detector exceptions in 24h: {details}")

    # P-15 leg in DD>2% AND age>24h = needs attention.
    for leg in current_legs:
        if leg.get("alert"):
            out.append(
                f"[P15] {leg['pair']} {leg['direction']} dd={leg['dd_pct']:.2f}% "
                f"age={leg['age_h']:.1f}h — consider manual close"
            )

    # P-15 realized PnL deeply negative last 24h.
    pnl_24h = _p15_equity_delta(p15_events)
    if pnl_24h < -50:
        out.append(f"[P15] realized PnL 24h: ${pnl_24h:+.2f} — significant loss")

    return out


def main() -> int:
    now = datetime.now(timezone.utc)
    window_end = now
    window_start = now - timedelta(hours=WINDOW_HOURS)

    metrics = _read_jsonl_in_window(METRICS, window_start, window_end)
    audit = _read_jsonl_in_window(GC_AUDIT, window_start, window_end)
    p15_events = _read_jsonl_in_window(P15_EQUITY, window_start, window_end)

    funnel = _funnel(metrics)
    top_drops = _top_drop_reasons(metrics, n=5)
    gc_decisions, gc_by_type = _gc_breakdown(audit)
    p15_delta = _p15_equity_delta(p15_events)
    emitted = _emitted_setups_by_type(metrics)

    lines = []
    lines.append(f"[KPI] Bot7 за {WINDOW_HOURS}ч (до {now:%Y-%m-%d %H:%M UTC})")
    lines.append("")
    lines.append("Pipeline funnel:")
    for stage in ("detector_failed", "below_strength", "combo_blocked",
                  "semantic_dedup_skip", "type_pair_dedup_skip",
                  "gc_blocked", "gc_aligned", "gc_neutral",
                  "gc_misaligned_penalty", "mtf_aligned", "mtf_conflict",
                  "mtf_neutral", "emitted"):
        n = funnel.get(stage, 0)
        if n > 0:
            lines.append(f"  {stage}: {n}")
    if not metrics:
        lines.append("  (no pipeline events)")
    lines.append("")

    if top_drops:
        lines.append("Top drop reasons:")
        for reason, n in top_drops:
            lines.append(f"  {n}x{reason}")
        lines.append("")

    if emitted:
        lines.append("Emitted setups by type:")
        for t, n in emitted.most_common(10):
            lines.append(f"  {n}x{t}")
        lines.append("")

    if gc_decisions:
        lines.append("GC confirmation:")
        for d, n in gc_decisions.most_common():
            lines.append(f"  {d}: {n}")
        if gc_by_type:
            lines.append("  by detector:")
            for t, dec in sorted(gc_by_type.items()):
                summary = ", ".join(f"{k}={v}" for k, v in dec.most_common())
                lines.append(f"    {t}: {summary}")
        lines.append("")

    lines.append(f"P-15 realized PnL: ${p15_delta:+.2f} on {len(p15_events)} events")

    # Per-leg breakdown of P-15 activity in window.
    p15_breakdown = _p15_breakdown_by_leg(p15_events)
    if p15_breakdown:
        lines.append("  by leg (open/harvest/close/PnL):")
        for key in sorted(p15_breakdown):
            b = p15_breakdown[key]
            lines.append(f"    {key:<18} O={b['open']} H={b['harvest']} "
                          f"C={b['close']} PnL=${b['pnl']:+.2f}")

    # Currently open legs + DD alerts.
    current_legs = _p15_current_legs()
    if current_legs:
        lines.append("")
        lines.append(f"P-15 open right now ({len(current_legs)} legs):")
        for leg in current_legs:
            age_str = f"{leg['age_h']:.1f}h" if leg["age_h"] is not None else "n/a"
            alert = " [ALERT DD>2% age>24h]" if leg["alert"] else ""
            lines.append(
                f"  {leg['pair']:<10} {leg['direction']:<5}  "
                f"layers={leg['layers']}  ${leg['size_usd']:.0f}  "
                f"DD={leg['dd_pct']:.2f}%  age={age_str}{alert}"
            )
    lines.append("")

    # Alerts section — surface degraded or anomalous state.
    alerts = _compute_alerts(metrics, p15_events, current_legs, now)
    if alerts:
        lines.append("[ALERTS]")
        for a in alerts:
            lines.append(f"  {a}")
        lines.append("")

    if not metrics and not audit and not p15_events:
        lines.append("[WARN] No data in window — pipeline silent or files missing.")

    msg = "\n".join(lines)
    # Print with utf-8 to avoid cp1251 crashes on cyrillic/×/emoji.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(msg)

    # Send to TG via done.py if available
    done_script = ROOT / "scripts" / "done.py"
    if done_script.exists():
        try:
            import subprocess
            subprocess.run([sys.executable, str(done_script), msg],
                           cwd=str(ROOT), check=False, timeout=30)
        except Exception as exc:  # noqa: BLE001
            print(f"[kpi] TG send failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
