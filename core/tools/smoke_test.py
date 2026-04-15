from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one live smoke pass against the bot entrypoint.")
    parser.add_argument("--timeout", type=int, default=5, help="Max seconds to wait for the bot run.")
    parser.add_argument("--symbol", default="BTCUSDT", help="Reserved for future use.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    project_root = Path(__file__).resolve().parent.parent
    entrypoint = project_root / "main.py"
    if not entrypoint.exists():
        print("[ERROR] main.py not found")
        return 1

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(entrypoint)],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(int(args.timeout), 1),
        )
    except subprocess.TimeoutExpired as exc:
        partial_stdout = exc.stdout or ""
        partial_stderr = exc.stderr or ""
        print(f"[ERROR] Smoke test timeout after {args.timeout}s")
        if partial_stdout.strip():
            print("--- partial stdout ---")
            print(partial_stdout.strip())
        if partial_stderr.strip():
            print("--- partial stderr ---")
            print(partial_stderr.strip())
        return 1

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    combined = "\n".join(part for part in (stdout, stderr) if part).strip()

    if completed.returncode != 0:
        print(f"[ERROR] Bot run failed with code {completed.returncode}")
        if combined:
            print(combined)
        return 1

    lowered = combined.lower()
    forbidden_markers = ("traceback", "exception", "error:")
    if any(marker in lowered for marker in forbidden_markers):
        print("[ERROR] Smoke output contains failure markers")
        print(combined)
        return 1

    if "=== TELEGRAM OUTPUT ===" not in stdout:
        print("[ERROR] Smoke output missing TELEGRAM OUTPUT marker")
        if combined:
            print(combined)
        return 1

    telegram_part = stdout.split("=== TELEGRAM OUTPUT ===", 1)[-1].strip()
    if len(telegram_part) < 40:
        print("[ERROR] Telegram output is too short or empty")
        print(stdout)
        return 1

    if not any(ch.isalpha() for ch in telegram_part):
        print("[ERROR] Telegram output does not look like a real report")
        print(stdout)
        return 1

    print("[OK] Smoke test passed")
    print(f"[OK] Output length: {len(telegram_part)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
