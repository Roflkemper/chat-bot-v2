from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
EMPTY_POSITION = {
    'has_position': False,
    'side': None,
    'entry_price': None,
    'size': None,
    'opened_at': None,
}

def main() -> int:
    for path in [ROOT / 'state' / 'position_state.json', ROOT / 'data' / 'position_state.json']:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(EMPTY_POSITION, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'reset: {path.relative_to(ROOT)}')
    journal = ROOT / 'state' / 'decision_journal.jsonl'
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text('', encoding='utf-8')
    print(f'reset: {journal.relative_to(ROOT)}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
