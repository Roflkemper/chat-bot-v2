from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.batch_case_analyzer_service import (  # noqa: E402
    build_batch_summary,
    discover_case_dirs,
    render_batch_summary_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='Analyze a batch of saved bot cases')
    parser.add_argument('--cases-dir', default='exports', help='Directory containing unpacked btc_case_* folders')
    parser.add_argument('--out-dir', default=None, help='Optional directory to save batch summary files')
    parser.add_argument('--json', action='store_true', help='Print JSON output')
    args = parser.parse_args()

    cases_dir = Path(args.cases_dir).expanduser().resolve()
    case_dirs = discover_case_dirs(cases_dir)
    summary = build_batch_summary(case_dirs)
    text = render_batch_summary_text(summary)

    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'batch_case_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        (out_dir / 'batch_case_summary.txt').write_text(text, encoding='utf-8')

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
