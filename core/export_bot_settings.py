from __future__ import annotations

import json
from pathlib import Path

import config
from run_backtest import _default_frozen_path
from core import backtest_engine


def _mask(value: str, keep_left: int = 4, keep_right: int = 4) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    if len(raw) <= keep_left + keep_right:
        return '*' * len(raw)
    return f'{raw[:keep_left]}***{raw[-keep_right:]}'


def main() -> int:
    reports_dir = Path('reports')
    reports_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = _default_frozen_path('BTCUSDT', '1h', 90)
    payload = {
        'telegram': {
            'enable_telegram': config.ENABLE_TELEGRAM,
            'bot_token_masked': _mask(config.BOT_TOKEN, keep_left=8, keep_right=4),
            'chat_id_masked': _mask(config.CHAT_ID, keep_left=2, keep_right=2),
            'config_source': config.CONFIG_SOURCE,
        },
        'runtime': {
            'enable_ml': config.ENABLE_ML,
            'loop_seconds': config.LOOP_SECONDS,
            'auto_edge_alerts_enabled': config.AUTO_EDGE_ALERTS_ENABLED,
            'auto_edge_alerts_interval_sec': config.AUTO_EDGE_ALERTS_INTERVAL_SEC,
            'auto_edge_alerts_cooldown_sec': config.AUTO_EDGE_ALERTS_COOLDOWN_SEC,
            'auto_edge_alerts_timeframes': config.AUTO_EDGE_ALERTS_TIMEFRAMES,
            'ml_model_path': config.ML_MODEL_PATH,
        },
        'trade_filters': {
            'min_confidence_to_trade': config.MIN_CONFIDENCE_TO_TRADE,
            'min_rr': config.MIN_RR,
            'min_urgency_to_act': config.MIN_URGENCY_TO_ACT,
        },
        'coinglass': {
            'api_key_present': bool(config.COINGLASS_API_KEY),
            'base_url': config.COINGLASS_BASE_URL,
            'timeout_sec': config.COINGLASS_TIMEOUT_SEC,
            'cache_ttl_sec': config.COINGLASS_CACHE_TTL_SEC,
        },
        'backtest_defaults': {
            'timeframe': backtest_engine.DEFAULT_TIMEFRAME,
            'lookback_days': backtest_engine.DEFAULT_LOOKBACK_DAYS,
            'horizon_bars': backtest_engine.DEFAULT_HORIZON_BARS,
            'min_window_bars': backtest_engine.MIN_WINDOW_BARS,
            'max_window_bars': backtest_engine.MAX_WINDOW_BARS,
            'be_buffer_pct': backtest_engine.DEFAULT_BE_BUFFER_PCT,
            'be_trigger_to_tp1': backtest_engine.DEFAULT_BE_TRIGGER_TO_TP1,
            'partial_size': backtest_engine.DEFAULT_PARTIAL_SIZE,
            'tp1_atr_mult': backtest_engine.DEFAULT_TP1_ATR_MULT,
            'tp2_atr_mult': backtest_engine.DEFAULT_TP2_ATR_MULT,
            'stop_atr_mult': backtest_engine.DEFAULT_STOP_ATR_MULT,
            'max_stop_pct': backtest_engine.DEFAULT_MAX_STOP_PCT,
            'min_stop_pct': backtest_engine.DEFAULT_MIN_STOP_PCT,
            'dead_trade_min_bars': backtest_engine.DEFAULT_DEAD_TRADE_MIN_BARS,
            'dead_trade_max_profit_pct': backtest_engine.DEFAULT_DEAD_TRADE_MAX_PROFIT_PCT,
            'dead_trade_compression_ratio': backtest_engine.DEFAULT_DEAD_TRADE_COMPRESSION_RATIO,
            'tp3_tail_size': backtest_engine.DEFAULT_TP3_TAIL_SIZE,
            'frozen_backtest_file': frozen_path.as_posix(),
            'frozen_backtest_file_exists': frozen_path.exists(),
        },
    }

    json_path = reports_dir / 'current_bot_settings.json'
    txt_path = reports_dir / 'current_bot_settings.txt'
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        'CURRENT BOT SETTINGS',
        '====================',
        '',
        '[TELEGRAM]',
        f"ENABLE_TELEGRAM={payload['telegram']['enable_telegram']}",
        f"BOT_TOKEN={payload['telegram']['bot_token_masked']}",
        f"CHAT_ID={payload['telegram']['chat_id_masked']}",
        f"CONFIG_SOURCE={payload['telegram']['config_source']}",
        '',
        '[RUNTIME]',
        f"ENABLE_ML={payload['runtime']['enable_ml']}",
        f"LOOP_SECONDS={payload['runtime']['loop_seconds']}",
        f"AUTO_EDGE_ALERTS_ENABLED={payload['runtime']['auto_edge_alerts_enabled']}",
        f"AUTO_EDGE_ALERTS_INTERVAL_SEC={payload['runtime']['auto_edge_alerts_interval_sec']}",
        f"AUTO_EDGE_ALERTS_COOLDOWN_SEC={payload['runtime']['auto_edge_alerts_cooldown_sec']}",
        f"AUTO_EDGE_ALERTS_TIMEFRAMES={payload['runtime']['auto_edge_alerts_timeframes']}",
        '',
        '[TRADE FILTERS]',
        f"MIN_CONFIDENCE_TO_TRADE={payload['trade_filters']['min_confidence_to_trade']}",
        f"MIN_RR={payload['trade_filters']['min_rr']}",
        f"MIN_URGENCY_TO_ACT={payload['trade_filters']['min_urgency_to_act']}",
        '',
        '[BACKTEST DEFAULTS]',
        f"TIMEFRAME={payload['backtest_defaults']['timeframe']}",
        f"LOOKBACK_DAYS={payload['backtest_defaults']['lookback_days']}",
        f"HORIZON_BARS={payload['backtest_defaults']['horizon_bars']}",
        f"MIN_WINDOW_BARS={payload['backtest_defaults']['min_window_bars']}",
        f"MAX_WINDOW_BARS={payload['backtest_defaults']['max_window_bars']}",
        f"BE_BUFFER_PCT={payload['backtest_defaults']['be_buffer_pct']}",
        f"BE_TRIGGER_TO_TP1={payload['backtest_defaults']['be_trigger_to_tp1']}",
        f"PARTIAL_SIZE={payload['backtest_defaults']['partial_size']}",
        f"TP1_ATR_MULT={payload['backtest_defaults']['tp1_atr_mult']}",
        f"TP2_ATR_MULT={payload['backtest_defaults']['tp2_atr_mult']}",
        f"STOP_ATR_MULT={payload['backtest_defaults']['stop_atr_mult']}",
        f"MAX_STOP_PCT={payload['backtest_defaults']['max_stop_pct']}",
        f"MIN_STOP_PCT={payload['backtest_defaults']['min_stop_pct']}",
        f"DEAD_TRADE_MIN_BARS={payload['backtest_defaults']['dead_trade_min_bars']}",
        f"DEAD_TRADE_MAX_PROFIT_PCT={payload['backtest_defaults']['dead_trade_max_profit_pct']}",
        f"DEAD_TRADE_COMPRESSION_RATIO={payload['backtest_defaults']['dead_trade_compression_ratio']}",
        f"TP3_TAIL_SIZE={payload['backtest_defaults']['tp3_tail_size']}",
        f"FROZEN_BACKTEST_FILE={payload['backtest_defaults']['frozen_backtest_file']}",
        f"FROZEN_BACKTEST_FILE_EXISTS={payload['backtest_defaults']['frozen_backtest_file_exists']}",
    ]
    txt_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'SETTINGS_JSON: {json_path.as_posix()}')
    print(f'SETTINGS_TXT: {txt_path.as_posix()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
