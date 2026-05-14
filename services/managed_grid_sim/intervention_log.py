from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ManagedRunResult


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class InterventionLogWriter:
    def write_run(self, result: ManagedRunResult, output_dir: Path) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / f"{result.run_id}_summary.json"
        log_path = output_dir / f"{result.run_id}_interventions.jsonl"
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(result), handle, ensure_ascii=False, indent=2, default=_json_default)
        with log_path.open("w", encoding="utf-8") as handle:
            for event in result.intervention_log:
                handle.write(json.dumps(asdict(event), ensure_ascii=False, default=_json_default) + "\n")
        return summary_path, log_path

    def read_events(self, log_path: Path) -> list[dict[str, Any]]:
        if not log_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
