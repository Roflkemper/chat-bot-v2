from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.data_loader import load_klines
from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot
from services.analysis_service import AnalysisRequestContext
from services.health_service import build_health_snapshot, build_health_status_text
from services.debug_compare_service import build_comparison_summary_text, build_debug_comparison_pack
from services.debug_replay_service import build_replay_manifest, build_replay_readme, build_replay_tool_source
from utils.observability import RequestTrace

EXPORT_DIR = Path("exports")
LOG_DIR = Path("logs")
DATA_DIR = Path("data")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            return str(value)
    return str(value)


def _tail_text(path: Path, max_chars: int = 8000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[-max_chars:]


def create_runtime_debug_export(
    *,
    trace: RequestTrace | None,
    ctx: AnalysisRequestContext,
    command: str,
    timeframe: str,
    journal_snapshot: JournalSnapshot | None = None,
    position_snapshot: PositionSnapshot | None = None,
    case_mode: bool = False,
) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"btc_case_{stamp}" if case_mode else f"btc_debug_export_{stamp}"
    package_dir = EXPORT_DIR / base_name
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    analyses: dict[str, Any] = {}
    for tf in ["5m", "15m", "1h", "4h", "1d"]:
        try:
            df = load_klines(symbol="BTCUSDT", timeframe=tf, limit=220)
            df.to_csv(package_dir / f"BTCUSDT_{tf}.csv", index=False)
        except Exception as exc:
            analyses[tf] = {"error": f"csv export failed: {type(exc).__name__}: {exc}", "timeframe": tf}
            continue
        try:
            analyses[tf] = _json_safe(ctx.get_snapshot(tf))
        except Exception as exc:
            analyses[tf] = {"error": f"analysis snapshot failed: {type(exc).__name__}: {exc}", "timeframe": tf}

    comparison_pack = build_debug_comparison_pack(analyses)
    replay_manifest = build_replay_manifest(analyses=analyses, command=command, timeframe=timeframe)

    metadata = {
        "created_at_utc": _utc_now_iso(),
        "command": command,
        "timeframe": timeframe,
        "request": trace.as_metadata() if trace else None,
        "request_summary": ctx.summary_lines(),
    }
    (package_dir / "request_context.json").write_text(json.dumps(_json_safe(metadata), ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "analysis_snapshots.json").write_text(json.dumps(_json_safe(analyses), ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "comparison_pack.json").write_text(json.dumps(_json_safe(comparison_pack), ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "trader_expectation_template.json").write_text(
        json.dumps({tf: entry.get("trader_expectation_template") for tf, entry in (comparison_pack.get("timeframes") or {}).items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (package_dir / "comparison_summary.txt").write_text(build_comparison_summary_text(comparison_pack), encoding="utf-8")
    (package_dir / "replay_manifest.json").write_text(json.dumps(_json_safe(replay_manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "README_REPLAY.txt").write_text(build_replay_readme(), encoding="utf-8")
    (package_dir / "replay_case.py").write_text(build_replay_tool_source(), encoding="utf-8")
    (package_dir / "health_snapshot.txt").write_text(build_health_status_text(), encoding="utf-8")
    (package_dir / "health_snapshot.json").write_text(json.dumps(_json_safe(build_health_snapshot()), ensure_ascii=False, indent=2), encoding="utf-8")

    if journal_snapshot is not None:
        (package_dir / "journal_snapshot.json").write_text(json.dumps(_json_safe(journal_snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
    if position_snapshot is not None:
        (package_dir / "position_snapshot.json").write_text(json.dumps(_json_safe(position_snapshot), ensure_ascii=False, indent=2), encoding="utf-8")

    app_log = LOG_DIR / "app.log"
    err_log = LOG_DIR / "errors.log"
    (package_dir / "app_log_tail.txt").write_text(_tail_text(app_log), encoding="utf-8")
    (package_dir / "errors_log_tail.txt").write_text(_tail_text(err_log), encoding="utf-8")

    readme = [
        "RUNTIME DEBUG EXPORT 2.0",
        "",
        "Что внутри:",
        "- BTCUSDT_5m/15m/1h/4h/1d.csv — последние свечи Binance",
        "- analysis_snapshots.json — snapshots по таймфреймам",
        "- request_context.json — request_id, timings, command metadata",
        "- comparison_pack.json — что бот увидел по каждому TF и где внутренний конфликт",
        "- comparison_summary.txt — быстрый текстовый разбор конфликтов",
        "- replay_manifest.json — baseline snapshot для локального replay по выбранному TF",
        "- replay_case.py — локальный replay tool, который читает CSV вместо live Binance",
        "- README_REPLAY.txt — как воспроизвести кейс локально",
        "- trader_expectation_template.json — шаблон, куда можно вписать ожидание трейдера",
        "- health_snapshot.txt — SYSTEM STATUS на момент экспорта",
        "- health_snapshot.json — machine-readable snapshot для диагностики",
        "- journal_snapshot.json / position_snapshot.json — текущее состояние",
        "- app_log_tail.txt / errors_log_tail.txt — хвост последних логов",
    ]
    (package_dir / "README_DEBUG.txt").write_text("\n".join(readme), encoding="utf-8")

    zip_path = EXPORT_DIR / f"{base_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in package_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=f"{base_name}/{file_path.relative_to(package_dir)}")
    return zip_path
