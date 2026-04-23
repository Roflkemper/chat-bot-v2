from __future__ import annotations

import json
from typing import Any

from models.snapshots import AnalysisSnapshot

REPLAY_TOOL_RELATIVE_PATH = "tools/replay_case.py"


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_dict"):
        try:
            return _safe(value.to_dict())
        except Exception:
            return str(value)
    return str(value)


def build_replay_manifest(*, analyses: dict[str, AnalysisSnapshot | dict[str, Any]], command: str, timeframe: str) -> dict[str, Any]:
    normalized: dict[str, AnalysisSnapshot] = {}
    for tf, value in analyses.items():
        normalized[tf] = value if isinstance(value, AnalysisSnapshot) else AnalysisSnapshot.from_dict(value, timeframe=tf)

    available = {}
    for tf, snapshot in normalized.items():
        available[tf] = {
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "price": snapshot.price,
            "signal": snapshot.signal,
            "final_decision": snapshot.final_decision,
            "forecast_direction": snapshot.forecast_direction,
            "forecast_confidence": snapshot.forecast_confidence,
            "reversal_signal": snapshot.reversal_signal,
            "reversal_confidence": snapshot.reversal_confidence,
            "range_state": snapshot.range_state,
        }

    return {
        "replay_version": "4.3",
        "entry_command": command,
        "entry_timeframe": timeframe,
        "available_timeframes": sorted(list(available.keys())),
        "baseline_snapshots": _safe(available),
        "tooling": {
            "project_replay_tool": REPLAY_TOOL_RELATIVE_PATH,
            "recommended_command": f"python {REPLAY_TOOL_RELATIVE_PATH} --case-dir <PATH_TO_CASE_FOLDER> --timeframe {timeframe}",
        },
    }


def build_replay_readme() -> str:
    lines = [
        "CASE REPLAY PACK",
        "",
        "Цель:",
        "- локально воспроизвести решение бота по сохранённому кейсу",
        "- не по live Binance, а по CSV, которые уже лежат внутри debug/case архива",
        "",
        "Как запускать:",
        "1) распакуй case/debug zip",
        "2) положи папку кейса рядом с проектом бота или укажи абсолютный путь",
        f"3) из корня проекта запусти: python {REPLAY_TOOL_RELATIVE_PATH} --case-dir <PATH_TO_CASE_FOLDER> --timeframe 5m",
        "",
        "Что делает replay tool:",
        "- подменяет load_klines на чтение из CSV внутри case folder",
        "- заново прогоняет текущий analysis pipeline проекта",
        "- печатает replay snapshot и сравнивает его с baseline из replay_manifest.json",
        "",
        "Что особенно полезно:",
        "- можно быстро проверить 5m / 15m / 1h на одном и том же сохранённом кейсе",
        "- можно увидеть, изменилось ли решение бота после правок кода",
        "",
        "Примеры:",
        f"- python {REPLAY_TOOL_RELATIVE_PATH} --case-dir exports/btc_case_20260330_123456 --timeframe 5m",
        f"- python {REPLAY_TOOL_RELATIVE_PATH} --case-dir exports/btc_case_20260330_123456 --timeframe 1h --json",
    ]
    return "\n".join(lines)


def build_replay_tool_source() -> str:
    return r'''from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_LIMITS = {
    "5m": 320,
    "15m": 320,
    "1h": 320,
    "4h": 320,
    "1d": 320,
}


def _load_csv(case_dir: Path, timeframe: str) -> pd.DataFrame:
    path = case_dir / f"BTCUSDT_{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(f"CSV not found for timeframe {timeframe}: {path}")
    df = pd.read_csv(path)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["open_time", "close_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    df = df.dropna(subset=[c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]).reset_index(drop=True)
    return df


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_dict"):
        try:
            return _jsonable(value.to_dict())
        except Exception:
            return str(value)
    return str(value)


def _patched_load_klines(case_dir: Path):
    def _loader(symbol: str = "BTCUSDT", timeframe: str = "1h", limit: int = 300, use_cache: bool = True):
        df = _load_csv(case_dir, timeframe)
        return df.tail(limit if limit else DEFAULT_LIMITS.get(timeframe, 320)).reset_index(drop=True).copy()
    return _loader


def _patch_project_loader(case_dir: Path):
    import core.data_loader as data_loader
    import core.signal_engine as signal_engine
    import core.range_detector as range_detector
    import core.ginarea_advisor as ginarea_advisor

    loader = _patched_load_klines(case_dir)
    data_loader.load_klines = loader
    signal_engine.load_klines = loader
    range_detector.load_klines = loader
    ginarea_advisor.load_klines = loader
    try:
        import core.decision_engine as decision_engine
        decision_engine.load_klines = loader
    except Exception:
        pass
    try:
        data_loader.clear_klines_cache()
    except Exception:
        pass
    return loader


def _load_manifest(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "replay_manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_diff(baseline: dict[str, Any], replayed: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "signal",
        "final_decision",
        "forecast_direction",
        "forecast_confidence",
        "reversal_signal",
        "reversal_confidence",
        "range_state",
        "decision",
    ]
    diff = {}
    for key in keys:
        before = baseline.get(key)
        after = replayed.get(key)
        if before != after:
            diff[key] = {"baseline": before, "replayed": after}
    return diff


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay saved bot case using local CSV files")
    parser.add_argument("--case-dir", required=True, help="Path to unpacked btc_case_* or btc_debug_export_* folder")
    parser.add_argument("--timeframe", default="1h", help="5m | 15m | 1h | 4h | 1d")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    case_dir = Path(args.case_dir).expanduser().resolve()
    if not case_dir.exists():
        raise SystemExit(f"case dir not found: {case_dir}")

    _patch_project_loader(case_dir)

    from services.analysis_service import call_btc_analysis

    snapshot = call_btc_analysis(args.timeframe)
    replayed = snapshot.to_dict() if hasattr(snapshot, "to_dict") else _jsonable(snapshot)
    manifest = _load_manifest(case_dir)
    baseline = (((manifest.get("baseline_snapshots") or {}).get(args.timeframe)) or {})
    diff = _build_diff(baseline, replayed)

    payload = {
        "case_dir": str(case_dir),
        "timeframe": args.timeframe,
        "baseline": baseline,
        "replayed": replayed,
        "diff": diff,
    }

    if args.json:
        print(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2))
        return 0

    print("CASE REPLAY")
    print("")
    print(f"case_dir: {case_dir}")
    print(f"timeframe: {args.timeframe}")
    print("")
    print("BASELINE:")
    for key, value in baseline.items():
        print(f"- {key}: {value}")
    print("")
    print("REPLAYED:")
    for key in ["signal", "final_decision", "forecast_direction", "forecast_confidence", "reversal_signal", "reversal_confidence", "range_state"]:
        print(f"- {key}: {replayed.get(key)}")
    print("")
    if diff:
        print("DIFF:")
        for key, value in diff.items():
            print(f"- {key}: baseline={value.get('baseline')} | replayed={value.get('replayed')}")
    else:
        print("DIFF: нет изменений относительно baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
