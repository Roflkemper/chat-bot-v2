from __future__ import annotations

import json
from pathlib import Path

from services.health_service import build_health_snapshot, build_health_status_text


def main() -> int:
    out_dir = Path('exports') / 'system_snapshot'
    out_dir.mkdir(parents=True, exist_ok=True)

    text_path = out_dir / 'health_status.txt'
    json_path = out_dir / 'health_status.json'

    text_path.write_text(build_health_status_text(), encoding='utf-8')
    json_path.write_text(json.dumps(build_health_snapshot(), ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'health text saved: {text_path}')
    print(f'health json saved: {json_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
