from __future__ import annotations

import json
from pathlib import Path

from core.backtest_engine import run_backtest


def main() -> int:
    result = run_backtest(symbol='BTCUSDT', timeframe='1h', lookback_days=90, output_dir='backtests')
    for line in result.get('summary_lines') or []:
        print(line)
    summary_path = Path(result.get('report_path') or 'backtests/backtest_90d_report.json')
    print(f"REPORT: {summary_path.as_posix()}")
    txt_path = summary_path.with_suffix('.txt')
    txt_path.write_text('\n'.join(result.get('summary_lines') or []), encoding='utf-8')

    if result.get('if_then_triggered', 0) > 0 and result.get('if_then_executed', 0) == 0:
        return 2
    if result.get('trades', 0) == 0 and result.get('if_then_triggered', 0) > 0:
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
