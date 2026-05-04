"""Dry-run the dedup wrapper against state/decision_log/events.jsonl.

Adapts decision-log event types to dedup emitter keys and runs evaluate()
across the full 4-day production log. Reports per-emitter suppression rate
+ top-10 specific suppression examples.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.telegram.dedup_layer import DedupLayer, DedupConfig

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "state" / "decision_log" / "events.jsonl"


# Per-event-type dedup config. Real auto_edge / setup_detector configs differ;
# these are sensible defaults for decision-log event types.
PER_TYPE_CFG: dict[str, DedupConfig] = {
    "PNL_EVENT": DedupConfig(
        cooldown_sec=900,         # 15 min between emits
        value_delta_min=200.0,    # only re-emit if PnL delta moved by ≥$200
        cluster_enabled=False,
    ),
    "BOUNDARY_BREACH": DedupConfig(
        cooldown_sec=600,         # 10 min between emits
        value_delta_min=50.0,     # price delta ≥ $50 to re-emit
        cluster_enabled=False,
    ),
    "POSITION_CHANGE": DedupConfig(
        cooldown_sec=300,
        value_delta_min=0.05,     # BTC position delta ≥ 0.05
        cluster_enabled=False,
    ),
    "PNL_EXTREME": DedupConfig(
        cooldown_sec=1800,        # 30 min — PNL_EXTREME should be rare
        value_delta_min=500.0,
        cluster_enabled=False,
    ),
    "PARAM_CHANGE": DedupConfig(
        cooldown_sec=180,
        value_delta_min=0.0001,   # any change emits (params are discrete)
        cluster_enabled=False,
    ),
    "BOT_STATE_CHANGE": DedupConfig(
        cooldown_sec=60,
        value_delta_min=0.0,      # state changes always emit
        cluster_enabled=False,
    ),
    "REGIME_CHANGE": DedupConfig(
        cooldown_sec=60,
        value_delta_min=0.0,
        cluster_enabled=False,
    ),
}


def _value_for(event: dict) -> float:
    """Pull the primary value to dedup on per event type."""
    et = event.get("event_type", "")
    payload = event.get("payload", {}) or {}
    market = event.get("market_context", {}) or {}
    portfolio = event.get("portfolio_context", {}) or {}

    if et == "PNL_EVENT":
        return float(payload.get("delta_pnl_usd") or 0.0)
    if et == "BOUNDARY_BREACH":
        return float(payload.get("price") or market.get("price_btc") or 0.0)
    if et == "POSITION_CHANGE":
        return abs(float(portfolio.get("shorts_position_btc") or 0.0)) + \
               abs(float(portfolio.get("longs_position_usd") or 0.0)) / 1e5
    if et == "PNL_EXTREME":
        return float(payload.get("pnl_extreme_usd") or payload.get("delta_pnl_usd") or 0.0)
    if et == "PARAM_CHANGE":
        return float(payload.get("change_id") or hash(str(payload)) % 1_000_000)
    if et == "BOT_STATE_CHANGE":
        return float(hash(payload.get("new_state", "")) % 1_000_000)
    if et == "REGIME_CHANGE":
        return float(hash(payload.get("new_regime", "")) % 1_000_000)
    return 0.0


def _key_for(event: dict) -> str:
    """Within-emitter key (split state by bot_id when present)."""
    bot_id = event.get("bot_id")
    return str(bot_id) if bot_id and bot_id != "multiple" else "global"


def main() -> int:
    if not LOG.exists():
        print(f"ERROR: log not found at {LOG}", file=sys.stderr)
        return 1

    counts: dict[str, dict] = {
        et: {
            "candidates": 0,
            "would_emit": 0,
            "would_suppress_cooldown": 0,
            "would_suppress_state": 0,
            "first_emit_passes": 0,
            "suppression_examples": [],
        }
        for et in PER_TYPE_CFG
    }

    events = []
    with LOG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    print(f"Loaded {len(events)} events from {LOG.relative_to(ROOT)}")
    print(f"Window: {events[0]['ts']} to {events[-1]['ts']}")
    print()

    # Per-emitter (event_type) DedupLayer instances using ephemeral state files
    layers: dict[str, DedupLayer] = {}
    for et, cfg in PER_TYPE_CFG.items():
        state_path = Path(f"/tmp/dryrun_{et}.json")  # ephemeral, OK if /tmp doesn't exist on Windows
        if state_path.exists():
            state_path.unlink()
        try:
            layers[et] = DedupLayer(cfg, state_path=state_path)
        except OSError:
            # Windows fallback: use temp under repo
            tmp = ROOT / "data" / "telegram" / f"_dryrun_{et}.json"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            if tmp.exists():
                tmp.unlink()
            layers[et] = DedupLayer(cfg, state_path=tmp)

    for ev in events:
        et = ev.get("event_type", "")
        if et not in PER_TYPE_CFG:
            continue
        try:
            ts = datetime.fromisoformat(ev["ts"].replace("Z", "+00:00"))
            ts_epoch = ts.timestamp()
        except (KeyError, ValueError):
            continue
        value = _value_for(ev)
        key = _key_for(ev)

        decision = layers[et].evaluate(emitter=et, key=key, value=value, now_ts=ts_epoch)
        c = counts[et]
        c["candidates"] += 1
        if decision.should_emit:
            c["would_emit"] += 1
            if "первый" in decision.reason_ru:
                c["first_emit_passes"] += 1
            layers[et].record_emit(emitter=et, key=key, value=value, now_ts=ts_epoch)
        else:
            if "cooldown" in decision.reason_ru:
                c["would_suppress_cooldown"] += 1
            else:
                c["would_suppress_state"] += 1
            if len(c["suppression_examples"]) < 10:
                c["suppression_examples"].append({
                    "ts": ev["ts"],
                    "key": key,
                    "value": value,
                    "summary": ev.get("summary", "")[:120],
                    "reason": decision.reason_ru,
                })

    # Persist + report
    out_path = ROOT / "docs" / "RESEARCH" / "_dedup_dry_run_raw.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw written to {out_path.relative_to(ROOT)}\n")

    print(f"{'Emitter':<20s}  {'Cand':>5s}  {'Emit':>5s}  {'Suppr':>5s}  {'Suppr%':>7s}  Notes")
    print("-" * 80)
    for et, c in counts.items():
        if c["candidates"] == 0:
            print(f"{et:<20s}  {0:>5d}  {0:>5d}  {0:>5d}  {0:>6.1f}%  no events")
            continue
        suppr = c["would_suppress_cooldown"] + c["would_suppress_state"]
        rate = suppr / c["candidates"] * 100
        print(f"{et:<20s}  {c['candidates']:>5d}  {c['would_emit']:>5d}  {suppr:>5d}  "
              f"{rate:>6.1f}%  cd={c['would_suppress_cooldown']} state={c['would_suppress_state']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
