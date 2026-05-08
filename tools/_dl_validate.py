"""Decision Layer validation framework — TZ-DL-VALIDATION.

Audits state/decision_log/decisions.jsonl for:
  - Per-rule fire counts (last 7d, last 24h, all-time)
  - PRIMARY / VERBOSE / INFO breakdown
  - Stale-rate per rule (events with stale=true)
  - CAP-DIAG suppression rate
  - Dead rules (declared in RULE_IDS but 0 fires last 7d)
  - Top spammers (any rule >= 50 fires/24h after dedup → likely misconfig)

Usage:
    python tools/_dl_validate.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DECISIONS = Path("state/decision_log/decisions.jsonl")
SPAM_THRESHOLD_24H = 50


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def main() -> int:
    if not DECISIONS.exists():
        print(f"WARN: {DECISIONS} not found.")
        return 1

    from services.decision_layer.decision_layer import RULE_IDS

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    all_events: list[dict] = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            all_events.append(json.loads(line))
        except (ValueError, json.JSONDecodeError):
            continue

    print("=" * 80)
    print(f"DECISION LAYER VALIDATION — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)
    print(f"  total events all-time: {len(all_events)}")

    by_rule_all: Counter[str] = Counter()
    by_rule_24h: Counter[str] = Counter()
    by_rule_7d: Counter[str] = Counter()
    sev_breakdown: dict[str, Counter] = {}
    stale_per_rule: Counter[str] = Counter()

    for e in all_events:
        rid = e.get("rule_id", "?")
        sev = e.get("severity", "?")
        ts = _parse_iso(e.get("ts", ""))
        by_rule_all[rid] += 1
        sev_breakdown.setdefault(rid, Counter())[sev] += 1
        if e.get("stale"):
            stale_per_rule[rid] += 1
        if ts is not None:
            if ts >= cutoff_24h:
                by_rule_24h[rid] += 1
            if ts >= cutoff_7d:
                by_rule_7d[rid] += 1

    # ── Per-rule fire counts
    print("\nPER-RULE FIRES (24h / 7d / all-time)")
    print(f"  {'rule':<10} | {'24h':>5} | {'7d':>5} | {'all':>6} | breakdown (severity: count)")
    print("  " + "-" * 70)
    for rid in sorted(set(list(RULE_IDS) + list(by_rule_all.keys()))):
        bd = sev_breakdown.get(rid, Counter())
        bd_str = ", ".join(f"{s}:{c}" for s, c in bd.most_common())
        print(f"  {rid:<10} | {by_rule_24h.get(rid, 0):>5} | "
              f"{by_rule_7d.get(rid, 0):>5} | {by_rule_all.get(rid, 0):>6} | {bd_str}")

    # ── Dead rules with classification (cleanup task #6)
    # Some rules legitimately never fire because their conditions are rare;
    # others are dead because their input pipeline is broken.
    LEGITIMATE_DEAD = {
        "R-4": "candidate_regime field rarely populated by Classifier A — рare event normally",
        "M-1": "margin coef < 0.60 — operator runs at 0.95+ by design, this band never reached",
        "M-2": "margin coef in [0.60, 0.85) — operator skips this band entirely",
        "D-1": "snapshots fresh (live tracker writes every 60s) — normal state",
    }
    BROKEN_PIPELINE = {
        "T-1": "MTF phase_state.json not written — restart bot + check market_forward_analysis loop",
        "T-2": "MTF phase_state.json not written — restart bot + check market_forward_analysis loop",
        "T-3": "MTF phase_state.json not written — restart bot + check market_forward_analysis loop",
    }
    dead = [rid for rid in RULE_IDS if by_rule_7d.get(rid, 0) == 0]
    if dead:
        legit = [r for r in dead if r in LEGITIMATE_DEAD]
        broken = [r for r in dead if r in BROKEN_PIPELINE]
        unknown = [r for r in dead if r not in LEGITIMATE_DEAD and r not in BROKEN_PIPELINE]
        print(f"\nDEAD RULES (0 fires last 7d): {len(dead)} total")
        if legit:
            print(f"  LEGITIMATE (rare conditions, no action needed): {', '.join(legit)}")
            for r in legit:
                print(f"    {r}: {LEGITIMATE_DEAD[r]}")
        if broken:
            print(f"  BROKEN PIPELINE (input not arriving — needs fix): {', '.join(broken)}")
            for r in broken:
                print(f"    {r}: {BROKEN_PIPELINE[r]}")
        if unknown:
            print(f"  UNCLASSIFIED: {', '.join(unknown)}")
            print("    -> review whether config is correct or pipeline broken.")

    # ── Spammers
    spam = [(rid, n) for rid, n in by_rule_24h.items() if n >= SPAM_THRESHOLD_24H]
    if spam:
        print(f"\nSPAM CANDIDATES (>= {SPAM_THRESHOLD_24H} fires/24h after dedup):")
        for rid, n in sorted(spam, key=lambda x: -x[1]):
            print(f"  {rid}: {n} fires — review cooldown / payload signature granularity")
    else:
        print(f"\nNo spam candidates (all rules <{SPAM_THRESHOLD_24H} fires/24h).")

    # ── Stale rate
    if stale_per_rule:
        print("\nSTALE EVENTS (rule fired with inputs_stale=True):")
        for rid, n in stale_per_rule.most_common():
            total = by_rule_all.get(rid, 0)
            pct = round(100 * n / max(1, total), 1)
            print(f"  {rid}: {n}/{total} ({pct}%)")

    # ── Cap-diag rate
    cap_24h = by_rule_24h.get("CAP-DIAG", 0)
    cap_7d = by_rule_7d.get("CAP-DIAG", 0)
    if cap_24h > 0 or cap_7d > 0:
        print(f"\nCAP-DIAG SUPPRESSIONS: 24h={cap_24h}, 7d={cap_7d}")
        if cap_24h > 5:
            print("  WARN: Frequent cap hits — consider raising PRIMARY_HARD_CAP_24H or tightening cooldowns.")

    # ── Health verdict
    print("\nHEALTH VERDICT:")
    if not all_events:
        print("  no data — cannot verdict.")
    elif spam:
        print("  WARN: at least one rule spamming. Review noted above.")
    elif cap_24h > 5:
        print("  WARN: cap is hitting frequently — alert volume too high.")
    else:
        print("  OK: no spam, no cap pressure. DL operating in sane regime.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
