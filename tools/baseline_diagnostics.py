from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
JSON_REPORT_PATH = REPORTS_DIR / "baseline_diagnostics_report.json"
MD_REPORT_PATH = REPORTS_DIR / "baseline_diagnostics_report.md"
BACKTEST_REPORT_PATH = ROOT / "backtests" / "backtest_180d_report.txt"
FROZEN_DATA_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_180d_frozen.json"

TRACKED_STATE_FILES = [
    "state/regime_state.json",
    "state/pattern_memory_BTCUSDT_1h_2024.csv",
    "state/pattern_memory_BTCUSDT_1h_2025.csv",
    "state/pattern_memory_BTCUSDT_1h_2026.csv",
]


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.md5(path.read_bytes()).hexdigest()


def _read_text_preview(path: Path, limit: int = 400) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[:limit]


def snapshot_state() -> dict[str, Any]:
    files: dict[str, Any] = {}
    for rel_path in TRACKED_STATE_FILES:
        path = ROOT / rel_path
        files[rel_path] = {
            "exists": path.exists(),
            "md5": _hash_file(path),
            "size": path.stat().st_size if path.exists() else 0,
            "preview": _read_text_preview(path),
        }
    return {
        "system_time_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }


def parse_backtest_report() -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not BACKTEST_REPORT_PATH.exists():
        return {"error": f"Missing report: {BACKTEST_REPORT_PATH.as_posix()}"}
    for line in BACKTEST_REPORT_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "trades":
            result["trades"] = value
        elif key == "winrate":
            result["winrate"] = value
        elif key == "pnl":
            result["pnl"] = value
        elif key == "max dd":
            result["max_dd"] = value
        elif key == "avg rr":
            result["avg_rr"] = value
        elif key == "data_source":
            result["data_source"] = value
    return result


def diff_states(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    before_files = before.get("files") or {}
    after_files = after.get("files") or {}
    for rel_path in TRACKED_STATE_FILES:
        left = before_files.get(rel_path) or {}
        right = after_files.get(rel_path) or {}
        if left.get("md5") != right.get("md5") or left.get("size") != right.get("size"):
            changed[rel_path] = {
                "before_md5": left.get("md5"),
                "after_md5": right.get("md5"),
                "before_size": left.get("size"),
                "after_size": right.get("size"),
            }
    return changed


def run_backtest_once() -> dict[str, Any]:
    cmd = [
        sys.executable,
        "run_backtest.py",
        "--lookback-days",
        "180",
        "--mode",
        "frozen",
        "--data-file",
        str(FROZEN_DATA_PATH.relative_to(ROOT)),
        "--output-dir",
        "backtests",
    ]
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout_tail": (completed.stdout or "")[-2000:],
        "stderr_tail": (completed.stderr or "")[-2000:],
    }


def build_markdown_report(payload: dict[str, Any]) -> str:
    runs = list(payload.get("runs") or [])
    deterministic = bool(payload.get("deterministic"))
    changed_files = payload.get("changed_files_summary") or {}
    lines = [
        "# Baseline Diagnostics Report",
        "",
        f"Date: {payload.get('generated_at_utc')}",
        "",
        "## Summary",
        f"- Runs executed: {len(runs)}",
        f"- Deterministic: {'YES' if deterministic else 'NO'}",
        f"- Primary cause: {payload.get('primary_cause') or 'Undetermined'}",
        "",
        "## Results per run",
        "| Run | Trades | Winrate | PnL | Max DD |",
        "|-----|--------|---------|-----|--------|",
    ]
    for run in runs:
        result = run.get("backtest_result") or {}
        lines.append(
            f"| {run.get('run')} | {result.get('trades', '?')} | {result.get('winrate', '?')} | {result.get('pnl', '?')} | {result.get('max_dd', '?')} |"
        )
    lines.extend(["", "## State file changes"])
    for rel_path in TRACKED_STATE_FILES:
        state = changed_files.get(rel_path) or {}
        lines.append(f"- {rel_path}: {'CHANGED' if state.get('changed') else 'STABLE'}")
    lines.extend(["", "## Root cause analysis"])
    for item in payload.get("root_causes") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Proposed fix"])
    for item in payload.get("proposed_fix") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


def analyze_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_results = [run.get("backtest_result") or {} for run in runs]
    deterministic = all(result == normalized_results[0] for result in normalized_results[1:]) if normalized_results else True

    changed_summary: dict[str, Any] = {}
    for rel_path in TRACKED_STATE_FILES:
        hashes = []
        for run in runs:
            files = ((run.get("after_state") or {}).get("files") or {})
            hashes.append((files.get(rel_path) or {}).get("md5"))
        changed_summary[rel_path] = {
            "changed": len(set(hashes)) > 1,
            "unique_hashes": len(set(hashes)),
        }

    root_causes: list[str] = []
    proposed_fix: list[str] = []

    if changed_summary["state/regime_state.json"]["changed"]:
        root_causes.append("Persistent regime state changes between runs and can alter hysteresis/modifier evolution.")
        proposed_fix.append("Isolate or freeze `state/regime_state.json` during backtests.")
    if any(changed_summary[path]["changed"] for path in TRACKED_STATE_FILES if "pattern_memory" in path):
        root_causes.append("Pattern memory CSV files mutate between runs and can feed different historical context back into the pipeline.")
        proposed_fix.append("Isolate or freeze pattern memory state during backtests.")
    root_causes.append("`core/pipeline.py` passes `datetime.now(timezone.utc)` into regime classification, which ties classification to wall-clock time.")
    proposed_fix.append("Pass deterministic candle/reference time into `build_full_snapshot()` and down to `classify()`.")

    primary_cause = root_causes[0] if root_causes else "Undetermined"
    return {
        "deterministic": deterministic,
        "changed_files_summary": changed_summary,
        "root_causes": root_causes,
        "proposed_fix": proposed_fix,
        "primary_cause": primary_cause,
    }


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []

    for index in range(3):
        before_state = snapshot_state()
        backtest_info = run_backtest_once()
        after_state = snapshot_state()
        backtest_result = parse_backtest_report()
        runs.append(
            {
                "run": index + 1,
                "before_state": before_state,
                "after_state": after_state,
                "state_diff": diff_states(before_state, after_state),
                "backtest_result": backtest_result,
                "backtest_info": backtest_info,
            }
        )

    analysis = analyze_runs(runs)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        **analysis,
    }
    JSON_REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_REPORT_PATH.write_text(build_markdown_report(payload), encoding="utf-8")
    print(json.dumps({"json_report": JSON_REPORT_PATH.as_posix(), "md_report": MD_REPORT_PATH.as_posix()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
