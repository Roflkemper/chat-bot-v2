"""Weekly leaderboard refresh — Stage D2 cron wrapper.

Runs `tools/_walkfwd_historical_setups.py` to regenerate the strategy
leaderboard, then sends a TG summary so the operator sees changes
without opening the file.

Schedule via Windows Task Scheduler (or cron on Linux):
  - Frequency: weekly (e.g. Sunday 22:00 UTC)
  - Command: python C:\\bot7\\scripts\\leaderboard_weekly.py

Output:
  - docs/STRATEGY_LEADERBOARD.md (refreshed)
  - TG message to allowed chat with verdict counts + diff vs previous run
  - state/leaderboard_history.jsonl (one line per run for trend tracking)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LEADERBOARD = ROOT / "docs" / "STRATEGY_LEADERBOARD.md"
HISTORY = ROOT / "state" / "leaderboard_history.jsonl"
WALKFWD_SCRIPT = ROOT / "tools" / "_walkfwd_historical_setups.py"


def _parse_summary(md_text: str) -> dict[str, str]:
    """Extract {detector → verdict} from the Summary table."""
    out: dict[str, str] = {}
    in_summary = False
    for line in md_text.splitlines():
        if line.startswith("## Summary"):
            in_summary = True
            continue
        if in_summary and line.startswith("## "):
            break
        # Table rows look like `| \`detector\` | ... | **VERDICT** |`
        m = re.match(r"\|\s*`([^`]+)`\s*\|.*\|\s*\*\*([A-Z_]+)\*\*\s*\|", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _diff_verdicts(prev: dict[str, str], cur: dict[str, str]) -> list[str]:
    changes: list[str] = []
    for det, v in cur.items():
        if det not in prev:
            changes.append(f"➕ NEW {det}: {v}")
        elif prev[det] != v:
            changes.append(f"🔄 {det}: {prev[det]} → {v}")
    for det in prev:
        if det not in cur:
            changes.append(f"➖ DROPPED {det} (was {prev[det]})")
    return changes


def _read_prev_run() -> dict[str, str]:
    if not HISTORY.exists():
        return {}
    try:
        last_line = ""
        for line in HISTORY.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last_line = line
        if not last_line:
            return {}
        rec = json.loads(last_line)
        return rec.get("verdicts", {})
    except (OSError, ValueError):
        return {}


def _append_history(verdicts: dict[str, str]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdicts": verdicts,
        "stable_count": sum(1 for v in verdicts.values() if v == "STABLE"),
        "marginal_count": sum(1 for v in verdicts.values() if v == "MARGINAL"),
        "overfit_count": sum(1 for v in verdicts.values() if v == "OVERFIT"),
    }
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _send_tg(text: str) -> None:
    """Best-effort TG send. Same approach as supervisor's _send_telegram_alarm."""
    try:
        import requests
        from config import BOT_TOKEN, CHAT_ID
        token = BOT_TOKEN
        chat_ids = [p.strip() for p in str(CHAT_ID or "").replace(";", ",").split(",") if p.strip()]
        for cid in chat_ids:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": cid, "text": text}, timeout=10,
                )
            except Exception:
                pass
    except Exception:
        pass


def main() -> int:
    prev = _read_prev_run()

    print(f"[leaderboard_weekly] running walk-forward...")
    rc = subprocess.run([sys.executable, str(WALKFWD_SCRIPT)], cwd=ROOT).returncode
    if rc != 0:
        print(f"[leaderboard_weekly] walkfwd failed rc={rc}")
        return rc

    if not LEADERBOARD.exists():
        print(f"[leaderboard_weekly] {LEADERBOARD} missing after walkfwd")
        return 1

    md = LEADERBOARD.read_text(encoding="utf-8")
    cur = _parse_summary(md)
    if not cur:
        print(f"[leaderboard_weekly] failed to parse summary; aborting TG")
        return 1

    changes = _diff_verdicts(prev, cur)
    _append_history(cur)

    stable = sum(1 for v in cur.values() if v == "STABLE")
    marginal = sum(1 for v in cur.values() if v == "MARGINAL")
    overfit = sum(1 for v in cur.values() if v == "OVERFIT")

    lines = [f"📊 Strategy leaderboard — weekly refresh"]
    lines.append("")
    lines.append(f"STABLE: {stable}  MARGINAL: {marginal}  OVERFIT: {overfit}  "
                 f"({len(cur)} detectors)")
    lines.append("")
    if changes:
        lines.append("Changes since last run:")
        for ch in changes:
            lines.append(f"  {ch}")
    else:
        lines.append("No verdict changes since last run.")
    lines.append("")
    lines.append("Full table: docs/STRATEGY_LEADERBOARD.md")

    text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        # Windows cp1251 console can't render emoji — TG handles utf-8 fine,
        # so just send and skip stdout.
        print(text.encode("ascii", "replace").decode("ascii"))
    _send_tg(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
