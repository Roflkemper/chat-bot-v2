from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / 'main.py',
    ROOT / 'config.py',
    ROOT / 'requirements.txt',
    ROOT / 'core' / 'decision_engine.py',
    ROOT / 'core' / 'signal_engine.py',
    ROOT / 'core' / 'trade_manager.py',
    ROOT / 'services' / 'analysis_service.py',
    ROOT / 'renderers' / 'telegram_renderers.py',
]

OPTIONAL_JSON = [
    ROOT / 'state' / 'position_state.json',
    ROOT / 'data' / 'position_state.json',
]

def main() -> int:
    missing = [str(p.relative_to(ROOT)) for p in REQUIRED if not p.exists()]
    broken_json = []
    for path in OPTIONAL_JSON:
        if path.exists():
            try:
                json.loads(path.read_text(encoding='utf-8') or '{}')
            except Exception:
                broken_json.append(str(path.relative_to(ROOT)))
    if missing or broken_json:
        print('HEALTH CHECK FAILED')
        if missing:
            print('Missing files:')
            for item in missing:
                print(f' - {item}')
        if broken_json:
            print('Broken JSON files:')
            for item in broken_json:
                print(f' - {item}')
        return 1
    print('HEALTH CHECK OK')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
