from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "да"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return float(default)
    try:
        return float(value)
    except Exception:
        return float(default)


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _load_json_config(path: Path) -> Tuple[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _clean(data.get("BOT_TOKEN")), _clean(data.get("CHAT_ID"))
    except Exception:
        return "", ""


def _load_env_file(path: Path) -> Tuple[str, str]:
    token = ""
    chat_id = ""
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = _clean(value)
            if key == "BOT_TOKEN":
                token = value
            elif key == "CHAT_ID":
                chat_id = value
    except Exception:
        return "", ""
    return token, chat_id


def _find_external_config() -> Tuple[str, str, Optional[Path]]:
    candidates = [
        BASE_DIR / "bot_local_config.json",
        BASE_DIR / ".env",
        BASE_DIR.parent / "bot_local_config.json",
        BASE_DIR.parent / ".env",
        Path.cwd() / "bot_local_config.json",
        Path.cwd() / ".env",
    ]

    seen = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        if not path.exists() or not path.is_file():
            continue
        if path.suffix.lower() == ".json":
            token, chat_id = _load_json_config(path)
        else:
            token, chat_id = _load_env_file(path)
        if token and ":" in token:
            return token, chat_id, path
    return "", "", None


def _load_runtime_credentials() -> Tuple[str, str, str]:
    env_token = _clean(os.getenv("BOT_TOKEN"))
    env_chat = _clean(os.getenv("CHAT_ID"))
    if env_token and ":" in env_token:
        return env_token, env_chat, "environment"

    file_token, file_chat, file_path = _find_external_config()
    if file_token and ":" in file_token:
        return file_token, file_chat, str(file_path)

    fallback_token = _clean(os.getenv("BOT_TOKEN_FALLBACK", ""))
    fallback_chat = _clean(os.getenv("CHAT_ID_FALLBACK", ""))
    if fallback_token and ":" in fallback_token:
        return fallback_token, fallback_chat, "fallback_environment"

    return "", "", ""


BOT_TOKEN, CHAT_ID, CONFIG_SOURCE = _load_runtime_credentials()

ENABLE_TELEGRAM = _env_bool("ENABLE_TELEGRAM", True)
ENABLE_ML = _env_bool("ENABLE_ML", True)
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", "120"))
AUTO_EDGE_ALERTS_ENABLED = _env_bool("AUTO_EDGE_ALERTS_ENABLED", True)
AUTO_EDGE_ALERTS_INTERVAL_SEC = int(os.getenv("AUTO_EDGE_ALERTS_INTERVAL_SEC", "60"))
AUTO_EDGE_ALERTS_COOLDOWN_SEC = int(os.getenv("AUTO_EDGE_ALERTS_COOLDOWN_SEC", "180"))
AUTO_EDGE_ALERTS_TIMEFRAMES = os.getenv("AUTO_EDGE_ALERTS_TIMEFRAMES", "15m,1h")

ML_MODEL_PATH = os.getenv("ML_MODEL_PATH", str(BASE_DIR / "models" / "ml_signal_model.joblib"))

# Базовые фильтры входа
MIN_CONFIDENCE_TO_TRADE = _env_float("MIN_CONFIDENCE_TO_TRADE", 55.0)
MIN_RR = _env_float("MIN_RR", 1.5)
MIN_URGENCY_TO_ACT = _env_float("MIN_URGENCY_TO_ACT", 45.0)

# Пользовательские названия 4 ботов для GINAREA
BOT_LABELS = {
    "ct_long": "CT LONG бот",
    "ct_short": "CT SHORT бот",
    "range_long": "RANGE LONG бот",
    "range_short": "RANGE SHORT бот",
}


# Optional CoinGlass integration
COINGLASS_API_KEY = os.getenv('COINGLASS_API_KEY', '')
COINGLASS_BASE_URL = os.getenv('COINGLASS_BASE_URL', 'https://open-api-v4.coinglass.com')
COINGLASS_TIMEOUT_SEC = float(os.getenv('COINGLASS_TIMEOUT_SEC', '6'))
COINGLASS_CACHE_TTL_SEC = int(os.getenv('COINGLASS_CACHE_TTL_SEC', '90'))

KILLSWITCH_INITIAL_BALANCE_USD = float(os.getenv("KILLSWITCH_INITIAL_BALANCE_USD", "10000"))
KILLSWITCH_DRAWDOWN_THRESHOLD_PCT = float(os.getenv("KILLSWITCH_DRAWDOWN_THRESHOLD_PCT", "15.0"))
KILLSWITCH_FLASH_THRESHOLD_PCT = float(os.getenv("KILLSWITCH_FLASH_THRESHOLD_PCT", "5.0"))
KILLSWITCH_FLASH_WINDOW_SEC = int(os.getenv("KILLSWITCH_FLASH_WINDOW_SEC", "60"))

ORCHESTRATOR_LOOP_INTERVAL_SEC = int(os.getenv("ORCHESTRATOR_LOOP_INTERVAL_SEC", "300"))
ORCHESTRATOR_DAILY_REPORT_TIME = os.getenv("ORCHESTRATOR_DAILY_REPORT_TIME", "09:00")
ORCHESTRATOR_ENABLE_AUTO_ALERTS = _env_bool("ORCHESTRATOR_ENABLE_AUTO_ALERTS", True)
