from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.data_loader import get_klines_cache_info
from core.exchange_liquidity_engine import get_exchange_liquidity_context
from models.snapshots import JournalSnapshot, PositionSnapshot
from storage.position_store import load_position_state
from storage.trade_journal import load_trade_journal

LOG_DIR = Path('logs')
DATA_DIR = Path('data')
STATE_DIR = Path('state')
MODELS_DIR = Path('models')
EXPORTS_DIR = Path('exports')


def _fmt_bool(flag: bool) -> str:
    return 'OK' if flag else 'FAIL'


def _safe_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return 0


def _safe_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return '-'


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open('r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def build_health_snapshot() -> dict[str, Any]:
    issues: list[str] = []
    cache_info = get_klines_cache_info()

    try:
        journal = JournalSnapshot.from_dict(load_trade_journal())
        journal_ok = True
    except Exception as exc:
        journal_ok = False
        journal = None
        issues.append(f'journal read error: {type(exc).__name__}: {exc}')

    try:
        position = PositionSnapshot.from_dict(load_position_state())
        position_ok = True
    except Exception as exc:
        position_ok = False
        position = None
        issues.append(f'position read error: {type(exc).__name__}: {exc}')

    app_log = LOG_DIR / 'app.log'
    err_log = LOG_DIR / 'errors.log'
    liq_ctx = get_exchange_liquidity_context(price=0.0)

    model_files = {
        'signal_model.joblib': (MODELS_DIR / 'signal_model.joblib').exists(),
        'ml_signal_model.joblib': (MODELS_DIR / 'ml_signal_model.joblib').exists(),
        'xgb_direction.joblib': (MODELS_DIR / 'xgb_direction.joblib').exists(),
        'xgb_follow_through.joblib': (MODELS_DIR / 'xgb_follow_through.joblib').exists(),
        'xgb_reversal.joblib': (MODELS_DIR / 'xgb_reversal.joblib').exists(),
        'xgb_setup_quality.joblib': (MODELS_DIR / 'xgb_setup_quality.joblib').exists(),
        'xgb_train_report.json': (MODELS_DIR / 'xgb_train_report.json').exists(),
    }

    runtime_files = {
        'logs_dir': LOG_DIR.exists(),
        'data_dir': DATA_DIR.exists(),
        'state_dir': STATE_DIR.exists(),
        'exports_dir': EXPORTS_DIR.exists(),
        'app_log': app_log.exists(),
        'errors_log': err_log.exists(),
    }

    status = {
        'runtime': {
            'logs_dir': runtime_files['logs_dir'],
            'data_dir': runtime_files['data_dir'],
            'state_dir': runtime_files['state_dir'],
            'exports_dir': runtime_files['exports_dir'],
            'app_log_exists': runtime_files['app_log'],
            'errors_log_exists': runtime_files['errors_log'],
            'app_log_size_bytes': _safe_size(app_log),
            'errors_log_size_bytes': _safe_size(err_log),
            'app_log_lines': _count_lines(app_log),
            'errors_log_lines': _count_lines(err_log),
            'app_log_mtime': _safe_mtime(app_log),
            'errors_log_mtime': _safe_mtime(err_log),
        },
        'journal': {
            'ok': journal_ok,
            'has_active_trade': bool(journal.has_active_trade) if journal else False,
            'timeframe': journal.timeframe if journal else None,
            'side': getattr(journal, 'side', None) if journal else None,
        },
        'position': {
            'ok': position_ok,
            'has_position': bool(position.has_position) if position else False,
            'side': position.side if position else None,
            'timeframe': position.timeframe if position else None,
        },
        'market_cache': {
            'ttl_seconds': int(cache_info.get('ttl_seconds') or 0),
            'entries': int(cache_info.get('entries') or 0),
        },
        'liquidity_feed': {
            'feed_health': liq_ctx.get('feed_health') or 'UNKNOWN',
            'feed_stale_seconds': int(liq_ctx.get('feed_stale_seconds') or 0),
            'feed_summary': liq_ctx.get('feed_summary') or '-',
            'events_count': int(liq_ctx.get('events_count') or 0),
            'fallback_active': bool(liq_ctx.get('fallback_active')),
            'data_quality': liq_ctx.get('data_quality') or 'UNKNOWN',
        },
        'models': model_files,
        'issues': issues,
    }
    return status



def build_health_status_text() -> str:
    snap = build_health_snapshot()
    runtime = snap['runtime']
    journal = snap['journal']
    position = snap['position']
    market_cache = snap['market_cache']
    liq = snap['liquidity_feed']
    models = snap['models']
    issues = snap['issues']

    xgb_ready = any(models.get(name) for name in (
        'xgb_direction.joblib',
        'xgb_follow_through.joblib',
        'xgb_reversal.joblib',
        'xgb_setup_quality.joblib',
    ))

    lines = [
        '🩺 СТАТУС СИСТЕМЫ V6.7',
        '',
        'RUNTIME:',
        f"• папка logs: {_fmt_bool(runtime['logs_dir'])}",
        f"• папка data: {_fmt_bool(runtime['data_dir'])}",
        f"• папка state: {_fmt_bool(runtime['state_dir'])}",
        f"• папка exports: {_fmt_bool(runtime['exports_dir'])}",
        f"• app.log: {_fmt_bool(runtime['app_log_exists'])}",
        f"• errors.log: {_fmt_bool(runtime['errors_log_exists'])}",
        f"• размер app.log: {runtime['app_log_size_bytes']} байт",
        f"• размер errors.log: {runtime['errors_log_size_bytes']} байт",
        f"• строк в app.log: {runtime['app_log_lines']}",
        f"• строк в errors.log: {runtime['errors_log_lines']}",
        f"• app.log updated: {runtime['app_log_mtime']}",
        f"• errors.log updated: {runtime['errors_log_mtime']}",
        '',
        'STATE:',
        f"• журнал сделок: {_fmt_bool(journal['ok'])}",
        f"• активная сделка: {'ДА' if journal['has_active_trade'] else 'НЕТ'}",
        f"• таймфрейм журнала: {journal['timeframe'] or '-'}",
        f"• файл позиции: {_fmt_bool(position['ok'])}",
        f"• активная позиция: {'ДА' if position['has_position'] else 'НЕТ'}",
        f"• сторона позиции: {position['side'] or '-'}",
        f"• таймфрейм позиции: {position['timeframe'] or '-'}",
        '',
        'DATA FEED:',
        f"• ttl кэша рынка: {market_cache['ttl_seconds']} сек",
        f"• записей в кэше рынка: {market_cache['entries']}",
        f"• real-liq feed: {liq['feed_health']}",
        f"• real-liq stale: {liq['feed_stale_seconds']} сек",
        f"• real-liq events: {liq['events_count']}",
        f"• fallback active: {'YES' if liq['fallback_active'] else 'NO'}",
        f"• data quality: {liq['data_quality']}",
        f"• real-liq summary: {liq['feed_summary']}",
        '',
        'ML / MODELS:',
        f"• base signal model: {_fmt_bool(models['signal_model.joblib'])}",
        f"• base ml signal model: {_fmt_bool(models['ml_signal_model.joblib'])}",
        f"• XGBoost ready: {'YES' if xgb_ready else 'NO'}",
        f"• xgb direction: {_fmt_bool(models['xgb_direction.joblib'])}",
        f"• xgb follow-through: {_fmt_bool(models['xgb_follow_through.joblib'])}",
        f"• xgb reversal: {_fmt_bool(models['xgb_reversal.joblib'])}",
        f"• xgb setup quality: {_fmt_bool(models['xgb_setup_quality.joblib'])}",
        f"• xgb train report: {_fmt_bool(models['xgb_train_report.json'])}",
        '',
    ]

    if issues:
        lines.append('Последние проблемы:')
        lines.extend(f'• {item}' for item in issues[:5])
    else:
        lines.append('Проблем чтения state/journal не найдено.')

    return '\n'.join(lines)



def save_health_snapshot(path: Path) -> Path:
    snapshot = build_health_snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    return path
