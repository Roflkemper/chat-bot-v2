from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.weight_tuning_workspace_service import (
    build_weight_tuning_workspace,
    render_weight_tuning_workspace_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='Build weight tuning workspace from saved bot cases.')
    parser.add_argument('--cases-dir', required=True, help='Directory with saved case folders.')
    parser.add_argument('--out-dir', help='Optional directory to save workspace files.')
    parser.add_argument('--json', action='store_true', help='Print JSON to stdout.')
    args = parser.parse_args()

    workspace = build_weight_tuning_workspace(args.cases_dir)
    text = render_weight_tuning_workspace_text(workspace)

    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'weight_tuning_workspace.json').write_text(json.dumps(workspace, ensure_ascii=False, indent=2), encoding='utf-8')
        (out_dir / 'weight_tuning_workspace.txt').write_text(text, encoding='utf-8')

    if args.json:
        print(json.dumps(workspace, ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
