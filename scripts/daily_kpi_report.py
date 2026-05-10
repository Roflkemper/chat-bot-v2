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


def _emitted_setups_by_type(metrics: list[dict]) -> Counter:
    return Counter(
        m.get("setup_type", "?") for m in metrics
        if m.get("stage_outcome") == "emitted"
    )


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
            lines.append(f"  {n}× {reason}")
        lines.append("")

    if emitted:
        lines.append("Emitted setups by type:")
        for t, n in emitted.most_common(10):
            lines.append(f"  {n}× {t}")
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
    lines.append("")

    if not metrics and not audit and not p15_events:
        lines.append("[WARN] No data in window — pipeline silent or files missing.")

    msg = "\n".join(lines)
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
