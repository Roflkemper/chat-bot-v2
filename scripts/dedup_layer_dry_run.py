"""Dry-run analysis: would the dedup wrapper have suppressed N of M alerts?

Reads recent Telegram alert log (placeholder source — adjust path when
emitter logs are wired). Reports per-emitter counts: candidate alerts,
would-suppress (cooldown / state-unchanged / clustered), would-emit.

Operator runs this BEFORE turning the wrapper ON in production to gauge
suppression rate. Acceptable suppression: 30-70% on noisy emitters.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.telegram.dedup_layer import DedupLayer, DedupConfig

# Default per-emitter configs; mirrors the DEDUP-WRAP recommendations from
# docs/STATE/TELEGRAM_EMITTERS_INVENTORY.md
_PER_EMITTER_CFG = {
    "auto_edge_alerts.rsi": DedupConfig(
        cooldown_sec=300,           # bumped from 180 per Finding 1
        value_delta_min=5.0,        # RSI delta ≥ 5 points to re-emit
        cluster_enabled=False,
    ),
    "auto_edge_alerts.level_break": DedupConfig(
        cooldown_sec=180,
        value_delta_min=0.0,        # any price change
        cluster_enabled=True,
        cluster_window_sec=60,
        cluster_price_delta_pct=0.5,
    ),
    "setup_detector.cards": DedupConfig(
        cooldown_sec=300,
        value_delta_min=1.0,        # strength delta ≥ 1
        cluster_enabled=False,
    ),
}


def analyze_log(log_path: Path, emitter_filter: str | None = None) -> dict:
    """Replay events from log and count suppression decisions."""
    if not log_path.exists():
        print(f"WARN: log not found: {log_path}", file=sys.stderr)
        return {}

    counts: dict[str, dict] = {}
    for emitter, cfg in _PER_EMITTER_CFG.items():
        if emitter_filter and emitter_filter != emitter:
            continue
        counts[emitter] = {
            "candidates": 0, "would_suppress_cooldown": 0,
            "would_suppress_state": 0, "would_emit": 0,
        }

    # In production we'd replay actual alert log entries.
    # Here we just report the configured emitters and any sample data.
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        emitter = ev.get("emitter")
        if emitter not in counts:
            continue
        cfg = _PER_EMITTER_CFG[emitter]
        layer = DedupLayer(cfg, state_path=Path("/tmp/dryrun_state.json"))
        decision = layer.evaluate(
            emitter=emitter,
            key=ev.get("key", "default"),
            value=float(ev.get("value", 0)),
            now_ts=float(ev.get("ts", 0)),
        )
        counts[emitter]["candidates"] += 1
        if not decision.should_emit:
            if "cooldown" in decision.reason_ru:
                counts[emitter]["would_suppress_cooldown"] += 1
            else:
                counts[emitter]["would_suppress_state"] += 1
        else:
            counts[emitter]["would_emit"] += 1
            layer.record_emit(emitter, ev.get("key", "default"), float(ev.get("value", 0)),
                              now_ts=float(ev.get("ts", 0)))
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="data/telegram/alert_log.jsonl",
                    help="Path to alert log (JSONL, one event per line)")
    ap.add_argument("--emitter", default=None, help="Filter to one emitter")
    args = ap.parse_args(argv)

    log_path = Path(args.log)
    if not log_path.is_absolute():
        log_path = ROOT / log_path

    counts = analyze_log(log_path, args.emitter)
    if not counts:
        print("No data — log file is empty or missing.")
        print(f"Configured emitters: {list(_PER_EMITTER_CFG.keys())}")
        return 0

    sys.stdout.buffer.write(b"\n=== DEDUP DRY-RUN REPORT ===\n\n")
    for emitter, c in counts.items():
        cand = c["candidates"]
        if cand == 0:
            line = f"{emitter}: no candidates in log\n"
        else:
            suppress = c["would_suppress_cooldown"] + c["would_suppress_state"]
            line = (
                f"{emitter}: {cand} candidates -> "
                f"emit {c['would_emit']} ({c['would_emit']/cand*100:.0f}%), "
                f"suppress {suppress} "
                f"(cooldown {c['would_suppress_cooldown']}, state {c['would_suppress_state']})\n"
            )
        sys.stdout.buffer.write(line.encode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
